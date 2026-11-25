//! `bypass-server` — server-side façade for the Link4M Bypass Suite.
//!
//! Build:  cargo build --release
//! Check:  ./target/release/bypass-server --check
//! Run:    ./target/release/bypass-server
//!
//! The binary never imports a browser stack. Each job is delegated to
//! `python -m src.bypass_api --url ... --json`, so the engines and their
//! solvers keep living in the Python tree while the HTTP face is Rust.

use bypass_server::{api, config, state};

use tokio::net::TcpListener;
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;
use tracing_subscriber::EnvFilter;

#[tokio::main]
async fn main() {
    let args: Vec<String> = std::env::args().collect();
    let cfg = config::Config::from_env();

    if args.iter().any(|arg| arg == "--check") {
        api::print_check(&cfg);
        return;
    }
    if args.iter().any(|arg| arg == "--version" || arg == "-V") {
        println!("bypass-server {}", env!("CARGO_PKG_VERSION"));
        return;
    }

    tracing_subscriber::registry()
        .with(
            EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| EnvFilter::new("bypass_server=info,tower_http=info")),
        )
        .with(tracing_subscriber::fmt::layer().with_target(false))
        .init();

    for line in cfg.summary() {
        tracing::info!("{line}");
    }

    let app_state = state::AppState::new(cfg.clone());
    let app = api::router(app_state);

    let addr = format!("{}:{}", cfg.host, cfg.port);
    let listener = match TcpListener::bind(&addr).await {
        Ok(listener) => listener,
        Err(error) => {
            tracing::error!("bind {addr} thất bại: {error}");
            std::process::exit(1);
        }
    };
    tracing::info!("bypass-server listening on http://{addr}");

    if let Err(error) = axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await
    {
        tracing::error!("server dừng: {error}");
        std::process::exit(1);
    }
}

async fn shutdown_signal() {
    let ctrl_c = async {
        let _ = tokio::signal::ctrl_c().await;
    };

    #[cfg(unix)]
    let terminate = async {
        match tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate()) {
            Ok(mut signal) => {
                signal.recv().await;
            }
            Err(_) => std::future::pending::<()>().await,
        }
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }
    tracing::info!("shutdown signal received");
}
