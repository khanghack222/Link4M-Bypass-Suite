//! Link4M flow, native: navigate, read the page, solve the reCAPTCHA audio
//! challenge with local whisper, then hand back the destination URL.
//!
//! No Playwright, no Python, no captcha API. The only external service is the
//! page itself and Google's reCAPTCHA, exactly like a normal browser. An
//! optional browserless solver (`RC_SOLVER_CMD`) can mint the token instead;
//! the page still owns the final POST.

use crate::asr::Asr;
use crate::codes;
use crate::instr;
use crate::quest;
use crate::rcsolver;
use std::collections::{HashMap, HashSet};
use std::sync::{Arc, Mutex};
use crate::cdp::Cdp;
use crate::proxy::Proxy;
use base64::Engine;
use serde_json::{json, Value};
use std::time::{Duration, Instant};
use tracing::{debug, info, warn};

/// Value of a query parameter in a URL, without pulling in the `url` crate at
/// the call sites that only need `k=` or `hl=`.
fn url_param(url: &str, key: &str) -> Option<String> {
    let query = url.split_once('?')?.1;
    let query = query.split('#').next().unwrap_or(query);
    for pair in query.split('&') {
        let (name, value) = pair.split_once('=').unwrap_or((pair, ""));
        if name == key && !value.is_empty() {
            return Some(value.to_string());
        }
    }
    None
}

#[derive(Debug, Clone)]
pub struct FlowError {
    pub kind: &'static str,
    pub message: String,
}

impl FlowError {
    pub fn new(kind: &'static str, message: impl Into<String>) -> Self {
        Self { kind, message: message.into() }
    }
}

impl std::fmt::Display for FlowError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}: {}", self.kind, self.message)
    }
}

impl std::error::Error for FlowError {}

type FlowResult<T> = std::result::Result<T, FlowError>;

/// Adaptive poll cadence: a freshly loaded page usually settles in tens of
/// milliseconds, so start at 60 ms and back off to 400 ms. One flat interval
/// either spins the CDP socket on a dead page or adds latency to a fast one.
fn poll_delay(step: usize) -> Duration {
    const STEPS: [u64; 5] = [60, 100, 150, 250, 400];
    Duration::from_millis(STEPS[step.min(STEPS.len() - 1)])
}

const STATE_JS: &str = r#"(() => {
  const form = document.getElementById('main-form') || document.getElementById('main-form-2');
  const pw = form ? form.querySelector('input[name=password]') : null;
  const codeInput = form ? form.querySelector('input[name=code]') : null;
  const campInput = form ? form.querySelector('input[name=campaign_id]') : null;
  const wrapper = document.getElementById('captcha-html-wrapper');
  const pwVisible = !!(pw && (pw.offsetWidth || pw.offsetHeight));
  let err = '';
  const title = document.title || '';
  if (!form && !wrapper && !pwVisible && document.readyState !== 'loading') {
    const low = ((title + ' ' + (document.body ? document.body.innerText : '')) || '').toLowerCase();
    if (!low.includes('just a moment')) {
      if (low.includes('vượt quá giới hạn') || low.includes('access limit') || low.includes('too many requests') || low.includes('tần suất truy cập')) {
        err = 'rate_limit';
      } else if (low.includes('không tồn tại') || low.includes('does not exist') || low.includes('đã bị xóa') || low.includes('đã bị xoá') || low.includes('page not found') || /^404\b/.test(title.trim())) {
        err = 'not_found';
      }
    }
  }
  return {
    form: !!form,
    captcha: !!wrapper && !pwVisible,
    password: pwVisible,
    code: codeInput ? codeInput.value : (wrapper ? (wrapper.getAttribute('data-code') || '') : ''),
    campaign: campInput ? campInput.value : '',
    title,
    err
  };
})()"#;

pub const WARP_SPOOF_JS: &str = r#"
(() => {
  if (window.__l4m_warp_patched || typeof window.fetch !== 'function') return;
  window.__l4m_warp_patched = true;
  const origFetch = window.fetch.bind(window);
  window.fetch = async function(...args) {
    const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url ? args[0].url : '');
    if (url.includes('cdn-cgi/trace')) {
      return new Response('fl=mock\nh=1.1.1.1\nip=127.0.0.1\nwarp=off\ngateway=off\n', {
        status: 200,
        headers: { 'Content-Type': 'text/plain' }
      });
    }
    return origFetch(...args);
  };
})();
"#;

/// Sitekey of the widget that lives in the campaign form.
///
/// The page carries two or three reCAPTCHA widgets with *different* sitekeys
/// (campaign form, report modal). reCAPTCHA renders the challenge iframe at
/// body level, outside the widget container, so the challenge cannot be traced
/// back to its form by walking the DOM — the sitekey is the only stable link
/// between a `bframe?k=...` and the form that will accept its token.
const CAMPAIGN_SITEKEY_JS: &str = r#"(() => {
  const form = document.getElementById('main-form') || document.getElementById('main-form-2') || document.getElementById('main-form-3');
  const rc = document.getElementById('recaptcha') || document.getElementById('recaptcha-2');

  // 1. Check anchor frame k= inside main form or #recaptcha
  const anchor = (form ? form.querySelector('iframe[src*="/anchor"]') : null) || (rc ? rc.querySelector('iframe[src*="/anchor"]') : null);
  if (anchor && anchor.src) {
    const match = anchor.src.match(/[?&]k=([^&]+)/);
    if (match && match[1] && match[1].length > 10) return decodeURIComponent(match[1]);
  }

  // 2. Check window.recaptcha_key if set dynamically (must not match report modal key if report modal exists)
  const reportEl = document.getElementById('recaptcha-report');
  const reportKey = reportEl ? (reportEl.getAttribute('data-sitekey') || '').trim() : '';
  if (typeof recaptcha_key === 'string' && recaptcha_key.trim().length > 10) {
    const k = recaptcha_key.trim();
    if (!reportKey || k !== reportKey) {
      return k;
    }
  }

  // 3. Check data-sitekey on main form or #recaptcha
  if (form) {
    const box = form.querySelector('[data-sitekey]');
    const k = box ? (box.getAttribute('data-sitekey') || '').trim() : '';
    if (k.length > 10) return k;
  }
  if (rc) {
    const k = (rc.getAttribute('data-sitekey') || '').trim();
    if (k.length > 10) return k;
  }

  // 4. Fallback to window.recaptcha_key
  if (typeof recaptcha_key === 'string' && recaptcha_key.trim().length > 10) {
    return recaptcha_key.trim();
  }

  // 5. Global [data-sitekey] fallback, strictly skipping #modal-report and #recaptcha-report
  const candidates = Array.from(document.querySelectorAll('[data-sitekey]'));
  for (const el of candidates) {
    if (el.id === 'recaptcha-report' || (el.closest && el.closest('#modal-report, #modal-report-form, #recaptcha-report'))) {
      continue;
    }
    const k = (el.getAttribute('data-sitekey') || '').trim();
    if (k.length > 10) return k;
  }

  return '';
})()"#;

const TOKEN_JS: &str = r#"(() => {
  const form = document.getElementById('main-form') || document.getElementById('main-form-2') || document.getElementById('main-form-3');
  if (form) {
    const own = form.querySelector('textarea[name=g-recaptcha-response]');
    if (own && own.value && own.value.length > 50) return own.value;
  }
  const rc = document.getElementById('recaptcha') || document.getElementById('recaptcha-2');
  if (rc) {
    const t = rc.querySelector('textarea[name=g-recaptcha-response]');
    if (t && t.value && t.value.length > 50) return t.value;
  }
  return '';
})()"#;

/// One round-trip for the token fast path: `len` and `token` are strictly read
/// from the campaign form / #recaptcha container (never from the report modal).
const TOKEN_PROBE_JS: &str = r#"(() => {
  const form = document.getElementById('main-form') || document.getElementById('main-form-2') || document.getElementById('main-form-3');
  const rc = document.getElementById('recaptcha') || document.getElementById('recaptcha-2');
  let token = '';
  if (form) {
    const own = form.querySelector('textarea[name=g-recaptcha-response]');
    if (own && own.value && own.value.length > 50) token = own.value;
  }
  if (!token && rc) {
    const t = rc.querySelector('textarea[name=g-recaptcha-response]');
    if (t && t.value && t.value.length > 50) token = t.value;
  }
  return {len: token.length, token: token};
})()"#;

/// Landing-page boot signals. Waits specifically for #main-form / #recaptcha's
/// own anchor iframe or rendered container, NOT the static report modal's anchor.
const BOOT_JS: &str = r#"(() => {
  const form = document.getElementById('main-form') || document.getElementById('main-form-2') || document.getElementById('main-form-3');
  const rc = document.getElementById('recaptcha') || document.getElementById('recaptcha-2');
  const anchorInForm = form ? !!form.querySelector('iframe[src*="/anchor"]') : false;
  const anchorInRc = rc ? !!rc.querySelector('iframe[src*="/anchor"]') : false;
  const rcRendered = rc ? (rc.children.length > 0 || !!rc.querySelector('iframe')) : false;
  return {
    complete: document.readyState === 'complete',
    grecaptcha: typeof grecaptcha !== 'undefined',
    form: !!form,
    anchor: anchorInForm || anchorInRc,
    rendered: rcRendered
  };
})()"#;

const ANCHOR_CLICK_JS: &str = r#"(() => {
  const el = document.getElementById('recaptcha-anchor');
  if (!el) return false;
  el.click();
  return true;
})()"#;

const AUDIO_BUTTON_JS: &str = r#"(() => {
  const el = document.getElementById('recaptcha-audio-button');
  if (!el) return false;
  el.click();
  return true;
})()"#;

const AUDIO_READY_JS: &str = r#"(() => {
  if (!document.getElementById('audio-response')) return false;
  const srcEl = document.querySelector('#audio-source') || document.querySelector('audio');
  const src = srcEl ? (srcEl.src || srcEl.getAttribute('src') || '') : '';
  const dl = document.querySelector('.rc-audiochallenge-tdownload-link');
  const href = dl ? (dl.href || '') : '';
  return !!(src || href);
})()"#;

const CHALLENGE_JS: &str = r#"(() => {
  return !!(document.getElementById('rc-imageselect-target') ||
            document.getElementById('audio-response') ||
            document.getElementById('rc-audiochallenge-response-field'));
})()"#;

