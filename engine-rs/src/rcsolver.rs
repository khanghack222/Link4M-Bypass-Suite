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
    let output = match tokio::time::timeout(budget, cmd.output()).await {
        Ok(Ok(output)) => output,
        Ok(Err(err)) => {
            warn!(target: "engine", error = %err, "external captcha solver failed to run");
            return None;
        }
        Err(_) => {
            warn!(target: "engine", timeout_s = budget.as_secs(), "external captcha solver timed out");
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

/// The campaign page renders three widgets with the same sitekey. Read the
/// one inside the captcha wrapper first; fall back to the first widget on the
/// page. An empty result lets the solver derive it from the URL itself.
pub async fn sitekey(cdp: &crate::cdp::Cdp) -> Option<String> {
    const SITEKEY_JS: &str = r#"(() => {
  const wrapper = document.getElementById('captcha-html-wrapper');
  const own = wrapper ? (wrapper.getAttribute('data-sitekey') || '') : '';
  if (own) return own;
  const el = document.querySelector('[data-sitekey]');
  return el ? (el.getAttribute('data-sitekey') || '') : '';
})()"#;
    let value = cdp.eval(None, SITEKEY_JS).await.ok()?;
    let key = value.as_str().unwrap_or("").trim().to_string();
    if key.len() > 20 {
        debug!(target: "engine", sitekey = %key, "captcha sitekey read from page");
        return Some(key);
    }
    std::env::var("RC_SOLVER_SITEKEY")
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| value.len() > 20)
}

#[cfg(test)]
mod tests {
    use super::command_parts;

    #[test]
    fn command_parts_split_binary_and_fixed_args() {
        let (bin, args) = command_parts("python /opt/solver.py --quiet").unwrap();
        assert_eq!(bin, "python");
        assert_eq!(args, vec!["/opt/solver.py", "--quiet"]);
        assert!(command_parts("   ").is_none());
    }
}
