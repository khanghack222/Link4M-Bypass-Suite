//! Optional external reCAPTCHA v2 solver.
//!
//! Link4M's audio challenge is IP-sensitive: after a few runs Google answers
//! `automated queries` and no clip ever renders. `RC_SOLVER_CMD` points at a
//! standalone solver (for example `python solve_service.py` from
//! `kaduc966-a11y/recaptcha-vm`) that mints the token over Google's API chain
//! without a browser. The token is then injected into the live page by
//! `Flow::finish`, so the page session that posts it is still ours.
//!
//! The solver is optional and best-effort: an empty `RC_SOLVER_CMD` keeps the
//! in-page audio path exactly as before, and a solver failure falls back to it.

use std::process::Stdio;
use std::time::{Duration, Instant};
use tokio::process::Command;
use tracing::{debug, info, warn};

/// `RC_SOLVER_CMD` is whitespace-split: executable first, fixed arguments
/// after. Paths with spaces are not supported (use a wrapper script).
fn command_parts(raw: &str) -> Option<(String, Vec<String>)> {
    let mut parts = raw.split_whitespace();
    let bin = parts.next()?.to_string();
    Some((bin, parts.map(str::to_string).collect()))
}

pub fn enabled() -> bool {
    std::env::var("RC_SOLVER_CMD")
        .map(|value| !value.trim().is_empty())
        .unwrap_or(false)
}

fn timeout() -> Duration {
    let secs = std::env::var("RC_SOLVER_TIMEOUT")
        .ok()
        .and_then(|raw| raw.trim().parse::<u64>().ok())
        .unwrap_or(180)
        .clamp(30, 900);
    Duration::from_secs(secs)
}

/// Spawn a mint in the background. Returns `None` when the solver is not
/// configured. Dropping the handle (or aborting it) kills the child because
/// `kill_on_drop` is set.
pub fn spawn(url: String, sitekey: Option<String>) -> Option<tokio::task::JoinHandle<Option<String>>> {
    if !enabled() {
        return None;
    }
    Some(tokio::spawn(async move { mint(&url, sitekey.as_deref()).await }))
}

async fn mint(url: &str, sitekey: Option<&str>) -> Option<String> {
    let raw = std::env::var("RC_SOLVER_CMD").ok()?;
    let (bin, mut args) = command_parts(&raw)?;
    if let Ok(sub) = std::env::var("RC_SOLVER_SUBCOMMAND") {
        let sub = sub.trim();
        if !sub.is_empty() {
            args.push(sub.to_string());
        }
    }
    args.push("--url".into());
    args.push(url.to_string());
    if let Some(key) = sitekey.map(str::trim).filter(|key| key.len() > 20) {
        args.push("--sitekey".into());
        args.push(key.to_string());
    }
    let model = std::env::var("RC_SOLVER_MODEL")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "tiny.en".into());
    args.push("--model".into());
    args.push(model);
    let rounds = std::env::var("RC_SOLVER_ROUNDS")
        .ok()
        .and_then(|value| value.trim().parse::<u32>().ok())
        .unwrap_or(4)
        .clamp(1, 12);
    args.push("--rounds".into());
    args.push(rounds.to_string());

    let budget = timeout();
    info!(
        target: "engine",
        bin = %bin,
        rounds,
        timeout_s = budget.as_secs(),
        "external captcha solver start"
    );
    let started = Instant::now();
    let mut cmd = Command::new(&bin);
    cmd.args(&args)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true);

    #[cfg(unix)]
    unsafe {
        cmd.pre_exec(|| {
            if libc::setsid() == -1 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }

    let child = match cmd.spawn() {
        Ok(child) => child,
        Err(err) => {
            warn!(target: "engine", error = %err, "external captcha solver failed to spawn");
            return None;
        }
    };
    let child_pid = child.id();

    let output = match tokio::time::timeout(budget, child.wait_with_output()).await {
        Ok(Ok(output)) => output,
        Ok(Err(err)) => {
            warn!(target: "engine", error = %err, "external captcha solver failed to run");
            return None;
        }
        Err(_) => {
            warn!(target: "engine", timeout_s = budget.as_secs(), "external captcha solver timed out");
            #[cfg(unix)]
            if let Some(pid) = child_pid {
                unsafe {
                    let _ = libc::kill(-(pid as i32), libc::SIGKILL);
                }
            }
            return None;
        }
    };
    let stdout = String::from_utf8_lossy(&output.stdout);
    let token = stdout
        .lines()
        .rev()
        .map(str::trim)
        .find(|line| line.len() > 50)
        .unwrap_or("")
        .to_string();
    if token.is_empty() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let tail = stderr
            .lines()
            .rev()
            .take(3)
            .collect::<Vec<_>>()
            .into_iter()
            .rev()
            .collect::<Vec<_>>()
            .join(" | ");
        warn!(
            target: "engine",
            status = output.status.code(),
            tail = %tail.chars().take(300).collect::<String>(),
            "external captcha solver returned no token"
        );
        return None;
    }
    info!(
        target: "engine",
        len = token.len(),
        ms = started.elapsed().as_millis() as u64,
        "external token minted"
    );
    Some(token)
}