/// Fetch the challenge clip, decode it and resample to 16 kHz PCM in one page
/// call. Previously the clip went page → Rust → page (twice, base64) before
/// whisper saw it; one crossing is enough.
const AUDIO_PCM_JS: &str = r#"(async () => {
  const el = document.querySelector('#audio-source') || document.querySelector('audio');
  let src = el ? (el.src || el.getAttribute('src') || '') : '';
  if (!src) {
    const dl = document.querySelector('.rc-audiochallenge-tdownload-link');
    src = dl ? dl.href : '';
  }
  if (!src) return '';
  const response = await fetch(src, {credentials: 'omit'});
  if (!response.ok) return 'ERR' + response.status;
  const bytes = new Uint8Array(await response.arrayBuffer());
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  let buffer;
  try { buffer = await ctx.decodeAudioData(bytes.buffer); }
  catch (e) { return ''; }
  const channel = buffer.getChannelData(0);
  const srcRate = buffer.sampleRate, dstRate = 16000;
  const n = Math.floor(channel.length * dstRate / srcRate);
  const out = new Int16Array(n);
  for (let i = 0; i < n; i++) {
    const x = i * srcRate / dstRate;
    const i0 = Math.floor(x), i1 = Math.min(i0 + 1, channel.length - 1), f = x - i0;
    const v = channel[i0] * (1 - f) + channel[i1] * f;
    out[i] = Math.max(-1, Math.min(1, v)) * 32767;
  }
  if (ctx.close) ctx.close();
  const raw = new Uint8Array(out.buffer);
  let binaryOut = '';
  for (let i = 0; i < raw.length; i += 0x8000) {
    binaryOut += String.fromCharCode.apply(null, raw.subarray(i, i + 0x8000));
  }
  return btoa(binaryOut);
})()"#;

const AUDIO_ERROR_JS: &str = r#"(() => {
  const el = document.querySelector('.rc-audiochallenge-error-message');
  return el ? (el.innerText || '').trim() : '';
})()"#;

/// Fill the transcript and press verify in a single evaluation. The old path
/// spent a 250 ms sleep between two round-trips.
const AUDIO_FILL_VERIFY_JS: &str = r#"(() => {
  const el = document.getElementById('audio-response');
  if (!el) return false;
  el.focus();
  el.value = TEXT;
  el.dispatchEvent(new Event('input', {bubbles: true}));
  el.dispatchEvent(new Event('change', {bubbles: true}));
  const button = document.getElementById('recaptcha-verify-button');
  if (button) button.click();
  return true;
})()"#;

/// Snapshot used to tell when the reload button has actually swapped the clip.
const CLIP_STATE_JS: &str = r#"(() => {
  const el = document.querySelector('#audio-source') || document.querySelector('audio');
  const response = document.getElementById('audio-response');
  return {
    src: el ? (el.src || el.getAttribute('src') || '') : '',
    value: response ? (response.value || '') : ''
  };
})()"#;

const RELOAD_CLICK_JS: &str = r#"(() => {
  const el = document.getElementById('recaptcha-reload-button');
  if (!el) return false;
  el.click();
  return true;
})()"#;

const LINK_CLICK_JS: &str = r#"(() => {
  const el = document.querySelector('.get-link');
  if (!el) return false;
  if ((el.className || '').includes('disabled')) return false;
  el.click();
  return true;
})()"#;

const FINISH_STATE_JS: &str = r#"(() => {
  const form = document.getElementById('main-form') || document.getElementById('main-form-2') || document.getElementById('main-form-3');
  const el = document.querySelector('.get-link');
  const cls = el ? String(el.className || '') : '';
  let token = 0;
  if (form) {
    const t = form.querySelector('textarea[name=g-recaptcha-response]');
    token = t ? (t.value || '').length : 0;
  }
  if (!token) {
    const rc = document.getElementById('recaptcha') || document.getElementById('recaptcha-2');
    if (rc) {
      const t = rc.querySelector('textarea[name=g-recaptcha-response]');
      token = t ? (t.value || '').length : 0;
    }
  }
  return {
    url: location.href,
    href: el ? (el.getAttribute('href') || '') : '',
    has: !!el,
    disabled: cls.includes('disabled'),
    cls: cls.slice(0, 80),
    token: token,
    body: document.body ? (document.body.innerText || '').slice(-240) : ''
  };
})()"#;

/// Same POST the page's own `checkCaptcha`/`checkPassword` handlers send.
/// When password/code exists, posts to `/links/get-link-info`;
/// when captcha-only (no password input), posts to `/links/check-captcha`.
const POST_LINK_INFO_JS: &str = r#"(async () => {
  const form = document.getElementById('main-form') || document.getElementById('main-form-2') || document.getElementById('main-form-3');
  if (!form) return JSON.stringify({error: 'no form'});
  const api = (typeof api_domain === 'string' && api_domain) ? api_domain : 'https://s1.link4m.app';
  const params = new URLSearchParams(new FormData(form));
  const pwInput = form.querySelector('input[name=password]');
  const injected = window.__l4m_code || '';
  if (injected) params.set('password', injected);
  const token = (form.querySelector('textarea[name=g-recaptcha-response]') || {}).value || '';
  if (token) params.set('g-recaptcha-response', token);
  const hasPassword = !!(pwInput || injected);
  const endpoint = hasPassword ? '/links/get-link-info' : '/links/check-captcha';
  const body = params.toString();
  try {
    const response = await fetch(api + endpoint, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'x-requested-with': 'XMLHttpRequest'
      },
      body: body
    });
    const text = await response.text();
    return text.slice(0, 4000);
  } catch (err) {
    return JSON.stringify({error: String(err)});
  }
})()"#;

pub struct Flow<'a> {
    cdp: &'a Cdp,
    asr: Arc<Asr>,
    alias: String,
    code: Option<String>,
    port: u16,
    proxy: Option<Proxy>,
    deadline: Instant,
    /// Isolated-world execution contexts keyed by frame id. Creating a world
    /// costs a CDP round-trip on every anchor/challenge poll; the cache lives
    /// until a top-level navigation destroys the worlds.
    contexts: Mutex<HashMap<String, i64>>,
}

impl<'a> Flow<'a> {
    pub fn new(
        cdp: &'a Cdp,
        asr: Arc<Asr>,
        alias: &str,
        code: Option<String>,
        port: u16,
        proxy: Option<Proxy>,
        budget: Duration,
    ) -> Self {
        Self {
            cdp,
            asr,
            alias: alias.to_string(),
            code,
            port,
            proxy,
            deadline: Instant::now() + budget,
            contexts: Mutex::new(HashMap::new()),
        }
    }

