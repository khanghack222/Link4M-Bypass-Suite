//! Campaign instruction parsing.
//!
//! Every Link4M campaign ships a short instruction block. Direct campaigns
//! print the sponsor domain as text; search campaigns hide the keyword and the
//! sponsor inside bitmap strips, so those are OCR'd through the local
//! RapidOCR sidecar. The OCR text also carries noise (advertiser brand names,
//! unrelated links), so every candidate domain is probed for the what-on
//! widget before it is trusted. Results are cached per campaign id — the same
//! campaign is served to many aliases and the OCR only has to run once.

use crate::cdp::Cdp;
use crate::proxy::{self, Proxy};
use base64::Engine as _;
use futures_util::stream::{FuturesUnordered, StreamExt};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};
use tracing::{debug, info, warn};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Campaign {
    pub kind: String,
    pub sponsor: String,
    /// Widget key found on the sponsor page, when the probe reached it.
    #[serde(default)]
    pub key: String,
    #[serde(default)]
    pub keyword: String,
    /// Which referrer the widget accepts: `google`, `none`, or `auto`.
    #[serde(default)]
    pub refs: String,
}

const UA_MOBILE: &str = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 \
(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36";

const INSTR_JS: &str = r#"(() => {
  const h = [...document.querySelectorAll('h4')].find(e => /HƯỚNG DẪN LẤY MÃ/i.test(e.innerText || ''));
  const root = h ? h.parentElement : document.body;
  const imgs = root ? [...root.querySelectorAll('img')]
    .map(i => i.src)
    .filter(s => s && (s.startsWith('data:image') || /img\.link4m\.net\/uploads\/advertiser/.test(s)))
    .slice(0, 5) : [];
  const camp = document.querySelector('input[name=campaign_id]');
  return {
    text: root ? (root.innerText || '') : '',
    imgs,
    campaign: camp ? camp.value : ''
  };
})()"#;

const TLDS: &[&str] = &[
    "com", "net", "org", "vn", "life", "top", "site", "vip", "bet", "win", "app", "xyz", "info",
    "io", "co", "online", "club", "fun", "store", "shop", "live", "me", "tv", "cc", "pro", "asia",
    "biz", "link", "cloud", "one", "website", "casino", "game", "games", "dev", "page", "space",
];

const EXCLUDED: &[&str] = &[
    "google.",
    "facebook.",
    "youtube.",
    "link4m.",
    "gstatic.",
    "doubleclick.",
    "img.link4m",
    "googletagmanager",
    "google-analytics",
    "cdn.jsdelivr",
];

fn cache() -> &'static Mutex<Option<HashMap<String, Campaign>>> {
    static CACHE: OnceLock<Mutex<Option<HashMap<String, Campaign>>>> = OnceLock::new();
    CACHE.get_or_init(|| Mutex::new(None))
}

fn cache_path() -> PathBuf {
    std::env::var("L4M_CAMPAIGN_CACHE")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("data/campaigns.json"))
}

fn load_cache() -> HashMap<String, Campaign> {
    std::fs::read_to_string(cache_path())
        .ok()
        .and_then(|raw| serde_json::from_str::<HashMap<String, Campaign>>(&raw).ok())
        .unwrap_or_default()
}

fn store_cache(map: &HashMap<String, Campaign>) {
    if let Ok(raw) = serde_json::to_string_pretty(map) {
        atomic_write(&cache_path(), raw.as_bytes());
    }
}

/// Write through a sibling temp file and rename so a reader never observes a
/// half-written cache. `rename` cannot replace an existing file on Windows, so
/// the fallback drops the old file first.
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

fn temp_sibling(path: &Path) -> PathBuf {
    static SEQ: AtomicU64 = AtomicU64::new(0);
    let name = path
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("cache.json");
    let seq = SEQ.fetch_add(1, Ordering::Relaxed);
    path.with_file_name(format!(".{name}.{}.{}.tmp", std::process::id(), seq))
}

const OCR_CACHE_LIMIT: usize = 200;

/// One OCR result keyed by campaign id + a hash of the image source list. The
/// page re-renders the same strips for every alias, so the same key recurs.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
struct OcrCacheEntry {
    campaign: String,
    hash: u64,
    lines: Vec<String>,
}

#[derive(Debug, Default, Serialize, Deserialize)]
struct OcrCacheFile {
    #[serde(default)]
    entries: Vec<OcrCacheEntry>,
}

fn ocr_cache_slot() -> &'static Mutex<Option<Vec<OcrCacheEntry>>> {
    static CACHE: OnceLock<Mutex<Option<Vec<OcrCacheEntry>>>> = OnceLock::new();
    CACHE.get_or_init(|| Mutex::new(None))
}

/// `data/ocr-cache.json` by default. `L4M_OCR_CACHE=0` disables the cache;
/// any other non-boolean value is treated as an explicit path.
fn ocr_cache_path() -> Option<PathBuf> {
    match std::env::var("L4M_OCR_CACHE") {
        Ok(raw) => {
            let value = raw.trim();
            if value == "0"
                || value.eq_ignore_ascii_case("false")
                || value.eq_ignore_ascii_case("off")
            {
                None
            } else if value.is_empty()
                || value == "1"
                || value.eq_ignore_ascii_case("true")
                || value.eq_ignore_ascii_case("on")
            {
                Some(PathBuf::from("data/ocr-cache.json"))
            } else {
                Some(PathBuf::from(value))
            }
        }
        Err(_) => Some(PathBuf::from("data/ocr-cache.json")),
    }
}

fn ocr_cache_load_path(path: &Path) -> Vec<OcrCacheEntry> {
    let Ok(raw) = std::fs::read_to_string(path) else {
        return Vec::new();
    };
    let entries = match serde_json::from_str::<OcrCacheFile>(&raw) {
        Ok(file) => file.entries,
        // Tolerate a bare array left by an older/hand-written build.
        Err(_) => serde_json::from_str::<Vec<OcrCacheEntry>>(&raw).unwrap_or_default(),
    };
    entries
        .into_iter()
        .filter(|entry| !entry.campaign.is_empty() && !entry.lines.is_empty())
        .collect()
}

fn ocr_cache_store_path(path: &Path, entries: &[OcrCacheEntry]) {
    let file = OcrCacheFile {
        entries: entries.to_vec(),
    };
    if let Ok(raw) = serde_json::to_string_pretty(&file) {
        atomic_write(path, raw.as_bytes());
    }
}

fn ocr_cache_lookup(entries: &[OcrCacheEntry], campaign: &str, hash: u64) -> Option<Vec<String>> {
    entries
        .iter()
        .find(|entry| entry.campaign == campaign && entry.hash == hash)
        .map(|entry| entry.lines.clone())
        .filter(|lines| !lines.is_empty())
}

