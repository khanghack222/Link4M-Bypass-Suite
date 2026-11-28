//! l4m-engine: native Link4M bypass service.
//!
//! One binary: HTTP API, Chrome pool, reCAPTCHA audio solving through local
//! whisper.cpp, cache, queue. No Python, no Playwright, no captcha API.

use anyhow::{anyhow, Result};
use l4m_engine::api::{router, ApiState};
use l4m_engine::asr::Asr;
#[cfg(feature = "local-asr")]
use l4m_engine::asr::ensure_model;
use l4m_engine::cdp::Cdp;
use l4m_engine::chrome::ChromeProc;
use l4m_engine::flow::{run_alias, FlowError};
use l4m_engine::pool::Pool;
use l4m_engine::state::{Config, Inner};
use std::sync::Arc;
use std::time::Duration;
use tracing::{info, warn};
use tracing_subscriber::EnvFilter;

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| EnvFilter::new("l4m_engine=info,engine=info")),
        )
        .init();

    let args: Vec<String> = std::env::args().collect();
    let check = args.iter().any(|arg| arg == "--check");
    let once = args
        .iter()
        .position(|arg| arg == "--once")
        .and_then(|index| args.get(index + 1).cloned());

    l4m_engine::asr::silence_backend_logs();
    let cfg = Config::from_env();
    info!(target: "engine", workers = cfg.workers, "starting l4m-engine");

    let mut sweep_roots = vec![cfg.profile_dir.clone()];
    sweep_roots.push(std::env::temp_dir().join("l4m-once"));
    // Prefix match: `l4m-check-<pid>` from a killed --check run still matches.
    sweep_roots.push(std::env::temp_dir().join("l4m-check"));
    l4m_engine::chrome::sweep(&sweep_roots);

    if !std::path::Path::new(&cfg.chrome_bin).exists() {
        return Err(anyhow!(
            "chrome binary not found: {} (set CHROME_BIN)",
            cfg.chrome_bin
        ));
    }

    let model_path = cfg.model_path.clone();
    let model_url = cfg.model_url.clone();
    let threads = cfg.asr_threads;
    let remote = std::env::var("ASR_URL")
        .ok()
        .filter(|value| !value.trim().is_empty());
    let asr = match remote {
        Some(url) => {
            let asr = Asr::remote(&url)?;
            info!(target: "engine", endpoint = %url, "asr ready (remote)");
            asr
        }
        None => load_local_asr(&model_path, &model_url, threads).await?,
    };

    if check {
        report_side_channels().await;
        let binary = cfg.chrome_bin.clone();
        let headless = cfg.headless;
        let chrome = tokio::task::spawn_blocking(move || {
            ChromeProc::launch(
                &binary,
                headless,
                std::env::temp_dir().join(format!("l4m-check-{}", std::process::id())),
                true,
                None,
            )
        })
        .await??;
        let ws = chrome.page_ws()?;
        let cdp = Cdp::connect(&ws).await?;
        cdp.call("Page.enable", serde_json::json!({})).await?;
        info!(target: "engine", asr = asr.label(), "check ok: chrome + cdp + asr");
        return Ok(());
    }

    l4m_engine::instr::prewarm();
    let asr = Arc::new(asr);
    let res = if let Some(target) = once {
        run_once(cfg, asr, &target).await
    } else {
        let inner = Inner::new(cfg.clone(), Some(asr));
        let pool = Arc::new(Pool::spawn(inner.clone()));
        let state = Arc::new(ApiState { inner, pool });
        let listener = tokio::net::TcpListener::bind((cfg.host.as_str(), cfg.port)).await?;
        info!(target: "engine", "listening on http://{}:{}", cfg.host, cfg.port);
        // The timeout must bound the graceful drain only. Wrapping the whole
        // serve future in a 10 s timeout killed every long-running instance ten
        // seconds after boot, so API clients saw an empty reply mid-request.
        let (drain_tx, drain_rx) = tokio::sync::oneshot::channel::<()>();
        let server = axum::serve(listener, router(state)).with_graceful_shutdown(async move {
            shutdown_signal().await;
            let _ = drain_tx.send(());
        });
        let drain_deadline = async {
            let _ = drain_rx.await;
            tokio::time::sleep(Duration::from_secs(10)).await;
        };
        tokio::select! {
            result = server => result?,
            _ = drain_deadline => {
                warn!(target: "engine", "shutdown timed out, dropping open sessions");
            }
        }
        Ok(())
    };
    #[cfg(not(feature = "local-asr"))]
    if let Ok(mut guard) = ASR_CHILD.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
    res
}

#[cfg(feature = "local-asr")]
async fn load_local_asr(
    model_path: &std::path::Path,
    model_url: &str,
    threads: i32,
) -> Result<Asr> {
    let model_path = model_path.to_path_buf();
    let model_url = model_url.to_string();
    let asr = tokio::task::spawn_blocking(move || -> Result<Asr> {
        let path = ensure_model(&model_path, &model_url)?;
        Asr::load(&path, threads)
    })
    .await??;
    info!(target: "engine", "whisper ready ({} threads)", threads);
    Ok(asr)
}

