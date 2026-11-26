//! Worker pool: one Chrome instance per worker, competing on a bounded job
//! queue. A dead browser is relaunched on the next job instead of failing the
//! whole service.

use crate::cdp::Cdp;
use crate::chrome::ChromeProc;
use crate::flow::{run_alias, FlowError};
use crate::proxy::{self, Proxy, Relay};
use crate::state::{unix_now, Inner, JobView};
use std::sync::atomic::Ordering;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::{mpsc, oneshot, Mutex};
use tracing::{error, info, warn};

pub struct Job {
    pub job_id: String,
    pub key: String,
    pub alias: String,
    pub url: String,
    pub code: Option<String>,
    /// Row id on the live status board.
    pub track_id: String,
    pub respond: oneshot::Sender<JobOutcome>,
}

pub struct JobOutcome {
    pub destination: Option<String>,
    pub error: Option<FlowError>,
    pub elapsed_ms: f64,
}

pub struct Pool {
    sender: mpsc::Sender<Job>,
}

#[derive(Debug, Clone, Copy)]
pub struct QueueFull;

impl Pool {
    pub fn spawn(inner: Arc<Inner>) -> Self {
        let (sender, receiver) = mpsc::channel::<Job>(inner.cfg.max_queue);
        let receiver = Arc::new(Mutex::new(receiver));
        for worker_id in 0..inner.cfg.workers {
            let receiver = receiver.clone();
            let inner = inner.clone();
            tokio::spawn(async move {
                worker_loop(worker_id, inner, receiver).await;
            });
        }
        let resume_inner = inner.clone();
        let resume_sender = sender.clone();
        tokio::spawn(async move {
            resume_pending(resume_inner, resume_sender).await;
        });
        Self { sender }
    }

    /// The queue can no longer take the job. Callers only need to know that it
    /// was rejected, so the job itself is dropped here instead of being carried
    /// back in a 128-byte error variant.
    pub fn try_dispatch(&self, job: Job) -> std::result::Result<(), QueueFull> {
        self.sender.try_send(job).map_err(|_| QueueFull)
    }
}

struct Session {
    chrome: ChromeProc,
    cdp: Arc<Cdp>,
    _relay: Option<Relay>,
    proxy: Option<Proxy>,
}

/// Re-dispatch jobs that were accepted before the last shutdown. The HTTP
/// caller that was waiting is gone, so the oneshot receiver is dropped; the
/// worker still records the result on the board and in `/jobs/{id}`.
async fn resume_pending(inner: Arc<Inner>, sender: mpsc::Sender<Job>) {
    if !inner.cfg.resume_queue {
        return;
    }
    let pending = inner.queue_snapshot().await;
    if pending.is_empty() {
        return;
    }
    // Let the listener bind and the router come up before the first Chrome
    // launch, so a client can watch the resumed rows immediately.
    tokio::time::sleep(Duration::from_millis(600)).await;
    let mut resumed = 0usize;
    for entry in pending {
        let job_id = entry.job_id.clone();
        let job_url = entry.url.clone();
        let view_url = entry.url.clone();
        let created_at = entry.created_at;
        inner
            .job_put(JobView {
                job_id: job_id.clone(),
                status: "running".into(),
                url: view_url,
                destination_url: None,
                error: None,
                created_at,
                elapsed_ms: 0.0,
            })
            .await;
        let (respond, _receiver) = oneshot::channel();
        let job = Job {
            job_id: entry.job_id,
            key: entry.key,
            alias: entry.alias,
            url: job_url,
            code: entry.code,
            track_id: entry.track_id,
            respond,
        };
        // A full channel leaves the row on disk untouched for the next boot;
        // drop the provisional view so `/jobs` does not show a ghost.
        if sender.try_send(job).is_err() {
            inner.job_remove(&job_id).await;
            break;
        }
        resumed += 1;
    }
    if resumed > 0 {
        info!(target: "engine", resumed, "resumed queued jobs after restart");
    }
}

/// Google explicitly says the exit is burned. Only these messages justify
/// cooling down a proxy; a plain misread must not blacklist a good IP.
fn ip_blocked(err: &FlowError) -> bool {
    if err.kind != "audio" {
        return false;
    }
    let message = err.message.to_lowercase();
    message.contains("automated") || message.contains("try again later")
}

/// Any audio dead-end is worth a fresh Chrome/anchor; three bad transcripts
/// can be the profile, not the exit.
fn audio_blocked(err: &FlowError) -> bool {
    ip_blocked(err) || (err.kind == "audio" && err.message.to_lowercase().contains("three clips failed"))
}