/// Append one result, newest last, and evict the oldest insertions once the
/// file grows past the limit. Re-inserting an existing key refreshes it.
fn ocr_cache_remember(
    entries: &mut Vec<OcrCacheEntry>,
    campaign: &str,
    hash: u64,
    lines: &[String],
) {
    if campaign.is_empty() || lines.is_empty() {
        return;
    }
    if let Some(pos) = entries
        .iter()
        .position(|entry| entry.campaign == campaign && entry.hash == hash)
    {
        entries.remove(pos);
    }
    entries.push(OcrCacheEntry {
        campaign: campaign.to_string(),
        hash,
        lines: lines.to_vec(),
    });
    while entries.len() > OCR_CACHE_LIMIT {
        entries.remove(0);
    }
}

fn ocr_cache_get(campaign: &str, hash: u64) -> Option<Vec<String>> {
    if campaign.is_empty() {
        return None;
    }
    let path = ocr_cache_path()?;
    let mut guard = ocr_cache_slot().lock().ok()?;
    if guard.is_none() {
        *guard = Some(ocr_cache_load_path(&path));
    }
    guard
        .as_ref()
        .and_then(|entries| ocr_cache_lookup(entries, campaign, hash))
}

fn ocr_cache_put(campaign: &str, hash: u64, lines: &[String]) {
    if campaign.is_empty() || lines.is_empty() {
        return;
    }
    let Some(path) = ocr_cache_path() else {
        return;
    };
    let mut guard = ocr_cache_slot().lock().unwrap_or_else(|e| e.into_inner());
    if guard.is_none() {
        *guard = Some(ocr_cache_load_path(&path));
    }
    if let Some(entries) = guard.as_mut() {
        ocr_cache_remember(entries, campaign, hash, lines);
        ocr_cache_store_path(&path, entries);
    }
}

/// Stable FNV-1a over every image source in page order. `DefaultHasher` is
/// explicitly allowed to change between releases, which would silently miss
/// the cache after an engine upgrade; FNV does not.
fn hash_images(images: &[String]) -> u64 {
    const OFFSET: u64 = 0xcbf2_9ce4_8422_2325;
    const PRIME: u64 = 0x0000_0100_0000_01b3;
    let mut hash = OFFSET;
    for source in images {
        // Signed image URLs change their query string on every page load, so
        // hashing the whole URL made the OCR cache miss on every reload. The
        // path is stable for a given instruction set.
        let stable = source
            .split(['?', '#'])
            .next()
            .unwrap_or(source);
        for byte in stable.as_bytes() {
            hash ^= u64::from(*byte);
            hash = hash.wrapping_mul(PRIME);
        }
        hash ^= 0xff;
        hash = hash.wrapping_mul(PRIME);
    }
    hash
}

fn cache_get(campaign_id: &str) -> Option<Campaign> {
    if campaign_id.is_empty() {
        return None;
    }
    let mut guard = cache().lock().ok()?;
    if guard.is_none() {
        *guard = Some(load_cache());
    }
    guard.as_ref().and_then(|m| m.get(campaign_id).cloned())
}

fn cache_put(campaign_id: &str, value: &Campaign) {
    if campaign_id.is_empty() {
        return;
    }
    let mut guard = cache().lock().unwrap_or_else(|e| e.into_inner());
    if guard.is_none() {
        *guard = Some(load_cache());
    }
    if let Some(map) = guard.as_mut() {
        map.insert(campaign_id.to_string(), value.clone());
        store_cache(map);
    }
}

/// Drop a campaign whose cached sponsor no longer serves a widget. Without
/// this a dead sponsor stays cached in `data/campaigns.json` forever and every
/// alias burns a full harvest attempt on it.
pub fn forget(campaign_id: &str) {
    if campaign_id.is_empty() {
        return;
    }
    let mut guard = cache().lock().unwrap_or_else(|e| e.into_inner());
    if guard.is_none() {
        *guard = Some(load_cache());
    }
    if let Some(map) = guard.as_mut() {
        if map.remove(campaign_id).is_some() {
            store_cache(map);
            info!(
                target: "engine",
                campaign = %campaign_id,
                "campaign cache dropped after sponsor failure"
            );
        }
    }
}

fn clean_domains(blob: &str) -> Vec<String> {
    let mut out = Vec::new();
    let mut rest = blob;
    // Cheap scan for dotted tokens; avoids pulling a regex dependency.
    while let Some(pos) = rest.find('.') {
        let mut start = pos;
        while start > 0 {
            let b = rest.as_bytes()[start - 1];
            if b.is_ascii_alphanumeric() || b == b'-' || b == b'.' {
                start -= 1;
            } else {
                break;
            }
        }
        let mut end = pos + 1;
        while end < rest.len() {
            let b = rest.as_bytes()[end];
            if b.is_ascii_alphanumeric() || b == b'-' || b == b'.' {
                end += 1;
            } else {
                break;
            }
        }
        let token = rest[start..end].trim_matches('.').to_lowercase();
        rest = &rest[end..];
        if !token.contains('.') || token.len() < 5 || token.len() > 60 {
            continue;
        }
        if EXCLUDED.iter().any(|bad| token.contains(bad)) {
            continue;
        }
        let tld = token.rsplit('.').next().unwrap_or("");
        if !TLDS.contains(&tld) {
            continue;
        }
        if !out.contains(&token) {
            out.push(token);
        }
    }
    out
}

fn parse_keyword(blob: &str) -> String {
    let lower = blob.to_lowercase();
    for needle in [
        "từ khoá",
        "từ khoa",
        "tu khoa",
        "tim tu khoa",
        "khoá",
        "khoa",
    ] {
        let mut from = 0;
        while let Some(pos) = lower[from..].find(needle) {
            let at = from + pos;
            let tail = &blob[at + needle.len()..];
            let word: String = tail
                .trim_start_matches(|c: char| c == ':' || c == '-' || c.is_whitespace())
                .chars()
                .take_while(|c| c.is_ascii_alphanumeric())
                .collect();
            if word.len() >= 3 && !matches!(word.to_lowercase().as_str(), "la" | "cua" | "va") {
                return word;
            }
            from = at + needle.len();
        }
    }
    String::new()
}

