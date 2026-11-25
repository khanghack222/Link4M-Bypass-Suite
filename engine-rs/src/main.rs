//! l4m-engine: native Link4M bypass service.
//!
//! One binary: HTTP API, Chrome pool, reCAPTCHA audio solving through local
//! whisper.cpp, cache, queue. No Python, no Playwright, no captcha API.

use anyhow::{anyhow, Result};
use l4m_engine::api::{router, ApiState};
use l4m_engine::asr::{ensure_model, Asr};
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

    if !std::path::Path::new(&cfg.chrome_bin).exists() {
        return Err(anyhow!(
            "chrome binary not found: {} (set CHROME_BIN)",
            cfg.chrome_bin
        ));
    }

    let model_path = cfg.model_path.clone();
    let model_url = cfg.model_url.clone();
    let threads = cfg.asr_threads;
    let asr = tokio::task::spawn_blocking(move || -> Result<Asr> {
        let path = ensure_model(&model_path, &model_url)?;
        Asr::load(&path, threads)
    })
    .await??;
    info!(target: "engine", "whisper ready ({} threads)", cfg.asr_threads);

    if check {
        let binary = cfg.chrome_bin.clone();
        let headless = cfg.headless;
        let chrome = tokio::task::spawn_blocking(move || {
            ChromeProc::launch(
                &binary,
                headless,
                std::env::temp_dir().join(format!("l4m-check-{}", std::process::id())),
                true,
            )
        })
        .await??;
        let ws = chrome.page_ws()?;
        let cdp = Cdp::connect(&ws).await?;
        cdp.call("Page.enable", serde_json::json!({})).await?;
        info!(target: "engine", "check ok: chrome + cdp + whisper");
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
    axum::serve(listener, router(state)).await?;
    Ok(())
}

async fn run_once(cfg: Config, asr: Arc<Asr>, target: &str) -> Result<()> {
    let alias = l4m_engine::flow::extract_alias(target)
        .ok_or_else(|| anyhow!("cannot read link4m alias from {target}"))?;
    let binary = cfg.chrome_bin.clone();
    let headless = cfg.headless;
    let chrome = tokio::task::spawn_blocking(move || {
        ChromeProc::launch(
            &binary,
            headless,
            std::env::temp_dir().join(format!("l4m-once-{}", std::process::id())),
            true,
        )
    })
    .await??;
    let ws = chrome.page_ws()?;
    let cdp = Cdp::connect(&ws).await?;
    let started = std::time::Instant::now();
    let code = std::env::var("L4M_CODE").ok().filter(|c| !c.trim().is_empty());
    let result = run_alias(&cdp, &asr, &alias, code.as_deref(), cfg.job_timeout).await;
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