/// Terminal failures that happen before `run_alias` still need a
/// `/api/v1/jobs/{id}` row; otherwise a poller sees `running` forever.
async fn record_failure(inner: &Arc<Inner>, job: &Job, kind: &str, message: &str, elapsed_ms: f64) {
    inner
        .job_put(JobView {
            job_id: job.job_id.clone(),
            status: "failed".into(),
            url: job.url.clone(),
            destination_url: None,
            error: Some(format!("{kind}: {message}")),
            created_at: unix_now(),
            elapsed_ms,
        })
        .await;
}

async fn worker_loop(
    worker_id: usize,
    inner: Arc<Inner>,
    receiver: Arc<Mutex<mpsc::Receiver<Job>>>,
) {
    let mut session: Option<Session> = None;
    // Link4M stops serving sponsor campaigns after a handful of completions
    // from one exit. Rotate proactively instead of waiting for captcha-only
    // pages; 0 disables the counter.
    let rotate_after = std::env::var("PROXY_ROTATE_AFTER")
        .ok()
        .and_then(|value| value.trim().parse::<usize>().ok())
        .unwrap_or(4);
    let mut successes_on_exit = 0usize;
    loop {
        let job = {
            let mut guard = receiver.lock().await;
            guard.recv().await
        };
        let Some(job) = job else { break };
        let started = Instant::now();
        // Picked up: keep the entry on disk, marked running, so a crash can
        // requeue the full job (key + code) instead of losing it.
        inner.queue_mark_running(&job.job_id).await;
        inner.link_running(&job.track_id).await;

        // Without the whisper model the job can never finish; fail it before
        // paying for a Chrome launch.
        let Some(asr) = inner.asr.clone() else {
            let elapsed_ms = started.elapsed().as_secs_f64() * 1000.0;
            inner
                .link_finish(
                    &job.track_id,
                    "failed",
                    None,
                    Some("asr: whisper model not loaded".into()),
                    elapsed_ms,
                    false,
                )
                .await;
            record_failure(&inner, &job, "asr", "whisper model not loaded", elapsed_ms).await;
            inner.queue_remove(&job.job_id).await;
            let _ = job.respond.send(JobOutcome {
                destination: None,
                error: Some(FlowError {
                    kind: "asr",
                    message: "whisper model not loaded".into(),
                }),
                elapsed_ms,
            });
            continue;
        };

        if session.is_none() {
            match start_session(&inner, worker_id).await {
                Ok(ready) => {
                    info!(
                        target: "engine",
                        worker = worker_id,
                        port = ready.chrome.port,
                        proxy = %ready.proxy.as_ref().map(|p| format!("{}:{}", p.host, p.port)).unwrap_or_else(|| "direct".into()),
                        "chrome ready"
                    );
                    session = Some(ready);
                }
                Err(err) => {
                    error!(target: "engine", worker = worker_id, "chrome failed: {err}");
                    let elapsed_ms = started.elapsed().as_secs_f64() * 1000.0;
                    inner
                        .link_finish(
                            &job.track_id,
                            "failed",
                            None,
                            Some(format!("browser: {err}")),
                            elapsed_ms,
                            false,
                        )
                        .await;
                    record_failure(&inner, &job, "browser", &err.to_string(), elapsed_ms).await;
                    inner.queue_remove(&job.job_id).await;
                    let _ = job.respond.send(JobOutcome {
                        destination: None,
                        error: Some(FlowError {
                            kind: "browser",
                            message: err.to_string(),
                        }),
                        elapsed_ms,
                    });
                    tokio::time::sleep(std::time::Duration::from_secs(3)).await;
                    continue;
                }
            }
        }

        let Some(active) = session.as_ref() else { continue };
        let chrome_port = active.chrome.port;
        let cdp = active.cdp.clone();
        let active_proxy = active.proxy.clone();
        let outcome = run_alias(
            &cdp,
            &asr,
            &job.alias,
            job.code.as_deref(),
            chrome_port,
            inner.cfg.job_timeout,
        )
        .await;
        let elapsed_ms = started.elapsed().as_secs_f64() * 1000.0;

        let dead = match &outcome {
            Ok(_) => false,
            Err(err) => err.kind == "cdp",
        };
        if dead {
            warn!(target: "engine", worker = worker_id, "browser died, dropping session");
            session = None;
        }
        // reCAPTCHA answers "automated queries / try again later" when the IP
        // is burned. That is not a transient audio mistake: burn the exit and
        // let the next job start on a different one.
        let blocked = matches!(&outcome, Err(err) if audio_blocked(err));
        if let (Some(pool), Some(bad)) = (proxy::shared(), active_proxy.as_ref()) {
            match &outcome {
                Err(err) if matches!(err.kind, "cdp" | "browser" | "timeout") || ip_blocked(err) => {
                    pool.mark_bad(bad)
                }
                Ok(_) => pool.mark_good(bad),
                _ => {}
            }
        }
        let mut quota_reached = false;
        if outcome.is_ok() {
            successes_on_exit += 1;
            if rotate_after > 0
                && successes_on_exit >= rotate_after
                && proxy::shared().map(|pool| pool.len() > 1).unwrap_or(false)
            {
                if let (Some(pool), Some(used)) = (proxy::shared(), active_proxy.as_ref()) {
                    pool.mark_bad(used);
                }
                successes_on_exit = 0;
                quota_reached = true;
            }
        }
        // PROXY_ROTATE=1 gives every job a fresh exit; the cost is a Chrome
        // relaunch (~5 s) and a fresh profile boot.
        let rotate = std::env::var("PROXY_ROTATE")
            .map(|value| value != "0")
            .unwrap_or(false);
        if active_proxy.is_some() && (rotate || blocked || quota_reached) && session.is_some() {
            info!(
                target: "engine",
                worker = worker_id,
                reason = if blocked {
                    "captcha block"
                } else if quota_reached {
                    "proxy quota"
                } else {
                    "rotate"
                },
                "moving to the next proxy, relaunching chrome"
            );
            session = None;
        }

        let snapshot = match &outcome {
            Ok(destination) => {
                inner.stats.successes.fetch_add(1, Ordering::Relaxed);
                inner.cache_put(job.key.clone(), destination.clone()).await;
                JobView {
                    job_id: job.job_id.clone(),
                    status: "success".into(),
                    url: job.url.clone(),
                    destination_url: Some(destination.clone()),
                    error: None,
                    created_at: unix_now(),
                    elapsed_ms,
                }
            }
            Err(err) => {
                inner.stats.errors.fetch_add(1, Ordering::Relaxed);
                JobView {
                    job_id: job.job_id.clone(),
                    status: "failed".into(),
                    url: job.url.clone(),
                    destination_url: None,
                    error: Some(format!("{}: {}", err.kind, err.message)),
                    created_at: unix_now(),
                    elapsed_ms,
                }
            }
        };
        inner
            .link_finish(
                &job.track_id,
                &snapshot.status,
                snapshot.destination_url.clone(),
                snapshot.error.clone(),
                snapshot.elapsed_ms,
                false,
            )
            .await;
        inner.job_put(snapshot).await;
        // Terminal: the on-disk queue must not replay this job next boot.
        inner.queue_remove(&job.job_id).await;

        let _ = job.respond.send(match outcome {
            Ok(destination) => JobOutcome { destination: Some(destination), error: None, elapsed_ms },
            Err(err) => JobOutcome { destination: None, error: Some(err), elapsed_ms },
        });
    }
}

