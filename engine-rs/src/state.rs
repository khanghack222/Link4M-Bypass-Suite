//! Shared configuration and runtime state.

use crate::asr::{self, SharedAsr};
use anyhow::{anyhow, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use tokio::sync::{Mutex, Semaphore};

#[derive(Clone, Debug)]
pub struct Config {
    pub host: String,
    pub port: u16,
    pub api_key: String,
    pub workers: usize,
    pub max_queue: usize,
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

impl Config {
    pub fn from_env() -> Self {
        Self {
            host: env_or("HOST", "0.0.0.0"),
            port: env_num("PORT", 8080u16),
            api_key: env_or("API_KEY", ""),
            workers: env_num("WORKERS", 2usize).max(1),
            max_queue: env_num("MAX_QUEUE", 100usize).max(1),
            job_timeout: Duration::from_secs(env_num("JOB_TIMEOUT", 300u64).max(30)),
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
    pub asr: SharedAsr,
    pub cache: Mutex<HashMap<String, CacheEntry>>,
    pub jobs: Mutex<HashMap<String, JobView>>,
    pub locks: Mutex<HashMap<String, Arc<Mutex<()>>>>,
    pub stats: Stats,
    pub queue_slots: Semaphore,
}

impl Inner {
    pub fn new(cfg: Config, asr: SharedAsr) -> Arc<Self> {
        let cache = load_cache(&cfg.cache_file);
        Arc::new(Self {
            queue_slots: Semaphore::new(cfg.max_queue),
            started: Instant::now(),
            cfg,
            asr,
            cache: Mutex::new(cache),
            jobs: Mutex::new(HashMap::new()),
            locks: Mutex::new(HashMap::new()),
            stats: Stats::default(),
        })
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
