//! Shared configuration and runtime state.

use crate::asr::{self, SharedAsr};
use anyhow::{anyhow, Result};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, VecDeque};
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use tokio::sync::{broadcast, Mutex, Semaphore};

#[derive(Clone, Debug)]
pub struct Config {
    pub host: String,
    pub port: u16,
    pub api_key: String,
    pub workers: usize,
    pub max_queue: usize,
    pub max_batch: usize,
    pub batch_concurrency: usize,
    pub job_timeout: Duration,
    pub cache_ttl: Duration,
    pub cache_file: PathBuf,
    pub cache_enabled: bool,
    pub chrome_bin: String,
    pub headless: bool,
    pub profile_dir: PathBuf,
    pub model_path: PathBuf,
    pub model_url: String,
    pub asr_threads: i32,
}

fn env_or(key: &str, default: &str) -> String {
    std::env::var(key).unwrap_or_else(|_| default.to_string())
}

fn env_num<T: std::str::FromStr>(key: &str, default: T) -> T {
    std::env::var(key)
        .ok()
        .and_then(|v| v.trim().parse::<T>().ok())
        .unwrap_or(default)
}

fn find_chrome() -> String {
    for candidate in [
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "/opt/google/chrome/chrome",
    ] {
        if candidate.starts_with('/') {
            if std::path::Path::new(candidate).exists() {
                return candidate.to_string();
            }
            continue;
        }
        if let Ok(path) = which(candidate) {
            return path;
        }
    }
    "google-chrome".to_string()
}

fn which(binary: &str) -> Result<String> {
    let path = std::env::var("PATH").unwrap_or_default();
    for dir in path.split(':') {
        let candidate = std::path::Path::new(dir).join(binary);
        if candidate.is_file() {
            return Ok(candidate.display().to_string());
        }
    }
    Err(anyhow!("{binary} not found"))
}

/// `WORKERS=auto` sizes the pool from MemAvailable: one headful Chrome plus
/// its share of whisper costs ~1.4 GB, and the box needs ~900 MB to breathe.
fn parse_workers() -> usize {
    let raw = std::env::var("WORKERS").unwrap_or_else(|_| "2".into());
    if raw.trim().eq_ignore_ascii_case("auto") {
        let available_mb = std::fs::read_to_string("/proc/meminfo")
            .ok()
            .and_then(|text| {
                text.lines()
                    .find(|line| line.starts_with("MemAvailable:"))
                    .and_then(|line| line.split_whitespace().nth(1))
                    .and_then(|kb| kb.parse::<u64>().ok())
            })
            .map(|kb| kb / 1024)
            .unwrap_or(2048);
        let workers = available_mb.saturating_sub(900) / 1400;
        return (workers as usize).clamp(1, 32);
    }
    raw.trim().parse::<usize>().unwrap_or(2).max(1)
}