pub fn ocr_binary() -> PathBuf {
    if let Ok(path) = std::env::var("L4M_PYTHON") {
        let trimmed = path.trim();
        if !trimmed.is_empty() {
            return PathBuf::from(trimmed);
        }
    }
    let mut candidates: Vec<PathBuf> = vec![
        PathBuf::from(".venv/bin/python"),
        PathBuf::from("../.venv/bin/python"),
        PathBuf::from("engine-rs/.venv/bin/python"),
    ];
    #[cfg(windows)]
    {
        candidates.push(PathBuf::from(".venv\\Scripts\\python.exe"));
        candidates.push(PathBuf::from("..\\.venv\\Scripts\\python.exe"));
        candidates.push(PathBuf::from("engine-rs\\.venv\\Scripts\\python.exe"));
        if let Ok(local_app_data) = std::env::var("LOCALAPPDATA") {
            for ver in ["Python311", "Python312", "Python313", "Python310"] {
                candidates.push(
                    PathBuf::from(&local_app_data)
                        .join("Programs")
                        .join("Python")
                        .join(ver)
                        .join("python.exe"),
                );
            }
        }
    }
    for path in &candidates {
        if path.exists() && runnable(path, &["-c", "import rapidocr_onnxruntime"]) {
            return path.clone();
        }
    }
    for name in ["python3", "python"] {
        let path = PathBuf::from(name);
        if runnable(&path, &["-c", "import rapidocr_onnxruntime"]) {
            return path;
        }
    }
    for path in candidates {
        if path.exists() {
            return path;
        }
    }
    #[cfg(windows)]
    {
        PathBuf::from("python")
    }
    #[cfg(not(windows))]
    {
        PathBuf::from("python3")
    }
}

fn ocr_script() -> PathBuf {
    if let Ok(path) = std::env::var("L4M_OCR") {
        let trimmed = path.trim();
        if !trimmed.is_empty() {
            return PathBuf::from(trimmed);
        }
    }
    for candidate in ["tools/ocr.py", "engine-rs/tools/ocr.py", "../tools/ocr.py"] {
        let path = PathBuf::from(candidate);
        if path.exists() {
            return path;
        }
    }
    if let Ok(exe) = std::env::current_exe() {
        let mut dir = exe.parent();
        for _ in 0..4 {
            let Some(current) = dir else { break };
            for rel in ["tools/ocr.py", "engine-rs/tools/ocr.py"] {
                let candidate = current.join(rel);
                if candidate.exists() {
                    return candidate;
                }
            }
            dir = current.parent();
        }
    }
    PathBuf::from("tools/ocr.py")
}

/// Which OCR reader is available right now. `--check` prints this so a missing
/// sidecar and a missing tesseract are visible before a campaign needs them.
pub fn ocr_status() -> &'static str {
    if ocr_url().is_some() {
        return "remote";
    }
    let python = ocr_binary();
    let script = ocr_script();
    if script.exists() && runnable(&python, &["-c", "import rapidocr_onnxruntime"]) {
        return "rapidocr";
    }
    let tesseract = std::env::var("L4M_TESSERACT").unwrap_or_else(|_| "tesseract".into());
    if runnable(Path::new(&tesseract), &["--version"]) {
        "tesseract"
    } else {
        "none"
    }
}

/// OCR_URL wins over the local sidecar when it parses as an absolute HTTP(S)
/// URL. Anything else falls through to the old detection path.
fn ocr_url() -> Option<String> {
    let raw = std::env::var("OCR_URL").ok()?;
    let url = raw.trim();
    if url.is_empty() {
        return None;
    }
    let parsed = url::Url::parse(url).ok()?;
    if parsed.scheme() != "http" && parsed.scheme() != "https" {
        return None;
    }
    parsed.host_str()?;
    Some(url.to_string())
}

fn ocr_language() -> Option<String> {
    for key in ["L4M_TESSERACT_LANG", "OCR_LANGUAGE"] {
        if let Ok(raw) = std::env::var(key) {
            let value = raw.trim();
            if !value.is_empty() {
                return Some(value.to_string());
            }
        }
    }
    None
}

fn ocr_timeout() -> Duration {
    let secs = std::env::var("OCR_TIMEOUT")
        .ok()
        .and_then(|raw| raw.trim().parse::<u64>().ok())
        .unwrap_or(30)
        .clamp(1, 600);
    Duration::from_secs(secs)
}

fn runnable(binary: &Path, args: &[&str]) -> bool {
    std::process::Command::new(binary)
        .args(args)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .map(|status| status.success())
        .unwrap_or(false)
}

struct ImagePayload {
    name: String,
    data: Vec<u8>,
}

fn decode_image_bytes(src: &str, proxy: Option<&Proxy>) -> Option<Vec<u8>> {
    if let Some(rest) = src.strip_prefix("data:image/") {
        let payload = rest.split_once(',')?.1;
        return base64::engine::general_purpose::STANDARD
            .decode(payload.trim())
            .ok()
            .filter(|raw| !raw.is_empty());
    }
    if src.starts_with("http://") || src.starts_with("https://") {
        let fetch_with = |p: Option<&Proxy>, secs: u64| -> Option<Vec<u8>> {
            let body = proxy::agent_for(p, Duration::from_secs(secs), "Mozilla/5.0")
                .get(src)
                .call()
                .ok()?
                .into_reader();
            let mut buf = Vec::new();
            body.take(8 * 1024 * 1024).read_to_end(&mut buf).ok()?;
            (!buf.is_empty()).then_some(buf)
        };
        if let Some(buf) = fetch_with(proxy, 6) {
            return Some(buf);
        }
        if proxy.is_some() {
            return fetch_with(None, 8);
        }
    }
    None
}

fn image_payloads(images: &[String], proxy: Option<&Proxy>) -> Vec<ImagePayload> {
    // Instruction strips come from the same host; fetching them one by one
    // serialises four TLS handshakes behind the OCR that needs them. Four
    // workers is enough for the usual 2–4 strips and keeps memory flat.
    if images.len() <= 1 {
        return images
            .iter()
            .enumerate()
            .filter_map(|(index, src)| {
                decode_image_bytes(src, proxy).map(|data| ImagePayload {
                    name: format!("instr-{index}.png"),
                    data,
                })
            })
            .collect();
    }
    let workers = images.len().min(4);
    let next = AtomicUsize::new(0);
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::scope(|scope| {
        for _ in 0..workers {
            let tx = tx.clone();
            let next = &next;
            scope.spawn(move || loop {
                let index = next.fetch_add(1, Ordering::Relaxed);
                let Some(src) = images.get(index) else {
                    break;
                };
                let payload = decode_image_bytes(src, proxy).map(|data| ImagePayload {
                    name: format!("instr-{index}.png"),
                    data,
                });
                if tx.send((index, payload)).is_err() {
                    break;
                }
            });
        }
    });
    drop(tx);
    let mut collected: Vec<(usize, ImagePayload)> = rx
        .into_iter()
        .filter_map(|(index, payload)| payload.map(|payload| (index, payload)))
        .collect();
    collected.sort_by_key(|(index, _)| *index);
    collected.into_iter().map(|(_, payload)| payload).collect()
}

fn spill_payloads(payloads: &[ImagePayload]) -> Vec<PathBuf> {
    let dir = std::env::temp_dir().join("l4m-instr");
    let _ = std::fs::create_dir_all(&dir);
    let mut files = Vec::new();
    for payload in payloads {
        let path = dir.join(&payload.name);
        if std::fs::write(&path, &payload.data).is_ok() {
            files.push(path);
        }
    }
    files
}