    pub async fn run(&mut self) -> FlowResult<String> {
        let started = Instant::now();
        self.cdp
            .call("Page.enable", json!({}))
            .await
            .map_err(|e| FlowError::new("cdp", e.to_string()))?;
        self.cdp
            .call("Runtime.enable", json!({}))
            .await
            .map_err(|e| FlowError::new("cdp", e.to_string()))?;
        self.cdp
            .call("DOM.enable", json!({}))
            .await
            .map_err(|e| FlowError::new("cdp", e.to_string()))?;

        let spoof_warp = std::env::var("L4M_SPOOF_WARP")
            .map(|v| v != "0")
            .unwrap_or(true);
        if spoof_warp {
            let res = self
                .cdp
                .call(
                    "Page.addScriptToEvaluateOnNewDocument",
                    json!({ "source": WARP_SPOOF_JS }),
                )
                .await;
            if let Err(err) = res {
                warn!(target: "engine", "failed to install warp spoof script: {err}");
            }
        }

        let url = format!("https://link4m.net/go/{}", self.alias);
        self.navigate(&url).await?;

        // The first navigation can land on an error or interstitial page. One
        // renavigation normally clears it and is much cheaper than failing a
        // job that still has budget left.
        let mut state = match self.wait_for_page().await {
            Ok(state) => state,
            Err(err) if (err.kind == "page" || err.kind == "cdp") && self.remaining() > Duration::from_secs(60) => {
                warn!(target: "engine", alias = %self.alias, "page not ready ({err}), renavigating once");
                self.navigate_and_settle(&url).await?;
                self.wait_for_page().await?
            }
            Err(err) => return Err(err),
        };
        // Test/debug aid: keep reloading until the page serves a given campaign.
        // When Link4M serves a captcha-only page there is no campaign to match,
        // so pinning is skipped instead of burning 24 reloads on a mismatch.
        if state.password {
            if let Ok(want) = std::env::var("L4M_CAMPAIGN") {
            // Comma-separated list: pin a set (e.g. every campaign that already
            // has a proven code) instead of one rotating id.
            let wanted: Vec<&str> = want
                .split(',')
                .map(str::trim)
                .filter(|id| !id.is_empty())
                .collect();
            if !wanted.is_empty() {
                let mut tries = 0;
                while !wanted.contains(&state.campaign.as_str()) && tries < 24 {
                    if self.remaining() < Duration::from_secs(90) {
                        debug!(target: "engine", "campaign pin: out of budget before a match");
                        break;
                    }
                    tries += 1;
                    debug!(target: "engine", want = %want, got = %state.campaign, tries, "campaign mismatch, re-rolling");
                    // The document stamp wait replaces the fixed 1.8 s settle;
                    // wait_for_page then handles however long the new page takes.
                    self.navigate_and_settle(&url).await?;
                    state = self.wait_for_page().await?;
                }
                if !wanted.contains(&state.campaign.as_str()) {
                    return Err(FlowError::new("campaign", format!("never landed on campaign {want}")));
                }
            }
            }
        }
        if !state.password && !state.captcha {
            // An error/interstitial page can parse cleanly and still carry no
            // form. One more navigation is cheap compared with failing work
            // that has budget left.
            if self.remaining() > Duration::from_secs(60) {
                warn!(target: "engine", alias = %self.alias, "page has no form, renavigating once");
                self.navigate_and_settle(&url).await?;
                state = self.wait_for_page().await?;
            }
        }
        if !state.password && !state.captcha {
            return Err(FlowError::new("page", "no captcha or code form on page"));
        }
        let page_mark = Instant::now();
        // `prepared` holds (campaign id, code) while the page wants a sponsor
        // code. A code that unlocks a destination is cached for the next alias
        // on the same campaign; a rejected one is dropped and re-harvested.
        let mut prepared = self.ensure_code_roll(&url).await?;
        if let Some((_, code)) = &prepared {
            info!(target: "engine", alias = %self.alias, code = %code, "campaign code filled");
        }
        // The site swaps the code form for the captcha once its handler sees the
        // code. Poll for that transition instead of paying a flat 1.2 s; the
        // widget is normally armed before the eval even returns.
        self.await_widget_arm(Duration::from_millis(1200)).await;
        let code_mark = Instant::now();
        info!(target: "engine", alias = %self.alias, "captcha step");

        let mut attempt = 0;
        let mut last_err: Option<FlowError> = None;
        let mut bad_campaigns: HashSet<String> = HashSet::new();
        while attempt < 2 && self.remaining().as_secs() > 8 {
            attempt += 1;
            if attempt > 1 {
                debug!(target: "engine", attempt, "re-navigating page for a fresh anchor/campaign");
                self.navigate_and_settle(&url).await?;
                prepared = self.ensure_code_roll_excluding(&url, &bad_campaigns).await?;
            }
            let campaign_key = self.campaign_sitekey().await;
            if let Some(key) = &campaign_key {
                debug!(target: "engine", key = %key, "campaign sitekey");
            }
            if !self.click_anchor(campaign_key.as_deref()).await? {
                warn!(target: "engine", "anchor not found");
                tokio::time::sleep(Duration::from_millis(150)).await;
                continue;
            }

            // Optional browserless solver: mint the token over Google's API
            // chain while the page's own challenge is still arming. The token
            // is injected into this page by `finish`, so the Link4M session
            // that posts it remains ours.
            let sitekey = rcsolver::sitekey(self.cdp).await;
            let mut external = rcsolver::spawn(url.clone(), sitekey);

            // Race the token against the challenge panel: a checkbox that passes
            // silently returns a token in a second or two, while a challenge
            // (audio/grid) opens in the same window. The first 1.2 s belongs to
            // the fast path: one eval, 80 ms cadence, no frame-tree walk. Only
            // after that does a challenge frame get looked for, and its isolated
            // world is cached across polls.
            let mut token: Option<String> = None;
            let watch = (Instant::now() + Duration::from_secs(10)).min(self.deadline);
            let watch_start = Instant::now();
            let mut probe_step = 0usize;
            // Widgets proven to hand their token to the wrong form. Skipping
            // them lets the same attempt try the campaign widget instead of
            // reloading the page and solving the same wrong one again.
            let skip: HashSet<String> = HashSet::new();
            while Instant::now() < watch && token.is_none() {
                if let Ok(value) = self.cdp.eval(None, TOKEN_PROBE_JS).await {
                    let len = value.get("len").and_then(Value::as_u64).unwrap_or(0);
                    let found = value.get("token").and_then(Value::as_str).unwrap_or("");
                    if len > 50 && found.len() > 50 {
                        token = Some(found.to_string());
                        break;
                    }
                }
                if watch_start.elapsed() >= Duration::from_millis(250) {
                    if let Some(frame) = self.challenge_frame(campaign_key.as_deref(), &skip).await? {
                        debug!(target: "engine", frame = %frame.0, "challenge open");
                        match self.solve_audio(&frame.0).await {
                            Ok(found) => {
                                info!(target: "engine", len = found.len(), "audio solved token accepted");
                                token = Some(found);
                                break;
                            }
                            Err(err) => {
                                warn!(target: "engine", "audio attempt failed: {err}");
                                last_err = Some(err);
                            }
                        }
                    }
                }
                let delay = if watch_start.elapsed() < Duration::from_millis(250) {
                    Duration::from_millis(80)
                } else {
                    poll_delay(probe_step)
                };
                tokio::time::sleep(delay).await;
                probe_step += 1;
            }

            if token.is_none() {
                if let Some(mut handle) = external.take() {
                    let budget = Duration::from_secs(
                        std::env::var("RC_SOLVER_TIMEOUT")
                            .ok()
                            .and_then(|raw| raw.trim().parse::<u64>().ok())
                            .unwrap_or(180)
                            .clamp(30, 900),
                    )
                    .min(self.remaining());
                    match tokio::time::timeout(budget, &mut handle).await {
                        Ok(Ok(Some(found))) => {
                            info!(target: "engine", len = found.len(), "external token ready");
                            token = Some(found);
                        }
                        Ok(Ok(None)) => debug!(target: "engine", "external solver gave no token"),
                        Ok(Err(err)) => debug!(target: "engine", error = %err, "external solver task failed"),
                        Err(_) => {
                            debug!(target: "engine", "external solver wait timed out");
                            handle.abort();
                        }
                    }
                }
            } else if let Some(handle) = external.take() {
                handle.abort();
            }

            let Some(token) = token else { continue };
            debug!(target: "engine", len = token.len(), "token ready");
            let finish_mark = Instant::now();
            match self.finish(token).await {
                Ok(destination) => {
                    if let Some((campaign, code)) = &prepared {
                        codes::put(campaign, code);
                    }
                    info!(
                        target: "engine",
                        alias = %self.alias,
                        total_ms = started.elapsed().as_millis() as u64,
                        page_ms = page_mark.duration_since(started).as_millis() as u64,
                        code_ms = code_mark.duration_since(page_mark).as_millis() as u64,
                        captcha_ms = finish_mark.duration_since(code_mark).as_millis() as u64,
                        finish_ms = finish_mark.elapsed().as_millis() as u64,
                        "flow timing"
                    );
                    return Ok(destination);
                }
                Err(err) => {
                    warn!(target: "engine", "token did not unlock: {err}");
                    if err.kind == "code" {
                        if let Some((campaign, _)) = &prepared {
                            warn!(target: "engine", campaign = %campaign, "cached code rejected, invalidating and excluding campaign");
                            codes::invalidate(campaign);
                            instr::forget(campaign);
                            bad_campaigns.insert(campaign.clone());
                        }
                        self.code = None;
                        return Err(err);
                    }
                    if err.kind == "rate_limit" || (prepared.is_none() && err.kind == "captcha" && attempt >= 2) {
                        return Err(err);
                    }
                    last_err = Some(err);
                }
            }
        }
        Err(last_err.unwrap_or_else(|| FlowError::new("captcha", "captcha not solved in budget")))
    }

    /// Campaigns rotate and some of them have no usable sponsor (dead widget,
    /// masked domain OCR cannot resolve). Instead of failing the job, roll a
    /// fresh campaign and try again.
    async fn ensure_code_roll(&mut self, url: &str) -> FlowResult<Option<(String, String)>> {
        let empty = HashSet::new();
        self.ensure_code_roll_excluding(url, &empty).await
    }

    async fn ensure_code_roll_excluding(
        &mut self,
        url: &str,
        excluded: &HashSet<String>,
    ) -> FlowResult<Option<(String, String)>> {
        let mut last: Option<FlowError> = None;
        for attempt in 0..2 {
            let state = self.wait_for_page().await?;
            if state.password && excluded.contains(&state.campaign) {
                debug!(target: "engine", campaign = %state.campaign, "skipping excluded campaign, failing fast");
                return Err(last.unwrap_or_else(|| {
                    FlowError::new("needs_code", format!("campaign {} already failed", state.campaign))
                }));
            }
            match self.ensure_code().await {
                Ok(prepared) => return Ok(prepared),
                Err(err) if err.kind == "needs_code" => {
                    warn!(target: "engine", attempt = attempt + 1, "campaign has no usable sponsor: {err}");
                    last = Some(err);
                    if attempt == 0 && self.remaining() >= Duration::from_secs(95) {
                        self.navigate_and_settle(url).await?;
                    } else {
                        break;
                    }
                }
                Err(err) => return Err(err),
            }
        }
        Err(last.unwrap_or_else(|| FlowError::new("needs_code", "no campaign served a code")))
    }

    /// Resolve the sponsor code for the campaign currently on screen: the CLI
    /// override first, then a proven code from the cache, then a fresh harvest
    /// behind a per-campaign lock so concurrent jobs share one quest.
    async fn ensure_code(&mut self) -> FlowResult<Option<(String, String)>> {
        let state = self.wait_for_page().await?;
        if !state.password {
            return Ok(None);
        }
        let campaign = state.campaign.clone();
        if let Some(code) = self
            .code
            .as_deref()
            .map(str::trim)
            .filter(|c| !c.is_empty())
            .map(str::to_string)
        {
            self.fill_code(&code).await?;
            return Ok(Some((campaign, code)));
        }
        if let Some(code) = codes::get(&campaign) {
            info!(target: "engine", campaign = %campaign, "campaign code cache hit");
            self.fill_code(&code).await?;
            self.code = Some(code.clone());
            return Ok(Some((campaign, code)));
        }
        let lock = codes::lock_for(&campaign).await;
        let _guard = lock.lock().await;
        if let Some(code) = codes::get(&campaign) {
            info!(target: "engine", campaign = %campaign, "campaign code cache hit after wait");
            self.fill_code(&code).await?;
            self.code = Some(code.clone());
            return Ok(Some((campaign, code)));
        }
        let Some(code) = self.harvest_code(&campaign).await else {
            return Err(FlowError::new(
                "needs_code",
                "campaign code unavailable: sponsor widget did not return one",
            ));
        };
        self.fill_code(&code).await?;
        self.code = Some(code.clone());
        Ok(Some((campaign, code)))
    }

    /// Ask the sponsored page for its campaign code.
    async fn harvest_code(&self, campaign_id: &str) -> Option<String> {
        let campaign = instr::discover(self.cdp, self.proxy.clone()).await?;
        let budget = self.remaining().min(Duration::from_secs(260));
        if budget.as_secs() < 60 {
            return None;
        }
        let keyword = if campaign.keyword.is_empty() {
            campaign
                .sponsor
                .split('.')
                .rev()
                .nth(1)
                .unwrap_or("")
                .to_string()
        } else {
            campaign.keyword.clone()
        };
        let sponsor_url = if campaign.sponsor.contains('/') {
            format!("https://{}", campaign.sponsor)
        } else {
            format!("https://{}/", campaign.sponsor)
        };
        info!(target: "engine", alias = %self.alias, sponsor = %campaign.sponsor, keyword = %keyword, "harvesting sponsor code");
        match quest::harvest(self.port, &sponsor_url, &keyword, &campaign.key, &campaign.refs, budget).await {
            Ok(code) => Some(code),
            Err(err) => {
                warn!(target: "engine", "sponsor harvest failed: {err}");
                // A `widget` failure means the cached sponsor no longer serves
                // a working quest; drop it so the next job re-runs discovery
                // and can pick another candidate domain.
                if err.kind == "widget" {
                    instr::forget(campaign_id);
                }
                None
            }
        }
    }

