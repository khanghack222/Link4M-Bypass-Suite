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
use futures_util::future::join_all;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::io::Read;
use std::path::{Path, PathBuf};
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
    .slice(0, 8) : [];
  const camp = document.querySelector('input[name=campaign_id]');
  return {
    text: root ? (root.innerText || '') : '',
    imgs,
    campaign: camp ? camp.value : ''
  };
})()"#;

const TLDS: &[&str] = &[
    "com", "net", "org", "vn", "life", "top", "site", "vip", "bet", "win", "app",
    "xyz", "info", "io", "co", "online", "club", "fun", "store", "shop", "live",
    "me", "tv", "cc", "pro", "asia", "biz", "link", "cloud", "one", "website",
    "casino", "game", "games", "dev", "page", "space",
];

const EXCLUDED: &[&str] = &[
    "google.", "facebook.", "youtube.", "link4m.", "gstatic.", "doubleclick.",
    "img.link4m", "googletagmanager", "google-analytics", "cdn.jsdelivr",
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
    let path = cache_path();
    if let Some(dir) = path.parent() {
        let _ = std::fs::create_dir_all(dir);
    }
    if let Ok(raw) = serde_json::to_string_pretty(map) {
        let _ = std::fs::write(path, raw);
    }
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
    let mut guard = cache().lock().expect("campaign cache");
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
    let mut guard = cache().lock().expect("campaign cache");
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
    for needle in ["từ khoá", "từ khoa", "tu khoa", "tim tu khoa", "khoá", "khoa"] {
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

fn ocr_binary() -> PathBuf {
    if let Ok(path) = std::env::var("L4M_PYTHON") {
        return PathBuf::from(path);
    }
    for candidate in [".venv/bin/python", "../.venv/bin/python"] {
        let path = PathBuf::from(candidate);
        if path.exists() {
            return path;
        }
    }
    #[cfg(windows)]
    for candidate in [".venv\\Scripts\\python.exe", "..\\.venv\\Scripts\\python.exe"] {
        let path = PathBuf::from(candidate);
        if path.exists() {
            return path;
        }
    }
    PathBuf::from("python3")
}

fn ocr_script() -> PathBuf {
    if let Ok(path) = std::env::var("L4M_OCR") {
        return PathBuf::from(path);
    }
    PathBuf::from("tools/ocr.py")
}

/// Which OCR reader is available right now. `--check` prints this so a missing
/// sidecar and a missing tesseract are visible before a campaign needs them.
pub fn ocr_status() -> &'static str {
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

fn runnable(binary: &Path, args: &[&str]) -> bool {
    std::process::Command::new(binary)
        .args(args)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .map(|status| status.success())
        .unwrap_or(false)
}

fn decode_image(src: &str, dir: &Path, index: usize, proxy: Option<&Proxy>) -> Option<PathBuf> {
    let path = dir.join(format!("instr-{index}.png"));
    if let Some(rest) = src.strip_prefix("data:image/") {
        let payload = rest.split_once(',')?.1;
        let raw = base64::engine::general_purpose::STANDARD.decode(payload).ok()?;
        std::fs::write(&path, raw).ok()?;
        return Some(path);
    }
    if src.starts_with("http://") || src.starts_with("https://") {
        let body = proxy::agent_for(proxy, Duration::from_secs(12), "Mozilla/5.0")
            .get(src)
            .call()
            .ok()?
            .into_reader();
        let mut buf = Vec::new();
        let mut reader = body.take(8 * 1024 * 1024);
        reader.read_to_end(&mut buf).ok()?;
        std::fs::write(&path, buf).ok()?;
        return Some(path);
    }
    None
}

fn run_ocr(images: &[String], proxy: Option<&Proxy>) -> Vec<String> {
    let dir = std::env::temp_dir().join("l4m-instr");
    let _ = std::fs::create_dir_all(&dir);
    let mut files = Vec::new();
    for (i, src) in images.iter().enumerate() {
        if let Some(path) = decode_image(src, &dir, i, proxy) {
            files.push(path);
        }
    }
    if files.is_empty() {
        return Vec::new();
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
    let binary = std::env::var("L4M_TESSERACT").unwrap_or_else(|_| "tesseract".into());
    let language = std::env::var("L4M_TESSERACT_LANG").unwrap_or_else(|_| "eng".into());
    let mut lines = Vec::new();
    for file in files {
        let mut command = std::process::Command::new(&binary);
        command
            .arg(file)
            .arg("stdout")
            .arg("-l")
            .arg(&language);
        let Some(output) = run_with_timeout(command, Duration::from_secs(45)) else {
            continue;
        };
        if !output.status.success() {
            continue;
        }
        for line in String::from_utf8_lossy(&output.stdout).lines() {
            let line = line.trim();
            if !line.is_empty() {
                lines.push(line.to_string());
            }
        }
    }
    if !lines.is_empty() {
        debug!(target: "engine", lines = lines.len(), "tesseract fallback OCR");
    }
    lines
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
    let Ok(response) = proxy::agent_for(proxy, Duration::from_secs(8), UA_MOBILE)
        .get(&url)
        .call()
    else {
        return "auto".into();
    };
    let Ok(js) = response.into_string() else {
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

/// Fetch a candidate homepage and return `(final host, widget key)`.
fn probe(domain: &str, proxy: Option<&Proxy>) -> Option<(String, String)> {
    let agent = proxy::agent_for(proxy, Duration::from_secs(9), UA_MOBILE);
    let response = agent.get(&format!("https://{domain}/")).call().ok()?;
    let final_url = response.get_url().to_string();
    let mut body = String::new();
    response
        .into_reader()
        .take(3 * 1024 * 1024)
        .read_to_string(&mut body)
        .ok()?;
    let key = widget_key(&body)?;
    let host = url::Url::parse(&final_url).ok()?.host_str()?.to_string();
    let refs = widget_refs(&body, proxy);
    Some((host, format!("{key}\u{1}{refs}")))
}

/// Probe candidates in parallel, keeping the OCR order as priority.
async fn probe_all(candidates: Vec<String>, proxy: Option<Proxy>) -> Option<(String, String)> {
    for chunk in candidates.chunks(4) {
        let futures = chunk.iter().enumerate().map(|(i, domain)| {
            let domain = domain.clone();
            let proxy = proxy.clone();
            async move {
                let hit = tokio::task::spawn_blocking(move || probe(&domain, proxy.as_ref()))
                    .await
                    .ok()
                    .flatten();
                (i, hit)
            }
        });
        let results = join_all(futures).await;
        let best = results
            .into_iter()
            .filter_map(|(i, hit)| hit.map(|h| (i, h)))
            .min_by_key(|(i, _)| *i);
        if let Some((_, hit)) = best {
            return Some(hit);
        }
    }
    None
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
        if let Some((host, packed)) = probe_all(vec![hit.sponsor.clone()], proxy.clone()).await {
            let (key, refs) = packed
                .split_once('\u{1}')
                .map(|(k, r)| (k.to_string(), r.to_string()))
                .unwrap_or((packed, "auto".into()));
            let updated = Campaign { sponsor: host, key, refs, ..hit.clone() };
            cache_put(campaign_id, &updated);
            return Some(updated);
        }
    }

    let direct = text.to_uppercase().contains("TRỰC TIẾP");
    let mut domains = clean_domains(text);
    let mut keyword = parse_keyword(text);

    if !direct || domains.is_empty() {
        let images: Vec<String> = value
            .get("imgs")
            .and_then(Value::as_array)
            .map(|a| a.iter().filter_map(Value::as_str).map(str::to_string).collect())
            .unwrap_or_default();
        let lines = run_ocr(&images, proxy.as_ref());
        if lines.is_empty() {
            warn!(target: "engine", "instruction OCR returned nothing");
        }
        let blob = lines.join("\n");
        debug!(target: "engine", ocr = %blob.replace('\n', " | "), "instruction OCR");
        for domain in clean_domains(&blob) {
            if !domains.contains(&domain) {
                domains.push(domain);
            }
        }
        if keyword.is_empty() {
            keyword = parse_keyword(&blob);
        }
    }

    let (sponsor, packed) = probe_all(domains, proxy).await?;
    let (key, refs) = packed
        .split_once('\u{1}')
        .map(|(k, r)| (k.to_string(), r.to_string()))
        .unwrap_or((packed, "auto".into()));
    let campaign = Campaign {
        kind: if direct { "direct".into() } else { "search".into() },
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
    fn extracts_widget_key() {
        let body = r#"<script src="//s1.what-on.com/widget/service-v2.js?key=GlY39k"></script>"#;
        assert_eq!(widget_key(body).as_deref(), Some("GlY39k"));
        assert_eq!(widget_key("<html>no widget</html>"), None);
    }
}