impl Config {
    pub fn from_env() -> Self {
        let workers = parse_workers();
        Self {
            host: env_or("HOST", "0.0.0.0"),
            port: env_num("PORT", 8080u16),
            api_key: env_or("API_KEY", ""),
            workers,
            max_batch: env_num("MAX_BATCH", 50usize).clamp(1, 500),
            // Batch fan-out follows the pool: on a one-worker box the old
            // fixed 4 only queued work that could not run in parallel.
            batch_concurrency: env_num("BATCH_CONCURRENCY", workers.max(4)).clamp(1, 64),
            max_queue: env_num("MAX_QUEUE", 100usize).max(1),
            job_timeout: Duration::from_secs(env_num("JOB_TIMEOUT", 480u64).max(30)),
            cache_ttl: Duration::from_secs(env_num("CACHE_TTL", 21_600u64)),
            cache_file: PathBuf::from(env_or("CACHE_FILE", "data/native_cache.json")),
            cache_enabled: env_or("CACHE_ENABLED", "true") != "false",
            chrome_bin: env_or("CHROME_BIN", &find_chrome()),
            headless: match std::env::var("L4M_HEADLESS") {
                Ok(value) => value != "0",
                Err(_) => std::env::var("DISPLAY").map(|d| d.trim().is_empty()).unwrap_or(true),
            },
            profile_dir: PathBuf::from(
                std::env::var("CHROME_PROFILE")
                    .ok()
                    .filter(|v| !v.trim().is_empty())
                    .unwrap_or_else(|| "data/chrome-profile".to_string()),
            ),
            model_path: PathBuf::from(env_or("WHISPER_MODEL", "models/ggml-tiny.en.bin")),
            model_url: env_or("WHISPER_MODEL_URL", asr::DEFAULT_MODEL_URL),
            asr_threads: env_num("ASR_THREADS", 2i32).max(1),
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CacheEntry {
    pub destination_url: String,
    pub stored_at: u64,
}

impl CacheEntry {
    fn fresh(&self, ttl: Duration) -> bool {
        let now = unix_now();
        now.saturating_sub(self.stored_at) < ttl.as_secs()
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct JobView {
    pub job_id: String,
    pub status: String,
    pub url: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub destination_url: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    pub created_at: u64,
    pub elapsed_ms: f64,
}

/// One row on the live status board. `JobView` is the polling contract;
/// `LinkEntry` is the board contract and keeps finished links around so a
/// fresh browser tab can render what already ran.
#[derive(Clone, Debug, Serialize)]
pub struct LinkEntry {
    pub id: String,
    pub url: String,
    /// `queued` -> `running` -> `success` | `failed`.
    pub status: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub destination_url: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub provider: Option<String>,
    pub cached: bool,
    pub elapsed_ms: f64,
    pub created_at: u64,
    pub updated_at: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

#[derive(Default)]
pub struct Stats {
    pub total: AtomicU64,
    pub successes: AtomicU64,
    pub errors: AtomicU64,
    pub cache_hits: AtomicU64,
}

impl Stats {
    pub fn snapshot(&self, cache_len: usize, queued: usize) -> serde_json::Value {
        serde_json::json!({
            "total_jobs": self.total.load(Ordering::Relaxed),
            "successes": self.successes.load(Ordering::Relaxed),
            "errors": self.errors.load(Ordering::Relaxed),
            "cache_hits": self.cache_hits.load(Ordering::Relaxed),
            "cached_links": cache_len,
            "queued": queued,
        })
    }
}

pub struct Inner {
    pub cfg: Config,
    pub started: Instant,
    /// `None` only in tests: the API surface (decode, supported, auth, jobs)
    /// must be exercisable without a 77 MB whisper model on disk.
    pub asr: Option<SharedAsr>,
    pub cache: Mutex<HashMap<String, CacheEntry>>,
    pub jobs: Mutex<HashMap<String, JobView>>,
    pub links: Mutex<VecDeque<LinkEntry>>,
    /// Fan-out for the status board. Slow SSE clients lag and skip instead of
    /// blocking dispatch.
    pub events: broadcast::Sender<serde_json::Value>,
    pub locks: Mutex<HashMap<String, Arc<Mutex<()>>>>,
    pub stats: Stats,
    pub queue_slots: Semaphore,
}

/// Board history is bounded: a long-running service must not grow with traffic.
const LINK_HISTORY: usize = 500;

impl Inner {
    pub fn new(cfg: Config, asr: Option<SharedAsr>) -> Arc<Self> {
        let cache = load_cache(&cfg.cache_file);
        let (events, _) = broadcast::channel(512);
        Arc::new(Self {
            queue_slots: Semaphore::new(cfg.max_queue),
            started: Instant::now(),
            cfg,
            asr,
            cache: Mutex::new(cache),
            jobs: Mutex::new(HashMap::new()),
            links: Mutex::new(VecDeque::new()),
            events,
            locks: Mutex::new(HashMap::new()),
            stats: Stats::default(),
        })
    }

    pub fn subscribe(&self) -> broadcast::Receiver<serde_json::Value> {
        self.events.subscribe()
    }

    fn emit_link(&self, entry: &LinkEntry) {
        let _ = self.events.send(serde_json::json!(entry));
    }

    /// Record a request as soon as it is accepted, before a browser touches it.
    pub async fn link_begin(&self, url: &str, provider: Option<&str>) -> String {
        let now = unix_now();
        let entry = LinkEntry {
            id: new_job_id(),
            url: url.to_string(),
            status: "queued".into(),
            destination_url: None,
            provider: provider.map(str::to_string),
            cached: false,
            elapsed_ms: 0.0,
            created_at: now,
            updated_at: now,
            error: None,
        };
        {
            let mut links = self.links.lock().await;
            links.push_front(entry.clone());
            while links.len() > LINK_HISTORY {
                links.pop_back();
            }
        }
        self.emit_link(&entry);
        entry.id
    }

    pub async fn link_running(&self, id: &str) {
        self.link_update(id, |entry| {
            entry.status = "running".into();
        })
        .await;
    }

    #[allow(clippy::too_many_arguments)]
    pub async fn link_finish(
        &self,
        id: &str,
        status: &str,
        destination: Option<String>,
        error: Option<String>,
        elapsed_ms: f64,
        cached: bool,
    ) {
        self.link_update(id, move |entry| {
            entry.status = status.to_string();
            entry.destination_url = destination;
            entry.error = error;
            entry.elapsed_ms = elapsed_ms;
            entry.cached = cached;
        })
        .await;
    }

    async fn link_update<F>(&self, id: &str, mutate: F)
    where
        F: FnOnce(&mut LinkEntry),
    {
        let updated = {
            let mut links = self.links.lock().await;
            let Some(entry) = links.iter_mut().find(|entry| entry.id == id) else {
                return;
            };
            mutate(entry);
            entry.updated_at = unix_now();
            entry.clone()
        };
        self.emit_link(&updated);
    }

    pub async fn links_snapshot(&self) -> Vec<LinkEntry> {
        self.links.lock().await.iter().cloned().collect()
    }

    pub async fn cache_get(&self, key: &str) -> Option<String> {
        let cache = self.cache.lock().await;
        cache
            .get(key)
            .filter(|entry| entry.fresh(self.cfg.cache_ttl))
            .map(|entry| entry.destination_url.clone())
    }

    pub async fn cache_put(&self, key: String, destination: String) {
        if !self.cfg.cache_enabled {
            return;
        }
        {
            let mut cache = self.cache.lock().await;
            cache.insert(
                key,
                CacheEntry { destination_url: destination, stored_at: unix_now() },
            );
        }
        self.persist_cache().await;
    }

    async fn persist_cache(&self) {
        let snapshot: HashMap<String, CacheEntry> = self.cache.lock().await.clone();
        let path = self.cfg.cache_file.clone();
        let _ = tokio::task::spawn_blocking(move || {
            if let Some(parent) = path.parent() {
                let _ = std::fs::create_dir_all(parent);
            }
            if let Ok(body) = serde_json::to_string(&snapshot) {
                let tmp = path.with_extension("tmp");
                if std::fs::write(&tmp, body).is_ok() {
                    let _ = std::fs::rename(&tmp, &path);
                }
            }
        })
        .await;
    }

    pub async fn job_put(&self, job: JobView) {
        let mut jobs = self.jobs.lock().await;
        if jobs.len() > 2000 {
            let mut entries: Vec<(String, u64)> =
                jobs.iter().map(|(k, v)| (k.clone(), v.created_at)).collect();
            entries.sort_by_key(|(_, created)| *created);
            for (key, _) in entries.into_iter().take(500) {
                jobs.remove(&key);
            }
        }
        jobs.insert(job.job_id.clone(), job);
    }

    pub async fn job_get(&self, id: &str) -> Option<JobView> {
        self.jobs.lock().await.get(id).cloned()
    }

    /// Drop a job that never reached a worker (queue full), so `GET /jobs/{id}`
    /// cannot report a phantom job as running forever.
    pub async fn job_remove(&self, id: &str) {
        self.jobs.lock().await.remove(id);
    }

    pub async fn key_lock(&self, key: &str) -> Arc<Mutex<()>> {
        let mut locks = self.locks.lock().await;
        locks
            .entry(key.to_string())
            .or_insert_with(|| Arc::new(Mutex::new(())))
            .clone()
    }
}

pub fn unix_now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

pub fn load_cache(path: &PathBuf) -> HashMap<String, CacheEntry> {
    std::fs::read_to_string(path)
        .ok()
        .and_then(|body| serde_json::from_str(&body).ok())
        .unwrap_or_default()
}

pub fn new_job_id() -> String {
    use std::time::SystemTime;
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    let pid = std::process::id() as u128;
    format!("{:x}{:x}", pid, nanos)
}

pub fn elapsed_ms(start: Instant) -> f64 {
    start.elapsed().as_secs_f64() * 1000.0
}