    async fn fill_code(&self, code: &str) -> FlowResult<()> {
        let script = format!(
            r#"(() => {{
              const form = document.getElementById('main-form') || document.getElementById('main-form-2');
              if (!form) return false;
              const input = form.querySelector('input[name=password]');
              if (!input) return false;
              input.focus();
              input.value = {};
              input.dispatchEvent(new Event('input', {{bubbles: true}}));
              input.dispatchEvent(new Event('change', {{bubbles: true}}));
              return true;
            }})()"#,
            serde_json::to_string(code).unwrap_or_else(|_| "\"\"".into())
        );
        let value = self
            .cdp
            .eval(None, &script)
            .await
            .map_err(|e| FlowError::new("page", e.to_string()))?;
        if value.as_bool() != Some(true) {
            return Err(FlowError::new("page", "code input not found"));
        }
        Ok(())
    }

    async fn navigate(&self, url: &str) -> FlowResult<()> {
        // A top-level navigation destroys every isolated world. Drop the cache
        // before the command so a stale context is never evaluated after it.
        self.clear_contexts();
        self.cdp
            .call("Page.navigate", json!({"url": url}))
            .await
            .map_err(|e| FlowError::new("cdp", e.to_string()))?;
        Ok(())
    }

    /// Navigate and wait for the new document to replace the old one.
    ///
    /// `performance.timeOrigin` changes with every document; polling it is
    /// cheaper and more reliable than a fixed settle sleep, because the old
    /// page already reports `readyState === "complete"` while the navigation
    /// is still in flight.
    async fn navigate_and_settle(&self, url: &str) -> FlowResult<()> {
        let before = self.document_time_origin().await;
        self.navigate(url).await?;
        self.await_document_swap(before).await;
        Ok(())
    }

    async fn document_time_origin(&self) -> Option<f64> {
        match self.cdp.eval(None, "performance.timeOrigin").await {
            Ok(Value::Number(value)) => value.as_f64(),
            _ => None,
        }
    }

    async fn await_document_swap(&self, before: Option<f64>) {
        let Some(before) = before else {
            // No stamp to compare (e.g. the context is mid-navigation): keep a
            // short settle and poll document.readyState briefly so callers don't pay
            // dead wait while avoiding evaluating the previous document.
            tokio::time::sleep(Duration::from_millis(60)).await;
            for _ in 0..3 {
                if let Ok(Value::String(state)) = self.cdp.eval(None, "document.readyState").await {
                    if state == "complete" || state == "interactive" {
                        break;
                    }
                }
                tokio::time::sleep(Duration::from_millis(50)).await;
            }
            return;
        };
        // Commit normally lands in well under a second; 10 s is only a guard
        // against a navigation that never happens, not a load wait.
        let until = Instant::now() + Duration::from_secs(10);
        let mut step = 0usize;
        while Instant::now() < until {
            if let Ok(Value::Number(value)) = self.cdp.eval(None, "performance.timeOrigin").await {
                if value.as_f64().map_or(false, |now| now != before) {
                    return;
                }
            }
            tokio::time::sleep(poll_delay(step)).await;
            step += 1;
        }
    }

    async fn reload(&self) -> FlowResult<()> {
        let before = self.document_time_origin().await;
        self.clear_contexts();
        self.cdp
            .call("Page.reload", json!({}))
            .await
            .map_err(|e| FlowError::new("cdp", e.to_string()))?;
        self.await_document_swap(before).await;
        self.wait_ready().await?;
        // The reload is only useful once the form/wrapper it exists for is
        // back; poll for that instead of the old flat 2 s. Cap the wait so a
        // broken reload does not eat the next attempt's budget.
        let until = Instant::now() + Duration::from_secs(10).min(self.remaining());
        let mut step = 0usize;
        while Instant::now() < until {
            if let Ok(value) = self.cdp.eval(None, STATE_JS).await {
                if PageState::from_value(&value).is_ready() {
                    break;
                }
            }
            tokio::time::sleep(poll_delay(step)).await;
            step += 1;
        }
        Ok(())
    }

    async fn wait_ready(&self) -> FlowResult<()> {
        let until = Instant::now() + Duration::from_secs(30);
        while Instant::now() < until {
            if let Ok(value) = self.cdp.eval(None, "document.readyState").await {
                if value.as_str() == Some("complete") {
                    return Ok(());
                }
            }
            tokio::time::sleep(Duration::from_millis(80)).await;
        }
        Err(FlowError::new("page", "document never reached complete"))
    }

    async fn wait_for_page(&self) -> FlowResult<PageState> {
        let started = Instant::now();
        let until = started + Duration::from_secs(18);
        let mut state = PageState::default();
        let mut step = 0usize;
        while Instant::now() < until {
            if let Ok(value) = self.cdp.eval(None, STATE_JS).await {
                state = PageState::from_value(&value);
                // The campaign/landing page also ships a `#captcha-html-wrapper`
                // while the code form is still missing. Treating that skeleton as
                // ready sends the flow into a captcha whose token can never unlock
                // anything; wait for the form that owns the widget.
                if state.is_ready() {
                    self.await_widget_boot(state.password).await;
                    return Ok(state);
                }
                if state.err == "rate_limit" {
                    return Err(FlowError::new("rate_limit", format!("rate limited on landing page (title: {})", state.title)));
                }
                if state.err == "not_found" {
                    return Err(FlowError::new("not_found", format!("link not found (title: {})", state.title)));
                }
                if started.elapsed() >= Duration::from_secs(4)
                    && state.title.starts_with("Untitled #")
                {
                    return Err(FlowError::new(
                        "interstitial",
                        format!("untitled interstitial (title: {})", state.title),
                    ));
                }
                if state.title.to_lowercase().contains("just a moment") {
                    if self.solve_cf_clearance().await {
                        let _ = self.cdp.call("Page.reload", json!({})).await;
                        tokio::time::sleep(Duration::from_millis(1200)).await;
                    } else {
                        self.click_cf_challenge().await;
                        tokio::time::sleep(Duration::from_millis(1200)).await;
                    }
                    step = 0;
                    continue;
                }
            }
            tokio::time::sleep(poll_delay(step)).await;
            step += 1;
        }
        Err(FlowError::new(
            "page",
            format!("page did not expose a captcha (title: {})", state.title),
        ))
    }

    async fn solve_cf_clearance(&self) -> bool {
        static CF_CACHE: std::sync::OnceLock<Mutex<HashMap<String, (String, String, String, Instant)>>> =
            std::sync::OnceLock::new();
        let cache = CF_CACHE.get_or_init(|| Mutex::new(HashMap::new()));
        let proxy_arg = self
            .proxy
            .as_ref()
            .map(|p| {
                let scheme = match p.scheme {
                    crate::proxy::Scheme::Socks5 => "socks5",
                    crate::proxy::Scheme::Http => "http",
                };
                if p.user.is_empty() {
                    format!("{scheme}://{}:{}", p.host, p.port)
                } else {
                    format!("{scheme}://{}:{}@{}:{}", p.user, p.pass, p.host, p.port)
                }
            })
            .unwrap_or_default();
        let cached = cache.lock().ok().and_then(|guard| {
            guard.get(&proxy_arg).and_then(|(val, dom, path, at)| {
                (at.elapsed() < Duration::from_secs(720))
                    .then(|| (val.clone(), dom.clone(), path.clone()))
            })
        });
        if let Some((val, dom, path)) = cached {
            if self
                .cdp
                .call(
                    "Network.setCookie",
                    json!({
                        "name": "cf_clearance",
                        "value": val,
                        "domain": dom,
                        "path": path,
                        "secure": true,
                        "httpOnly": true
                    }),
                )
                .await
                .is_ok()
            {
                debug!(target: "engine", alias = %self.alias, "reused cached cf_clearance");
                return true;
            }
        }

        let mut script = None;
        for candidate in [
            "tools/cf_clearance.py",
            "engine-rs/tools/cf_clearance.py",
            "../tools/cf_clearance.py",
        ] {
            let p = std::path::PathBuf::from(candidate);
            if p.exists() {
                script = Some(p);
                break;
            }
        }
        let Some(script) = script else {
            return false;
        };
        let python = instr::ocr_binary();
        let url = format!("https://link4m.net/go/{}", self.alias);
        let ua = self
            .cdp
            .eval(None, "navigator.userAgent")
            .await
            .ok()
            .and_then(|v| v.as_str().map(str::to_string))
            .unwrap_or_default();
        let proxy_for_cmd = proxy_arg.clone();

        let out = tokio::task::spawn_blocking(move || {
            std::process::Command::new(&python)
                .arg(&script)
                .arg(&url)
                .arg(&proxy_for_cmd)
                .arg(&ua)
                .output()
        })
        .await
        .ok()
        .and_then(Result::ok);

        let Some(output) = out else {
            return false;
        };
        if !output.status.success() {
            return false;
        }
        let stdout = String::from_utf8_lossy(&output.stdout);
        let Ok(val) = serde_json::from_str::<Value>(stdout.trim()) else {
            return false;
        };
        let Some(cookie) = val.get("cookie") else {
            return false;
        };
        let Some(value) = cookie.get("value").and_then(Value::as_str) else {
            return false;
        };
        let domain = cookie
            .get("domain")
            .and_then(Value::as_str)
            .unwrap_or(".link4m.net");
        let path = cookie.get("path").and_then(Value::as_str).unwrap_or("/");
        let res = self
            .cdp
            .call(
                "Network.setCookie",
                json!({
                    "name": "cf_clearance",
                    "value": value,
                    "domain": domain,
                    "path": path,
                    "secure": true,
                    "httpOnly": true
                }),
            )
            .await;
        if res.is_ok() {
            if let Ok(mut guard) = cache.lock() {
                guard.insert(
                    proxy_arg,
                    (value.to_string(), domain.to_string(), path.to_string(), Instant::now()),
                );
            }
            info!(target: "engine", alias = %self.alias, "injected cf_clearance via Patchright");
            true
        } else {
            false
        }
    }

    /// Click the Cloudflare Managed Challenge checkbox iframe when stuck on
    /// `Just a moment...`, using CDP `Page.getFrameTree` + `DOM.getFrameOwner`
    /// + `DOM.getBoxModel` so it works even inside shadow roots.
    async fn click_cf_challenge(&self) {
        let Ok(tree) = self.cdp.call("Page.getFrameTree", json!({})).await else {
            return;
        };
        let mut stack = vec![tree.get("frameTree").cloned().unwrap_or(Value::Null)];
        let mut cf_frame_id: Option<String> = None;
        while let Some(node) = stack.pop() {
            if let Some(frame) = node.get("frame") {
                let url = frame.get("url").and_then(Value::as_str).unwrap_or("");
                if url.contains("challenges.cloudflare.com") {
                    cf_frame_id = frame.get("id").and_then(Value::as_str).map(str::to_string);
                    break;
                }
            }
            if let Some(children) = node.get("childFrames").and_then(Value::as_array) {
                for child in children {
                    stack.push(child.clone());
                }
            }
        }
        let Some(frame_id) = cf_frame_id else {
            return;
        };
        let Ok(owner) = self
            .cdp
            .call("DOM.getFrameOwner", json!({ "frameId": frame_id }))
            .await
        else {
            return;
        };
        let Some(backend_id) = owner.get("backendNodeId").and_then(Value::as_i64) else {
            return;
        };
        let Ok(box_model) = self
            .cdp
            .call("DOM.getBoxModel", json!({ "backendNodeId": backend_id }))
            .await
        else {
            return;
        };
        let Some(content) = box_model
            .get("model")
            .and_then(|m| m.get("content"))
            .and_then(Value::as_array)
        else {
            return;
        };
        if content.len() < 8 {
            return;
        }
        let (Some(x0), Some(y0), Some(y2)) = (
            content[0].as_f64(),
            content[1].as_f64(),
            content[5].as_f64(),
        ) else {
            return;
        };
        let cx = x0 + 28.0;
        let cy = (y0 + y2) / 2.0;
        debug!(target: "engine", x = cx, y = cy, "clicking Cloudflare challenge checkbox");
        let _ = self
            .cdp
            .call(
                "Input.dispatchMouseEvent",
                json!({ "type": "mouseMoved", "x": cx, "y": cy }),
            )
            .await;
        tokio::time::sleep(Duration::from_millis(60)).await;
        let _ = self
            .cdp
            .call(
                "Input.dispatchMouseEvent",
                json!({ "type": "mousePressed", "x": cx, "y": cy, "button": "left", "clickCount": 1 }),
            )
            .await;
        tokio::time::sleep(Duration::from_millis(40)).await;
        let _ = self
            .cdp
            .call(
                "Input.dispatchMouseEvent",
                json!({ "type": "mouseReleased", "x": cx, "y": cy, "button": "left", "clickCount": 1 }),
            )
            .await;
    }

    /// Wait up to ~2 s for the widget to arm, then proceed regardless. A page
    /// that already has `complete` plus grecaptcha/anchor costs one poll; a
    /// slow one no longer pays the old flat 2.2 s sleep.
    async fn await_widget_boot(&self, password_only: bool) {
        let until = Instant::now() + Duration::from_secs(2);
        let mut step = 0usize;
        while Instant::now() < until {
            let armed = match self.cdp.eval(None, BOOT_JS).await {
                Ok(value) => {
                    let complete = value.get("complete").and_then(Value::as_bool).unwrap_or(false);
                    let grecaptcha = value.get("grecaptcha").and_then(Value::as_bool).unwrap_or(false);
                    let anchor = value.get("anchor").and_then(Value::as_bool).unwrap_or(false);
                    let rendered = value.get("rendered").and_then(Value::as_bool).unwrap_or(false);
                    complete && (password_only || anchor || (grecaptcha && rendered))
                }
                Err(_) => false,
            };
            if armed {
                return;
            }
            tokio::time::sleep(poll_delay(step)).await;
            step += 1;
        }
    }

    /// Wait until the captcha widget exists or the budget expires. Used after
    /// the campaign code is filled: the page re-renders the code form into the
    /// captcha step, and clicking before the widget arms just wastes a poll.
    async fn await_widget_arm(&self, budget: Duration) {
        let until = Instant::now() + budget.min(self.remaining());
        let mut step = 0usize;
        while Instant::now() < until {
            if let Ok(value) = self.cdp.eval(None, BOOT_JS).await {
                let anchor = value.get("anchor").and_then(Value::as_bool).unwrap_or(false);
                let rendered = value.get("rendered").and_then(Value::as_bool).unwrap_or(false);
                let grecaptcha = value.get("grecaptcha").and_then(Value::as_bool).unwrap_or(false);
                if anchor || (grecaptcha && rendered) {
                    return;
                }
            }
            tokio::time::sleep(poll_delay(step)).await;
            step += 1;
        }
    }

    async fn frames(&self) -> FlowResult<Vec<(String, String)>> {
        let tree = self
            .cdp
            .call("Page.getFrameTree", json!({}))
            .await
            .map_err(|e| FlowError::new("cdp", e.to_string()))?;
        let mut out = Vec::new();
        collect_frames(tree.get("frameTree"), &mut out);
        Ok(out)
    }

    async fn context_for(&self, frame_id: &str) -> FlowResult<i64> {
        let reply = self
            .cdp
            .call(
                "Page.createIsolatedWorld",
                json!({"frameId": frame_id, "worldName": "l4m-engine", "grantUniveralAccess": true}),
            )
            .await
            .map_err(|e| FlowError::new("cdp", e.to_string()))?;
        reply
            .get("executionContextId")
            .and_then(Value::as_i64)
            .ok_or_else(|| FlowError::new("cdp", "isolated world returned no context"))
    }

    async fn context_cached(&self, frame_id: &str) -> FlowResult<i64> {
        if let Ok(contexts) = self.contexts.lock() {
            if let Some(context) = contexts.get(frame_id).copied() {
                return Ok(context);
            }
        }
        let context = self.context_for(frame_id).await?;
        if let Ok(mut contexts) = self.contexts.lock() {
            contexts.insert(frame_id.to_string(), context);
        }
        Ok(context)
    }

    fn forget_context(&self, frame_id: &str) {
        if let Ok(mut contexts) = self.contexts.lock() {
            contexts.remove(frame_id);
        }
    }

    fn clear_contexts(&self) {
        if let Ok(mut contexts) = self.contexts.lock() {
            contexts.clear();
        }
    }

    /// Evaluate in a frame's cached isolated world. If the world was destroyed
    /// (an iframe navigation), recreate it once and retry the script.
    async fn eval_frame(&self, frame_id: &str, context: &mut i64, script: &str) -> FlowResult<Value> {
        match self.cdp.eval(Some(*context), script).await {
            Ok(value) => Ok(value),
            Err(_) => {
                self.forget_context(frame_id);
                *context = self.context_cached(frame_id).await?;
                self.cdp
                    .eval(Some(*context), script)
                    .await
                    .map_err(|e| FlowError::new("cdp", e.to_string()))
            }
        }
    }

    /// True when the campaign form itself owns a token.
    #[allow(dead_code)]
    async fn campaign_token_ready(&self) -> Option<bool> {
        match self.cdp.eval(None, TOKEN_PROBE_JS).await {
            Ok(value) => Some(value.get("len").and_then(Value::as_u64).unwrap_or(0) > 50),
            Err(_) => None,
        }
    }

    /// Name of the reCAPTCHA widget that owns a frame, or the containing form id.
    ///
    /// The page renders multiple widgets with different sitekeys (main form,
    /// report modal). A token solved in the report modal is rejected by Link4M.
    /// Trace the frame to its container cleanly using closest/ancestor walk,
    /// identifying recaptcha-report and modal-report.
    async fn owner_widget(&self, frame_id: &str) -> Option<String> {
        let owner = self
            .cdp
            .call("DOM.getFrameOwner", json!({"frameId": frame_id}))
            .await
            .ok()?;
        let backend = owner.get("backendNodeId").and_then(Value::as_i64)?;
        let resolved = self
            .cdp
            .call("DOM.resolveNode", json!({"backendNodeId": backend}))
            .await
            .ok()?;
        let object_id = resolved
            .get("object")
            .and_then(|o| o.get("objectId"))
            .and_then(Value::as_str)?
            .to_string();
        let reply = self
            .cdp
            .call(
                "Runtime.callFunctionOn",
                json!({
                    "objectId": object_id,
                    "functionDeclaration": "function(){ let n=this; if(!n) return ''; if(n.closest){ if(n.closest('#recaptcha-report, #modal-report, #modal-report-form, .modal-report')) return 'recaptcha-report'; if(n.closest('#recaptcha')) return 'recaptcha'; if(n.closest('#recaptcha-2')) return 'recaptcha-2'; if(n.closest('#main-form')) return 'main-form'; if(n.closest('#main-form-2')) return 'main-form-2'; if(n.closest('#main-form-3')) return 'main-form-3'; } for(let i=0;i<20&&n;i++){ if(n.id==='recaptcha'||n.id==='recaptcha-2'||n.id==='recaptcha-report') return n.id; if(n.id==='main-form'||n.id==='main-form-2'||n.id==='main-form-3'||n.id==='modal-report'||n.id==='modal-report-form') return n.id; n=n.parentElement; } return ''; }",
                    "returnByValue": true
                }),
            )
            .await
            .ok()?;
        reply
            .get("result")
            .and_then(|r| r.get("value"))
            .and_then(Value::as_str)
            .filter(|value| !value.is_empty())
            .map(str::to_string)
    }

    /// True when the frame belongs to the campaign form's own widget.
    async fn is_main_widget(&self, frame_id: &str) -> bool {
        matches!(
            self.owner_widget(frame_id).await.as_deref(),
            Some("recaptcha") | Some("recaptcha-2") | Some("main-form") | Some("main-form-2") | Some("main-form-3")
        )
    }

    /// True when the frame belongs to the report modal / report widget.
    async fn is_report_widget(&self, frame_id: &str) -> bool {
        matches!(
            self.owner_widget(frame_id).await.as_deref(),
            Some("recaptcha-report") | Some("modal-report") | Some("modal-report-form")
        )
    }

    /// Sitekey of the report modal if present on the page.
    async fn report_sitekey(&self) -> Option<String> {
        let script = r#"(() => {
          const el = document.getElementById('recaptcha-report');
          return el ? (el.getAttribute('data-sitekey') || '') : '';
        })()"#;
        if let Ok(Value::String(key)) = self.cdp.eval(None, script).await {
            let key = key.trim().to_string();
            if key.len() > 10 {
                return Some(key);
            }
        }
        None
    }

    /// Sitekey the campaign form will accept a token for.
    ///
    /// Evaluates CAMPAIGN_SITEKEY_JS first. When needed, inspects main widget
    /// anchor frames and takes their `k=` parameter, strictly excluding any
    /// report modal widgets.
    async fn campaign_sitekey(&self) -> Option<String> {
        if let Ok(Value::String(key)) = self.cdp.eval(None, CAMPAIGN_SITEKEY_JS).await {
            let key = key.trim().to_string();
            if key.len() > 10 {
                return Some(key);
            }
        }
        let report_key = self.report_sitekey().await;
        for (id, url) in self.frames().await.ok()? {
            if !url.contains("/anchor") {
                continue;
            }
            if self.is_report_widget(&id).await {
                continue;
            }
            if !self.is_main_widget(&id).await {
                continue;
            }
            if let Some(key) = url_param(&url, "k") {
                if let Some(rk) = &report_key {
                    if &key == rk {
                        continue;
                    }
                }
                return Some(key);
            }
        }
        None
    }

    async fn click_anchor(&self, campaign_key: Option<&str>) -> FlowResult<bool> {
        let until = Instant::now() + Duration::from_secs(10);
        let report_key = self.report_sitekey().await;
        while Instant::now() < until {
            let mut all: Vec<(String, String)> = Vec::new();
            for (id, url) in self.frames().await? {
                if url.contains("/api2/anchor") || url.contains("/enterprise/anchor") {
                    if self.is_report_widget(&id).await {
                        continue;
                    }
                    if let Some(k) = url_param(&url, "k") {
                        if let Some(rk) = &report_key {
                            if &k == rk {
                                continue;
                            }
                        }
                    }
                    all.push((id, url));
                }
            }
            // Sitekey first, container id second. Never fall back to non-main / report widgets.
            let mut ordered: Vec<(String, String)> = Vec::new();
            if let Some(key) = campaign_key {
                for pair in &all {
                    if url_param(&pair.1, "k").as_deref() == Some(key) {
                        ordered.push(pair.clone());
                    }
                }
            }
            for pair in &all {
                if !ordered.iter().any(|(id, _)| id == &pair.0) && self.is_main_widget(&pair.0).await {
                    ordered.push(pair.clone());
                }
            }

            for (id, _) in ordered {
                let Ok(mut context) = self.context_cached(&id).await else { continue };
                if let Ok(Value::Bool(true)) = self.eval_frame(&id, &mut context, ANCHOR_CLICK_JS).await {
                    debug!(target: "engine", frame = %id, "anchor clicked");
                    return Ok(true);
                }
            }
            if self.mouse_click_anchor().await? {
                return Ok(true);
            }
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
        Ok(false)
    }

    async fn mouse_click_anchor(&self) -> FlowResult<bool> {
        let rect = self
            .cdp
            .eval(
                None,
                r#"(() => {
                  const form = document.getElementById('main-form') || document.getElementById('main-form-2') || document.getElementById('main-form-3');
                  let f = form ? form.querySelector('iframe[src*="/anchor"]') : null;
                  if (!f) {
                    const rc = document.getElementById('recaptcha') || document.getElementById('recaptcha-2');
                    if (rc) f = rc.querySelector('iframe[src*="/anchor"]');
                  }
                  if (!f) return null;
                  // Dismiss report modal / modal backdrop if overlaying
                  const reportModal = document.getElementById('modal-report');
                  if (reportModal) {
                    reportModal.classList.remove('show');
                    reportModal.style.display = 'none';
                  }
                  document.querySelectorAll('.modal-backdrop').forEach(el => el.remove());
                  const r = f.getBoundingClientRect();
                  if (r.width === 0 || r.height === 0) return null;
                  return {x: r.x + 28, y: r.y + r.height / 2};
                })()"#,
            )
            .await
            .map_err(|e| FlowError::new("cdp", e.to_string()))?;
        let (Some(x), Some(y)) = (
            rect.get("x").and_then(Value::as_f64),
            rect.get("y").and_then(Value::as_f64),
        ) else {
            return Ok(false);
        };
        for kind in ["mouseMoved", "mousePressed", "mouseReleased"] {
            let mut params = json!({"type": kind, "x": x, "y": y, "button": "left", "clickCount": 1});
            if kind == "mouseMoved" {
                params = json!({"type": kind, "x": x, "y": y});
            }
            self.cdp
                .call("Input.dispatchMouseEvent", params)
                .await
                .map_err(|e| FlowError::new("cdp", e.to_string()))?;
            tokio::time::sleep(Duration::from_millis(60)).await;
        }
        Ok(true)
    }

    async fn challenge_frame(
        &self,
        campaign_key: Option<&str>,
        skip: &HashSet<String>,
    ) -> FlowResult<Option<(String, i64)>> {
        let report_key = self.report_sitekey().await;
        let frames: Vec<(String, String)> = self
            .frames()
            .await?
            .into_iter()
            .filter(|(id, url)| url.contains("bframe") && !skip.contains(id))
            .collect();
        // Exclude report widgets or frames matching report modal's sitekey
        let mut candidates: Vec<(String, String)> = Vec::new();
        for (id, url) in frames {
            if self.is_report_widget(&id).await {
                continue;
            }
            if let Some(k) = url_param(&url, "k") {
                if let Some(rk) = &report_key {
                    if &k == rk {
                        continue;
                    }
                }
            }
            candidates.push((id, url));
        }

        let mut ordered: Vec<(String, String)> = Vec::new();
        if let Some(key) = campaign_key {
            for pair in &candidates {
                if url_param(&pair.1, "k").as_deref() == Some(key) {
                    ordered.push(pair.clone());
                }
            }
        }
        for pair in &candidates {
            if !ordered.iter().any(|(id, _)| id == &pair.0) && self.is_main_widget(&pair.0).await {
                ordered.push(pair.clone());
            }
        }
        if campaign_key.is_none() {
            for pair in &candidates {
                if !ordered.iter().any(|(id, _)| id == &pair.0) {
                    ordered.push(pair.clone());
                }
            }
        }
        for (id, _) in ordered {
            let Ok(mut context) = self.context_cached(&id).await else { continue };
            if let Ok(Value::Bool(true)) = self.eval_frame(&id, &mut context, CHALLENGE_JS).await {
                return Ok(Some((id, context)));
            }
        }
        Ok(None)
    }

    #[allow(dead_code)]
    async fn wait_token(&self, budget: Duration) -> FlowResult<Option<String>> {
        let until = Instant::now() + budget;
        while Instant::now() < until {
            if let Ok(value) = self.cdp.eval(None, TOKEN_PROBE_JS).await {
                let len = value.get("len").and_then(Value::as_u64).unwrap_or(0);
                let token = value.get("token").and_then(Value::as_str).unwrap_or("");
                if len > 50 && token.len() > 50 {
                    return Ok(Some(token.to_string()));
                }
            }
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
        Ok(None)
    }

    async fn solve_audio(&mut self, frame_id: &str) -> FlowResult<String> {
        let mut context = self.context_cached(frame_id).await?;
        let mut audio: Option<(String, i64)> = self.wait_audio_frame_for(Duration::from_millis(80)).await?;
        if audio.is_none() {
            for attempt in 1..=2 {
                // Wait briefly for `#recaptcha-audio-button` to mount before clicking
                // so attempt 1 does not miss a still-hydrating challenge panel.
                let btn_until = Instant::now() + Duration::from_millis(2000);
                let mut clicked = false;
                while Instant::now() < btn_until {
                    match self.eval_frame(frame_id, &mut context, AUDIO_BUTTON_JS).await {
                        Ok(Value::Bool(true)) => {
                            clicked = true;
                            debug!(target: "engine", attempt, "audio button clicked");
                            break;
                        }
                        _ => tokio::time::sleep(Duration::from_millis(80)).await,
                    }
                }
                if !clicked {
                    debug!(target: "engine", attempt, "audio button missing");
                }
                let wait = if attempt == 1 {
                    Duration::from_secs(6)
                } else {
                    Duration::from_secs(4)
                };
                if let Some(found) = self.wait_audio_frame_for(wait).await? {
                    audio = Some(found);
                    break;
                }
                if let Ok(Value::String(text)) = self
                    .eval_frame(frame_id, &mut context, "document.body ? document.body.innerText : ''")
                    .await
                {
                    debug!(target: "engine", attempt, text = %text.chars().take(180).collect::<String>(), "challenge text");
                }
                if let Ok(frames) = self.frames().await {
                    let urls: Vec<String> = frames
                        .iter()
                        .map(|(_, url)| url.chars().take(70).collect())
                        .collect();
                    debug!(target: "engine", attempt, ?urls, "frames");
                }
            }
        }
        let (audio_frame_id, mut context) = audio
            .ok_or_else(|| FlowError::new("audio", "audio challenge never appeared"))?;

        for round in 1..=3 {
            if Instant::now() >= self.deadline {
                return Err(FlowError::new("captcha", "budget exhausted in audio"));
            }
            let src_until = Instant::now() + Duration::from_millis(1500);
            let mut encoded = String::new();
            while Instant::now() < src_until {
                let blob = self
                    .eval_frame(&audio_frame_id, &mut context, AUDIO_PCM_JS)
                    .await?;
                let val = blob.as_str().unwrap_or("");
                if !val.is_empty() {
                    encoded = val.to_string();
                    break;
                }
                tokio::time::sleep(Duration::from_millis(100)).await;
            }
            if encoded.is_empty() || encoded.starts_with("ERR") {
                return Err(FlowError::new("audio", format!("no clip ({encoded})")));
            }
            let raw = base64::engine::general_purpose::STANDARD
                .decode(encoded)
                .map_err(|e| FlowError::new("audio", format!("bad pcm base64: {e}")))?;
            debug!(target: "engine", round, bytes = raw.len(), "clip decoded");
            let pcm = crate::asr::pcm16_to_f32(&raw);
            if pcm.is_empty() {
                return Err(FlowError::new("audio", "clip could not be decoded"));
            }
            let asr = self.asr.clone();
            let text = tokio::task::spawn_blocking(move || asr.transcribe(&pcm))
                .await
                .map_err(|e| FlowError::new("asr", e.to_string()))?
                .map_err(|e| FlowError::new("asr", e.to_string()))?;
            let text = text.trim().to_string();
            if text.is_empty() {
                warn!(target: "engine", "empty transcript, next clip");
                self.next_clip(&audio_frame_id, &mut context).await?;
                continue;
            }
            debug!(target: "engine", %text, "transcript");

            // Fill and verify in one eval; the old path paid a 250 ms sleep
            // plus a second round-trip for the same two DOM calls.
            let _ = self
                .eval_frame(&audio_frame_id, &mut context, &audio_fill_verify_js(&text))
                .await;

            let until = Instant::now() + Duration::from_secs(30);
            while Instant::now() < until {
                if let Ok(Value::String(token)) = self.cdp.eval(None, TOKEN_JS).await {
                    if token.len() > 50 {
                        info!(target: "engine", len = token.len(), "audio solved");
                        return Ok(token);
                    }
                }
                if let Ok(Value::String(err)) = self
                    .eval_frame(&audio_frame_id, &mut context, AUDIO_ERROR_JS)
                    .await
                {
                    let low = err.to_lowercase();
                    if !low.is_empty() {
                        if low.contains("try again later") || low.contains("automated") {
                            return Err(FlowError::new("audio", err));
                        }
                        if low.contains("multiple") || low.contains("try again") {
                            break;
                        }
                        if low.contains("incorrect") {
                            break;
                        }
                    }
                }
                tokio::time::sleep(Duration::from_millis(100)).await;
            }
            if round < 3 {
                self.next_clip(&audio_frame_id, &mut context).await?;
            }
        }
        Err(FlowError::new("audio", "three clips failed"))
    }

    async fn wait_audio_frame_for(&self, budget: Duration) -> FlowResult<Option<(String, i64)>> {
        let until = Instant::now() + budget;
        while Instant::now() < until {
            for (id, url) in self.frames().await? {
                if !url.contains("bframe") {
                    continue;
                }
                let Ok(mut context) = self.context_cached(&id).await else { continue };
                if let Ok(Value::Bool(true)) =
                    self.eval_frame(&id, &mut context, AUDIO_READY_JS).await
                {
                    return Ok(Some((id, context)));
                }
            }
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
        Ok(None)
    }

    /// Click reload and wait for the next clip instead of a flat 1.5 s: a new
    /// `audio` src or a reset response field is the signal that it is ready.
    async fn next_clip(&self, frame_id: &str, context: &mut i64) -> FlowResult<()> {
        let before = self
            .eval_frame(frame_id, context, CLIP_STATE_JS)
            .await
            .unwrap_or(Value::Null);
        let before_src = before.get("src").and_then(Value::as_str).unwrap_or("").to_string();
        let before_value = before.get("value").and_then(Value::as_str).unwrap_or("").to_string();
        let _ = self.eval_frame(frame_id, context, RELOAD_CLICK_JS).await;
        let until = Instant::now() + Duration::from_millis(1500);
        let mut step = 0usize;
        while Instant::now() < until {
            if let Ok(snapshot) = self.eval_frame(frame_id, context, CLIP_STATE_JS).await {
                let src = snapshot.get("src").and_then(Value::as_str).unwrap_or("");
                let value = snapshot.get("value").and_then(Value::as_str).unwrap_or("");
                let src_changed = !before_src.is_empty() && src != before_src;
                let value_changed = !before_value.is_empty() && value != before_value;
                if src_changed || value_changed {
                    return Ok(());
                }
            }
            tokio::time::sleep(poll_delay(step)).await;
            step += 1;
        }
        Ok(())
    }

    async fn finish(&mut self, token: String) -> FlowResult<String> {
        let budget = Duration::from_secs(50).min(self.remaining());
        let until = Instant::now() + budget;
        let mut clicked = false;
        let mut direct_tries = 0u8;
        let mut injected = false;
        let mut last_state = FinishState::default();
        let mut last_log = Instant::now();
        let mut last_direct: Option<Instant> = None;

        while Instant::now() < until {
            // `state.url` comes from `location.href`, so it already reflects a
            // navigation; the extra Page.getNavigationHistory round-trip every
            // loop was pure latency.
            let state = match self.cdp.eval(None, FINISH_STATE_JS).await {
                Ok(value) => FinishState::from_value(&value),
                Err(err) => {
                    debug!(target: "engine", "finish state read failed: {err}");
                    tokio::time::sleep(Duration::from_millis(100)).await;
                    continue;
                }
            };
            last_state = state.clone();

            if state.url.starts_with("http") && !is_link4m(&state.url) {
                return Ok(state.url.clone());
            }
            if state.href.starts_with("http") && !is_link4m(&state.href) {
                return Ok(state.href.clone());
            }

            // The widget normally writes the token into the form it belongs to
            // and the site's data-callback fires on its own. If the challenge
            // was solved in another widget (the page renders three), copy the
            // token into the main form so its POST can validate it.
            if !injected {
                let _ = self.cdp.eval(None, &inject_token_js(&token)).await;
                injected = true;
            }

            // Callback path: the button exists but no href yet, click it once
            // its class loses `disabled`. The site then fetches the destination.
            if state.has && !state.disabled && !clicked {
                info!(target: "engine", "continue button enabled");
                clicked = true;
                let _ = self.cdp.eval(None, LINK_CLICK_JS).await;
            }

            // The site's own handler is the happy path, but its callback is
            // not always reachable from an automation context. Post the same
            // form to the same endpoint the page uses; the JSON carries the
            // destination. This never navigates, so nothing races the click.
            if state.token > 50
                && state.href.is_empty()
                && direct_tries < 3
                && last_direct.map_or(true, |at| {
                    Instant::now().duration_since(at) >= Duration::from_millis(1500)
                })
            {
                direct_tries += 1;
                last_direct = Some(Instant::now());
                last_log = Instant::now();
                match self.post_link_info().await {
                    Ok(Some(destination)) => return Ok(destination),
                    Ok(None) => debug!(target: "engine", "direct post returned no url"),
                    Err(err) if err.kind == "code" || err.kind == "captcha" || err.kind == "rate_limit" => return Err(err),
                    Err(err) => debug!(target: "engine", "direct post failed: {err}"),
                }
            }

            if Instant::now().duration_since(last_log) >= Duration::from_secs(6) {
                last_log = Instant::now();
                debug!(
                    target: "engine",
                    url = %state.url.chars().take(80).collect::<String>(),
                    has = state.has,
                    disabled = state.disabled,
                    token = state.token,
                    href = %state.href.chars().take(60).collect::<String>(),
                    body = %state.body.replace('\n', " ").chars().take(160).collect::<String>(),
                    "finish poll"
                );
            }
            tokio::time::sleep(Duration::from_millis(100)).await;
        }

        Err(FlowError::new(
            "destination",
            format!(
                "destination never appeared (button: {}, href: {:?}, token: {}, page: {:?})",
                last_state.has,
                last_state.href,
                last_state.token,
                last_state.body.replace('\n', " ").chars().take(160).collect::<String>()
            ),
        ))
    }

    async fn post_link_info(&self) -> FlowResult<Option<String>> {
        if let Some(code) = self.code.as_deref().filter(|c| !c.trim().is_empty()) {
            let script = format!(
                "window.__l4m_code = {};",
                serde_json::to_string(code.trim()).unwrap_or_else(|_| "\"\"".into())
            );
            let _ = self.cdp.eval(None, &script).await;
        }
        let raw = self
            .cdp
            .eval(None, POST_LINK_INFO_JS)
            .await
            .map_err(|e| FlowError::new("destination", e.to_string()))?;
        let text = raw.as_str().unwrap_or("");
        if text.is_empty() {
            return Ok(None);
        }
        let value: Value = serde_json::from_str(text).unwrap_or(Value::Null);
        if value.get("success").and_then(Value::as_bool) == Some(true) {
            let url = value
                .get("url")
                .or_else(|| value.get("link"))
                .and_then(Value::as_str)
                .unwrap_or("");
            if url.starts_with("http") && !is_link4m(url) {
                return Ok(Some(url.to_string()));
            }
        }
        info!(target: "engine", reply = %text.chars().take(200).collect::<String>(), "link-info reply");
        if let Some(info) = value.get("info").and_then(Value::as_str) {
            let lower = info.to_lowercase();
            if lower.contains("captcha") {
                return Err(FlowError::new("captcha", info.to_string()));
            }
            if lower.contains("vượt quá giới hạn")
                || lower.contains("quay lại sau")
                || lower.contains("rate limit")
                || lower.contains("access limit")
                || lower.contains("too many requests")
            {
                return Err(FlowError::new("rate_limit", info.to_string()));
            }
            if info.contains("Mã không hợp lệ")
                || info.contains("Sai url")
                || info.contains("Không lấy được code")
                || lower.contains("invalid code")
                || lower.contains("incorrect search url")
            {
                return Err(FlowError::new("code", info.to_string()));
            }
        }
        Ok(None)
    }

    fn remaining(&self) -> Duration {
        self.deadline.saturating_duration_since(Instant::now())
    }
}

#[derive(Default, Clone)]
struct FinishState {
    url: String,
    href: String,
    has: bool,
    disabled: bool,
    token: u64,
    body: String,
}

impl FinishState {
    fn from_value(value: &Value) -> Self {
        Self {
            url: value.get("url").and_then(Value::as_str).unwrap_or("").to_string(),
            href: value.get("href").and_then(Value::as_str).unwrap_or("").to_string(),
            has: value.get("has").and_then(Value::as_bool).unwrap_or(false),
            disabled: value.get("disabled").and_then(Value::as_bool).unwrap_or(false),
            token: value.get("token").and_then(Value::as_u64).unwrap_or(0),
            body: value.get("body").and_then(Value::as_str).unwrap_or("").to_string(),
        }
    }
}

fn inject_token_js(token: &str) -> String {
    format!(
        r#"(() => {{
          const form = document.getElementById('main-form') || document.getElementById('main-form-2') || document.getElementById('main-form-3');
          if (!form) return false;
          let el = form.querySelector('textarea[name=g-recaptcha-response]');
          if (!el) {{
            el = document.createElement('textarea');
            el.name = 'g-recaptcha-response';
            el.style.display = 'none';
            form.appendChild(el);
          }}
          el.value = {};
          el.dispatchEvent(new Event('input', {{bubbles: true}}));
          el.dispatchEvent(new Event('change', {{bubbles: true}}));
          return true;
        }})()"#,
        serde_json::to_string(token).unwrap_or_else(|_| "\"\"".into())
    )
}