#[cfg(not(feature = "local-asr"))]
static ASR_CHILD: std::sync::Mutex<Option<std::process::Child>> = std::sync::Mutex::new(None);

#[cfg(not(feature = "local-asr"))]
fn find_asr_script() -> Option<std::path::PathBuf> {
    for candidate in ["tools/asr_server.py", "engine-rs/tools/asr_server.py", "../tools/asr_server.py"] {
        let path = std::path::PathBuf::from(candidate);
        if path.exists() {
            return Some(path);
        }
    }
    if let Ok(exe) = std::env::current_exe() {
        let mut dir = exe.parent();
        for _ in 0..4 {
            let Some(current) = dir else { break };
            for rel in ["tools/asr_server.py", "engine-rs/tools/asr_server.py"] {
                let candidate = current.join(rel);
                if candidate.exists() {
                    return Some(candidate);
                }
            }
            dir = current.parent();
        }
    }
    None
}

#[cfg(not(feature = "local-asr"))]
fn find_asr_python() -> std::path::PathBuf {
    let mut candidates = vec![
        l4m_engine::instr::ocr_binary(),
        std::path::PathBuf::from(".venv/bin/python"),
        std::path::PathBuf::from("engine-rs/.venv/bin/python"),
    ];
    #[cfg(windows)]
    {
        candidates.push(std::path::PathBuf::from(".venv\\Scripts\\python.exe"));
        candidates.push(std::path::PathBuf::from("engine-rs\\.venv\\Scripts\\python.exe"));
        if let Ok(local_app_data) = std::env::var("LOCALAPPDATA") {
            for ver in ["Python311", "Python312", "Python313", "Python310"] {
                candidates.push(
                    std::path::PathBuf::from(&local_app_data)
                        .join("Programs")
                        .join("Python")
                        .join(ver)
                        .join("python.exe"),
                );
            }
        }
    }
    candidates.push(std::path::PathBuf::from("python3"));
    candidates.push(std::path::PathBuf::from("python"));
    for path in &candidates {
        let ok = std::process::Command::new(path)
            .args(["-c", "import faster_whisper"])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()
            .map(|s| s.success())
            .unwrap_or(false);
        if ok {
            return path.clone();
        }
    }
    l4m_engine::instr::ocr_binary()
}