fn multipart_boundary() -> String {
    static SEQ: AtomicU64 = AtomicU64::new(0);
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|delta| delta.as_nanos())
        .unwrap_or(0);
    format!(
        "----l4mocr{:x}{:x}{:x}",
        std::process::id(),
        nanos,
        SEQ.fetch_add(1, Ordering::Relaxed)
    )
}

fn multipart_body(payloads: &[ImagePayload], language: Option<&str>, boundary: &str) -> Vec<u8> {
    let mut body = Vec::new();
    for payload in payloads {
        body.extend_from_slice(
            format!(
                "--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; \
                 filename=\"{}\"\r\nContent-Type: image/png\r\n\r\n",
                payload.name
            )
            .as_bytes(),
        );
        body.extend_from_slice(&payload.data);
        body.extend_from_slice(b"\r\n");
    }
    if let Some(language) = language {
        body.extend_from_slice(
            format!(
                "--{boundary}\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\n\
                 {language}\r\n"
            )
            .as_bytes(),
        );
    }
    body.extend_from_slice(format!("--{boundary}--\r\n").as_bytes());
    body
}

/// One keep-alive agent for every remote OCR call: the engine OCRs a strip per
/// campaign, and reusing the TLS connection removes a handshake from each.
fn remote_ocr_agent() -> &'static ureq::Agent {
    static AGENT: OnceLock<ureq::Agent> = OnceLock::new();
    AGENT.get_or_init(|| proxy::agent_for(None, ocr_timeout(), UA_MOBILE))
}

fn remote_ocr(url: &str, payloads: &[ImagePayload], language: Option<&str>) -> Option<Vec<String>> {
    if payloads.is_empty() {
        return None;
    }
    let boundary = multipart_boundary();
    let body = multipart_body(payloads, language, &boundary);
    let response = remote_ocr_agent()
        .post(url)
        .set(
            "Content-Type",
            &format!("multipart/form-data; boundary={boundary}"),
        )
        .send_bytes(&body)
        .ok()?;
    let mut raw = String::new();
    response
        .into_reader()
        .take(4 * 1024 * 1024)
        .read_to_string(&mut raw)
        .ok()?;
    let lines = parse_remote_lines(&raw);
    if lines.is_empty() {
        None
    } else {
        Some(lines)
    }
}

/// Accept the three shapes OCR servers actually return: `[[..],..]` from the
/// local sidecar, `{"lines":[..]}` from JSON wrappers, and plain text.
fn parse_remote_lines(raw: &str) -> Vec<String> {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return Vec::new();
    }
    let mut lines = Vec::new();
    if let Ok(value) = serde_json::from_str::<Value>(trimmed) {
        match value {
            Value::Array(blocks) => {
                for block in blocks {
                    match block {
                        Value::Array(items) => push_json_lines(&items, &mut lines),
                        Value::String(line) => push_json_line(&line, &mut lines),
                        _ => {}
                    }
                }
            }
            Value::Object(map) => {
                if let Some(Value::Array(items)) = map.get("lines") {
                    for item in items {
                        match item {
                            Value::String(line) => push_json_line(line, &mut lines),
                            Value::Array(nested) => push_json_lines(nested, &mut lines),
                            _ => {}
                        }
                    }
                }
            }
            _ => {}
        }
        if !lines.is_empty() {
            return lines;
        }
    }
    for line in trimmed.lines() {
        let line = line.trim();
        if !line.is_empty() {
            lines.push(line.to_string());
        }
    }
    lines
}

fn push_json_line(line: &str, out: &mut Vec<String>) {
    let trimmed = line.trim();
    if !trimmed.is_empty() {
        out.push(trimmed.to_string());
    }
}

fn push_json_lines(items: &[Value], out: &mut Vec<String>) {
    for item in items {
        if let Some(line) = item.as_str() {
            push_json_line(line, out);
        }
    }
}

/// Long-lived RapidOCR process. Loading the ONNX models costs more than the
/// recognition itself, so a fresh interpreter per campaign is pure latency.
/// Requests are one JSON line in, one JSON line out; the reader thread owns
/// stdout and forwards each response over a channel so the caller can apply a
/// timeout without desynchronising the stream.
struct OcrSidecar {
    child: std::process::Child,
    stdin: std::process::ChildStdin,
    rx: std::sync::mpsc::Receiver<String>,
}

static OCR_SIDECAR: Mutex<Option<OcrSidecar>> = Mutex::new(None);

fn sidecar_enabled() -> bool {
    !matches!(std::env::var("L4M_OCR_SERVE"), Ok(value) if value.trim() == "0")
}

fn sidecar_timeout() -> Duration {
    let secs = std::env::var("OCR_SERVE_TIMEOUT")
        .ok()
        .and_then(|raw| raw.trim().parse::<u64>().ok())
        .unwrap_or(90)
        .clamp(10, 300);
    Duration::from_secs(secs)
}

fn spawn_sidecar() -> Option<OcrSidecar> {
    let mut child = std::process::Command::new(ocr_binary())
        .arg(ocr_script())
        .arg("--serve")
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null())
        .spawn()
        .ok()?;
    let stdin = child.stdin.take()?;
    let stdout = child.stdout.take()?;
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::spawn(move || {
        use std::io::BufRead;
        for line in std::io::BufReader::new(stdout).lines() {
            let Ok(line) = line else { break };
            if tx.send(line).is_err() {
                break;
            }
        }
    });
    Some(OcrSidecar { child, stdin, rx })
}

/// Serve one OCR request through the persistent sidecar. Returns `None` when
/// the sidecar is disabled, cannot start, or times out (the caller then falls
/// back to the one-shot path, which also covers the tesseract reader).
fn sidecar_ocr(files: &[PathBuf]) -> Option<Vec<String>> {
    use std::io::Write;
    if files.is_empty() || !sidecar_enabled() {
        return None;
    }
    let mut guard = OCR_SIDECAR.lock().ok()?;
    let stale = match guard.as_mut() {
        None => true,
        Some(sidecar) => !matches!(sidecar.child.try_wait(), Ok(None)),
    };
    if stale {
        *guard = spawn_sidecar();
    }
    let sidecar = guard.as_mut()?;
    let request = serde_json::json!({
        "files": files
            .iter()
            .map(|path| path.to_string_lossy().to_string())
            .collect::<Vec<_>>(),
    });
    let mut line = request.to_string();
    line.push('\n');
    if sidecar.stdin.write_all(line.as_bytes()).is_err() || sidecar.stdin.flush().is_err() {
        *guard = None;
        return None;
    }
    let reply = match sidecar.rx.recv_timeout(sidecar_timeout()) {
        Ok(reply) => reply,
        Err(_) => {
            warn!(target: "engine", "ocr sidecar timed out, restarting it");
            if let Some(mut sidecar) = guard.take() {
                let _ = sidecar.child.kill();
                let _ = sidecar.child.wait();
            }
            return None;
        }
    };
    let parsed: Value = serde_json::from_str(&reply).ok()?;
    if let Some(ms) = parsed.get("ms").and_then(Value::as_array) {
        let timings: Vec<u64> = ms.iter().filter_map(Value::as_u64).collect();
        debug!(target: "engine", per_image_ms = ?timings, "ocr sidecar timings");
    }
    let mut lines = Vec::new();
    for block in parsed.get("blocks")?.as_array()? {
        for item in block.as_array()? {
            if let Some(text) = item.as_str() {
                if !text.trim().is_empty() {
                    lines.push(text.trim().to_string());
                }
            }
        }
    }
    if lines.is_empty() {
        return None;
    }
    Some(lines)
}