/// Fill the transcript and press verify in one round-trip.
fn audio_fill_verify_js(text: &str) -> String {
    AUDIO_FILL_VERIFY_JS.replace(
        "TEXT",
        &serde_json::to_string(text).unwrap_or_else(|_| "\"\"".into()),
    )
}

#[derive(Default)]
struct PageState {
    form: bool,
    captcha: bool,
    password: bool,
    #[allow(dead_code)]
    code: String,
    campaign: String,
    title: String,
    err: String,
}

impl PageState {
    /// True once the page holds the form that can actually be solved.
    ///
    /// A bare `#captcha-html-wrapper` shows up on the campaign skeleton before
    /// the code form arrives; solving there produces a token with no campaign.
    fn is_ready(&self) -> bool {
        self.password || (self.form && self.captcha)
    }

    fn from_value(value: &Value) -> Self {
        Self {
            form: value.get("form").and_then(Value::as_bool).unwrap_or(false),
            captcha: value.get("captcha").and_then(Value::as_bool).unwrap_or(false),
            password: value.get("password").and_then(Value::as_bool).unwrap_or(false),
            code: value.get("code").and_then(Value::as_str).unwrap_or("").to_string(),
            campaign: value.get("campaign").and_then(Value::as_str).unwrap_or("").to_string(),
            title: value.get("title").and_then(Value::as_str).unwrap_or("").to_string(),
            err: value.get("err").and_then(Value::as_str).unwrap_or("").to_string(),
        }
    }
}