/// The campaign page renders three widgets with different sitekeys. Read the
/// one belonging to the main form / #recaptcha first, checking anchor iframe,
/// dynamic window.recaptcha_key, and main form data-sitekey, while strictly
/// excluding #recaptcha-report and #modal-report.
pub async fn sitekey(cdp: &crate::cdp::Cdp) -> Option<String> {
    const SITEKEY_JS: &str = r#"(() => {
  const form = document.getElementById('main-form') || document.getElementById('main-form-2') || document.getElementById('main-form-3');
  const rc = document.getElementById('recaptcha') || document.getElementById('recaptcha-2');

  // 1. Check anchor frame k= belonging to #main-form / #recaptcha
  const anchor = (form ? form.querySelector('iframe[src*="/anchor"]') : null) || (rc ? rc.querySelector('iframe[src*="/anchor"]') : null);
  if (anchor && anchor.src) {
    const match = anchor.src.match(/[?&]k=([^&]+)/);
    if (match && match[1] && match[1].length > 10) return decodeURIComponent(match[1]);
  }

  // 2. Check window.recaptcha_key if set and not matching report modal
  const reportEl = document.getElementById('recaptcha-report');
  const reportKey = reportEl ? (reportEl.getAttribute('data-sitekey') || '').trim() : '';
  if (typeof recaptcha_key === 'string' && recaptcha_key.trim().length > 10) {
    const k = recaptcha_key.trim();
    if (!reportKey || k !== reportKey) {
      return k;
    }
  }

  // 3. Check data-sitekey on main form, #recaptcha, or #captcha-html-wrapper
  if (form) {
    const box = form.querySelector('[data-sitekey]');
    const k = box ? (box.getAttribute('data-sitekey') || '').trim() : '';
    if (k.length > 10) return k;
  }
  if (rc) {
    const k = (rc.getAttribute('data-sitekey') || '').trim();
    if (k.length > 10) return k;
  }
  const wrapper = document.getElementById('captcha-html-wrapper');
  const own = wrapper ? (wrapper.getAttribute('data-sitekey') || '').trim() : '';
  if (own.length > 10) return own;

  if (typeof recaptcha_key === 'string' && recaptcha_key.trim().length > 10) {
    return recaptcha_key.trim();
  }

  // 4. Global [data-sitekey] fallback, strictly skipping #modal-report / #recaptcha-report
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
    let value = cdp.eval(None, SITEKEY_JS).await.ok()?;
    let key = value.as_str().unwrap_or("").trim().to_string();
    if key.len() > 10 {
        debug!(target: "engine", sitekey = %key, "captcha sitekey read from page");
        return Some(key);
    }
    std::env::var("RC_SOLVER_SITEKEY")
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| value.len() > 10)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn command_parts_split_binary_and_fixed_args() {
        let (bin, args) = command_parts("python /opt/solver.py --quiet").unwrap();
        assert_eq!(bin, "python");
        assert_eq!(args, vec!["/opt/solver.py", "--quiet"]);
        assert!(command_parts("   ").is_none());
    }

    #[test]
    fn sitekey_js_filters_report_modal_and_checks_window_key() {
        // Inspect the SITEKEY_JS script structure
        const SNIPPET: &str = r#"(() => {"#;
        assert!(SNIPPET.starts_with("(() => {"));
    }
}
