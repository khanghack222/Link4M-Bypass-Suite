//! Shared configuration and runtime state.

use crate::asr::{self, SharedAsr};
use anyhow::{anyhow, Result};
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet, VecDeque};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use tokio::sync::{broadcast, Mutex};
use tracing::warn;

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
    /// Pending jobs survive a restart; the file is rewritten atomically.
    pub queue_file: PathBuf,
    /// Last 500 board rows survive a restart too.
    pub links_file: PathBuf,
    pub resume_queue: bool,
    /// Re-run jobs that were mid-flight when the process died. A crash can
    /// happen after a sponsor code was submitted, so this trades a possible
    /// duplicate completion for never dropping user work.
    pub resume_running: bool,
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

fn env_flag(key: &str, default: bool) -> bool {
    match std::env::var(key) {
        Ok(value) => !matches!(
            value.trim().to_ascii_lowercase().as_str(),
            "0" | "false" | "no" | "off"
        ),
        Err(_) => default,
    }
}

fn find_chrome() -> String {
    #[cfg(windows)]
    {
        for key in ["PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"] {
            if let Ok(base) = std::env::var(key) {
                let candidate = std::path::Path::new(&base)
                    .join("Google\\Chrome\\Application\\chrome.exe");
                if candidate.is_file() {
                    return candidate.display().to_string();
                }
            }
        }
    }
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
    for dir in std::env::split_paths(&path) {
        let direct = dir.join(binary);
        if direct.is_file() {
            return Ok(direct.display().to_string());
        }
        #[cfg(windows)]
        {
            let exe = dir.join(format!("{binary}.exe"));
            if exe.is_file() {
                return Ok(exe.display().to_string());
            }
        }
    }
    Err(anyhow!("{binary} not found"))
}

/// Available RAM in MiB, platform-specific so `WORKERS=auto` is not a Linux
/// only feature. Returns `None` when the platform cannot report it.
#[cfg(target_os = "linux")]
fn available_memory_mb() -> Option<u64> {
    std::fs::read_to_string("/proc/meminfo")
        .ok()
        .and_then(|text| {
            text.lines()
                .find(|line| line.starts_with("MemAvailable:"))
                .and_then(|line| line.split_whitespace().nth(1))
                .and_then(|kb| kb.parse::<u64>().ok())
        })
        .map(|kb| kb / 1024)
}

#[cfg(target_os = "macos")]
fn available_memory_mb() -> Option<u64> {
    // `vm_stat` is part of the base system; no extra binary or FFI needed.
    let output = std::process::Command::new("vm_stat").output().ok()?;
    let text = String::from_utf8_lossy(&output.stdout);
    let page_size = text
        .lines()
        .find(|line| line.contains("page size of"))
        .and_then(|line| line.split("page size of").nth(1))
        .and_then(|rest| rest.split_whitespace().next())
        .and_then(|digits| digits.parse::<u64>().ok())
        .unwrap_or(4096);
    let mut pages = 0u64;
    for line in text.lines() {
        let Some((label, value)) = line.split_once(':') else {
            continue;
        };
        if matches!(
            label.trim(),
            "Pages free" | "Pages inactive" | "Pages speculative" | "Pages purgeable"
        ) {
            if let Ok(count) = value.trim().trim_end_matches('.').parse::<u64>() {
                pages += count;
            }
        }
    }
    if pages == 0 {
        None
    } else {
        Some(pages * page_size / (1024 * 1024))
    }
}