fn collect_frames(node: Option<&Value>, out: &mut Vec<(String, String)>) {
    let Some(node) = node else { return };
    if let Some(frame) = node.get("frame") {
        let id = frame.get("id").and_then(Value::as_str).unwrap_or("").to_string();
        let url = frame.get("url").and_then(Value::as_str).unwrap_or("").to_string();
        if !id.is_empty() {
            out.push((id, url));
        }
    }
    if let Some(children) = node.get("childFrames").and_then(Value::as_array) {
        for child in children {
            collect_frames(Some(child), out);
        }
    }
}

pub fn is_link4m(url: &str) -> bool {
    let lower = url.to_lowercase();
    lower.contains("link4m.net") || lower.contains("link4m.org") || lower.contains("link4m.com")
}

pub fn extract_alias(input: &str) -> Option<String> {
    let trimmed = input.trim();
    if trimmed.is_empty() {
        return None;
    }
    if !trimmed.contains('/') && !trimmed.contains('.') {
        return Some(trimmed.to_string());
    }
    let after = trimmed
        .split("/go/")
        .nth(1)
        .or_else(|| trimmed.split('/').next_back())
        .unwrap_or("");
    let alias: String = after
        .chars()
        .take_while(|c| c.is_ascii_alphanumeric() || *c == '-' || *c == '_')
        .collect();
    if alias.is_empty() {
        None
    } else {
        Some(alias)
    }
}

