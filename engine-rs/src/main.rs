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
use l4m_engine::flow::run_alias;
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

    let asr = Arc::new(asr);
    if let Some(target) = once {
        return run_once(cfg, asr, &target).await;
    }

    let inner = Inner::new(cfg.clone(), Some(asr));
    let pool = Arc::new(Pool::spawn(inner.clone()));
    let state = Arc::new(ApiState { inner, pool });
    let listener = tokio::net::TcpListener::bind((cfg.host.as_str(), cfg.port)).await?;
    info!(target: "engine", "listening on http://{}:{}", cfg.host, cfg.port);
    let server = axum::serve(listener, router(state))
        .with_graceful_shutdown(shutdown_signal());
    if tokio::time::timeout(Duration::from_secs(10), server)
        .await
        .is_err()
    {
        warn!(target: "engine", "shutdown timed out, dropping open sessions");
    }
    Ok(())
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
async fn load_local_asr(
    _model_path: &std::path::Path,
    _model_url: &str,
    _threads: i32,
) -> Result<Asr> {
    Err(anyhow!(
        "this build has no local ASR; set ASR_URL to a whisper.cpp server \
         or an OpenAI-compatible transcription endpoint"
    ))
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
    let chrome = tokio::task::spawn_blocking(move || {
        ChromeProc::launch(
            &binary,
            headless,
            std::env::temp_dir().join(format!("l4m-once-{}", std::process::id())),
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
    let result = run_alias(
        &cdp,
        &asr,
        &alias,
        code.as_deref(),
        chrome.port,
        proxy.clone(),
        cfg.job_timeout,
    )
    .await;
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
            std::process::exit(1);
        }
    }
    tokio::time::sleep(Duration::from_millis(200)).await;
    Ok(())
}