/// Load the RapidOCR models before the first campaign needs them. The sidecar
/// costs ~145 MB resident, but it removes the cold model load (about 3 s) from
/// campaign discovery, which runs on every new campaign.
pub fn prewarm() {
    if !sidecar_enabled() || ocr_url().is_some() {
        return;
    }
    std::thread::spawn(|| {
        let Ok(mut guard) = OCR_SIDECAR.lock() else {
            return;
        };
        if guard.is_none() {
            *guard = spawn_sidecar();
            if guard.is_some() {
                debug!(target: "engine", "ocr sidecar prewarmed");
            }
        }
    });
}

fn run_ocr(images: &[String], proxy: Option<&Proxy>) -> Vec<String> {
    let payloads = image_payloads(images, proxy);
    if payloads.is_empty() {
        return Vec::new();
    }

    // Remote backend first when configured; a network failure or an empty
    // answer falls through to the local readers instead of burning the run.
    if let Some(url) = ocr_url() {
        let language = ocr_language();
        if let Some(lines) = remote_ocr(&url, &payloads, language.as_deref()) {
            debug!(target: "engine", lines = lines.len(), "remote OCR");
            return lines;
        }
        warn!(target: "engine", "remote OCR failed, falling back to local");
    }

    let files = spill_payloads(&payloads);
    if files.is_empty() {
        return Vec::new();
    }
    // Warm sidecar first: one model load per engine process instead of one per
    // campaign. Empty output falls through to the one-shot readers below.
    if let Some(lines) = sidecar_ocr(&files) {
        debug!(target: "engine", lines = lines.len(), "ocr sidecar");
        return lines;
    }
    // The Python sidecar is the best reader, but it is optional. Timeout is
    // enforced in-process so Windows does not need GNU `timeout`, and a
    // missing/broken sidecar falls back to a tesseract binary when present.
    let mut command = std::process::Command::new(ocr_binary());
    command.arg(ocr_script()).args(&files);
    let sidecar = run_with_timeout(command, Duration::from_secs(120));
    let mut lines = Vec::new();
    match sidecar {
        Some(output) if output.status.success() => {
            let parsed: Vec<Vec<String>> =
                serde_json::from_slice(&output.stdout).unwrap_or_default();
            for block in parsed {
                lines.extend(block);
            }
        }
        Some(output) => {
            warn!(target: "engine", status = ?output.status.code(), "ocr sidecar exited non-zero");
        }
        None => {
            warn!(target: "engine", "ocr sidecar missing or timed out");
        }
    }
    if lines.is_empty() {
        lines = tesseract_ocr(&files);
    }
    lines
}

fn run_with_timeout(
    mut command: std::process::Command,
    limit: Duration,
) -> Option<std::process::Output> {
    command
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped());
    let mut child = command.spawn().ok()?;
    let (Some(mut stdout), Some(mut stderr)) = (child.stdout.take(), child.stderr.take()) else {
        let _ = child.kill();
        let _ = child.wait();
        return None;
    };
    // Drain both pipes while waiting: OCR output can exceed a pipe buffer, and
    // a child blocked on write would never reach try_wait().
    let out_reader = std::thread::spawn(move || {
        let mut buf = Vec::new();
        let _ = stdout.read_to_end(&mut buf);
        buf
    });
    let err_reader = std::thread::spawn(move || {
        let mut buf = Vec::new();
        let _ = stderr.read_to_end(&mut buf);
        buf
    });
    let deadline = Instant::now() + limit;
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Some(status),
            Ok(None) if Instant::now() < deadline => {
                std::thread::sleep(Duration::from_millis(50));
            }
            Ok(None) => {
                let _ = child.kill();
                let _ = child.wait();
                break None;
            }
            Err(_) => {
                let _ = child.kill();
                let _ = child.wait();
                break None;
            }
        }
    };
    let stdout = out_reader.join().unwrap_or_default();
    let stderr = err_reader.join().unwrap_or_default();
    status.map(|status| std::process::Output {
        status,
        stdout,
        stderr,
    })
}

fn tesseract_ocr(files: &[PathBuf]) -> Vec<String> {
    if files.is_empty() {
        return Vec::new();
    }
    let binary = std::env::var("L4M_TESSERACT").unwrap_or_else(|_| "tesseract".into());
    let language = std::env::var("L4M_TESSERACT_LANG").unwrap_or_else(|_| "eng".into());
    // Tesseract is CPU-bound; two concurrent processes cut a multi-strip page
    // in half without letting a wide campaign monopolise the box.
    let workers = files.len().min(2);
    let next = AtomicUsize::new(0);
    let results: Mutex<Vec<Vec<String>>> =
        Mutex::new((0..files.len()).map(|_| Vec::new()).collect());
    std::thread::scope(|scope| {
        for _ in 0..workers {
            scope.spawn(|| loop {
                let index = next.fetch_add(1, Ordering::Relaxed);
                if index >= files.len() {
                    break;
                }
                let lines = tesseract_one(&files[index], &binary, &language);
                if let Ok(mut slots) = results.lock() {
                    slots[index] = lines;
                }
            });
        }
    });
    let blocks = results.into_inner().unwrap_or_default();
    let mut lines = Vec::new();
    for block in blocks {
        lines.extend(block);
    }
    if !lines.is_empty() {
        debug!(target: "engine", lines = lines.len(), "tesseract fallback OCR");
    }
    lines
}

fn tesseract_one(file: &Path, binary: &str, language: &str) -> Vec<String> {
    let mut command = std::process::Command::new(binary);
    command.arg(file).arg("stdout").arg("-l").arg(language);
    let Some(output) = run_with_timeout(command, Duration::from_secs(45)) else {
        return Vec::new();
    };
    if !output.status.success() {
        return Vec::new();
    }
    String::from_utf8_lossy(&output.stdout)
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .map(str::to_string)
        .collect()
}

/// Pull the what-on widget key out of a sponsor page body.
fn widget_key(body: &str) -> Option<String> {
    let mut from = 0;
    while let Some(pos) = body[from..].find("/widget/") {
        let at = from + pos;
        let rest = &body[at..];
        if let Some(q) = rest.find("key=") {
            let key: String = rest[q + 4..]
                .chars()
                .take_while(|c| c.is_ascii_alphanumeric())
                .collect();
            if (4..=12).contains(&key.len()) {
                return Some(key);
            }
        }
        from = at + 8;
    }
    None
}