/// Convenience used by the worker: drive one alias end to end.
pub async fn run_alias(
    cdp: &Cdp,
    asr: &Arc<Asr>,
    alias: &str,
    code: Option<&str>,
    port: u16,
    proxy: Option<Proxy>,
    budget: Duration,
) -> FlowResult<String> {
    let mut flow = Flow::new(
        cdp,
        asr.clone(),
        alias,
        code.map(str::to_string),
        port,
        proxy,
        budget,
    );
    flow.run().await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn alias_from_full_url() {
        assert_eq!(extract_alias("https://link4m.net/go/2kCcIqn").as_deref(), Some("2kCcIqn"));
        assert_eq!(extract_alias("https://link4m.org/go/mNkqHg2?x=1").as_deref(), Some("mNkqHg2"));
        assert_eq!(extract_alias("mNkqHg2").as_deref(), Some("mNkqHg2"));
        assert_eq!(extract_alias("  "), None);
    }

    #[test]
    fn page_state_requires_the_owning_form() {
        let bare_wrapper = PageState { captcha: true, ..PageState::default() };
        assert!(!bare_wrapper.is_ready());
        let code_form = PageState { form: true, password: true, ..PageState::default() };
        assert!(code_form.is_ready());
        let captcha_form = PageState { form: true, captcha: true, ..PageState::default() };
        assert!(captcha_form.is_ready());
    }

    #[test]
    fn destination_filter() {
        assert!(is_link4m("https://link4m.net/go/x"));
        assert!(!is_link4m("https://dash.nvnmc.cloud/earn/callback/abc"));
    }

    #[test]
    fn poll_cadence_starts_fast_and_caps() {
        assert_eq!(poll_delay(0), Duration::from_millis(60));
        assert_eq!(poll_delay(2), Duration::from_millis(150));
        assert_eq!(poll_delay(4), Duration::from_millis(400));
        assert_eq!(poll_delay(99), Duration::from_millis(400));
    }

    #[test]
    fn audio_fill_script_is_single_eval() {
        let script = audio_fill_verify_js("hello \"world\"");
        assert!(script.contains("audio-response"));
        assert!(script.contains("recaptcha-verify-button"));
        assert!(script.contains("\"hello \\\"world\\\"\""));
        assert!(!script.contains("TEXT"));
    }

    #[test]
    fn pcm_roundtrip() {
        let samples: Vec<f32> = vec![0.0, 0.5, -0.5, 1.0];
        let bytes: Vec<u8> = samples
            .iter()
            .flat_map(|s| ((s * 32767.0) as i16).to_le_bytes())
            .collect();
        let back = crate::asr::pcm16_to_f32(&bytes);
        assert_eq!(back.len(), 4);
        assert!((back[1] - 0.5).abs() < 0.01);
    }

    #[test]
    fn campaign_sitekey_js_checks_window_key_and_excludes_report() {
        assert!(CAMPAIGN_SITEKEY_JS.contains("recaptcha-report"));
        assert!(CAMPAIGN_SITEKEY_JS.contains("modal-report"));
        assert!(CAMPAIGN_SITEKEY_JS.contains("recaptcha_key"));
        assert!(CAMPAIGN_SITEKEY_JS.contains("iframe[src*=\"/anchor\"]"));
    }

    #[test]
    fn token_js_reads_strictly_from_main_form_not_report() {
        assert!(TOKEN_JS.contains("main-form"));
        assert!(TOKEN_JS.contains("textarea[name=g-recaptcha-response]"));
        assert!(!TOKEN_JS.contains("querySelectorAll('textarea"));

        assert!(TOKEN_PROBE_JS.contains("main-form"));
        assert!(!TOKEN_PROBE_JS.contains("querySelectorAll('textarea"));
    }

    #[test]
    fn boot_js_checks_main_form_and_recaptcha_not_global_anchors() {
        assert!(BOOT_JS.contains("main-form"));
        assert!(BOOT_JS.contains("recaptcha"));
        assert!(!BOOT_JS.contains("document.querySelectorAll('iframe')"));
    }

    #[test]
    fn post_link_info_js_switches_endpoint_on_password() {
        assert!(POST_LINK_INFO_JS.contains("/links/get-link-info"));
        assert!(POST_LINK_INFO_JS.contains("/links/check-captcha"));
        assert!(POST_LINK_INFO_JS.contains("hasPassword"));
    }

    #[test]
    fn captcha_error_classification() {
        let error_info = "Mã captcha đã sai hoặc quá hạn. Bạn vui lòng check lại captcha";
        let is_captcha_err = error_info.to_lowercase().contains("captcha");
        assert!(is_captcha_err);

        let rate_limit_info = "Đã vượt quá giới hạn truy cập vui lòng quay lại sau";
        let is_rate_limit = rate_limit_info.to_lowercase().contains("vượt quá giới hạn");
        assert!(is_rate_limit);

        let code_err_info = "Mã không hợp lệ";
        assert!(!code_err_info.to_lowercase().contains("captcha"));
        assert!(!code_err_info.to_lowercase().contains("vượt quá giới hạn"));
        assert!(code_err_info.contains("Mã không hợp lệ"));
    }

    #[test]
    fn widget_id_classification() {
        let is_main = |id: &str| matches!(id, "recaptcha" | "recaptcha-2" | "main-form" | "main-form-2" | "main-form-3");
        let is_report = |id: &str| matches!(id, "recaptcha-report" | "modal-report" | "modal-report-form");

        assert!(is_main("recaptcha"));
        assert!(is_main("recaptcha-2"));
        assert!(is_main("main-form"));
        assert!(!is_main("recaptcha-report"));
        assert!(!is_main("modal-report"));

        assert!(is_report("recaptcha-report"));
        assert!(is_report("modal-report"));
        assert!(is_report("modal-report-form"));
        assert!(!is_report("main-form"));
        assert!(!is_report("recaptcha"));
    }

    #[test]
    fn warp_spoof_script_integrity() {
        assert!(WARP_SPOOF_JS.contains("__l4m_warp_patched"));
        assert!(WARP_SPOOF_JS.contains("cdn-cgi/trace"));
        assert!(WARP_SPOOF_JS.contains("warp=off"));
        assert!(WARP_SPOOF_JS.contains("gateway=off"));
    }
}
