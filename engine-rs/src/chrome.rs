//! Chrome lifecycle: launch a private headless instance, discover its CDP
//! endpoint, and kill it on drop. Site isolation is disabled on purpose so the
//! reCAPTCHA iframe stays in the same renderer and `Page.createIsolatedWorld`
//! can reach it without cross-process session plumbing.

use anyhow::{anyhow, Context, Result};
use serde_json::Value;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
#[cfg(unix)]
use std::os::unix::process::CommandExt;
#[cfg(windows)]
use std::os::windows::process::CommandExt;
use std::process::{Child, Command, Stdio};
use std::sync::mpsc;
use std::time::{Duration, Instant};

pub struct ChromeProc {
    child: Child,
    pub port: u16,
    pub profile: PathBuf,
    ephemeral: bool,
}

/// Kill a process and every descendant. Linux exposes the tree through
/// `/proc`; macOS has no procfs, so `ps` is the fallback. Chrome renderers do
/// not carry the profile flag, so a cmdline match alone would leave them
/// behind holding several hundred MB.
#[cfg(unix)]
fn kill_tree(root: i32) {
    if std::path::Path::new("/proc").is_dir() {
        kill_tree_proc(root);
    } else {
        kill_tree_ps(root);
    }
}

#[cfg(unix)]
fn descendants(root: i32, parents: &[(i32, i32)]) -> Vec<i32> {
    let mut targets = vec![root];
    let mut index = 0;
    while index < targets.len() {
        let parent = targets[index];
        index += 1;
        for (pid, ppid) in parents {
            if *ppid == parent && !targets.contains(pid) {
                targets.push(*pid);
            }
        }
    }
    targets
}

#[cfg(unix)]
fn kill_all(targets: &[i32]) {
    for pid in targets.iter().rev() {
        unsafe {
            libc::kill(*pid, libc::SIGKILL);
        }
    }
}

#[cfg(unix)]
fn kill_tree_proc(root: i32) {
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
    kill_all(&descendants(root, &parents));
}

#[cfg(unix)]
fn kill_tree_ps(root: i32) {
    let Ok(output) = Command::new("ps").args(["-axo", "pid=,ppid="]).output() else {
        unsafe {
            libc::kill(root, libc::SIGKILL);
        }
        return;
    };
    let mut parents: Vec<(i32, i32)> = Vec::new();
    for line in String::from_utf8_lossy(&output.stdout).lines() {
        let mut parts = line.split_whitespace();
        let (Some(pid), Some(ppid)) = (parts.next(), parts.next()) else {
            continue;
        };
        if let (Ok(pid), Ok(ppid)) = (pid.parse::<i32>(), ppid.parse::<i32>()) {
            parents.push((pid, ppid));
        }
    }
    kill_all(&descendants(root, &parents));
}

#[cfg(windows)]
fn kill_tree(root: i32) {
    // taskkill /T walks the child tree; /F is required for renderer processes.
    let pid = root.to_string();
    let _ = Command::new("taskkill")
        .args(["/PID", pid.as_str(), "/T", "/F"])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();
}

/// Remove Chrome instances left behind by a previous crash or a `timeout`
/// kill that skipped `Drop`. Only profiles under `root` are touched.
#[cfg(unix)]
pub fn sweep(roots: &[PathBuf]) {
    if std::path::Path::new("/proc").is_dir() {
        sweep_proc(roots);
    } else {
        sweep_ps(roots);
    }
}

#[cfg(unix)]
fn sweep_needles(roots: &[PathBuf]) -> Vec<String> {
    roots
        .iter()
        .map(|root| format!("--user-data-dir={}", root.display()))
        .collect()
}