/// The widget script URL embedded in a sponsor page.
fn widget_src(body: &str) -> Option<String> {
    let at = body.find("/widget/")?;
    let head = &body[..at];
    let src_at = head.rfind("src=")?;
    let rest = &body[src_at + 4..];
    let quote = rest.chars().next()?;
    if quote != '"' && quote != '\'' {
        return None;
    }
    let end = rest[1..].find(quote)?;
    Some(rest[1..1 + end].to_string())
}

/// Read `ref_domain_list` out of the widget script: an empty list accepts a
/// bare navigation, a Google list requires a Google referrer.
fn widget_refs(body: &str, proxy: Option<&Proxy>) -> String {
    let Some(src) = widget_src(body) else {
        return "auto".into();
    };
    let url = if src.starts_with("//") {
        format!("https:{src}")
    } else if src.starts_with("http") {
        src
    } else {
        return "auto".into();
    };
    let fetch_js = |p: Option<&Proxy>| -> Option<String> {
        let response = proxy::agent_for(p, Duration::from_secs(4), UA_MOBILE)
            .get(&url)
            .call()
            .ok()?;
        response.into_string().ok()
    };
    let Some(js) = fetch_js(proxy).or_else(|| if proxy.is_some() { fetch_js(None) } else { None }) else {
        return "auto".into();
    };
    let Some(at) = js.find("ref_domain_list") else {
        return "auto".into();
    };
    let rest = &js[at..];
    let Some(open) = rest.find('[') else {
        return "auto".into();
    };
    let Some(close) = rest[open..].find(']') else {
        return "auto".into();
    };
    let list = &rest[open + 1..open + close];
    if list.trim().is_empty() {
        "none".into()
    } else if list.contains("google.com") {
        "google".into()
    } else {
        "custom".into()
    }
}

/// Extract a lowercase URL path/slug from Google search snippet breadcrumbs
/// such as `https://like.vn>mua-follow-tiktok` or `https://like.vn/slug`,
/// ignoring capitalized page titles like `> Kuwin Chinh Hang`.
fn extract_sponsor_target(blob: &str, domain: &str) -> String {
    let lower_domain = domain.to_ascii_lowercase();
    for line in blob.lines() {
        let trimmed = line.trim();
        let lower = trimmed.to_ascii_lowercase();
        let Some(pos) = lower.find(&lower_domain) else {
            continue;
        };
        let after = &trimmed[pos + lower_domain.len()..];
        let rest = after
            .trim_start_matches(|c: char| c == '/' || c == '>' || c == '›' || c == ' ');
        if rest.is_empty() {
            continue;
        }
        // Only treat as a URL slug when it starts lowercase and has no spaces
        // before the next separator (e.g. `mua-follow-tiktok`), not `Kuwin Chinh Hang`.
        let slug: String = rest
            .chars()
            .take_while(|c| c.is_ascii_alphanumeric() || matches!(c, '-' | '_' | '.'))
            .collect();
        if slug.len() >= 3 && slug.contains('-') && slug.chars().all(|c| !c.is_ascii_uppercase()) {
            if slug.ends_with('.') || slug.ends_with('-') {
                let prefix = slug.trim_end_matches('.');
                if prefix.len() >= 4 {
                    return format!("{domain}/{prefix}*");
                }
            } else {
                return format!("{domain}/{slug}");
            }
        }
    }
    domain.to_string()
}

fn resolve_truncated_href(body: &str, host: &str, prefix: &str, ocr_blob: &str) -> Option<String> {
    let needle = format!("/{prefix}");
    let mut best: Option<(usize, String)> = None;
    let ocr_norm: String = ocr_blob
        .chars()
        .filter(|c| c.is_ascii_alphanumeric())
        .map(|c| c.to_ascii_lowercase())
        .collect();
    let mut pos = 0;
    while let Some(at) = body[pos..].find("href=") {
        let start = pos + at + 5;
        let rest = &body[start..];
        let quote = rest.chars().next()?;
        if quote == '"' || quote == '\'' {
            if let Some(end) = rest[1..].find(quote) {
                let href = &rest[1..1 + end];
                let path = if let Some(stripped) = href.strip_prefix(&format!("https://{host}")) {
                    stripped
                } else if let Some(stripped) = href.strip_prefix(&format!("http://{host}")) {
                    stripped
                } else {
                    href
                };
                if path.starts_with(&needle) && path.len() > needle.len() && !path.contains('?') {
                    let slug_norm: String = path
                        .chars()
                        .filter(|c| c.is_ascii_alphabetic())
                        .map(|c| c.to_ascii_lowercase())
                        .collect();
                    let score = if !slug_norm.is_empty() && ocr_norm.contains(&slug_norm) {
                        100 + slug_norm.len()
                    } else {
                        slug_norm.len()
                    };
                    if best.as_ref().map(|(s, _)| score > *s).unwrap_or(true) {
                        best = Some((score, path.trim_start_matches('/').to_string()));
                    }
                }
                pos = start + 1 + end;
                continue;
            }
        }
        pos = start + 1;
    }
    best.map(|(_, p)| format!("{host}/{p}"))
}

/// Fetch a candidate page and return `(final host[/path], widget key)`.
fn probe(target: &str, ocr_blob: &str, proxy: Option<&Proxy>) -> Option<(String, String)> {
    let try_probe = |cand: &str, p: Option<&Proxy>| -> Option<(String, String)> {
        let agent = proxy::agent_for(p, Duration::from_secs(5), UA_MOBILE);
        let url = if cand.contains('/') {
            format!("https://{cand}")
        } else {
            format!("https://{cand}/")
        };
        let response = agent.get(&url).call().ok()?;
        let final_url = response.get_url().to_string();
        let mut body = String::new();
        response
            .into_reader()
            .take(3 * 1024 * 1024)
            .read_to_string(&mut body)
            .ok()?;
        let key = widget_key(&body)?;
        let parsed = url::Url::parse(&final_url).ok()?;
        let host = parsed.host_str()?.to_string();
        let path = parsed.path().trim_end_matches('/');
        let sponsor = if cand.contains('/') && !path.is_empty() {
            format!("{host}{path}")
        } else {
            host
        };
        let refs = widget_refs(&body, p);
        Some((sponsor, format!("{key}\u{1}{refs}")))
    };
    if let Some((host, pat)) = target.split_once('/') {
        if let Some(prefix) = pat.strip_suffix('*') {
            let fetch_home = |p: Option<&Proxy>| -> Option<String> {
                let agent = proxy::agent_for(p, Duration::from_secs(5), UA_MOBILE);
                let resp = agent.get(&format!("https://{host}/")).call().ok()?;
                let mut body = String::new();
                resp.into_reader().take(2 * 1024 * 1024).read_to_string(&mut body).ok()?;
                Some(body)
            };
            if let Some(home) = fetch_home(proxy).or_else(|| if proxy.is_some() { fetch_home(None) } else { None }) {
                if let Some(resolved) = resolve_truncated_href(&home, host, prefix, ocr_blob) {
                    if let Some(hit) = try_probe(&resolved, proxy).or_else(|| if proxy.is_some() { try_probe(&resolved, None) } else { None }) {
                        return Some(hit);
                    }
                }
            }
            return try_probe(host, proxy).or_else(|| if proxy.is_some() { try_probe(host, None) } else { None });
        }
    }
    if let Some(hit) = try_probe(target, proxy) {
        return Some(hit);
    }
    if proxy.is_some() {
        if let Some(hit) = try_probe(target, None) {
            return Some(hit);
        }
    }
    if let Some((host, _)) = target.split_once('/') {
        if let Some(hit) = try_probe(host, proxy) {
            return Some(hit);
        }
        if proxy.is_some() {
            return try_probe(host, None);
        }
    }
    None
}

