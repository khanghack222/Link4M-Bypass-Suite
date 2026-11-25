//! Chrome lifecycle: launch a private headless instance, discover its CDP
//! endpoint, and kill it on drop. Site isolation is disabled on purpose so the
//! reCAPTCHA iframe stays in the same renderer and `Page.createIsolatedWorld`
//! can reach it without cross-process session plumbing.

use anyhow::{anyhow, Context, Result};
use serde_json::Value;
use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::mpsc;
use std::time::Duration;

pub struct ChromeProc {
    child: Child,
    pub port: u16,
    pub profile: PathBuf,
    ephemeral: bool,
}

impl ChromeProc {
    pub fn launch(binary: &str, headless: bool, profile: PathBuf, fresh: bool) -> Result<Self> {
        if fresh && profile.exists() {
            let _ = std::fs::remove_dir_all(&profile);
        }
        std::fs::create_dir_all(&profile).context("create chrome profile")?;

        let mut command = Command::new(binary);
        command
            .arg("--remote-debugging-port=0")
            .arg(format!("--user-data-dir={}", profile.display()))
            .arg("--no-first-run")
            .arg("--no-default-browser-check")
            .arg("--disable-gpu")
            .arg("--disable-dev-shm-usage")
            .arg("--disable-site-isolation-trials")
            .arg("--disable-features=IsolateOrigins,site-per-process,Translate")
            .arg("--disable-blink-features=AutomationControlled")
            .arg("--no-proxy-server")
            .arg("--lang=en-US")
            .arg("--window-size=1280,1000")
            .arg("--renderer-process-limit=2")
            .arg("about:blank")
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .stdin(Stdio::null());
        if headless {
            command.arg("--headless=new");
            // HeadlessChrome in the UA is enough for reCAPTCHA to disable the
            // audio challenge; present a normal desktop string instead.
            command.arg("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/158.0.0.0 Safari/537.36");
        }
        if let Ok(extra) = std::env::var("CHROME_FLAGS") {
            for flag in extra.split_whitespace() {
                command.arg(flag);
            }
        }
        if std::env::var("CHROME_NO_SANDBOX").map(|v| v != "0").unwrap_or(true) {
            command.arg("--no-sandbox");
        }

        let mut child = command.spawn().context("spawn chrome")?;
        let stderr = child.stderr.take().context("chrome stderr")?;
        let (tx, rx) = mpsc::channel::<Option<String>>();

        std::thread::spawn(move || {
            let reader = BufReader::new(stderr);
            let mut announced = false;
            for line in reader.lines().map_while(std::result::Result::ok) {
                if !announced {
                    if let Some(rest) = line.split("DevTools listening on ").nth(1) {
                        let _ = tx.send(Some(rest.trim().to_string()));
                        announced = true;
                    }
                }
                // Keep draining so Chrome never blocks on a full stderr pipe.
            }
            if !announced {
                let _ = tx.send(None);
            }
        });

        let ws_url = match rx.recv_timeout(Duration::from_secs(30)) {
            Ok(Some(url)) => url,
            Ok(None) => return Err(anyhow!("chrome exited before announcing CDP")),
            Err(_) => return Err(anyhow!("chrome did not announce CDP in 30s")),
        };
        let port = ws_url
            .rsplit(':')
            .next()
            .and_then(|tail| tail.split('/').next())
            .and_then(|p| p.parse::<u16>().ok())
            .ok_or_else(|| anyhow!("bad devtools url: {ws_url}"))?;

        Ok(Self { child, port, profile, ephemeral: fresh })
    }

    /// WebSocket URL of the first page target (the about:blank tab).
    pub fn page_ws(&self) -> Result<String> {
        let endpoint = format!("http://127.0.0.1:{}/json/list", self.port);
        let body = ureq::get(&endpoint)
            .timeout(Duration::from_secs(10))
            .call()
            .context("query /json/list")?
            .into_string()
            .context("read /json/list")?;
        let targets: Vec<Value> = serde_json::from_str(&body).context("parse /json/list")?;
        targets
            .iter()
            .find(|t| t.get("type").and_then(Value::as_str) == Some("page"))
            .and_then(|t| t.get("webSocketDebuggerUrl").and_then(Value::as_str))
            .map(str::to_string)
            .ok_or_else(|| anyhow!("no page target"))
    }
}

impl Drop for ChromeProc {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
        if self.ephemeral {
            let _ = std::fs::remove_dir_all(&self.profile);
        }
    }
}