#[cfg(not(feature = "local-asr"))]
async fn load_local_asr(
    _model_path: &std::path::Path,
    _model_url: &str,
    _threads: i32,
) -> Result<Asr> {
    let port: u16 = std::env::var("ASR_PORT")
        .ok()
        .and_then(|v| v.trim().parse().ok())
        .filter(|p| *p > 0)
        .unwrap_or(18089);
    let health_url = format!("http://127.0.0.1:{port}/");
    let infer_url = format!("http://127.0.0.1:{port}/inference");

    let already_up = tokio::task::spawn_blocking({
        let health_url = health_url.clone();
        move || {
            std::net::TcpStream::connect_timeout(
                &std::net::SocketAddr::from(([127, 0, 0, 1], port)),
                Duration::from_millis(120),
            )
            .is_ok()
                && health_url.starts_with("http")
        }
    })
    .await
    .unwrap_or(false);

    if !already_up {
        let script = find_asr_script().ok_or_else(|| {
            anyhow!(
                "this build has no local ASR and tools/asr_server.py was not found; set ASR_URL"
            )
        })?;
        let python = find_asr_python();
        let err_log = std::env::temp_dir().join(format!("l4m-asr-{}.log", std::process::id()));
        let err_file = std::fs::File::create(&err_log).ok();
        let mut cmd = std::process::Command::new(&python);
        cmd.arg(&script)
            .env("ASR_PORT", port.to_string())
            .stdout(std::process::Stdio::null());
        if let Some(f) = err_file {
            cmd.stderr(std::process::Stdio::from(f));
        } else {
            cmd.stderr(std::process::Stdio::null());
        }
        let child = cmd
            .spawn()
            .map_err(|e| anyhow!("failed to spawn asr_server.py: {e}"))?;
        if let Ok(mut guard) = ASR_CHILD.lock() {
            *guard = Some(child);
        }
        let deadline = std::time::Instant::now() + Duration::from_secs(45);
        let mut ready = false;
        while std::time::Instant::now() < deadline {
            if let Ok(mut guard) = ASR_CHILD.lock() {
                if let Some(child) = guard.as_mut() {
                    if let Ok(Some(status)) = child.try_wait() {
                        let detail = std::fs::read_to_string(&err_log).unwrap_or_default();
                        let _ = std::fs::remove_file(&err_log);
                        return Err(anyhow!(
                            "asr_server.py exited early ({status}): {}",
                            detail.trim()
                        ));
                    }
                }
            }
            let ok = tokio::task::spawn_blocking(move || {
                std::net::TcpStream::connect_timeout(
                    &std::net::SocketAddr::from(([127, 0, 0, 1], port)),
                    Duration::from_millis(150),
                )
                .is_ok()
            })
            .await
            .unwrap_or(false);
            if ok {
                ready = true;
                break;
            }
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
        let _ = std::fs::remove_file(&err_log);
        if !ready {
            return Err(anyhow!("asr_server.py did not start on {health_url} within 45s"));
        }
        info!(target: "engine", endpoint = %infer_url, "auto-started local faster-whisper ASR");
    } else {
        info!(target: "engine", endpoint = %infer_url, "asr ready (existing local server)");
    }

    Asr::remote(&infer_url)
}

/// `--check` used to leave proxy and OCR misconfiguration for the first job to
/// discover. Probe the configured exit and name the OCR backend up front.
async fn report_side_channels() {
    if let Some(pool) = l4m_engine::proxy::shared() {
        let count = pool.len();
        if let Some(proxy) = pool.next() {
            let exit = format!("{}:{}", proxy.host, proxy.port);
            let probe = proxy.clone();
            let ok = tokio::task::spawn_blocking(move || {
                let agent = l4m_engine::proxy::agent_for(
                    Some(&probe),
                    Duration::from_secs(20),
                    "Mozilla/5.0",
                );
                agent
                    .get("https://www.google.com/generate_204")
                    .call()
                    .map(|response| response.status() == 204)
                    .unwrap_or(false)
            })
            .await
            .unwrap_or(false);
            if ok {
                info!(target: "engine", proxies = count, exit = %exit, "proxy check ok");
            } else {
                warn!(target: "engine", proxies = count, exit = %exit, "proxy check failed");
            }
        } else {
            warn!(target: "engine", proxies = count, "proxy pool is empty");
        }
    } else {
        info!(target: "engine", "proxy: direct connection (no pool)");
    }
    info!(
        target: "engine",
        backend = l4m_engine::instr::ocr_status(),
        "ocr backend"
    );
}

async fn shutdown_signal() {
    #[cfg(unix)]
    {
        let mut terminate =
            tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
                .expect("install SIGTERM handler");
        tokio::select! {
            _ = tokio::signal::ctrl_c() => {}
            _ = terminate.recv() => {}
        }
    }
    #[cfg(not(unix))]
    {
        let _ = tokio::signal::ctrl_c().await;
    }
    info!(target: "engine", "shutdown signal, closing sessions");
}

async fn run_once(cfg: Config, asr: Arc<Asr>, target: &str) -> Result<()> {
    let alias = l4m_engine::flow::extract_alias(target)
        .ok_or_else(|| anyhow!("cannot read link4m alias from {target}"))?;
    let binary = cfg.chrome_bin.clone();
    let headless = cfg.headless;
    // One-shot jobs use the same proxy path as the pool so a pinned exit can
    // be verified without starting the server.
    let proxy = l4m_engine::proxy::shared().and_then(|pool| pool.next());
    let relay = match &proxy {
        Some(upstream) => Some(l4m_engine::proxy::start_relay(upstream.clone()).await?),
        None => None,
    };
    let proxy_port = relay.as_ref().map(|relay| relay.port);
    let once_dir = std::env::temp_dir().join(format!("l4m-once-{}", std::process::id()));
    let once_dir_clone = once_dir.clone();
    let chrome = tokio::task::spawn_blocking(move || {
        ChromeProc::launch(
            &binary,
            headless,
            once_dir_clone,
            true,
            proxy_port,
        )
    })
    .await??;
    let _relay = relay;
    let ws = chrome.page_ws()?;
    let cdp = Cdp::connect(&ws).await?;
    let started = std::time::Instant::now();
    let code = std::env::var("L4M_CODE").ok().filter(|c| !c.trim().is_empty());
    let result = tokio::select! {
        result = run_alias(
            &cdp,
            &asr,
            &alias,
            code.as_deref(),
            chrome.port,
            proxy.clone(),
            cfg.job_timeout,
        ) => result,
        // `timeout` and Ctrl-C otherwise kill the process before ChromeProc's
        // Drop runs, leaving a browser tree behind on a memory-tight box.
        _ = shutdown_signal() => {
            l4m_engine::chrome::sweep(&[once_dir.clone()]);
            Err(FlowError {
                kind: "shutdown",
                message: "shutdown requested".into(),
            })
        }
    };
    drop(chrome);
    l4m_engine::chrome::sweep(&[once_dir]);
    let elapsed = started.elapsed().as_secs_f64() * 1000.0;
    match result {
        Ok(destination) => {
            println!(
                "{}",
                serde_json::json!({
                    "status": "success",
                    "alias": alias,
                    "destination_url": destination,
                    "elapsed_ms": elapsed,
                })
            );
        }
        Err(err) => {
            warn!(target: "engine", "once failed: {err}");
            println!(
                "{}",
                serde_json::json!({
                    "status": "failed",
                    "alias": alias,
                    "error": err.message,
                    "kind": err.kind,
                    "elapsed_ms": elapsed,
                })
            );
            // Return instead of process::exit: exit skips ChromeProc::drop and
            // leaves a whole browser tree holding RAM on a small box.
            return Err(anyhow!("{}", err.message));
        }
    }
    tokio::time::sleep(Duration::from_millis(200)).await;
    Ok(())
}