async fn probe_indexed(
    idx: usize,
    domain: String,
    blob: String,
    proxy: Option<Proxy>,
) -> (usize, Option<(String, String)>) {
    let hit = tokio::task::spawn_blocking(move || probe(&domain, &blob, proxy.as_ref()))
        .await
        .ok()
        .flatten();
    (idx, hit)
}

/// Probe candidates concurrently with early exit once priority #0 hits or
/// higher-priority slots fail/timeout briefly after a valid hit arrives.
async fn probe_all(candidates: Vec<String>, ocr_blob: String, proxy: Option<Proxy>) -> Option<(String, String)> {
    let total = candidates.len();
    if total == 0 {
        return None;
    }
    let mut iter = candidates.into_iter().enumerate();
    let mut in_flight = FuturesUnordered::new();
    for _ in 0..4 {
        let Some((idx, domain)) = iter.next() else { break };
        in_flight.push(probe_indexed(idx, domain, ocr_blob.clone(), proxy.clone()));
    }

    let mut best: Option<(usize, (String, String))> = None;
    let mut grace_deadline: Option<tokio::time::Instant> = None;
    loop {
        let next_item = if let Some(deadline) = grace_deadline {
            match tokio::time::timeout_at(deadline, in_flight.next()).await {
                Ok(item) => item,
                Err(_) => break,
            }
        } else {
            in_flight.next().await
        };
        let Some((idx, hit)) = next_item else { break };
        if let Some(h) = hit {
            let better = best.as_ref().map(|(bi, _)| idx < *bi).unwrap_or(true);
            if better {
                best = Some((idx, h));
                if idx == 0 {
                    break;
                }
                grace_deadline = Some(tokio::time::Instant::now() + Duration::from_millis(1200));
            }
        }
        if let Some((next_idx, domain)) = iter.next() {
            let can_beat = best.as_ref().map(|(bi, _)| next_idx < *bi).unwrap_or(true);
            if can_beat {
                in_flight.push(probe_indexed(next_idx, domain, ocr_blob.clone(), proxy.clone()));
            }
        }
    }
    best.map(|(_, h)| h)
}