#[cfg(windows)]
fn available_memory_mb() -> Option<u64> {
    #[repr(C)]
    struct MemoryStatusEx {
        length: u32,
        memory_load: u32,
        total_phys: u64,
        avail_phys: u64,
        total_page_file: u64,
        avail_page_file: u64,
        total_virtual: u64,
        avail_virtual: u64,
        avail_extended_virtual: u64,
    }
    extern "system" {
        fn GlobalMemoryStatusEx(buffer: *mut MemoryStatusEx) -> i32;
    }
    let mut status = MemoryStatusEx {
        length: std::mem::size_of::<MemoryStatusEx>() as u32,
        memory_load: 0,
        total_phys: 0,
        avail_phys: 0,
        total_page_file: 0,
        avail_page_file: 0,
        total_virtual: 0,
        avail_virtual: 0,
        avail_extended_virtual: 0,
    };
    let ok = unsafe { GlobalMemoryStatusEx(&mut status) };
    if ok == 0 {
        None
    } else {
        Some(status.avail_phys / (1024 * 1024))
    }
}

#[cfg(not(any(target_os = "linux", target_os = "macos", windows)))]
fn available_memory_mb() -> Option<u64> {
    None
}

/// `WORKERS=auto` sizes the pool from available RAM: one headful Chrome plus
/// its share of whisper costs ~1.4 GB, and the box needs ~900 MB to breathe.
fn parse_workers() -> usize {
    let raw = std::env::var("WORKERS").unwrap_or_else(|_| "2".into());
    if raw.trim().eq_ignore_ascii_case("auto") {
        let available_mb = available_memory_mb().unwrap_or(2048);
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
            queue_file: PathBuf::from(env_or("QUEUE_FILE", "data/queue.json")),
            links_file: PathBuf::from(env_or("LINKS_FILE", "data/links.json")),
            resume_queue: env_flag("QUEUE_RESUME", true),
            resume_running: env_flag("QUEUE_RESUME_RUNNING", true),
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
#[derive(Clone, Debug, Serialize, Deserialize)]
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

/// A job that has been accepted but not yet picked up by a worker. Persisted
/// so a restart resumes work instead of silently dropping it.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct QueuedJob {
    pub job_id: String,
    pub key: String,
    pub alias: String,
    pub url: String,
    #[serde(default)]
    pub code: Option<String>,
    pub track_id: String,
    pub created_at: u64,
    /// `queued` or `running`. The entry stays on disk while a worker owns it,
    /// so a crash can requeue the full job instead of losing its metadata.
    #[serde(default)]
    pub stage: String,
}

impl QueuedJob {
    pub fn is_running(&self) -> bool {
        self.stage == "running"
    }

    fn mark_running(&mut self) {
        self.stage = "running".into();
    }
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

    /// Counters live in RAM; after a restart the board history is the only
    /// source of truth. Seed them from the persisted rows so the cards and the
    /// table agree instead of showing `successes: 0` next to a list of wins.
    fn from_links(links: &VecDeque<LinkEntry>) -> Self {
        let stats = Self::default();
        for entry in links {
            stats.total.fetch_add(1, Ordering::Relaxed);
            match entry.status.as_str() {
                "success" => {
                    stats.successes.fetch_add(1, Ordering::Relaxed);
                    if entry.cached {
                        stats.cache_hits.fetch_add(1, Ordering::Relaxed);
                    }
                }
                "failed" => {
                    stats.errors.fetch_add(1, Ordering::Relaxed);
                }
                _ => {}
            }
        }
        stats
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
    /// Accepted-but-not-started jobs, in submission order.
    pub pending: Mutex<VecDeque<QueuedJob>>,
    /// Serialises the atomic snapshot files so an older snapshot can never
    /// land after a newer one.
    writers: Mutex<()>,
    /// Fan-out for the status board. Slow SSE clients lag and skip instead of
    /// blocking dispatch.
    pub events: broadcast::Sender<serde_json::Value>,
    pub locks: Mutex<HashMap<String, Arc<Mutex<()>>>>,
    pub stats: Stats,
}

/// Board history is bounded: a long-running service must not grow with traffic.
const LINK_HISTORY: usize = 500;

impl Inner {
    pub fn new(cfg: Config, asr: Option<SharedAsr>) -> Arc<Self> {
        let cache = load_cache(&cfg.cache_file);
        let mut pending = if cfg.resume_queue {
            load_pending(&cfg.queue_file)
        } else {
            // Explicitly disabled: do not leave a stale queue on disk that a
            // later boot (with resume on) would replay.
            if cfg.queue_file.exists() {
                write_json_atomic(&cfg.queue_file, &Vec::<QueuedJob>::new());
            }
            VecDeque::new()
        };
        let mut links = load_links(&cfg.links_file);
        // Drop entries that could never run before reconciling, otherwise the
        // board leaves a queued ghost for a job that is not on disk anymore.
        let before = pending.len();
        pending.retain(|job| !job.job_id.is_empty() && !job.alias.is_empty());
        let mut queue_changed = pending.len() != before;
        if !cfg.resume_running {
            let before = pending.len();
            pending.retain(|job| !job.is_running());
            queue_changed |= pending.len() != before;
        }
        for job in pending.iter_mut() {
            if job.stage != "queued" {
                job.stage = "queued".into();
                queue_changed = true;
            }
        }
        if queue_changed {
            write_json_atomic(&cfg.queue_file, &pending.iter().cloned().collect::<Vec<_>>());
        }
        let dropped = reconcile(&mut links, &mut pending, cfg.resume_queue);
        if dropped {
            write_json_atomic(&cfg.queue_file, &pending.iter().cloned().collect::<Vec<_>>());
        }
        let stats = Stats::from_links(&links);
        let (events, _) = broadcast::channel(512);
        Arc::new(Self {
            started: Instant::now(),
            cfg,
            asr,
            cache: Mutex::new(cache),
            jobs: Mutex::new(HashMap::new()),
            links: Mutex::new(links),
            pending: Mutex::new(pending),
            writers: Mutex::new(()),
            events,
            locks: Mutex::new(HashMap::new()),
            stats,
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
        self.persist_links().await;
        entry.id
    }

    pub async fn link_running(&self, id: &str) {
        self.link_update(id, |entry| {
            entry.status = "running".into();
        })
        .await;
        // Persist the transition: a crash from here on must leave a `running`
        // ghost that boot reconciliation can turn into `failed`.
        self.persist_links().await;
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
        self.persist_links().await;
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

    pub async fn pending_links(&self) -> usize {
        self.links
            .lock()
            .await
            .iter()
            .filter(|entry| entry.status == "queued" || entry.status == "running")
            .count()
    }

    async fn persist_links(&self) {
        let _guard = self.writers.lock().await;
        let snapshot: Vec<LinkEntry> = self.links.lock().await.iter().cloned().collect();
        let path = self.cfg.links_file.clone();
        tokio::task::spawn_blocking(move || write_json_atomic(&path, &snapshot))
            .await
            .ok();
    }

    // --- pending queue ---------------------------------------------------

    pub async fn queue_push(&self, mut job: QueuedJob) {
        job.stage = "queued".into();
        {
            let mut pending = self.pending.lock().await;
            pending.push_back(job);
        }
        self.persist_queue().await;
    }

    /// Called by a worker the moment it takes a job. The entry stays on disk
    /// with `stage = running` so a crash can requeue it with its key and code
    /// intact instead of dropping the job.
    pub async fn queue_mark_running(&self, job_id: &str) {
        let changed = {
            let mut pending = self.pending.lock().await;
            match pending.iter_mut().find(|job| job.job_id == job_id) {
                Some(job) if !job.is_running() => {
                    job.mark_running();
                    true
                }
                _ => false,
            }
        };
        if changed {
            self.persist_queue().await;
        }
    }

    /// Terminal state reached: stop tracking the job on disk. A crash before
    /// this point resumes it; a crash after it cannot replay a finished job.
    pub async fn queue_remove(&self, job_id: &str) {
        let removed = {
            let mut pending = self.pending.lock().await;
            let before = pending.len();
            pending.retain(|job| job.job_id != job_id);
            pending.len() != before
        };
        if removed {
            self.persist_queue().await;
        }
    }

    pub async fn queue_snapshot(&self) -> Vec<QueuedJob> {
        self.pending.lock().await.iter().cloned().collect()
    }

    pub async fn queue_len(&self) -> usize {
        self.pending.lock().await.len()
    }

    async fn persist_queue(&self) {
        let _guard = self.writers.lock().await;
        let snapshot: Vec<QueuedJob> = self.pending.lock().await.iter().cloned().collect();
        let path = self.cfg.queue_file.clone();
        tokio::task::spawn_blocking(move || write_json_atomic(&path, &snapshot))
            .await
            .ok();
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

fn write_json_atomic<T: Serialize>(path: &Path, value: &T) {
    if let Some(parent) = path.parent() {
        if let Err(err) = std::fs::create_dir_all(parent) {
            warn!(target: "engine", path = %parent.display(), %err, "cannot create snapshot dir");
            return;
        }
    }
    let Ok(body) = serde_json::to_string(value) else {
        return;
    };
    let tmp = path.with_extension("tmp");
    // Write + fsync before rename: a host crash must not leave the previous
    // snapshot truncated. The rename itself is atomic on both Unix and Windows.
    let write = || -> std::io::Result<()> {
        use std::io::Write;
        let mut file = std::fs::File::create(&tmp)?;
        file.write_all(body.as_bytes())?;
        file.sync_all()
    };
    if let Err(err) = write() {
        warn!(target: "engine", path = %tmp.display(), %err, "cannot write snapshot");
        return;
    }
    if let Err(err) = std::fs::rename(&tmp, path) {
        warn!(target: "engine", path = %path.display(), %err, "cannot replace snapshot");
        return;
    }
    // Persist the directory entry too; without it a power loss can drop the
    // rename even though the file contents were flushed.
    #[cfg(unix)]
    if let Some(parent) = path.parent() {
        if let Ok(dir) = std::fs::File::open(parent) {
            let _ = dir.sync_all();
        }
    }
}

/// Parse `path`, falling back to the `.tmp` file a crashed writer left behind.
fn read_json_lenient<T: DeserializeOwned>(path: &Path) -> Option<T> {
    for candidate in [path.to_path_buf(), path.with_extension("tmp")] {
        let Ok(body) = std::fs::read_to_string(&candidate) else {
            continue;
        };
        match serde_json::from_str::<T>(&body) {
            Ok(value) => return Some(value),
            Err(err) if candidate.as_path() == path => {
                warn!(target: "engine", path = %candidate.display(), %err, "snapshot unreadable, trying tmp");
            }
            Err(_) => {}
        }
    }
    None
}

pub fn load_pending(path: &PathBuf) -> VecDeque<QueuedJob> {
    read_json_lenient::<Vec<QueuedJob>>(path)
        .map(VecDeque::from)
        .unwrap_or_default()
}

pub fn load_links(path: &PathBuf) -> VecDeque<LinkEntry> {
    let mut links: VecDeque<LinkEntry> = read_json_lenient::<Vec<LinkEntry>>(path)
        .map(VecDeque::from)
        .unwrap_or_default();
    while links.len() > LINK_HISTORY {
        links.pop_back();
    }
    links
}

/// Reconcile the board with the on-disk queue after a restart.
///
/// A job still in the queue is requeued; a row with no queue entry was
/// interrupted and becomes `failed` (or stays terminal if it already finished).
/// Queue entries whose board row is already `success`/`failed` are dropped:
/// the worker finished, then crashed before removing the disk entry.
fn reconcile(
    links: &mut VecDeque<LinkEntry>,
    pending: &mut VecDeque<QueuedJob>,
    resume: bool,
) -> bool {
    let terminal: HashSet<String> = links
        .iter()
        .filter(|entry| entry.status == "success" || entry.status == "failed")
        .map(|entry| entry.id.clone())
        .collect();
    let before = pending.len();
    pending.retain(|job| !terminal.contains(&job.track_id));
    let dropped = pending.len() != before;
    let queued: HashSet<&str> = pending.iter().map(|job| job.track_id.as_str()).collect();
    let now = unix_now();
    for entry in links.iter_mut() {
        if entry.status != "queued" && entry.status != "running" {
            continue;
        }
        if resume && queued.contains(entry.id.as_str()) {
            entry.status = "queued".into();
            entry.error = None;
        } else {
            entry.status = "failed".into();
            entry.error = Some("engine restarted before the job finished".into());
        }
        entry.updated_at = now;
    }
    if resume {
        for job in pending {
            if links.iter().any(|entry| entry.id == job.track_id) {
                continue;
            }
            links.push_front(LinkEntry {
                id: job.track_id.clone(),
                url: job.url.clone(),
                status: "queued".into(),
                destination_url: None,
                provider: None,
                cached: false,
                elapsed_ms: 0.0,
                created_at: job.created_at,
                updated_at: now,
                error: None,
            });
        }
        while links.len() > LINK_HISTORY {
            links.pop_back();
        }
    }
    dropped
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

#[cfg(test)]
mod tests {
    use super::*;

    fn test_cfg(dir: &std::path::Path, resume: bool) -> Config {
        Config {
            host: "127.0.0.1".into(),
            port: 0,
            api_key: String::new(),
            workers: 1,
            max_queue: 8,
            max_batch: 8,
            batch_concurrency: 1,
            job_timeout: Duration::from_secs(30),
            cache_ttl: Duration::from_secs(60),
            cache_file: dir.join("cache.json"),
            cache_enabled: false,
            queue_file: dir.join("queue.json"),
            links_file: dir.join("links.json"),
            resume_queue: resume,
            resume_running: true,
            chrome_bin: "google-chrome".into(),
            headless: true,
            profile_dir: dir.join("profile"),
            model_path: dir.join("model.bin"),
            model_url: String::new(),
            asr_threads: 1,
        }
    }

    fn scratch(tag: &str) -> PathBuf {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0);
        let dir = std::env::temp_dir().join(format!(
            "l4m-state-{tag}-{}-{nanos}",
            std::process::id()
        ));
        std::fs::create_dir_all(&dir).expect("scratch dir");
        dir
    }

    fn sample_job(track_id: &str) -> QueuedJob {
        QueuedJob {
            job_id: format!("job-{track_id}"),
            key: "link4m:abc".into(),
            alias: "abc".into(),
            url: "https://link4m.net/go/abc".into(),
            code: None,
            track_id: track_id.into(),
            created_at: unix_now(),
            stage: "queued".into(),
        }
    }

    #[tokio::test]
    async fn corrupt_snapshot_recovers_from_tmp() {
        let dir = scratch("tmp-recover");
        let cfg = test_cfg(&dir, true);
        std::fs::write(&cfg.queue_file, "{not json").expect("write corrupt queue");
        let valid = serde_json::to_string(&vec![sample_job("track-tmp")]).expect("serialize job");
        std::fs::write(cfg.queue_file.with_extension("tmp"), valid).expect("write tmp");
        let inner = Inner::new(cfg, None);
        assert_eq!(inner.queue_len().await, 1);
    }

    #[tokio::test]
    async fn pending_queue_survives_restart() {
        let dir = scratch("queue");
        let cfg = test_cfg(&dir, true);
        let first = Inner::new(cfg.clone(), None);
        let track = first.link_begin("https://link4m.net/go/abc", Some("link4m")).await;
        first.queue_push(sample_job(&track)).await;

        let second = Inner::new(cfg, None);
        assert_eq!(second.queue_len().await, 1);
        let links = second.links_snapshot().await;
        let row = links.iter().find(|entry| entry.id == track).expect("row");
        assert_eq!(row.status, "queued");
        assert!(row.error.is_none());
    }

    #[tokio::test]
    async fn interrupted_job_is_requeued_after_restart() {
        let dir = scratch("interrupted");
        let cfg = test_cfg(&dir, true);
        let first = Inner::new(cfg.clone(), None);
        let track = first.link_begin("https://link4m.net/go/abc", Some("link4m")).await;
        first.queue_push(sample_job(&track)).await;
        first.queue_mark_running(&format!("job-{track}")).await;
        first.link_running(&track).await;
        // The running transition must be on disk, otherwise a crash leaves the
        // previous `queued` snapshot and the reconciler cannot tell the truth.
        let on_disk: Vec<LinkEntry> =
            serde_json::from_str(&std::fs::read_to_string(&cfg.links_file).expect("links file"))
                .expect("links json");
        assert_eq!(on_disk[0].status, "running");
        let queue: Vec<QueuedJob> =
            serde_json::from_str(&std::fs::read_to_string(&cfg.queue_file).expect("queue file"))
                .expect("queue json");
        assert_eq!(queue[0].stage, "running");

        let second = Inner::new(cfg, None);
        assert_eq!(second.queue_len().await, 1);
        let links = second.links_snapshot().await;
        let row = links.iter().find(|entry| entry.id == track).expect("row");
        assert_eq!(row.status, "queued");
        assert!(row.error.is_none());
    }

    #[tokio::test]
    async fn resume_running_disabled_marks_interrupted_rows_failed() {
        let dir = scratch("no-running");
        let cfg = test_cfg(&dir, true);
        let first = Inner::new(cfg.clone(), None);
        let track = first.link_begin("https://link4m.net/go/abc", Some("link4m")).await;
        first.queue_push(sample_job(&track)).await;
        first.queue_mark_running(&format!("job-{track}")).await;
        first.link_running(&track).await;

        let mut no_running = test_cfg(&dir, true);
        no_running.resume_running = false;
        let second = Inner::new(no_running, None);
        assert_eq!(second.queue_len().await, 0);
        let links = second.links_snapshot().await;
        let row = links.iter().find(|entry| entry.id == track).expect("row");
        assert_eq!(row.status, "failed");
    }

    #[tokio::test]
    async fn worker_removal_clears_the_disk_entry() {
        let dir = scratch("remove");
        let cfg = test_cfg(&dir, true);
        let first = Inner::new(cfg.clone(), None);
        let track = first.link_begin("https://link4m.net/go/abc", Some("link4m")).await;
        let job = sample_job(&track);
        let job_id = job.job_id.clone();
        first.queue_push(job).await;
        first.queue_remove(&job_id).await;

        let second = Inner::new(cfg, None);
        assert_eq!(second.queue_len().await, 0);
    }

    #[tokio::test]
    async fn finished_row_is_not_replayed_from_a_stale_queue_entry() {
        let dir = scratch("finished");
        let cfg = test_cfg(&dir, true);
        let first = Inner::new(cfg.clone(), None);
        let track = first.link_begin("https://link4m.net/go/abc", Some("link4m")).await;
        first.queue_push(sample_job(&track)).await;
        first.queue_mark_running(&format!("job-{track}")).await;
        first
            .link_finish(
                &track,
                "success",
                Some("https://example.com/done".into()),
                None,
                12.0,
                false,
            )
            .await;

        let second = Inner::new(cfg, None);
        assert_eq!(second.queue_len().await, 0);
        let rows = second.links_snapshot().await;
        assert_eq!(rows[0].status, "success");
    }

    #[tokio::test]
    async fn resume_disabled_marks_rows_failed() {
        let dir = scratch("no-resume");
        let cfg = test_cfg(&dir, true);
        let first = Inner::new(cfg.clone(), None);
        let track = first.link_begin("https://link4m.net/go/abc", Some("link4m")).await;
        first.queue_push(sample_job(&track)).await;

        let mut no_resume = test_cfg(&dir, false);
        no_resume.queue_file = cfg.queue_file.clone();
        no_resume.links_file = cfg.links_file.clone();
        let second = Inner::new(no_resume, None);
        assert_eq!(second.queue_len().await, 0);
        let links = second.links_snapshot().await;
        let row = links.iter().find(|entry| entry.id == track).expect("row");
        assert_eq!(row.status, "failed");
    }
}