fn copy_dir(from: &std::path::Path, to: &std::path::Path) -> std::io::Result<()> {
    std::fs::create_dir_all(to)?;
    for entry in std::fs::read_dir(from)? {
        let entry = entry?;
        let target = to.join(entry.file_name());
        if entry.file_type()?.is_dir() {
            copy_dir(&entry.path(), &target)?;
        } else {
            std::fs::copy(entry.path(), &target)?;
        }
    }
    Ok(())
}

async fn start_session(inner: &Arc<Inner>, worker_id: usize) -> anyhow::Result<Session> {
    let binary = inner.cfg.chrome_bin.clone();
    let headless = inner.cfg.headless;
    let base = inner.cfg.profile_dir.clone();
    let profile = if inner.cfg.workers == 1 {
        base.clone()
    } else {
        let name = base
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_else(|| "chrome-profile".into());
        base.with_file_name(format!("{name}-w{worker_id}"))
    };
    // Seed every extra worker from the base profile once, so a session that
    // already passed the code step is shared instead of re-solved.
    if profile != base && !profile.exists() && base.exists() {
        let (from, to) = (base.clone(), profile.clone());
        let _ = tokio::task::spawn_blocking(move || copy_dir(&from, &to)).await;
    }
    let pool = proxy::shared();
    let chosen = pool.as_ref().and_then(|pool| pool.next());
    let relay = match &chosen {
        Some(upstream) => Some(proxy::start_relay(upstream.clone()).await?),
        None => None,
    };
    let proxy_port = relay.as_ref().map(|relay| relay.port);
    let chrome = tokio::task::spawn_blocking(move || {
        ChromeProc::launch(&binary, headless, profile, false, proxy_port)
    })
    .await??;
    let ws = chrome.page_ws()?;
    let cdp = Cdp::connect(&ws).await?;
    Ok(Session { chrome, cdp, _relay: relay, proxy: chosen })
}