/// Read the instruction block on the current campaign page.
pub async fn discover(cdp: &Cdp, proxy: Option<Proxy>) -> Option<Campaign> {
    let value = cdp.eval(None, INSTR_JS).await.ok()?;
    let text = value.get("text").and_then(Value::as_str).unwrap_or("");
    let campaign_id = value.get("campaign").and_then(Value::as_str).unwrap_or("");

    if let Some(hit) = cache_get(campaign_id) {
        if !hit.sponsor.is_empty() && !hit.key.is_empty() {
            debug!(target: "engine", campaign = %campaign_id, sponsor = %hit.sponsor, "campaign cache hit");
            return Some(hit);
        }
        // Cached before the probe existed, or the probe failed last time.
        if let Some((host, packed)) = probe_all(vec![hit.sponsor.clone()], String::new(), proxy.clone()).await {
            let (key, refs) = packed
                .split_once('\u{1}')
                .map(|(k, r)| (k.to_string(), r.to_string()))
                .unwrap_or((packed, "auto".into()));
            let updated = Campaign {
                sponsor: host,
                key,
                refs,
                ..hit.clone()
            };
            cache_put(campaign_id, &updated);
            return Some(updated);
        }
    }

    let direct = text.to_uppercase().contains("TRỰC TIẾP");
    let mut domains = clean_domains(text);
    let mut keyword = parse_keyword(text);

    let mut ocr_blob = String::new();
    if !direct || domains.is_empty() {
        let images: Vec<String> = value
            .get("imgs")
            .and_then(Value::as_array)
            .map(|a| {
                a.iter()
                    .filter_map(Value::as_str)
                    .map(str::to_string)
                    .collect()
            })
            .unwrap_or_default();
        let images_hash = hash_images(&images);
        let cached_lines = if images.is_empty() {
            None
        } else {
            ocr_cache_get(campaign_id, images_hash)
        };
        let lines = match cached_lines {
            Some(lines) => {
                debug!(target: "engine", campaign = %campaign_id, lines = lines.len(), "instruction OCR cache hit");
                lines
            }
            None => {
                // OCR shells out to Python/tesseract or waits on a remote
                // socket; keep it off the async runtime thread so the API and
                // other workers are not stalled for the whole read.
                let ocr_images = images;
                let ocr_proxy = proxy.clone();
                let lines = tokio::task::spawn_blocking(move || {
                    run_ocr(&ocr_images, ocr_proxy.as_ref())
                })
                .await
                .unwrap_or_default();
                // Empty stays uncached: the strips may be a transient 404 and
                // the next alias should retry instead of inheriting nothing.
                if !lines.is_empty() {
                    ocr_cache_put(campaign_id, images_hash, &lines);
                }
                lines
            }
        };
        if lines.is_empty() {
            warn!(target: "engine", "instruction OCR returned nothing");
        }
        let blob = lines.join("\n");
        ocr_blob = blob.clone();
        debug!(target: "engine", ocr = %blob.replace('\n', " | "), "instruction OCR");
        for domain in clean_domains(&blob) {
            let target = extract_sponsor_target(&blob, &domain);
            if !domains.contains(&target) {
                domains.push(target);
            }
        }
        if keyword.is_empty() {
            keyword = parse_keyword(&blob);
        }
    }

    let (sponsor, packed) = probe_all(domains, ocr_blob, proxy).await?;
    let (key, refs) = packed
        .split_once('\u{1}')
        .map(|(k, r)| (k.to_string(), r.to_string()))
        .unwrap_or((packed, "auto".into()));
    let campaign = Campaign {
        kind: if direct {
            "direct".into()
        } else {
            "search".into()
        },
        sponsor,
        key,
        keyword,
        refs,
    };
    info!(target: "engine", campaign = %campaign_id, sponsor = %campaign.sponsor, widget = %campaign.key, keyword = %campaign.keyword, kind = %campaign.kind, "campaign discovered");
    cache_put(campaign_id, &campaign);
    Some(campaign)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn finds_sponsor_domain() {
        let text = "Bước 1: Copy link\nm.fafa999k1.com\nBước 2: Mở tab mới";
        assert_eq!(clean_domains(text), vec!["m.fafa999k1.com"]);
    }

    #[test]
    fn ignores_google_and_link4m() {
        let text = "google.com link4m.net img.link4m.net sevenam.vn";
        assert_eq!(clean_domains(text), vec!["sevenam.vn"]);
    }

    #[test]
    fn reads_keyword() {
        assert_eq!(parse_keyword("Bước 2: Gõ tìm từ khoá sevenam"), "sevenam");
        assert_eq!(parse_keyword("Buoc 2: Go tim tu khoa betmoney"), "betmoney");
        assert_eq!(parse_keyword("Buoc 2: Go tim tp khoa bet88"), "bet88");
    }

    #[test]
    fn extracts_sponsor_slug_from_breadcrumb() {
        let blob = "Like.vn\nhttps://like.vn>mua-follow-tiktok\nTang,BuffFollow";
        assert_eq!(extract_sponsor_target(blob, "like.vn"), "like.vn/mua-follow-tiktok");
        let title_blob = "grbets527.com\nhttps://m.grbets527.com > Kuwin Chinh Hang";
        assert_eq!(extract_sponsor_target(title_blob, "m.grbets527.com"), "m.grbets527.com");
    }

    #[test]
    fn extracts_widget_key() {
        let body = r#"<script src="//s1.what-on.com/widget/service-v2.js?key=GlY39k"></script>"#;
        assert_eq!(widget_key(body).as_deref(), Some("GlY39k"));
        assert_eq!(widget_key("<html>no widget</html>"), None);
    }

    fn temp_cache_path(tag: &str) -> PathBuf {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|delta| delta.as_nanos())
            .unwrap_or(0);
        std::env::temp_dir()
            .join(format!("l4m-ocr-{tag}-{}-{nanos}", std::process::id()))
            .join("ocr-cache.json")
    }

    #[test]
    fn ocr_cache_round_trip_and_eviction() {
        let path = temp_cache_path("cache");
        let mut entries = Vec::new();
        for index in 0..=OCR_CACHE_LIMIT {
            let lines = vec![format!("line {index}"), format!("domain{index}.com")];
            ocr_cache_remember(&mut entries, &format!("camp{index}"), index as u64, &lines);
        }
        assert_eq!(entries.len(), OCR_CACHE_LIMIT);
        assert!(ocr_cache_lookup(&entries, "camp0", 0).is_none());
        assert_eq!(
            ocr_cache_lookup(
                &entries,
                &format!("camp{OCR_CACHE_LIMIT}"),
                OCR_CACHE_LIMIT as u64
            )
            .as_deref(),
            Some(
                &[
                    format!("line {OCR_CACHE_LIMIT}"),
                    format!("domain{OCR_CACHE_LIMIT}.com")
                ][..]
            )
        );

        ocr_cache_store_path(&path, &entries);
        let loaded = ocr_cache_load_path(&path);
        assert_eq!(loaded, entries);
        assert_eq!(
            ocr_cache_lookup(&loaded, "camp7", 7).as_deref(),
            Some(&["line 7".to_string(), "domain7.com".to_string()][..])
        );
        let _ = std::fs::remove_dir_all(path.parent().unwrap());
    }

    fn serve_ocr_once(payload: &'static str) -> (u16, std::thread::JoinHandle<()>) {
        use std::io::{Read, Write};
        let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("bind");
        let port = listener.local_addr().unwrap().port();
        let server = std::thread::spawn(move || {
            let (mut socket, _) = listener.accept().expect("accept");
            socket
                .set_read_timeout(Some(Duration::from_secs(10)))
                .unwrap();
            let mut buf = Vec::new();
            let mut chunk = [0u8; 4096];
            let header_end = loop {
                let n = socket.read(&mut chunk).expect("read head");
                assert!(n > 0, "client closed before headers");
                buf.extend_from_slice(&chunk[..n]);
                if let Some(pos) = buf.windows(4).position(|w| w == b"\r\n\r\n") {
                    break pos + 4;
                }
            };
            let head = String::from_utf8_lossy(&buf[..header_end]).to_lowercase();
            let length: usize = head
                .lines()
                .find_map(|line| line.strip_prefix("content-length:"))
                .and_then(|value| value.trim().parse().ok())
                .expect("content-length");
            while buf.len() < header_end + length {
                let n = socket.read(&mut chunk).expect("read body");
                if n == 0 {
                    break;
                }
                buf.extend_from_slice(&chunk[..n]);
            }
            let body = String::from_utf8_lossy(&buf[header_end..]).to_string();
            assert!(
                body.contains("filename=\"instr-0.png\""),
                "missing image field"
            );
            assert!(body.contains("name=\"language\""), "missing language field");
            assert!(
                body.contains("\r\n\r\nvie+eng\r\n"),
                "language value missing"
            );
            let reply = format!(
                "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\
                 Content-Length: {}\r\n\r\n{}",
                payload.len(),
                payload
            );
            socket.write_all(reply.as_bytes()).expect("write reply");
        });
        (port, server)
    }

    fn ocr_upload() -> Vec<ImagePayload> {
        vec![ImagePayload {
            name: "instr-0.png".into(),
            data: b"\x89PNG\r\n\x1a\n".to_vec(),
        }]
    }

    #[test]
    fn remote_ocr_reads_nested_json_blocks() {
        let payload = r#"[["alpha.com","beta"],["gamma.com"]]"#;
        let (port, server) = serve_ocr_once(payload);
        let url = format!("http://127.0.0.1:{port}/ocr");
        let lines = remote_ocr(&url, &ocr_upload(), Some("vie+eng")).expect("remote lines");
        server.join().expect("server");
        assert_eq!(lines, vec!["alpha.com", "beta", "gamma.com"]);
    }

    #[test]
    fn remote_ocr_reads_lines_object() {
        let payload = r#"{"lines":["delta.com","epsilon.net"]}"#;
        let (port, server) = serve_ocr_once(payload);
        let url = format!("http://127.0.0.1:{port}/ocr");
        let lines = remote_ocr(&url, &ocr_upload(), Some("vie+eng")).expect("remote lines");
        server.join().expect("server");
        assert_eq!(lines, vec!["delta.com", "epsilon.net"]);
    }

    #[test]
    fn remote_ocr_reads_plain_text() {
        let payload = "one.com\ntwo.net\n";
        let (port, server) = serve_ocr_once(payload);
        let url = format!("http://127.0.0.1:{port}/ocr");
        let lines = remote_ocr(&url, &ocr_upload(), Some("vie+eng")).expect("remote lines");
        server.join().expect("server");
        assert_eq!(lines, vec!["one.com", "two.net"]);
    }
}
