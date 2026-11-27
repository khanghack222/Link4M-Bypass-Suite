//! Sponsor-code cache.
//!
//! The campaign page validates the sponsor's promo code server-side, and the
//! same code is valid for every visitor of the same campaign while the
//! advertiser keeps it published. Harvesting it costs a full widget quest
//! (~2 min), so a code that already produced a destination is reused for the
//! next aliases on that campaign until the TTL expires.
//!
//! Only proven codes are stored: `put` is called after a destination was
//! returned, and `invalidate` drops the entry the moment link4m rejects it.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::sync::Mutex as AsyncMutex;

#[derive(Clone, Debug, Serialize, Deserialize)]
struct Entry {
    code: String,
    ts: u64,
}

fn ttl() -> u64 {
    std::env::var("L4M_CODE_TTL")
        .ok()
        .and_then(|v| v.trim().parse::<u64>().ok())
        .unwrap_or(900)
}

fn path() -> PathBuf {
    std::env::var("L4M_CODE_FILE")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("data/codes.json"))
}

fn store() -> &'static Mutex<HashMap<String, Entry>> {
    static STORE: OnceLock<Mutex<HashMap<String, Entry>>> = OnceLock::new();
    STORE.get_or_init(|| Mutex::new(load()))
}

fn load() -> HashMap<String, Entry> {
    std::fs::read_to_string(path())
        .ok()
        .and_then(|raw| serde_json::from_str(&raw).ok())
        .unwrap_or_default()
}

fn temp_sibling(path: &Path) -> PathBuf {
    static SEQ: AtomicU64 = AtomicU64::new(0);
    let name = path
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("codes.json");
    let seq = SEQ.fetch_add(1, Ordering::Relaxed);
    path.with_file_name(format!(".{name}.{}.{}.tmp", std::process::id(), seq))
}

fn atomic_write(path: &Path, bytes: &[u8]) {
    if let Some(dir) = path.parent() {
        if !dir.as_os_str().is_empty() {
            let _ = std::fs::create_dir_all(dir);
        }
    }
    let tmp = temp_sibling(path);
    if std::fs::write(&tmp, bytes).is_err() {
        return;
    }
    if std::fs::rename(&tmp, path).is_ok() {
        return;
    }
    let _ = std::fs::remove_file(path);
    if std::fs::rename(&tmp, path).is_err() {
        let _ = std::fs::remove_file(&tmp);
    }
}

fn save(map: &HashMap<String, Entry>) {
    let p = path();
    if let Ok(raw) = serde_json::to_string_pretty(map) {
        atomic_write(&p, raw.as_bytes());
    }
}

fn now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

/// A code that produced a destination and is still inside the TTL window.
pub fn get(campaign: &str) -> Option<String> {
    if campaign.is_empty() {
        return None;
    }
    let guard = store().lock().ok()?;
    let entry = guard.get(campaign)?;
    if now().saturating_sub(entry.ts) > ttl() {
        return None;
    }
    Some(entry.code.clone())
}

pub fn put(campaign: &str, code: &str) {
    if campaign.is_empty() || code.trim().is_empty() {
        return;
    }
    let mut guard = store().lock().unwrap_or_else(|e| e.into_inner());
    guard.insert(
        campaign.to_string(),
        Entry { code: code.trim().to_string(), ts: now() },
    );
    save(&guard);
}

pub fn invalidate(campaign: &str) {
    if campaign.is_empty() {
        return;
    }
    let mut guard = store().lock().unwrap_or_else(|e| e.into_inner());
    if guard.remove(campaign).is_some() {
        save(&guard);
    }
}

/// One async mutex per campaign, so concurrent jobs for a cold campaign run a
/// single quest and the rest wait for its result instead of hammering the
/// sponsor site.
pub async fn lock_for(campaign: &str) -> Arc<AsyncMutex<()>> {
    static LOCKS: OnceLock<AsyncMutex<HashMap<String, Arc<AsyncMutex<()>>>>> = OnceLock::new();
    let locks = LOCKS.get_or_init(|| AsyncMutex::new(HashMap::new()));
    let mut guard = locks.lock().await;
    guard
        .entry(campaign.to_string())
        .or_insert_with(|| Arc::new(AsyncMutex::new(())))
        .clone()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trip_and_expiry() {
        let test_path = std::env::temp_dir().join(format!("l4m-codes-test-{}.json", std::process::id()));
        std::env::set_var("L4M_CODE_FILE", test_path.to_str().unwrap());
        std::env::set_var("L4M_CODE_TTL", "900");
        let _ = std::fs::remove_file(path());
        assert!(get("camp-x").is_none());
        put("camp-x", "AbC123");
        assert_eq!(get("camp-x").as_deref(), Some("AbC123"));
        invalidate("camp-x");
        assert!(get("camp-x").is_none());
        let _ = std::fs::remove_file(path());
    }

    #[test]
    fn atomic_save_and_load_roundtrip() {
        let test_path = std::env::temp_dir().join(format!("l4m-codes-atomic-{}.json", std::process::id()));
        let mut map = HashMap::new();
        map.insert(
            "camp-atomic".to_string(),
            Entry {
                code: "SECRET_999".to_string(),
                ts: now(),
            },
        );
        let raw = serde_json::to_string_pretty(&map).unwrap();
        atomic_write(&test_path, raw.as_bytes());

        let read_back: HashMap<String, Entry> = std::fs::read_to_string(&test_path)
            .ok()
            .and_then(|s| serde_json::from_str(&s).ok())
            .unwrap();
        assert_eq!(read_back.get("camp-atomic").unwrap().code, "SECRET_999");
        let _ = std::fs::remove_file(&test_path);
    }
}
