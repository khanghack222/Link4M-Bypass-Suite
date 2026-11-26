//! Chrome lifecycle: launch a private headless instance, discover its CDP
//! endpoint, and kill it on drop. Site isolation is disabled on purpose so the
//! reCAPTCHA iframe stays in the same renderer and `Page.createIsolatedWorld`
//! can reach it without cross-process session plumbing.

use anyhow::{anyhow, Context, Result};
use serde_json::Value;
use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::os::unix::process::CommandExt;
use std::process::{Child, Command, Stdio};
use std::sync::mpsc;
use std::time::{Duration, Instant};

pub struct ChromeProc {
    child: Child,
    pub port: u16,
    pub profile: PathBuf,
    ephemeral: bool,
}

/// Kill a process and every descendant. `/proc` is the only portable-enough
/// way here: Chrome's renderers do not carry the profile flag, so a cmdline
/// match alone would leave them behind holding several hundred MB.
fn kill_tree(root: i32) {
    let mut parents: Vec<(i32, i32)> = Vec::new();
    if let Ok(entries) = std::fs::read_dir("/proc") {
        for entry in entries.flatten() {
            let Ok(pid) = entry.file_name().to_string_lossy().parse::<i32>() else {
                continue;
            };
            let Ok(stat) = std::fs::read_to_string(format!("/proc/{pid}/stat")) else {
                continue;
            };
            let Some(tail) = stat.rsplit_once(") ") else { continue };
            let mut fields = tail.1.split_whitespace();
            let _state = fields.next();
            if let Some(ppid) = fields.next().and_then(|v| v.parse::<i32>().ok()) {
                parents.push((pid, ppid));
            }
        }
    }
    let mut targets = vec![root];
    let mut index = 0;
    while index < targets.len() {
        let parent = targets[index];
        index += 1;
        for (pid, ppid) in &parents {
            if *ppid == parent && !targets.contains(pid) {
                targets.push(*pid);
            }
        }
    }
    for pid in targets.iter().rev() {
        unsafe {
            libc::kill(*pid, libc::SIGKILL);
        }
    }
}

/// Remove Chrome instances left behind by a previous crash or a `timeout`
/// kill that skipped `Drop`. Only profiles under `root` are touched.
pub fn sweep(roots: &[PathBuf]) {
    let needles: Vec<String> = roots
        .iter()
        .map(|root| format!("--user-data-dir={}", root.display()))
        .collect();
    let mut killed = 0;
    if let Ok(entries) = std::fs::read_dir("/proc") {
        for entry in entries.flatten() {
            let Ok(pid) = entry.file_name().to_string_lossy().parse::<i32>() else {
                continue;
            };
            if pid == std::process::id() as i32 {
                continue;
            }
            let Ok(cmdline) = std::fs::read(format!("/proc/{pid}/cmdline")) else {
                continue;
            };
            let text = String::from_utf8_lossy(&cmdline).replace('\0', " ");
            if !text.contains("--remote-debugging-port=0")
                || !needles.iter().any(|needle| text.contains(needle))
            {
                continue;
            }
            // Only orphans: a live engine owns its Chrome and may be a sibling
            // process of this one. A dead parent means the job was killed
            // before Drop could run, which is exactly the leak being cleaned.
            let Ok(stat) = std::fs::read_to_string(format!("/proc/{pid}/stat")) else {
                continue;
            };
            let ppid = stat
                .rsplit_once(") ")
                .and_then(|(_, tail)| tail.split_whitespace().nth(1))
                .and_then(|v| v.parse::<i32>().ok())
                .unwrap_or(1);
            if ppid > 1 {
                let parent = std::fs::read(format!("/proc/{ppid}/cmdline"))
                    .map(|raw| String::from_utf8_lossy(&raw).replace('\0', " "))
                    .unwrap_or_default();
                if parent.contains("l4m-engine") {
                    continue;
                }
            }
            kill_tree(pid);
            killed += 1;
        }
    }
    if killed > 0 {
        std::thread::sleep(Duration::from_millis(400));
        eprintln!("swept {killed} stale chrome instance(s)");
    }
}

impl ChromeProc {
    pub fn launch(
        binary: &str,
        headless: bool,
        profile: PathBuf,
        fresh: bool,
        proxy_port: Option<u16>,
    ) -> Result<Self> {
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
            .arg("--lang=en-US")
            .arg("--window-size=1280,1000")
            .arg("--renderer-process-limit=2")
            .arg("about:blank")
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .stdin(Stdio::null());
        if let Some(port) = proxy_port {
            // Every request goes through the local relay, which injects the
            // upstream proxy credentials Chrome cannot carry itself.
            command.arg(format!("--proxy-server=http://127.0.0.1:{port}"));
        } else {
            command.arg("--no-proxy-server");
        }
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
        // Own session: a timeout kill that takes down the engine must not leave
        // Chrome holding memory on a 3.7 GB box. Drop kills the whole group.
        unsafe {
            command.pre_exec(|| {
                if libc::setsid() == -1 {
                    return Err(std::io::Error::last_os_error());
                }
                Ok(())
            });
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
    ///
    /// The port file appears before the DevTools HTTP server is answering, and
    /// on a loaded box that gap can reach several seconds. Poll instead of
    /// failing the whole job on the first refused connection.
    pub fn page_ws(&self) -> Result<String> {
        let endpoint = format!("http://127.0.0.1:{}/json/list", self.port);
        let deadline = Instant::now() + Duration::from_secs(40);
        let mut last: Option<anyhow::Error> = None;
        while Instant::now() < deadline {
            let attempt = ureq::get(&endpoint)
                .timeout(Duration::from_secs(5))
                .call()
                .context("query /json/list")
                .and_then(|r| r.into_string().context("read /json/list"));
            match attempt {
                Ok(body) => {
                    let targets: Vec<Value> =
                        serde_json::from_str(&body).context("parse /json/list")?;
                    if let Some(ws) = targets
                        .iter()
                        .find(|t| t.get("type").and_then(Value::as_str) == Some("page"))
                        .and_then(|t| t.get("webSocketDebuggerUrl").and_then(Value::as_str))
                    {
                        return Ok(ws.to_string());
                    }
                }
                Err(err) => last = Some(err),
            }
            std::thread::sleep(Duration::from_millis(400));
        }
        Err(last.unwrap_or_else(|| anyhow!("no page target")))
    }
}

impl Drop for ChromeProc {
    fn drop(&mut self) {
        let pid = self.child.id() as i32;
        // Negative pid targets the group created by setsid().
        unsafe {
            libc::kill(-pid, libc::SIGKILL);
        }
        let _ = self.child.kill();
        let _ = self.child.wait();
        kill_tree(pid);
        if self.ephemeral {
            let _ = std::fs::remove_dir_all(&self.profile);
        }
    }
}
