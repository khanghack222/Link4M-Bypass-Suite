//! Shared server state: jobs, destination cache, counters and the engine
//! semaphore. Jobs and cache live in memory; the cache is mirrored to a JSON
//! file so a restart keeps the Link4M aliases already resolved.

use std::collections::{HashMap, VecDeque};
use std::path::Path;
use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};
use tokio::sync::{RwLock, Semaphore};

use crate::config::Config;

pub fn now_secs() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

#[derive(Debug, Clone, Serialize)]
pub struct Job {
    pub id: String,
    pub url: String,
    pub provider: String,
    pub key: String,
    pub status: String,
    pub destination: Option<String>,
    pub error: Option<String>,
    pub tries: u32,
    pub elapsed_ms: f64,
    pub cached: bool,
    pub client: String,
    pub created: f64,
    pub updated: f64,
}

impl Job {
    pub fn new(id: String, url: String, provider: String, key: String, client: String) -> Self {
        let now = now_secs();
        Job {
            id,
            url,
            provider,
            key,
            status: "queued".to_string(),
            destination: None,
            error: None,
            tries: 0,
            elapsed_ms: 0.0,
            cached: false,
            client,
            created: now,
            updated: now,
        }
    }

    pub fn is_terminal(&self) -> bool {
        matches!(self.status.as_str(), "success" | "error" | "timeout")
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CacheEntry {
    pub destination: String,
    pub updated: f64,
    pub hits: u64,
}

pub struct AppState {
    pub cfg: Config,
    pub cache: RwLock<HashMap<String, CacheEntry>>,
    pub jobs: RwLock<HashMap<String, Job>>,
    pub recent: RwLock<VecDeque<Job>>,
    pub sem: Arc<Semaphore>,
    pub queued: AtomicUsize,
    pub inflight: AtomicUsize,
    pub total_jobs: AtomicU64,
    pub successes: AtomicU64,
    pub errors: AtomicU64,
    pub cache_hits: AtomicU64,
    pub started: f64,
}

impl AppState {
    pub fn new(cfg: Config) -> Arc<Self> {
        let cache = load_cache(&cfg.cache_file);
        Arc::new(AppState {
            sem: Arc::new(Semaphore::new(cfg.workers)),
            cfg,
            cache: RwLock::new(cache),
            jobs: RwLock::new(HashMap::new()),
            recent: RwLock::new(VecDeque::with_capacity(100)),
            queued: AtomicUsize::new(0),
            inflight: AtomicUsize::new(0),
            total_jobs: AtomicU64::new(0),
            successes: AtomicU64::new(0),
            errors: AtomicU64::new(0),
            cache_hits: AtomicU64::new(0),
            started: now_secs(),
        })
    }

    pub fn queue_depth(&self) -> usize {
        self.queued.load(Ordering::Relaxed) + self.inflight.load(Ordering::Relaxed)
    }

    pub async fn cache_get(&self, provider: &str, key: &str) -> Option<String> {
        if !self.cfg.cache_enabled {
            return None;
        }
        let cache_key = format!("{provider}:{key}");
        let mut cache = self.cache.write().await;
        let entry = cache.get_mut(&cache_key)?;
        if now_secs() - entry.updated > self.cfg.cache_ttl as f64 {
            cache.remove(&cache_key);
            return None;
        }
        entry.hits += 1;
        self.cache_hits.fetch_add(1, Ordering::Relaxed);
        Some(entry.destination.clone())
    }

    pub async fn cache_put(&self, provider: &str, key: &str, destination: &str) {
        if !self.cfg.cache_enabled {
            return;
        }
        let cache_key = format!("{provider}:{key}");
        let snapshot = {
            let mut cache = self.cache.write().await;
            cache.insert(
                cache_key,
                CacheEntry {
                    destination: destination.to_string(),
                    updated: now_secs(),
                    hits: 0,
                },
            );
            cache.clone()
        };
        persist_cache(&self.cfg.cache_file, &snapshot).await;
    }

    pub async fn insert_job(&self, job: Job) {
        self.jobs.write().await.insert(job.id.clone(), job);
    }

    pub async fn get_job(&self, id: &str) -> Option<Job> {
        self.jobs.read().await.get(id).cloned()
    }

    pub async fn update_job<F>(&self, id: &str, update: F)
    where
        F: FnOnce(&mut Job),
    {
        if let Some(job) = self.jobs.write().await.get_mut(id) {
            update(job);
            job.updated = now_secs();
        }
    }

    /// Move a finished job into the recent ring (bounded at 100 entries).
    pub async fn finish_job(&self, id: &str) {
        let job = self.jobs.read().await.get(id).cloned();
        if let Some(job) = job {
            let mut recent = self.recent.write().await;
            recent.push_front(job);
            recent.truncate(100);
        }
    }

    pub async fn recent(&self, limit: usize) -> Vec<Job> {
        self.recent
            .read()
            .await
            .iter()
            .take(limit)
            .cloned()
            .collect()
    }

    pub async fn stats(&self) -> serde_json::Value {
        let jobs = self.jobs.read().await;
        let mut by_status: HashMap<&str, u64> = HashMap::new();
        for job in jobs.values() {
            *by_status.entry(job.status.as_str()).or_insert(0) += 1;
        }
        let cached_links = self.cache.read().await.len();
        serde_json::json!({
            "total_jobs": self.total_jobs.load(Ordering::Relaxed),
            "by_status": by_status,
            "cached_links": cached_links,
            "successes": self.successes.load(Ordering::Relaxed),
            "errors": self.errors.load(Ordering::Relaxed),
            "cache_hits": self.cache_hits.load(Ordering::Relaxed),
            "uptime_sec": (now_secs() - self.started).round(),
        })
    }
}

fn load_cache(path: &Path) -> HashMap<String, CacheEntry> {
    match std::fs::read_to_string(path) {
        Ok(text) => serde_json::from_str(&text).unwrap_or_default(),
        Err(_) => HashMap::new(),
    }
}

async fn persist_cache(path: &Path, cache: &HashMap<String, CacheEntry>) {
    let Some(parent) = path.parent() else { return };
    if tokio::fs::create_dir_all(parent).await.is_err() {
        return;
    }
    let Ok(text) = serde_json::to_string(cache) else {
        return;
    };
    let tmp = path.with_extension("json.tmp");
    if tokio::fs::write(&tmp, text).await.is_ok() {
        let _ = tokio::fs::rename(&tmp, path).await;
    }
}