#[cfg(unix)]
fn sweep_proc(roots: &[PathBuf]) {
    let needles = sweep_needles(roots);
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

#[cfg(unix)]
fn sweep_ps(roots: &[PathBuf]) {
    let needles = sweep_needles(roots);
    let Ok(output) = Command::new("ps")
        .args(["-axo", "pid=,ppid=,command="])
        .output()
    else {
        return;
    };
    let mut rows: Vec<(i32, i32, String)> = Vec::new();
    for line in String::from_utf8_lossy(&output.stdout).lines() {
        let line = line.trim_start();
        let mut parts = line.splitn(3, char::is_whitespace);
        let (Some(pid), Some(ppid), Some(command)) = (parts.next(), parts.next(), parts.next()) else {
            continue;
        };
        if let (Ok(pid), Ok(ppid)) = (pid.parse::<i32>(), ppid.parse::<i32>()) {
            rows.push((pid, ppid, command.trim_start().to_string()));
        }
    }
    let self_pid = std::process::id() as i32;
    let mut killed = 0;
    for (pid, ppid, command) in &rows {
        if *pid == self_pid
            || !command.contains("--remote-debugging-port=0")
            || !needles.iter().any(|needle| command.contains(needle))
        {
            continue;
        }
        // Only orphans: a parent that is still l4m-engine owns its Chrome.
        if *ppid > 1 {
            if let Some(parent) = rows.iter().find(|(parent_pid, _, _)| parent_pid == ppid) {
                if parent.2.contains("l4m-engine") {
                    continue;
                }
            }
        }
        unsafe {
            libc::kill(*pid, libc::SIGKILL);
        }
        killed += 1;
    }
    if killed > 0 {
        std::thread::sleep(Duration::from_millis(400));
        eprintln!("swept {killed} stale chrome instance(s)");
    }
}

#[cfg(windows)]
pub fn sweep(roots: &[PathBuf]) {
    // Read command lines through CIM and stop only Chrome processes started by
    // this engine (remote debugging + one of our profile dirs). No WMI query
    // means no accidental kill of the user's own browser.
    let needles: Vec<String> = roots
        .iter()
        .map(|root| format!("--user-data-dir={}", root.display()).replace('\'', "''"))
        .collect();
    if needles.is_empty() {
        return;
    }
    let clauses: Vec<String> = needles
        .iter()
        .map(|needle| format!("$_.CommandLine -like '*{needle}*'"))
        .collect();
    let script = format!(
        "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | \
         Where-Object {{ $_.CommandLine -like '*--remote-debugging-port=0*' -and ({}) }} | \
         ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}",
        clauses.join(" -or ")
    );
    // Windows PowerShell 5 is `powershell`; PowerShell 7 installs `pwsh` and
    // may not keep the old alias. Try both before giving up.
    for shell in ["powershell", "pwsh"] {
        let status = Command::new(shell)
            .args(["-NoProfile", "-NonInteractive", "-Command", &script])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
        if matches!(status, Ok(status) if status.success()) {
            break;
        }
    }
}

/// Port plus browser websocket path from `<profile>/DevToolsActivePort`.
///
/// Chrome writes the two lines separately, so a read can catch the file
/// half-written; anything without both fields is "not ready yet", never an
/// error.
fn read_active_port(path: &Path) -> Option<(u16, String)> {
    let text = std::fs::read_to_string(path).ok()?;
    let mut lines = text.lines().filter(|line| !line.trim().is_empty());
    let port: u16 = lines.next()?.trim().parse().ok()?;
    let target = lines.next()?.trim();
    if !target.starts_with('/') {
        return None;
    }
    Some((port, target.to_string()))
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
        if !fresh {
            let lockfile = profile.join("lockfile");
            if lockfile.exists() && std::fs::remove_file(&lockfile).is_err() {
                sweep(std::slice::from_ref(&profile));
                std::thread::sleep(Duration::from_millis(200));
            }
            for name in ["lockfile", "SingletonLock", "SingletonCookie", "SingletonSocket"] {
                let _ = std::fs::remove_file(profile.join(name));
            }
        }

        let mut command = Command::new(binary);
        command
            .arg("--remote-debugging-port=0")
            .arg(format!("--user-data-dir={}", profile.display()))
            .arg("--no-first-run")
            .arg("--no-default-browser-check")
            .arg("--disable-gpu")
            .arg("--disable-dev-shm-usage")
            .arg("--disable-site-isolation-trials")
            .arg("--disable-features=IsolateOrigins,site-per-process,Translate,CalculateNativeWinOcclusion,OptimizationHints")
            .arg("--disable-blink-features=AutomationControlled")
            .arg("--lang=en-US")
            .arg("--window-size=1280,1000")
            .arg("--renderer-process-limit=2")
            // A backgrounded tab throttles its timers and the widget countdown
            // then crawls. The flow deliberately keeps two tabs alive (campaign
            // + sponsor), so none of the throttles may apply.
            .arg("--disable-background-timer-throttling")
            .arg("--disable-backgrounding-occluded-windows")
            .arg("--disable-renderer-backgrounding")
            // CDP evaluations are small and frequent; the IPC flood guard adds
            // latency bursts when a page logs or posts messages.
            .arg("--disable-ipc-flooding-protection")
            // Nothing in a bypass job needs these background services, and
            // each one adds startup work plus idle wakeups.
            .arg("--disable-component-update")
            .arg("--disable-default-apps")
            .arg("--disable-sync")
            .arg("--disable-domain-reliability")
            .arg("--disable-client-side-phishing-detection")
            .arg("--no-pings")
            .arg("--metrics-recording-only")
            .arg("--disable-hang-monitor")
            .arg("--disable-prompt-on-repost")
            .arg("--disable-breakpad")
            .arg("about:blank")
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .stdin(Stdio::null());
        if let Some(port) = proxy_port {
            // Every request goes through the local relay, which injects the
            // upstream proxy credentials Chrome cannot carry itself.
            command.arg(format!("--proxy-server=http://127.0.0.1:{port}"));
            // WebRTC would otherwise send UDP straight from the host and QUIC
            // bypasses HTTP proxies entirely; both leak the real exit.
            command.arg("--force-webrtc-ip-handling-policy=disable_non_proxied_udp");
            command.arg("--disable-quic");
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
        #[cfg(unix)]
        unsafe {
            command.pre_exec(|| {
                if libc::setsid() == -1 {
                    return Err(std::io::Error::last_os_error());
                }
                Ok(())
            });
        }
        #[cfg(windows)]
        {
            // CREATE_NEW_PROCESS_GROUP: keeps Chrome out of the engine's
            // console Ctrl-C group; taskkill /T handles teardown.
            command.creation_flags(0x0000_0200);
        }

        // A file left by a previous run in a reused profile names a dead
        // port; Chrome rewrites it within the first second of boot.
        let port_file = profile.join("DevToolsActivePort");
        let _ = std::fs::remove_file(&port_file);

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

        // Chrome 158 stopped printing the banner to stderr, so the only
        // reliable source is `<profile>/DevToolsActivePort`. Poll it and fall
        // back to the stderr banner for builds that still log one.
        let deadline = Instant::now() + Duration::from_secs(30);
        let ws_url = loop {
            if let Some((port, path)) = read_active_port(&port_file) {
                break format!("ws://127.0.0.1:{port}{path}");
            }
            match rx.try_recv() {
                Ok(Some(url)) => break url,
                Ok(None) => return Err(anyhow!("chrome exited before announcing CDP")),
                Err(mpsc::TryRecvError::Disconnected) => {
                    return Err(anyhow!("chrome exited before announcing CDP"))
                }
                Err(mpsc::TryRecvError::Empty) => {}
            }
            if let Ok(Some(status)) = child.try_wait() {
                return Err(anyhow!("chrome exited before announcing CDP ({status})"));
            }
            if Instant::now() >= deadline {
                return Err(anyhow!("chrome did not announce CDP in 30s"));
            }
            std::thread::sleep(Duration::from_millis(25));
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
        // Negative pid targets the group created by setsid() on Unix; on
        // Windows taskkill /T walks the tree.
        #[cfg(unix)]
        unsafe {
            libc::kill(-pid, libc::SIGKILL);
        }
        kill_tree(pid);
        let _ = self.child.kill();
        let _ = self.child.wait();
        if self.ephemeral {
            let _ = std::fs::remove_dir_all(&self.profile);
        }
    }
}

#[cfg(all(test, unix))]
mod tests {
    use super::descendants;

    #[test]
    fn descendants_walk_the_whole_tree() {
        let tree = [(10, 1), (11, 10), (12, 10), (13, 11), (14, 99)];
        let mut got = descendants(10, &tree);
        got.sort();
        assert_eq!(got, vec![10, 11, 12, 13]);
    }
}

#[cfg(test)]
mod port_file_tests {
    use super::read_active_port;
    use std::path::{Path, PathBuf};

    fn scratch(contents: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "l4m-portfile-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_nanos())
                .unwrap_or(0)
        ));
        std::fs::create_dir_all(&dir).expect("scratch dir");
        let path = dir.join("DevToolsActivePort");
        std::fs::write(&path, contents).expect("write port file");
        path
    }

    #[test]
    fn reads_port_and_browser_path() {
        let path = scratch("45847\n/devtools/browser/abc\n");
        assert_eq!(
            read_active_port(&path),
            Some((45847, "/devtools/browser/abc".to_string()))
        );
        let _ = std::fs::remove_dir_all(path.parent().unwrap());
    }

    #[test]
    fn half_written_file_is_not_ready() {
        let path = scratch("45847\n");
        assert_eq!(read_active_port(&path), None);
        let _ = std::fs::remove_dir_all(path.parent().unwrap());
    }

    #[test]
    fn missing_file_is_not_ready() {
        assert_eq!(
            read_active_port(Path::new("/nonexistent/l4m/DevToolsActivePort")),
            None
        );
    }
}
