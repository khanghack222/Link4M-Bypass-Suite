//! Sponsor-page code harvest.
//!
//! The campaign form asks for a short "mã" issued by a sponsored site. That
//! site embeds the what-on widget, whose quest is a two-step client-side
//! countdown: click `LẤY MÃ`, wait out step 1, reload, click again, read the
//! code. This module drives a second tab through that sequence with raw CDP
//! input events, exactly like a phone user.
//!
//! The tab lives in the same Chrome instance as the campaign page, so the
//! session cookies and the residential-looking fingerprint are shared.

use crate::cdp::Cdp;
use serde_json::{json, Value};
use std::time::{Duration, Instant};
use tracing::{debug, info};

#[derive(Debug, Clone)]
pub struct QuestError {
    pub kind: &'static str,
    pub message: String,
}

impl QuestError {
    fn new(kind: &'static str, message: impl Into<String>) -> Self {
        Self { kind, message: message.into() }
    }
}

impl std::fmt::Display for QuestError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}: {}", self.kind, self.message)
    }
}

impl std::error::Error for QuestError {}

type QuestResult<T> = std::result::Result<T, QuestError>;

const UA_MOBILE: &str = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 \
(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36";

const FIND_WIDGET_JS: &str = r#"(() => {
  const keys = [...document.querySelectorAll('script[src*="/widget/"]')]
    .map(s => (s.src.match(/key=([A-Za-z0-9]+)/) || [])[1]).filter(Boolean);
  for (const k of [...new Set(keys)]) {
    const e = document.getElementById(k);
    if (e && (e.querySelector('button') || /LẤY MÃ/i.test(e.innerText || ''))) return k;
  }
  for (const e of document.querySelectorAll('div[id]')) {
    if (!/^[A-Za-z0-9]{6,10}$/.test(e.id)) continue;
    if (e.querySelector('.whatoncode')) return e.id;
    const b = e.querySelector('button');
    if (b && /LẤY MÃ/i.test(b.innerText || '')) return e.id;
  }
  return '';
})()"#;

const CLEAR_QUEST_JS: &str = r#"(() => {
  const out = [];
  for (let i = localStorage.length - 1; i >= 0; i--) {
    const k = localStorage.key(i);
    if (/_quest$/.test(k)) { out.push(k); localStorage.removeItem(k); }
  }
  return out;
})()"#;

const STATUS_JS: &str = r#"(() => {
  const e = document.getElementById(KEY);
  return e ? (e.innerText || '').trim() : '';
})()"#;

const RECT_JS: &str = r#"(() => {
  const e = document.getElementById(KEY);
  if (!e) return null;
  e.scrollIntoView({ block: 'center' });
  const b = e.querySelector('button') || e;
  const r = b.getBoundingClientRect();
  return {
    x: r.x + r.width / 2,
    y: r.y + r.height / 2,
    touch: 'ontouchstart' in document.documentElement
  };
})()"#;

const JS_CLICK_JS: &str = r#"(() => {
  const e = document.getElementById(KEY);
  if (!e) return false;
  const b = e.querySelector('button') || e;
  b.click();
  return true;
})()"#;

fn with_key(script: &str, key: &str) -> String {
    let quoted = serde_json::to_string(key).unwrap_or_else(|_| "\"\"".into());
    script.replace("KEY", &quoted)
}

fn open_tab(port: u16) -> anyhow::Result<(String, String)> {
    let url = format!("http://127.0.0.1:{port}/json/new?about:blank");
    let body = ureq::put(&url)
        .timeout(Duration::from_secs(10))
        .call()?
        .into_string()?;
    let value: Value = serde_json::from_str(&body)?;
    let ws = value
        .get("webSocketDebuggerUrl")
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow::anyhow!("new tab has no ws url"))?
        .to_string();
    let id = value
        .get("id")
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow::anyhow!("new tab has no id"))?
        .to_string();
    Ok((ws, id))
}

fn close_tab(port: u16, id: &str) {
    let url = format!("http://127.0.0.1:{port}/json/close/{id}");
    let _ = ureq::get(&url).timeout(Duration::from_secs(5)).call();
}

