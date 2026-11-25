//! Engine dispatch: one Python subprocess per job, JSON line on stdout.
//!
//! The Rust façade never reimplements a browser flow. It calls the same
//! `python -m src.bypass_api --url ... --json` contract that `menu.js`,
//! `bot_discord.js` and the FastAPI worker call, then normalises the trailing
//! `__BYPASS_JSON__` object.

use std::process::Stdio;
use std::time::Duration;

use serde_json::Value;
use tokio::process::Command;

use crate::config::Config;

#[derive(Debug, Default, Clone)]
#[allow(dead_code)] // provider/stage are kept for structured logs and future routing
pub struct EngineOutcome {
    pub success: bool,
    pub destination: Option<String>,
    pub provider: Option<String>,
    pub stage: Option<String>,
    pub error_code: Option<String>,
    pub error_message: Option<String>,
}

impl EngineOutcome {
    fn failure(code: &str, message: impl Into<String>) -> Self {
        EngineOutcome {
            success: false,
            error_code: Some(code.to_string()),
            error_message: Some(message.into()),
            ..Default::default()
        }
    }
}

fn string_field(payload: &Value, key: &str) -> Option<String> {
    payload
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
}

fn destination_field(payload: &Value) -> Option<String> {
    for key in [
        "destination_url",
        "finalUrl",
        "final_url",
        "destination",
        "url",
    ] {
        if let Some(value) = string_field(payload, key) {
            if value.starts_with("http") {
                return Some(value);
            }
        }
    }
    None
}

/// Parse the child's stdout. Exposed for tests; never panics on garbage.
pub fn parse_output(stdout: &str, stderr: &str, exit_success: bool) -> EngineOutcome {
    let mut payload: Option<Value> = None;
    for line in stdout.lines().rev() {
        let line = line.trim();
        if let Some(rest) = line.strip_prefix("__BYPASS_JSON__") {
            if let Ok(value) = serde_json::from_str::<Value>(rest.trim()) {
                payload = Some(value);
                break;
            }
        }
    }

    if let Some(payload) = payload {
        let destination = destination_field(&payload);
        let success = payload
            .get("success")
            .and_then(Value::as_bool)
            .unwrap_or(destination.is_some())
            && destination.is_some();
        return EngineOutcome {
            success,
            destination,
            provider: string_field(&payload, "provider")
                .or_else(|| string_field(&payload, "engine")),
            stage: string_field(&payload, "stage"),
            error_code: string_field(&payload, "error_code"),
            error_message: string_field(&payload, "error_message"),
        };
    }

    // Older engine builds only print the human line.
    for line in stdout.lines().rev() {
        if let Some((_, tail)) = line.split_once("FINAL DESTINATION URL:") {
            let destination = tail.trim();
            if destination.starts_with("http") {
                return EngineOutcome {
                    success: true,
                    destination: Some(destination.to_string()),
                    ..Default::default()
                };
            }
        }
    }

    let stderr_tail = stderr
        .lines()
        .rev()
        .map(str::trim)
        .find(|line| !line.is_empty())
        .unwrap_or("engine completed without unlocking destination");
    EngineOutcome::failure(
        if exit_success {
            "ERR_DESTINATION_NOT_FOUND"
        } else {
            "ERR_ENGINE_EXIT"
        },
        stderr_tail.chars().take(300).collect::<String>(),
    )
}

pub async fn run_engine(
    cfg: &Config,
    url: &str,
    engine: Option<&str>,
    timeout_secs: u64,
) -> EngineOutcome {
    let mut command = Command::new(&cfg.python);
    command
        .current_dir(&cfg.repo)
        .arg("-u")
        .arg("-X")
        .arg("utf8")
        .arg("-m")
        .arg("src.bypass_api")
        .arg("--url")
        .arg(url)
        .arg("--json")
        .env("PYTHONUNBUFFERED", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .env("L4M_REPO", &cfg.repo)
        .env("L4M_ENGINE", &cfg.l4m_engine)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true);

    if let Some(engine) = engine {
        command.arg("--engine").arg(engine.to_uppercase());
    }
    if cfg.headless {
        command.env("L4M_HEADLESS", "1");
    }
    // Same rule as service/config.py: a local proxy breaks CDP and link4m.
    for (key, _) in std::env::vars() {
        if key.to_lowercase().contains("proxy") {
            command.env_remove(&key);
        }
    }

    let child = match command.spawn() {
        Ok(child) => child,
        Err(error) => {
            return EngineOutcome::failure(
                "ERR_ENGINE_SPAWN",
                format!("không chạy được {}: {error}", cfg.python),
            )
        }
    };

    match tokio::time::timeout(Duration::from_secs(timeout_secs), child.wait_with_output()).await {
        Ok(Ok(output)) => {
            let stdout = String::from_utf8_lossy(&output.stdout);
            let stderr = String::from_utf8_lossy(&output.stderr);
            let outcome = parse_output(&stdout, &stderr, output.status.success());
            if !outcome.success {
                tracing::warn!(
                    code = outcome.error_code.as_deref().unwrap_or("-"),
                    stderr = %stderr.lines().rev().find(|l| !l.trim().is_empty()).unwrap_or("-"),
                    "engine thất bại"
                );
            }
            outcome
        }
        Ok(Err(error)) => {
            EngineOutcome::failure("ERR_ENGINE_IO", format!("engine process lỗi: {error}"))
        }
        Err(_) => {
            EngineOutcome::failure("ERR_ENGINE_TIMEOUT", format!("engine vượt {timeout_secs}s"))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_json_line_after_log_noise() {
        let stdout = "log one\nlog two\n__BYPASS_JSON__{\"success\":true,\"destination_url\":\"https://example.com/x\",\"provider\":\"LINK4M\",\"stage\":\"browser\"}\n";
        let outcome = parse_output(stdout, "", true);
        assert!(outcome.success);
        assert_eq!(
            outcome.destination.as_deref(),
            Some("https://example.com/x")
        );
        assert_eq!(outcome.provider.as_deref(), Some("LINK4M"));
        assert_eq!(outcome.stage.as_deref(), Some("browser"));
    }

    #[test]
    fn parses_failure_payload() {
        let stdout = "__BYPASS_JSON__{\"success\":false,\"error_code\":\"ERR_PROVIDER_UNKNOWN\",\"error_message\":\"nope\"}\n";
        let outcome = parse_output(stdout, "", true);
        assert!(!outcome.success);
        assert_eq!(outcome.error_code.as_deref(), Some("ERR_PROVIDER_UNKNOWN"));
    }

    #[test]
    fn falls_back_to_human_line() {
        let stdout = "noise\nFINAL DESTINATION URL: https://example.com/legacy\n";
        let outcome = parse_output(stdout, "", true);
        assert!(outcome.success);
        assert_eq!(
            outcome.destination.as_deref(),
            Some("https://example.com/legacy")
        );
    }

    #[test]
    fn garbage_stdout_never_panics() {
        let outcome = parse_output("not json\n", "boom\n", false);
        assert!(!outcome.success);
        assert_eq!(outcome.error_code.as_deref(), Some("ERR_ENGINE_EXIT"));
        assert_eq!(outcome.error_message.as_deref(), Some("boom"));
    }
}
