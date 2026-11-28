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
    if (e && (e.querySelector('button') || e.querySelector('.whatoncode') || /LẤY MÃ|GET CODE|Mã KM|\ds/i.test(e.innerText || ''))) return k;
  }
  for (const e of document.querySelectorAll('div[id]')) {
    if (!/^[A-Za-z0-9]{4,12}$/.test(e.id)) continue;
    if (e.querySelector('.whatoncode')) return e.id;
    const b = e.querySelector('button');
    if (b && /LẤY MÃ|GET CODE/i.test(b.innerText || '')) return e.id;
    if (/LẤY MÃ|GET CODE|Mã KM/i.test(e.innerText || '') && (e.innerText || '').length < 120) return e.id;
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

const HAS_QUEST_JS: &str = r#"(() => {
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i);
    if (/_quest$/.test(k)) return true;
  }
  return false;
})()"#;

const STATUS_JS: &str = r#"(() => {
  const e = document.getElementById(KEY);
  let text = e ? (e.innerText || '').trim() : '';
  // Some widget builds move the countdown/code node out of the keyed div and
  // append it to <body> as `.whatoncode` (service-v3 does exactly this after
  // the first press). Read that node too, otherwise the press looks idle and
  // the quest is abandoned while it is actually running.
  if (!text) {
    const live = document.querySelector('.whatoncode');
    if (live) text = (live.innerText || '').trim();
  }
  return text;
})()"#;