async fn wheel(cdp: &Cdp, dy: i64) -> anyhow::Result<()> {
    // scrollBy runs in the page and costs no Input round-trip; the widget only
    // needs scroll events to lazy-load its script.
    cdp.eval(None, &format!("window.scrollBy(0, {dy}); true"))
        .await?;
    Ok(())
}

async fn tap(cdp: &Cdp, x: f64, y: f64, touch: bool) -> anyhow::Result<()> {
    if touch {
        cdp.call(
            "Input.dispatchTouchEvent",
            json!({"type": "touchStart", "touchPoints": [{"x": x, "y": y, "id": 1, "radiusX": 12, "radiusY": 12}]}),
        )
        .await?;
        tokio::time::sleep(Duration::from_millis(120)).await;
        cdp.call(
            "Input.dispatchTouchEvent",
            json!({"type": "touchEnd", "touchPoints": []}),
        )
        .await?;
    } else {
        cdp.call(
            "Input.dispatchMouseEvent",
            json!({"type": "mouseMoved", "x": x - 15.0, "y": y - 8.0}),
        )
        .await?;
        tokio::time::sleep(Duration::from_millis(250)).await;
        cdp.call(
            "Input.dispatchMouseEvent",
            json!({"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1}),
        )
        .await?;
        tokio::time::sleep(Duration::from_millis(60)).await;
        cdp.call(
            "Input.dispatchMouseEvent",
            json!({"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1}),
        )
        .await?;
    }
    Ok(())
}

/// Pull the 6-char campaign code out of the widget text.
pub fn parse_code(text: &str) -> Option<String> {
    let idx = text.find("Mã KM")?;
    let rest = &text[idx..];
    let after = rest.split(':').nth(1).unwrap_or("");
    let code: String = after
        .trim()
        .chars()
        .take_while(|c| c.is_ascii_alphanumeric())
        .collect();
    if (4..=10).contains(&code.len()) {
        Some(code)
    } else {
        None
    }
}

fn countdown_secs(text: &str) -> Option<u32> {
    let bytes = text.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i].is_ascii_digit() {
            let start = i;
            while i < bytes.len() && bytes[i].is_ascii_digit() {
                i += 1;
            }
            if i < bytes.len() && bytes[i] == b's' {
                if let Ok(value) = text[start..i].parse::<u32>() {
                    return Some(value);
                }
            }
        } else {
            i += 1;
        }
    }
    None
}

async fn status(cdp: &Cdp, key: &str) -> String {
    match cdp.eval(None, &with_key(STATUS_JS, key)).await {
        Ok(Value::String(text)) => text,
        _ => String::new(),
    }
}

async fn press_widget(cdp: &Cdp, key: &str) -> bool {
    let rect = match cdp.eval(None, &with_key(RECT_JS, key)).await {
        Ok(value) => value,
        Err(_) => return false,
    };
    let (x, y) = match (rect.get("x").and_then(Value::as_f64), rect.get("y").and_then(Value::as_f64)) {
        (Some(x), Some(y)) => (x, y),
        _ => return false,
    };
    let touch = rect.get("touch").and_then(Value::as_bool).unwrap_or(false);
    tokio::time::sleep(Duration::from_millis(800)).await;
    tap(cdp, x, y, touch).await.is_ok()
}

async fn click_widget(cdp: &Cdp, key: &str) -> bool {
    for attempt in 1..=4 {
        if !press_widget(cdp, key).await {
            return false;
        }
        tokio::time::sleep(Duration::from_millis(1500)).await;
        let text = status(cdp, key).await;
        let idle = text.to_uppercase().contains("LẤY MÃ") && countdown_secs(&text).is_none();
        if !idle {
            return true;
        }
        match attempt {
            2 => {
                let _ = cdp.eval(None, &with_key(JS_CLICK_JS, key)).await;
            }
            3 => {
                let _ = cdp
                    .eval(
                        None,
                        &with_key(
                            "(() => { const e = document.getElementById(KEY); const b = e && (e.querySelector('button') || e); if (b) b.focus(); return true; })()",
                            key,
                        ),
                    )
                    .await;
                let _ = cdp
                    .call(
                        "Input.dispatchKeyEvent",
                        json!({"type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13}),
                    )
                    .await;
                let _ = cdp
                    .call(
                        "Input.dispatchKeyEvent",
                        json!({"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13}),
                    )
                    .await;
            }
            _ => {
                for _ in 0..3 {
                    let _ = wheel(cdp, 120).await;
                    tokio::time::sleep(Duration::from_millis(350)).await;
                }
                let _ = wheel(cdp, -120).await;
            }
        }
        tokio::time::sleep(Duration::from_millis(1200)).await;
    }
    false
}

/// Open `sponsor`, run the widget quest, return the code.
pub async fn harvest(
    port: u16,
    sponsor: &str,
    _keyword: &str,
    key_hint: &str,
    refs: &str,
    budget: Duration,
) -> QuestResult<String> {
    let (ws, target_id) = open_tab(port).map_err(|e| QuestError::new("quest", e.to_string()))?;
    let cdp = Cdp::connect(&ws)
        .await
        .map_err(|e| QuestError::new("quest", e.to_string()))?;

    let outcome = drive(&cdp, sponsor, key_hint, refs, budget).await;
    close_tab(port, &target_id);
    outcome
}

async fn load_and_scroll(cdp: &Cdp, url: &str, referrer: Option<&str>) -> QuestResult<()> {
    let mut params = json!({"url": url});
    if let Some(referrer) = referrer {
        params["referrer"] = json!(referrer);
    }
    cdp.call("Page.navigate", params)
        .await
        .map_err(|e| QuestError::new("cdp", e.to_string()))?;
    tokio::time::sleep(Duration::from_secs(5)).await;
    for _ in 0..10 {
        let _ = wheel(cdp, 400).await;
        tokio::time::sleep(Duration::from_millis(300)).await;
    }
    Ok(())
}

const DIAG_JS: &str = r#"(() => {
  const scripts = [...document.querySelectorAll('script[src*="/widget/"]')]
    .map(s => s.src.slice(0, 90));
  const divs = [...document.querySelectorAll('div[id]')]
    .filter(e => /^[A-Za-z0-9]{5,12}$/.test(e.id))
    .map(e => e.id + ':' + ((e.innerText || '').trim().slice(0, 40).replace(/\n/g, ' ')))
    .slice(0, 8);
  return {
    title: document.title.slice(0, 80),
    url: location.href.slice(0, 120),
    body: (document.body ? document.body.innerText.length : 0),
    scripts, divs,
    ready: document.readyState
  };
})()"#;

async fn find_widget(cdp: &Cdp) -> String {
    for attempt in 0..14 {
        match cdp.eval(None, FIND_WIDGET_JS).await {
            Ok(Value::String(found)) if !found.is_empty() => return found,
            _ => {
                let _ = wheel(cdp, 500).await;
                tokio::time::sleep(Duration::from_millis(1500)).await;
                if attempt == 6 {
                    if let Ok(diag) = cdp.eval(None, DIAG_JS).await {
                        debug!(target: "engine", diag = %diag, "sponsor page before widget");
                    }
                }
            }
        }
    }
    String::new()
}

/// Poll the widget until it shows the code, or until the first step hands over
/// to the second one.
async fn wait_step(cdp: &Cdp, key: &str, step: u8, budget: Duration) -> QuestResult<Option<String>> {
    let started = Instant::now();
    let mut deadline = started + budget;
    // Countdowns vary per advertiser (70 s, 120 s, 180 s...). When the widget
    // announces one longer than the remaining budget, extend to cover it.
    let hard_cap = started + budget + Duration::from_secs(120);
    let mut last = String::new();
    let mut saw_countdown = false;
    let mut empty_polls = 0u8;
    while Instant::now() < deadline {
        if let Ok(Value::String(visibility)) = cdp.eval(None, "document.visibilityState").await {
            if visibility != "visible" {
                let _ = cdp.call("Page.bringToFront", json!({})).await;
            }
        }
        let _ = wheel(cdp, 70).await;
        tokio::time::sleep(Duration::from_millis(900)).await;
        let text = status(cdp, key).await;
        if text != last {
            debug!(target: "engine", text = %text.replace('\n', " | ").chars().take(120).collect::<String>(), "widget status");
            last = text.clone();
        }
        if let Some(code) = parse_code(&text) {
            return Ok(Some(code));
        }
        if let Some(left) = countdown_secs(&text) {
            saw_countdown = true;
            let wanted = Instant::now() + Duration::from_secs(u64::from(left) + 20);
            if wanted > deadline {
                deadline = wanted.min(hard_cap);
            }
        }
        if step == 1 {
            if text.trim().is_empty() {
                empty_polls = empty_polls.saturating_add(1);
            } else {
                empty_polls = 0;
            }
            // The widget sometimes rebuilds its DOM at the end of step 1: the
            // node stays but the text goes blank. A blank node after a
            // countdown means the step is over; reload and continue at 2/2.
            if saw_countdown && empty_polls >= 3 {
                debug!(target: "engine", "widget went blank after countdown, moving to step 2");
                return Ok(None);
            }
            // Hard fallback: some builds show neither a countdown nor a link
            // at the end of step 1. After 140 s a reload is always safe — the
            // widget keeps its quest state in localStorage.
            if Instant::now().duration_since(started) > Duration::from_secs(140)
                && countdown_secs(&text).is_none()
            {
                debug!(target: "engine", "step 1 timed out without a marker, reloading");
                return Ok(None);
            }
        }
        if step == 1 {
            let low = text.to_lowercase();
            if low.contains("(2/2)") || low.contains("bước 2") || low.contains("link") {
                return Ok(None);
            }
            // The widget marks the end of step 1 with a link whose wording
            // varies per advertiser ("Nhấn vào đây", "Tải lại trang"...). The
            // stable signal is the countdown disappearing while no code has
            // been issued yet.
            if !text.trim().is_empty()
                && countdown_secs(&text).is_none()
                && !text.to_uppercase().contains("LẤY MÃ")
            {
                return Ok(None);
            }
        }
    }
    Err(QuestError::new("widget", "code did not appear before budget"))
}

async fn drive(
    cdp: &Cdp,
    sponsor: &str,
    key_hint: &str,
    refs: &str,
    budget: Duration,
) -> QuestResult<String> {
    for method in ["Page.enable", "Runtime.enable", "Network.enable"] {
        cdp.call(method, json!({}))
            .await
            .map_err(|e| QuestError::new("cdp", e.to_string()))?;
    }
    // disable-devtool closes tabs that expose CDP; ads only cost memory.
    let _ = cdp
        .call(
            "Network.setBlockedURLs",
            json!({"urls": [
                "*disable-devtool*",
                "*googletagmanager*",
                "*google-analytics*",
                "*doubleclick.net*",
                "*.mp4*", "*.webm*", "*.m3u8*",
                "*.woff*", "*.woff2*", "*.ttf*", "*.otf*",
                "*.png*", "*.jpg*", "*.jpeg*", "*.gif*", "*.webp*", "*.avif*", "*.svg*"
            ]}),
        )
        .await;
    let _ = cdp
        .call(
            "Network.setUserAgentOverride",
            json!({"userAgent": UA_MOBILE, "platform": "Linux armv8l"}),
        )
        .await;
    let _ = cdp
        .call(
            "Emulation.setTouchEmulationEnabled",
            json!({"enabled": true, "maxTouchPoints": 5}),
        )
        .await;
    // The widget is a mobile banner: on a 1280-wide viewport its script
    // decides the slot is off-screen and never builds the button. Match the
    // phone geometry the real traffic uses.
    let _ = cdp
        .call(
            "Emulation.setDeviceMetricsOverride",
            json!({"width": 390, "height": 844, "deviceScaleFactor": 3, "mobile": true}),
        )
        .await;
    // A background tab throttles timers: the widget countdown then advances
    // ~1 s per 9 s and the quest never completes. Keep the tab focused and
    // tell the page it is visible.
    let _ = cdp.call("Page.bringToFront", json!({})).await;
    let _ = cdp
        .call("Emulation.setFocusEmulationEnabled", json!({"enabled": true}))
        .await;

    // `check_ref` in the widget script: an empty `ref_domain_list` accepts a
    // bare navigation, a Google list requires a Google referrer. The probe
    // already read which list this key ships, so load with the right one.
    let google = Some("https://www.google.com/");
    let attempts: Vec<(&str, Option<&str>)> = match refs {
        "google" => vec![(sponsor, google)],
        "none" => vec![(sponsor, None)],
        _ => vec![(sponsor, None), (sponsor, google)],
    };
    let mut key = String::new();
    for (url, referrer) in attempts {
        load_and_scroll(cdp, url, referrer).await?;
        // A quest left by a previous visit makes the widget jump straight to
        // step 2 with an expired id; start clean.
        if let Ok(Value::Array(keys)) = cdp.eval(None, CLEAR_QUEST_JS).await {
            if !keys.is_empty() {
                debug!(target: "engine", stale = keys.len(), "clearing stale quest state");
                load_and_scroll(cdp, url, referrer).await?;
            }
        }
        key = find_widget(cdp).await;
        if !key.is_empty() {
            break;
        }
    }
    // Last resort: the widget's own `#ss-<key>` hatch forces the button on.
    if key.is_empty() && !key_hint.is_empty() {
        let forced = format!("{}#ss-{}", sponsor.trim_end_matches('/'), key_hint);
        debug!(target: "engine", url = %forced, "retrying with forced widget hash");
        load_and_scroll(cdp, &forced, None).await?;
        key = find_widget(cdp).await;
    }
    if key.is_empty() {
        return Err(QuestError::new("widget", "sponsor page has no what-on widget"));
    }
    info!(target: "engine", widget = %key, "sponsor widget found");

    if !click_widget(cdp, &key).await {
        return Err(QuestError::new("widget", "LẤY MÃ button did not start the quest"));
    }
    info!(target: "engine", "quest step 1 started");

    let step1 = budget.min(Duration::from_secs(200));
    match wait_step(cdp, &key, 1, step1).await? {
        Some(code) => {
            info!(target: "engine", code = %code, "sponsor code harvested");
            return Ok(code);
        }
        None => debug!(target: "engine", "quest step 1 done, reloading for step 2"),
    }

    // Step 2: reload with the quest id in local storage, then click again.
    load_and_scroll(cdp, sponsor, if refs == "google" { google } else { None }).await?;
    let key = find_widget(cdp).await;
    if key.is_empty() {
        return Err(QuestError::new("widget", "widget missing on step 2 reload"));
    }
    if !click_widget(cdp, &key).await {
        return Err(QuestError::new("widget", "LẤY MÃ button did not start step 2"));
    }
    info!(target: "engine", "quest step 2 started");
    let step2 = budget.min(Duration::from_secs(90));
    match wait_step(cdp, &key, 2, step2).await? {
        Some(code) => {
            info!(target: "engine", code = %code, "sponsor code harvested");
            Ok(code)
        }
        None => Err(QuestError::new("widget", "code did not appear on step 2")),
    }
}

#[cfg(test)]
mod tests {
    use super::{countdown_secs, parse_code};

    #[test]
    fn parses_widget_code() {
        assert_eq!(parse_code("Mã KM: wq8YJK").as_deref(), Some("wq8YJK"));
        assert_eq!(parse_code("Lấy mã sau 14s (2/2)\nMã KM: j1A2eI"), Some("j1A2eI".into()));
        assert_eq!(parse_code("Lấy mã sau 14s"), None);
    }

    #[test]
    fn reads_countdown() {
        assert_eq!(countdown_secs("Vui lòng chờ 21s (1/2)"), Some(21));
        assert_eq!(countdown_secs("LẤY MÃ"), None);
    }
}
