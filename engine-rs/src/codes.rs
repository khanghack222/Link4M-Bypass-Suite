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
use std::path::PathBuf;
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

fn save(map: &HashMap<String, Entry>) {
    let path = path();
    if let Some(dir) = path.parent() {
        let _ = std::fs::create_dir_all(dir);
    }
    if let Ok(raw) = serde_json::to_string_pretty(map) {
        let _ = std::fs::write(path, raw);
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
    let mut guard = store().lock().expect("code cache");
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
    let mut guard = store().lock().expect("code cache");
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
        std::env::set_var("L4M_CODE_FILE", "/tmp/l4m-codes-test.json");
        std::env::set_var("L4M_CODE_TTL", "900");
        let _ = std::fs::remove_file(path());
        assert!(get("camp-x").is_none());
        put("camp-x", "AbC123");
        assert_eq!(get("camp-x").as_deref(), Some("AbC123"));
        invalidate("camp-x");
        assert!(get("camp-x").is_none());
    }
}