const RECT_JS: &str = r#"(() => {
  const e = document.getElementById(KEY);
  if (!e) return null;
  // Instant scroll so the rect read below is final; the tap now follows in
  // ~80 ms instead of the old 800 ms wait.
  e.scrollIntoView({ block: 'center', behavior: 'instant' });
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
        .set("Content-Length", "0")
        .timeout(Duration::from_secs(10))
        .send_bytes(&[])?
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
        tokio::time::sleep(Duration::from_millis(20)).await;
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
        tokio::time::sleep(Duration::from_millis(40)).await;
        cdp.call(
            "Input.dispatchMouseEvent",
            json!({"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1}),
        )
        .await?;
        tokio::time::sleep(Duration::from_millis(10)).await;
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
    let idx = text
        .find("Mã KM")
        .or_else(|| text.find("Code:"))
        .or_else(|| text.find("CODE:"))
        .or_else(|| text.find("Code :"))
        .or_else(|| text.find("CODE :"))?;
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
    // The rect is already scrolled into view; give the compositor a beat, not
    // the old flat 800 ms.
    tokio::time::sleep(Duration::from_millis(80)).await;
    tap(cdp, x, y, touch).await.is_ok()
}

/// The widget is idle when it still offers `LẤY MÃ` or `GET CODE` and no countdown is live.
fn is_idle(text: &str) -> bool {
    let up = text.to_uppercase();
    (up.contains("LẤY MÃ") || up.contains("GET CODE")) && countdown_secs(text).is_none()
}

async fn click_widget(cdp: &Cdp, key: &str) -> bool {
    for attempt in 1..=4 {
        let mut clicked = press_widget(cdp, key).await;
        if !clicked {
            // Fall back to DOM `.click()` when the visual rect is missing or
            // occluded (e.g. sticky ad header) instead of aborting attempt 1.
            clicked = matches!(cdp.eval(None, &with_key(JS_CLICK_JS, key)).await, Ok(Value::Bool(true)));
        }
        // Poll for the quest actually starting instead of sleeping 1.5 s and
        // reading once: a countdown or any non-idle label is the signal. An
        // empty status is not a start — the tap can land on an ad and navigate
        // the tab away, leaving the widget missing.
        if clicked {
            let until = Instant::now() + Duration::from_millis(1500);
            while Instant::now() < until {
                tokio::time::sleep(Duration::from_millis(100)).await;
                let text = status(cdp, key).await;
                if !text.trim().is_empty() && !is_idle(&text) {
                    return true;
                }
            }
        }
        match attempt {
            1 => {
                let _ = cdp.eval(None, &with_key(JS_CLICK_JS, key)).await;
            }
            2 => {
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
                    tokio::time::sleep(Duration::from_millis(120)).await;
                }
                let _ = wheel(cdp, -120).await;
            }
        }
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

/// `performance.timeOrigin` changes with every document, so it tells a fresh
/// page from the previous one without waiting a fixed settle.
async fn document_signature(cdp: &Cdp) -> Option<f64> {
    match cdp.eval(None, "performance.timeOrigin").await {
        Ok(Value::Number(value)) => value.as_f64(),
        _ => None,
    }
}

async fn load_and_scroll(cdp: &Cdp, url: &str, referrer: Option<&str>) -> QuestResult<()> {
    // When navigating to a URL with a `#hash` fragment (such as `#ss-<key>`)
    // that shares the same base document already loaded in the tab, Chrome
    // performs an in-page fragment scroll instead of a document load:
    // `performance.timeOrigin` never changes and the new `Referer` header is
    // never sent. Resetting through `about:blank` when a current document
    // already exists guarantees a real HTTP navigation with the right referrer.
    if document_signature(cdp).await.is_some() {
        if let Ok(Value::String(cur)) = cdp.eval(None, "location.href").await {
            let cur_base = cur.split('#').next().unwrap_or(&cur).trim_end_matches('/');
            let dst_base = url.split('#').next().unwrap_or(url).trim_end_matches('/');
            if !cur_base.is_empty() && cur_base == dst_base {
                let _ = cdp.call("Page.navigate", json!({"url": "about:blank"})).await;
                tokio::time::sleep(Duration::from_millis(60)).await;
            }
        }
    }
    let mut params = json!({"url": url});
    if let Some(referrer) = referrer {
        params["referrer"] = json!(referrer);
    }
    let before = document_signature(cdp).await;
    cdp.call("Page.navigate", params)
        .await
        .map_err(|e| QuestError::new("cdp", e.to_string()))?;
    // Wait for the new document, not for a wall clock: an eval on the old page
    // would still see the previous widget and return before the reload landed.
    match before {
        Some(before) => {
            let until = Instant::now() + Duration::from_secs(10);
            while Instant::now() < until {
                if let Some(now) = document_signature(cdp).await {
                    if now != before {
                        break;
                    }
                }
                tokio::time::sleep(Duration::from_millis(60)).await;
            }
        }
        None => tokio::time::sleep(Duration::from_millis(250)).await,
    }

    // Poll for the widget while nudging lazy scripts into view. The old path
    // slept 5 s and scrolled ten times regardless of whether it was ready.
    let until = Instant::now() + Duration::from_secs(8);
    let mut step = 0usize;
    while Instant::now() < until {
        if let Ok(Value::String(found)) = cdp.eval(None, FIND_WIDGET_JS).await {
            if !found.is_empty() {
                return Ok(());
            }
        }
        // Light scroll roughly once a second so the banner enters the viewport
        // without hammering the page.
        if step % 8 == 0 {
            let _ = wheel(cdp, 240).await;
        }
        tokio::time::sleep(Duration::from_millis(120)).await;
        step += 1;
    }
    Ok(())
}

async fn reload_and_scroll(cdp: &Cdp) -> QuestResult<()> {
    let before = document_signature(cdp).await;
    cdp.call("Page.reload", json!({}))
        .await
        .map_err(|e| QuestError::new("cdp", e.to_string()))?;
    if let Some(before) = before {
        let until = Instant::now() + Duration::from_secs(10);
        while Instant::now() < until {
            if let Some(now) = document_signature(cdp).await {
                if now != before {
                    break;
                }
            }
            tokio::time::sleep(Duration::from_millis(60)).await;
        }
    } else {
        tokio::time::sleep(Duration::from_millis(250)).await;
    }

    let until = Instant::now() + Duration::from_secs(8);
    let mut step = 0usize;
    while Instant::now() < until {
        if let Ok(Value::String(found)) = cdp.eval(None, FIND_WIDGET_JS).await {
            if !found.is_empty() {
                return Ok(());
            }
        }
        if step % 8 == 0 {
            let _ = wheel(cdp, 240).await;
        }
        tokio::time::sleep(Duration::from_millis(120)).await;
        step += 1;
    }
    Ok(())
}

pub fn sponsor_with_hash(sponsor: &str, key_hint: &str) -> String {
    let clean = sponsor.trim_end_matches('/');
    if key_hint.is_empty() {
        clean.to_string()
    } else {
        format!("{clean}#ss-{key_hint}")
    }
}

pub fn check_countdown_stall(
    left: u32,
    last_countdown: &mut Option<u32>,
    last_progress: &mut Instant,
    now: Instant,
    stall_bounce_threshold: Duration,
    stall_abort_threshold: Duration,
) -> Result<bool, &'static str> {
    match *last_countdown {
        Some(prev) if left < prev => {
            *last_countdown = Some(left);
            *last_progress = now;
            Ok(false)
        }
        Some(prev) if left == prev => {
            let stalled = now.duration_since(*last_progress);
            if stalled >= stall_abort_threshold {
                Err("countdown stalled")
            } else if stalled >= stall_bounce_threshold {
                Ok(true) // trigger bounce
            } else {
                Ok(false)
            }
        }
        _ => {
            *last_countdown = Some(left);
            *last_progress = now;
            Ok(false)
        }
    }
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
    // load_and_scroll already waited for the common case, so this loop is a
    // short safety net. Poll fast; scroll only occasionally.
    for attempt in 0..14 {
        match cdp.eval(None, FIND_WIDGET_JS).await {
            Ok(Value::String(found)) if !found.is_empty() => return found,
            _ => {
                if attempt % 4 == 0 {
                    let _ = wheel(cdp, 400).await;
                }
                if attempt == 10 {
                    if let Ok(diag) = cdp.eval(None, DIAG_JS).await {
                        debug!(target: "engine", diag = %diag, "sponsor page before widget");
                    }
                }
                tokio::time::sleep(Duration::from_millis(150)).await;
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

    let mut scroll_dir: usize = 0;
    let mut last_countdown: Option<u32> = None;
    let mut last_progress = Instant::now();

    // The widget text is the signal; 120 ms polling catches a countdown or a
    // code almost immediately. Scrolling and the visibility check are
    // housekeeping, so they stay on a ~1 s cadence.
    let mut last_side_effect = Instant::now() - Duration::from_secs(2);
    while Instant::now() < deadline {
        let tick = Instant::now();
        if tick.duration_since(last_side_effect) >= Duration::from_secs(1) {
            last_side_effect = tick;
            if let Ok(Value::String(visibility)) = cdp.eval(None, "document.visibilityState").await {
                if visibility != "visible" {
                    let _ = cdp.call("Page.bringToFront", json!({})).await;
                }
            }
            // Alternate scroll direction each second tick so pageYOffset keeps
            // changing and satisfies the widget's mouseScroll watchdog without
            // pinning permanently to the document bottom.
            let dy = if scroll_dir % 2 == 0 { 160 } else { -160 };
            scroll_dir += 1;
            let _ = wheel(cdp, dy).await;
        }
        let text = status(cdp, key).await;
        if text != last {
            debug!(target: "engine", text = %text.replace('\n', " | ").chars().take(120).collect::<String>(), "widget status");
            last = text.clone();
        }
        let lower = text.to_lowercase();
        if lower.contains("chưa cập nhật được mã")
            || lower.contains("try again later")
            || lower.contains("code is not ready")
            || lower.contains("error getting code")
            || lower.contains("incorrect")
        {
            return Err(QuestError::new("widget", "widget rejected countdown (timer too fast or session invalid)"));
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

            let now = Instant::now();
            match check_countdown_stall(
                left,
                &mut last_countdown,
                &mut last_progress,
                now,
                Duration::from_secs(18),
                Duration::from_secs(40),
            ) {
                Ok(true) => {
                    debug!(target: "engine", left, "countdown frozen, triggering aggressive scroll bounce");
                    let _ = wheel(cdp, -320).await;
                    tokio::time::sleep(Duration::from_millis(80)).await;
                    let _ = wheel(cdp, 320).await;
                }
                Ok(false) => {}
                Err(msg) => {
                    return Err(QuestError::new("widget", msg));
                }
            }
        }
        if step == 1 {
            if lower.contains("(2/2)") || lower.contains("bước 2") {
                return Ok(None);
            }
            if saw_countdown {
                if let Ok(Value::Bool(true)) = cdp.eval(None, HAS_QUEST_JS).await {
                    debug!(target: "engine", "quest state saved in localStorage, moving to step 2");
                    return Ok(None);
                }
                if countdown_secs(&text).is_none() {
                    if text.trim().is_empty() {
                        empty_polls = empty_polls.saturating_add(1);
                        // The widget sometimes rebuilds its DOM at the end of step 1:
                        // a blank node after a countdown means the step is over.
                        if empty_polls >= 3 {
                            debug!(target: "engine", "widget went blank after countdown, moving to step 2");
                            return Ok(None);
                        }
                    } else if !is_idle(&text) {
                        debug!(target: "engine", "countdown gone without a code, moving to step 2");
                        return Ok(None);
                    }
                } else {
                    empty_polls = 0;
                }
            } else {
                if text.trim().is_empty() {
                    empty_polls = empty_polls.saturating_add(1);
                } else {
                    empty_polls = 0;
                }
                // No countdown ever appeared and the node has been blank for ~4 s:
                // the tap navigated away (ad overlay) or the widget died.
                if empty_polls >= 30 {
                    return Err(QuestError::new("widget", "widget disappeared after the press"));
                }
                // Hard fallback: some builds show neither a countdown nor a link
                // at the end of step 1.
                if Instant::now().duration_since(started) > Duration::from_secs(140)
                    && countdown_secs(&text).is_none()
                {
                    debug!(target: "engine", "step 1 timed out without a marker, reloading");
                    return Ok(None);
                }
            }
        }
        tokio::time::sleep(Duration::from_millis(120)).await;
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
    if let Ok(raw_scale) = std::env::var("L4M_TIMER_SCALE") {
        if let Ok(scale) = raw_scale.trim().parse::<f64>() {
            if scale > 0.05 && scale < 0.99 {
                let patch = format!(
                    "(() => {{ if (window.__l4m_timer_scaled) return; window.__l4m_timer_scaled = true; const orig = window.setInterval.bind(window); window.setInterval = function(fn, delay, ...args) {{ const d = (typeof delay === 'number' && delay >= 500) ? Math.max(100, Math.round(delay * {scale:.3})) : delay; return orig(fn, d, ...args); }}; }})()"
                );
                let _ = cdp
                    .call("Page.addScriptToEvaluateOnNewDocument", json!({ "source": patch }))
                    .await;
            }
        }
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
    let mut target_urls = Vec::new();
    // Try the clean sponsor URL with a Google referrer first so `jscd.href`
    // matches what Link4M expects (`#ss-<key>` is kept strictly as fallback).
    target_urls.push(sponsor.to_string());
    if !key_hint.is_empty() {
        target_urls.push(sponsor_with_hash(sponsor, key_hint));
    }

    let mut attempts: Vec<(String, Option<&str>)> = Vec::new();
    for u in target_urls {
        match refs {
            "google" => attempts.push((u, google)),
            "none" => attempts.push((u, None)),
            _ => {
                // Google referrer satisfies both `ref_domain_list = ["google.com"]`
                // and `ref_domain_list = []` on service-v2/v3 widgets, so try
                // it first when the probe could not determine `refs`.
                attempts.push((u.clone(), google));
                attempts.push((u, None));
            }
        }
    }
    let mut key = String::new();
    let mut active_url = sponsor.to_string();
    let mut active_ref: Option<&str> = if refs == "none" { None } else { google };
    for (url, referrer) in &attempts {
        load_and_scroll(cdp, url, *referrer).await?;
        // A quest left by a previous visit makes the widget jump straight to
        // step 2 with an expired id; start clean.
        if let Ok(Value::Array(keys)) = cdp.eval(None, CLEAR_QUEST_JS).await {
            if !keys.is_empty() {
                debug!(target: "engine", stale = keys.len(), "clearing stale quest state");
                reload_and_scroll(cdp).await?;
            }
        }
        key = find_widget(cdp).await;
        if !key.is_empty() {
            active_url = url.clone();
            active_ref = *referrer;
            break;
        }
    }
    // Last resort: the widget's own `#ss-<key>` hatch forces the button on.
    if key.is_empty() && !key_hint.is_empty() {
        let forced = sponsor_with_hash(sponsor, key_hint);
        debug!(target: "engine", url = %forced, "retrying with forced widget hash and document reload");
        load_and_scroll(cdp, &forced, google).await?;
        reload_and_scroll(cdp).await?;
        key = find_widget(cdp).await;
        if !key.is_empty() {
            active_url = forced;
            active_ref = google;
        }
    }
    if key.is_empty() {
        return Err(QuestError::new("widget", "sponsor page has no what-on widget"));
    }
    info!(target: "engine", widget = %key, "sponsor widget found");

    if !click_widget(cdp, &key).await {
        // A mis-aimed tap can hit an ad overlay and navigate the tab away from
        // the sponsor; a fresh load plus one more press is much cheaper than
        // losing the campaign code for this job.
        debug!(target: "engine", "press did not start the quest, reloading sponsor once");
        load_and_scroll(cdp, &active_url, active_ref).await?;
        let retry_key = find_widget(cdp).await;
        if retry_key.is_empty() || !click_widget(cdp, &retry_key).await {
            return Err(QuestError::new("widget", "LẤY MÃ button did not start the quest"));
        }
        key = retry_key;
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

    // Step 2: reload with the quest id in local storage, preserving the exact
    // URL (including `#ss-<key>`) and referrer that activated the widget in Step 1.
    load_and_scroll(cdp, &active_url, active_ref).await?;
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
    use super::{countdown_secs, is_idle, parse_code};

    #[test]
    fn idle_button_detection() {
        assert!(is_idle("LẤY MÃ"));
        assert!(!is_idle("Lấy mã sau 14s (1/2)"));
        assert!(!is_idle("Mã KM: wq8YJK"));
        assert!(!is_idle(""));
    }

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

    #[test]
    fn test_sponsor_with_hash() {
        assert_eq!(
            super::sponsor_with_hash("https://giaiphapdokiem.vn/", "nJBenYY"),
            "https://giaiphapdokiem.vn#ss-nJBenYY"
        );
        assert_eq!(
            super::sponsor_with_hash("https://example.com/sub", "key123"),
            "https://example.com/sub#ss-key123"
        );
        assert_eq!(
            super::sponsor_with_hash("https://example.com", ""),
            "https://example.com"
        );
    }

    #[test]
    fn test_countdown_stall_detection() {
        use std::time::{Duration, Instant};

        let start = Instant::now();
        let mut last_progress = start;
        let mut last_countdown = None;

        let r1 = super::check_countdown_stall(
            45,
            &mut last_countdown,
            &mut last_progress,
            start,
            Duration::from_secs(18),
            Duration::from_secs(40),
        );
        assert_eq!(r1, Ok(false));

        let r2 = super::check_countdown_stall(
            44,
            &mut last_countdown,
            &mut last_progress,
            start + Duration::from_secs(1),
            Duration::from_secs(18),
            Duration::from_secs(40),
        );
        assert_eq!(r2, Ok(false));

        let r3 = super::check_countdown_stall(
            44,
            &mut last_countdown,
            &mut last_progress,
            start + Duration::from_secs(11),
            Duration::from_secs(18),
            Duration::from_secs(40),
        );
        assert_eq!(r3, Ok(false));

        let r4 = super::check_countdown_stall(
            44,
            &mut last_countdown,
            &mut last_progress,
            start + Duration::from_secs(21),
            Duration::from_secs(18),
            Duration::from_secs(40),
        );
        assert_eq!(r4, Ok(true));

        let r5 = super::check_countdown_stall(
            44,
            &mut last_countdown,
            &mut last_progress,
            start + Duration::from_secs(42),
            Duration::from_secs(18),
            Duration::from_secs(40),
        );
        assert_eq!(r5, Err("countdown stalled"));
    }
}
