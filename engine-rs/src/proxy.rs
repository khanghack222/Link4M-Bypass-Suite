//! Outbound proxy pool.
//!
//! Link4M and the sponsor sites rate-limit by IP: after a handful of captchas
//! from one address the audio challenge starts failing. A pool of upstream
//! proxies, one per Chrome worker (or one per job when `PROXY_ROTATE=1`), moves
//! each flow onto a different exit.
//!
//! Chrome does not accept credentials inside `--proxy-server`, so every worker
//! talks to a local relay instead: the relay forwards CONNECT (and plain HTTP)
//! to the upstream proxy and injects `Proxy-Authorization`. The relay binds
//! 127.0.0.1 only and dies with the session that owns it.

use base64::Engine as _;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex, OnceLock, RwLock};
use std::time::{Duration, Instant};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpStream};
use tokio::task::JoinHandle;
use tracing::{info, warn};

const MAX_HEAD: usize = 32 * 1024;

/// How long a failed exit stays out of rotation. Configurable because a proxy
/// that only tripped a soft captcha can recover long before the default.
fn cooldown() -> Duration {
    static COOLDOWN: OnceLock<Duration> = OnceLock::new();
    *COOLDOWN.get_or_init(|| {
        std::env::var("PROXY_COOLDOWN")
            .ok()
            .and_then(|value| value.trim().parse::<u64>().ok())
            .filter(|secs| *secs > 0)
            .map(Duration::from_secs)
            .unwrap_or(Duration::from_secs(300))
    })
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Scheme {
    Http,
    Socks5,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Proxy {
    pub scheme: Scheme,
    pub host: String,
    pub port: u16,
    pub user: String,
    pub pass: String,
}

impl Proxy {
    fn key(&self) -> String {
        format!("{}:{}", self.host, self.port)
    }

    fn authorization(&self) -> Option<String> {
        if self.user.is_empty() {
            return None;
        }
        let raw = format!("{}:{}", self.user, self.pass);
        Some(base64::engine::general_purpose::STANDARD.encode(raw))
    }
}

/// Parse one line. Accepted shapes:
/// `host:port`, `user:pass@host:port`, `http://host:port`,
/// `http://user:pass@host:port`, `host:port:user:pass`.
pub fn parse_line(line: &str) -> Option<Proxy> {
    let line = line.trim();
    if line.is_empty() || line.starts_with('#') {
        return None;
    }
    let mut scheme = Scheme::Http;
    let mut rest = line;
    if let Some((prefix, tail)) = rest.split_once("://") {
        scheme = match prefix.to_ascii_lowercase().as_str() {
            "socks" | "socks5" | "socks5h" => Scheme::Socks5,
            _ => Scheme::Http,
        };
        rest = tail;
    }
    rest = rest.trim_end_matches('/');
    let (creds, hostport) = match rest.rsplit_once('@') {
        Some((creds, hostport)) => (Some(creds), hostport),
        None => (None, rest),
    };
    let mut parts = hostport.split(':');
    let host = parts.next()?.trim();
    let port = parts.next()?.trim().parse::<u16>().ok()?;
    if host.is_empty() {
        return None;
    }
    let (mut user, mut pass) = (String::new(), String::new());
    if let Some(creds) = creds {
        let (u, p) = creds.split_once(':').unwrap_or((creds, ""));
        user = u.to_string();
        pass = p.to_string();
    } else if let Some(extra) = parts.next() {
        // host:port:user:pass
        user = extra.to_string();
        pass = parts.next().unwrap_or("").to_string();
    }
    Some(Proxy { scheme, host: host.to_string(), port, user, pass })
}

fn parse_entries(raw: &str) -> Vec<Proxy> {
    raw.split(['\n', ',']).filter_map(parse_line).collect()
}

fn file_stamp(path: &Path) -> Option<(Option<std::time::SystemTime>, u64)> {
    let meta = std::fs::metadata(path).ok()?;
    Some((meta.modified().ok(), meta.len()))
}

pub struct ProxyPool {
    entries: RwLock<Vec<Proxy>>,
    next: AtomicUsize,
    cooldown: Mutex<HashMap<String, Instant>>,
    source: Option<PathBuf>,
    /// `(mtime, size)` of the last parsed proxy file; `PROXY_LIST` has none.
    stamp: Mutex<Option<(Option<std::time::SystemTime>, u64)>>,
}

impl ProxyPool {
    /// Build from `PROXY_LIST` (inline, newline/comma separated) or
    /// `PROXY_FILE` (default `data/proxies.txt`). Empty list → auto-detect
    /// local Cloudflare WARP SOCKS5 proxy (`127.0.0.1:40000`) when enabled.
    pub fn from_env() -> Option<Arc<ProxyPool>> {
        let configured = match std::env::var("PROXY_LIST") {
            Ok(value) if !value.trim().is_empty() => Self::build(&value, None),
            _ => {
                let path = std::env::var("PROXY_FILE")
                    .map(PathBuf::from)
                    .unwrap_or_else(|_| PathBuf::from("data/proxies.txt"));
                Self::from_file(path)
            }
        };
        if configured.is_some() {
            return configured;
        }
        detect_warp_proxy().and_then(|proxy| {
            info!(
                target: "engine",
                port = proxy.port,
                "detected local Cloudflare WARP proxy"
            );
            Self::build(&format!("socks5://{}:{}", proxy.host, proxy.port), None)
        })
    }

    fn from_file(path: PathBuf) -> Option<Arc<ProxyPool>> {
        let raw = std::fs::read_to_string(&path).ok()?;
        Self::build(&raw, Some(path))
    }

    fn build(raw: &str, source: Option<PathBuf>) -> Option<Arc<ProxyPool>> {
        let entries = parse_entries(raw);
        if entries.is_empty() {
            return None;
        }
        let stamp = source.as_deref().and_then(file_stamp);
        Some(Arc::new(Self {
            entries: RwLock::new(entries),
            next: AtomicUsize::new(0),
            cooldown: Mutex::new(HashMap::new()),
            source,
            stamp: Mutex::new(stamp),
        }))
    }

    /// Re-read `PROXY_FILE` when mtime/size changed. Adding or replacing exits
    /// no longer needs a restart; an empty parse is treated as an editor
    /// truncation and keeps the current pool instead of wiping it mid-run.
    fn refresh(&self) {
        let Some(path) = self.source.as_deref() else {
            return;
        };
        let Some(stamp) = file_stamp(path) else {
            return;
        };
        {
            let guard = self.stamp.lock().unwrap_or_else(|e| e.into_inner());
            if guard.as_ref() == Some(&stamp) {
                return;
            }
        }
        let Ok(raw) = std::fs::read_to_string(path) else {
            return;
        };
        let entries = parse_entries(&raw);
        if let Ok(mut guard) = self.stamp.lock() {
            *guard = Some(stamp);
        }
        if entries.is_empty() {
            warn!(
                target: "engine",
                path = %path.display(),
                "proxy file parsed empty; keeping current pool"
            );
            return;
        }
        let count = entries.len();
        *self.entries.write().expect("proxy entries") = entries;
        info!(
            target: "engine",
            proxies = count,
            path = %path.display(),
            "proxy file reloaded"
        );
    }

    pub fn len(&self) -> usize {
        self.refresh();
        self.entries.read().expect("proxy entries").len()
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// Next proxy that is not cooling down. When every entry is cooling, the
    /// oldest one is returned anyway: a bad exit still beats no exit.
    pub fn next(&self) -> Option<Proxy> {
        self.refresh();
        let entries = self.entries.read().expect("proxy entries").clone();
        if entries.is_empty() {
            return None;
        }
        let now = Instant::now();
        let guard = self.cooldown.lock().ok();
        let cooling = |proxy: &Proxy| {
            guard
                .as_ref()
                .and_then(|map| map.get(&proxy.key()).copied())
                .map(|until| until > now)
                .unwrap_or(false)
        };
        for _ in 0..entries.len() {
            let index = self.next.fetch_add(1, Ordering::Relaxed) % entries.len();
            let candidate = &entries[index];
            if !cooling(candidate) {
                return Some(candidate.clone());
            }
        }
        let index = self.next.fetch_add(1, Ordering::Relaxed) % entries.len();
        Some(entries[index].clone())
    }

    pub fn mark_bad(&self, proxy: &Proxy) {
        if let Ok(mut guard) = self.cooldown.lock() {
            guard.insert(proxy.key(), Instant::now() + cooldown());
        }
    }

    pub fn mark_good(&self, proxy: &Proxy) {
        if let Ok(mut guard) = self.cooldown.lock() {
            guard.remove(&proxy.key());
        }
    }
}

/// A `ureq` agent that leaves through a specific proxy. Side-channel requests
/// (instruction images, sponsor probe) must use the same exit as the Chrome
/// session; a different IP can invalidate a campaign or sponsor token.
pub fn agent_for(proxy: Option<&Proxy>, timeout: Duration, user_agent: &str) -> ureq::Agent {
    let mut builder = ureq::AgentBuilder::new()
        .timeout(timeout)
        .user_agent(user_agent);
    if let Some(proxy) = proxy {
        let scheme = match proxy.scheme {
            Scheme::Socks5 => "socks5",
            Scheme::Http => "http",
        };
        let url = if proxy.user.is_empty() {
            format!("{scheme}://{}:{}", proxy.host, proxy.port)
        } else {
            format!(
                "{scheme}://{}:{}@{}:{}",
                proxy.user, proxy.pass, proxy.host, proxy.port
            )
        };
        if let Ok(configured) = ureq::Proxy::new(&url) {
            builder = builder.proxy(configured);
        }
    }
    builder.build()
}

/// A `ureq` agent that leaves through the pool when one is configured. Used by
/// callers that have no bound Chrome session (startup probes, tests).
pub fn agent(timeout: Duration, user_agent: &str) -> ureq::Agent {
    match shared().and_then(|pool| pool.next()) {
        Some(proxy) => agent_for(Some(&proxy), timeout, user_agent),
        None => agent_for(None, timeout, user_agent),
    }
}

/// Process-wide pool, initialised once from the environment.
pub fn shared() -> Option<Arc<ProxyPool>> {
    static POOL: OnceLock<Option<Arc<ProxyPool>>> = OnceLock::new();
    POOL.get_or_init(ProxyPool::from_env).clone()
}

fn warp_proxy_port() -> u16 {
    std::env::var("L4M_WARP_PORT")
        .ok()
        .and_then(|v| v.trim().parse::<u16>().ok())
        .filter(|p| *p > 0)
        .unwrap_or(40000)
}

pub fn is_warp_proxy(proxy: &Proxy) -> bool {
    proxy.scheme == Scheme::Socks5
        && (proxy.host == "127.0.0.1" || proxy.host == "localhost")
        && proxy.port == warp_proxy_port()
}

fn detect_warp_proxy() -> Option<Proxy> {
    if matches!(std::env::var("L4M_WARP_PROXY"), Ok(v) if v.trim() == "0") {
        return None;
    }
    let port = warp_proxy_port();
    let addr = std::net::SocketAddr::from(([127, 0, 0, 1], port));
    if std::net::TcpStream::connect_timeout(&addr, Duration::from_millis(80)).is_ok() {
        Some(Proxy {
            scheme: Scheme::Socks5,
            host: "127.0.0.1".into(),
            port,
            user: String::new(),
            pass: String::new(),
        })
    } else {
        None
    }
}

/// Cycle the local Cloudflare WARP tunnel (`warp-cli disconnect` -> `connect`)
/// to obtain a fresh exit IP when Google reCAPTCHA or Link4M rate-limits the
/// current one. Serialized by a static lock so concurrent workers don't collide.
pub async fn rotate_warp_ip() -> bool {
    static ROTATING: OnceLock<tokio::sync::Mutex<Option<Instant>>> = OnceLock::new();
    if matches!(std::env::var("L4M_WARP_ROTATE"), Ok(v) if v.trim() == "0") {
        return false;
    }
    let lock = ROTATING.get_or_init(|| tokio::sync::Mutex::new(None));
    let mut last = lock.lock().await;
    if let Some(prev) = *last {
        if prev.elapsed() < Duration::from_secs(12) {
            return true;
        }
    }
    let port = warp_proxy_port();
    let rotated = tokio::task::spawn_blocking(move || {
        let off = std::process::Command::new("warp-cli")
            .arg("disconnect")
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()
            .map(|s| s.success())
            .unwrap_or(false);
        if !off {
            return false;
        }
        std::thread::sleep(Duration::from_millis(350));
        let on = std::process::Command::new("warp-cli")
            .arg("connect")
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()
            .map(|s| s.success())
            .unwrap_or(false);
        if !on {
            return false;
        }
        let addr = std::net::SocketAddr::from(([127, 0, 0, 1], port));
        for _ in 0..30 {
            if std::net::TcpStream::connect_timeout(&addr, Duration::from_millis(120)).is_ok() {
                return true;
            }
            std::thread::sleep(Duration::from_millis(200));
        }
        false
    })
    .await
    .unwrap_or(false);
    if rotated {
        *last = Some(Instant::now());
        info!(target: "engine", port, "rotated Cloudflare WARP exit IP");
    }
    rotated
}

/// A running local relay. Dropping it stops the listener.
pub struct Relay {
    pub port: u16,
    task: JoinHandle<()>,
}

impl Drop for Relay {
    fn drop(&mut self) {
        self.task.abort();
    }
}

/// Copy data bidirectionally between `a` and `b`, resetting an idle timer whenever
/// bytes are transferred in either direction. If neither side transfers data within
/// `idle` duration, the transfer completes with Ok.
pub async fn idle_copy_bidirectional(
    a: &mut TcpStream,
    b: &mut TcpStream,
    idle: Duration,
) -> std::io::Result<(u64, u64)> {
    let (mut ar, mut aw) = a.split();
    let (mut br, mut bw) = b.split();

    let mut buf_a = vec![0u8; 8192];
    let mut buf_b = vec![0u8; 8192];

    let mut a_to_b: u64 = 0;
    let mut b_to_a: u64 = 0;

    let mut a_done = false;
    let mut b_done = false;

    let sleep = tokio::time::sleep(idle);
    tokio::pin!(sleep);

    while !a_done || !b_done {
        tokio::select! {
            res = ar.read(&mut buf_a), if !a_done => {
                match res {
                    Ok(0) => {
                        a_done = true;
                        let _ = bw.shutdown().await;
                    }
                    Ok(n) => {
                        bw.write_all(&buf_a[..n]).await?;
                        a_to_b += n as u64;
                        sleep.as_mut().reset(tokio::time::Instant::now() + idle);
                    }
                    Err(e) => return Err(e),
                }
            }
            res = br.read(&mut buf_b), if !b_done => {
                match res {
                    Ok(0) => {
                        b_done = true;
                        let _ = aw.shutdown().await;
                    }
                    Ok(n) => {
                        aw.write_all(&buf_b[..n]).await?;
                        b_to_a += n as u64;
                        sleep.as_mut().reset(tokio::time::Instant::now() + idle);
                    }
                    Err(e) => return Err(e),
                }
            }
            _ = &mut sleep => {
                // Idle timeout reached with no transfer on either side
                break;
            }
        }
    }
    Ok((a_to_b, b_to_a))
}

const RELAY_IDLE_TIMEOUT: Duration = Duration::from_secs(60);
const RELAY_HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(20);

/// Start a relay that forwards every connection to `proxy`.
pub async fn start_relay(proxy: Proxy) -> std::io::Result<Relay> {
    let listener = TcpListener::bind(("127.0.0.1", 0)).await?;
    let port = listener.local_addr()?.port();
    let task = tokio::spawn(async move {
        loop {
            let Ok((client, _)) = listener.accept().await else {
                break;
            };
            let proxy = proxy.clone();
            tokio::spawn(async move {
                let _ = handle(client, proxy).await;
            });
        }
    });
    Ok(Relay { port, task })
}

async fn read_head(stream: &mut TcpStream) -> std::io::Result<Vec<u8>> {
    let mut buf = vec![0u8; MAX_HEAD];
    let mut filled = 0;
    loop {
        if filled == buf.len() {
            return Ok(buf);
        }
        let n = stream.read(&mut buf[filled..]).await?;
        if n == 0 {
            return Ok(buf[..filled].to_vec());
        }
        filled += n;
        if buf[..filled].windows(4).any(|w| w == b"\r\n\r\n") {
            return Ok(buf[..filled].to_vec());
        }
    }
}

fn header_end(buf: &[u8]) -> Option<usize> {
    buf.windows(4).position(|w| w == b"\r\n\r\n")
}

async fn handle(mut client: TcpStream, proxy: Proxy) -> std::io::Result<()> {
    // Captcha traffic is many small request/response pairs; Nagle adds up to
    // 40 ms to each one behind a proxy hop.
    let _ = client.set_nodelay(true);
    let head = tokio::time::timeout(RELAY_HANDSHAKE_TIMEOUT, read_head(&mut client))
        .await
        .map_err(|_| std::io::Error::new(std::io::ErrorKind::TimedOut, "client handshake timeout"))??;
    let Some(end) = header_end(&head) else {
        return Ok(());
    };
    let head = &head[..end];
    let first_line_end = head.windows(2).position(|w| w == b"\r\n").unwrap_or(head.len());
    let first_line = String::from_utf8_lossy(&head[..first_line_end]).to_string();
    let mut parts = first_line.split_whitespace();
    let method = parts.next().unwrap_or("");
    let target = parts.next().unwrap_or("");
    if target.is_empty() {
        return Ok(());
    }
    if proxy.scheme == Scheme::Socks5 {
        return handle_socks(client, proxy, head, first_line_end, method, target).await;
    }

    let mut upstream = tokio::time::timeout(
        RELAY_HANDSHAKE_TIMEOUT,
        TcpStream::connect((proxy.host.as_str(), proxy.port)),
    )
    .await
    .map_err(|_| std::io::Error::new(std::io::ErrorKind::TimedOut, "upstream connect timeout"))??;
    let _ = upstream.set_nodelay(true);
    let auth = proxy
        .authorization()
        .map(|value| format!("Proxy-Authorization: Basic {value}\r\n"))
        .unwrap_or_default();

    if method.eq_ignore_ascii_case("CONNECT") {
        let request = format!("CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n{auth}\r\n");
        tokio::time::timeout(RELAY_HANDSHAKE_TIMEOUT, upstream.write_all(request.as_bytes()))
            .await
            .map_err(|_| std::io::Error::new(std::io::ErrorKind::TimedOut, "upstream write timeout"))??;
        let reply = tokio::time::timeout(RELAY_HANDSHAKE_TIMEOUT, read_head(&mut upstream))
            .await
            .map_err(|_| std::io::Error::new(std::io::ErrorKind::TimedOut, "upstream read timeout"))??;
        let status = String::from_utf8_lossy(&reply)
            .lines()
            .next()
            .unwrap_or("")
            .to_string();
        if !status.contains(" 200") {
            return Ok(());
        }
        client
            .write_all(b"HTTP/1.1 200 Connection established\r\n\r\n")
            .await?;
        if let Some(end) = header_end(&reply) {
            let rest = &reply[end + 4..];
            if !rest.is_empty() {
                client.write_all(rest).await?;
            }
        }
        let _ = idle_copy_bidirectional(&mut client, &mut upstream, RELAY_IDLE_TIMEOUT).await;
    } else {
        // Plain HTTP proxying: keep the absolute URI, append credentials.
        upstream.write_all(head).await?;
        upstream.write_all(b"\r\n").await?;
        upstream.write_all(auth.as_bytes()).await?;
        upstream.write_all(b"\r\n").await?;
        let _ = idle_copy_bidirectional(&mut client, &mut upstream, RELAY_IDLE_TIMEOUT).await;
    }
    Ok(())
}

fn split_host_port(target: &str) -> Option<(String, u16)> {
    if let Some(rest) = target.strip_prefix('[') {
        let (host, after) = rest.split_once(']')?;
        return Some((host.to_string(), after.strip_prefix(':')?.parse().ok()?));
    }
    let (host, port) = target.rsplit_once(':')?;
    Some((host.to_string(), port.parse().ok()?))
}

/// Absolute URI -> `(host, port, origin-form path)` for a plain HTTP request
/// that has to travel through a SOCKS tunnel instead of an HTTP proxy.
fn origin_form(target: &str) -> Option<(String, u16, String)> {
    let parsed = url::Url::parse(target).ok()?;
    if parsed.scheme() != "http" {
        return None;
    }
    let host = parsed.host_str()?.to_string();
    let port = parsed.port_or_known_default()?;
    let mut path = parsed.path().to_string();
    if path.is_empty() {
        path.push('/');
    }
    if let Some(query) = parsed.query() {
        path.push('?');
        path.push_str(query);
    }
    Some((host, port, path))
}

async fn socks5_negotiate(stream: &mut TcpStream, proxy: &Proxy) -> std::io::Result<()> {
    let methods: &[u8] = if proxy.user.is_empty() {
        &[0x00]
    } else {
        &[0x00, 0x02]
    };
    let mut greeting = Vec::with_capacity(2 + methods.len());
    greeting.push(0x05);
    greeting.push(methods.len() as u8);
    greeting.extend_from_slice(methods);
    stream.write_all(&greeting).await?;
    let mut reply = [0u8; 2];
    stream.read_exact(&mut reply).await?;
    if reply[0] != 0x05 {
        return Err(std::io::Error::other("upstream is not socks5"));
    }
    match reply[1] {
        0x00 => Ok(()),
        0x02 => {
            let user = proxy.user.as_bytes();
            let pass = proxy.pass.as_bytes();
            if user.len() > 255 || pass.len() > 255 {
                return Err(std::io::Error::other("socks5 credentials too long"));
            }
            let mut auth = Vec::with_capacity(3 + user.len() + pass.len());
            auth.push(0x01);
            auth.push(user.len() as u8);
            auth.extend_from_slice(user);
            auth.push(pass.len() as u8);
            auth.extend_from_slice(pass);
            stream.write_all(&auth).await?;
            let mut status = [0u8; 2];
            stream.read_exact(&mut status).await?;
            if status[1] == 0x00 {
                Ok(())
            } else {
                Err(std::io::Error::other("socks5 authentication failed"))
            }
        }
        method => Err(std::io::Error::other(format!(
            "socks5 method {method} rejected"
        ))),
    }
}

async fn socks5_connect(stream: &mut TcpStream, host: &str, port: u16) -> std::io::Result<()> {
    let mut request = Vec::with_capacity(7 + host.len());
    request.extend_from_slice(&[0x05, 0x01, 0x00]);
    match host.parse::<std::net::Ipv4Addr>() {
        Ok(ip) => {
            request.push(0x01);
            request.extend_from_slice(&ip.octets());
        }
        Err(_) => match host.parse::<std::net::Ipv6Addr>() {
            Ok(ip) => {
                request.push(0x04);
                request.extend_from_slice(&ip.octets());
            }
            Err(_) => {
                let bytes = host.as_bytes();
                if bytes.len() > 255 {
                    return Err(std::io::Error::other("socks5 host too long"));
                }
                request.push(0x03);
                request.push(bytes.len() as u8);
                request.extend_from_slice(bytes);
            }
        },
    }
    request.extend_from_slice(&port.to_be_bytes());
    stream.write_all(&request).await?;

    let mut head = [0u8; 4];
    stream.read_exact(&mut head).await?;
    if head[0] != 0x05 {
        return Err(std::io::Error::other("socks5 reply is malformed"));
    }
    if head[1] != 0x00 {
        return Err(std::io::Error::other(format!(
            "socks5 connect failed (code {})",
            head[1]
        )));
    }
    let skip = match head[3] {
        0x01 => 4,
        0x04 => 16,
        0x03 => {
            let mut len = [0u8; 1];
            stream.read_exact(&mut len).await?;
            len[0] as usize
        }
        code => {
            return Err(std::io::Error::other(format!(
                "socks5 address type {code} rejected"
            )))
        }
    };
    let mut tail = vec![0u8; skip + 2];
    stream.read_exact(&mut tail).await?;
    Ok(())
}

async fn handle_socks(
    mut client: TcpStream,
    proxy: Proxy,
    head: &[u8],
    first_line_end: usize,
    method: &str,
    target: &str,
) -> std::io::Result<()> {
    let mut upstream = tokio::time::timeout(
        RELAY_HANDSHAKE_TIMEOUT,
        TcpStream::connect((proxy.host.as_str(), proxy.port)),
    )
    .await
    .map_err(|_| std::io::Error::new(std::io::ErrorKind::TimedOut, "socks5 connect timeout"))??;
    let _ = upstream.set_nodelay(true);
    tokio::time::timeout(RELAY_HANDSHAKE_TIMEOUT, socks5_negotiate(&mut upstream, &proxy))
        .await
        .map_err(|_| std::io::Error::new(std::io::ErrorKind::TimedOut, "socks5 negotiate timeout"))??;

    if method.eq_ignore_ascii_case("CONNECT") {
        let (host, port) = split_host_port(target)
            .ok_or_else(|| std::io::Error::other("bad CONNECT target"))?;
        socks5_connect(&mut upstream, &host, port).await?;
        client
            .write_all(b"HTTP/1.1 200 Connection established\r\n\r\n")
            .await?;
        let _ = idle_copy_bidirectional(&mut client, &mut upstream, RELAY_IDLE_TIMEOUT).await;
        return Ok(());
    }

    let (host, port, path) = origin_form(target)
        .ok_or_else(|| std::io::Error::other("bad absolute URI for socks5"))?;
    socks5_connect(&mut upstream, &host, port).await?;
    let mut request = format!("{method} {path} HTTP/1.1\r\n");
    let headers = String::from_utf8_lossy(&head[first_line_end + 2..]);
    let mut has_host = false;
    for line in headers.split("\r\n") {
        if line.is_empty() {
            continue;
        }
        let lower = line.to_ascii_lowercase();
        if lower.starts_with("proxy-connection:") || lower.starts_with("proxy-authorization:") {
            continue;
        }
        if lower.starts_with("host:") {
            has_host = true;
        }
        request.push_str(line);
        request.push_str("\r\n");
    }
    if !has_host {
        request.push_str(&format!("Host: {host}\r\n"));
    }
    request.push_str("\r\n");
    upstream.write_all(request.as_bytes()).await?;
    let _ = idle_copy_bidirectional(&mut client, &mut upstream, RELAY_IDLE_TIMEOUT).await;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{parse_line, start_relay, Proxy, ProxyPool, Scheme};
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    use tokio::net::TcpStream;

    #[test]
    fn parses_host_port() {
        let proxy = parse_line("1.2.3.4:8080").unwrap();
        assert_eq!((proxy.host.as_str(), proxy.port), ("1.2.3.4", 8080));
        assert!(proxy.user.is_empty());
    }

    #[test]
    fn parses_credentials() {
        let proxy = parse_line("http://user:pa55@10.0.0.1:3128").unwrap();
        assert_eq!(proxy.host, "10.0.0.1");
        assert_eq!(proxy.port, 3128);
        assert_eq!(proxy.user, "user");
        assert_eq!(proxy.pass, "pa55");

        let proxy = parse_line("10.0.0.2:8000:user:pass").unwrap();
        assert_eq!(proxy.user, "user");
        assert_eq!(proxy.pass, "pass");
    }

    #[tokio::test]
    async fn relay_injects_credentials_and_tunnels() {
        // Fake upstream proxy: accepts one CONNECT, checks the injected
        // header, then echoes whatever the client sends.
        let upstream = tokio::net::TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
        let upstream_port = upstream.local_addr().unwrap().port();
        tokio::spawn(async move {
            let (mut socket, _) = upstream.accept().await.unwrap();
            let mut buf = vec![0u8; 4096];
            let n = socket.read(&mut buf).await.unwrap();
            let head = String::from_utf8_lossy(&buf[..n]).to_string();
            assert!(head.contains("CONNECT example.com:443"));
            assert!(head.contains("Proxy-Authorization: Basic dXNlcjpwYXNz"));
            socket.write_all(b"HTTP/1.1 200 OK\r\n\r\n").await.unwrap();
            let n = socket.read(&mut buf).await.unwrap();
            socket.write_all(&buf[..n]).await.unwrap();
        });

        let proxy = Proxy {
            scheme: Scheme::Http,
            host: "127.0.0.1".into(),
            port: upstream_port,
            user: "user".into(),
            pass: "pass".into(),
        };
        let relay = start_relay(proxy).await.unwrap();
        let mut client = TcpStream::connect(("127.0.0.1", relay.port)).await.unwrap();
        client
            .write_all(b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n")
            .await
            .unwrap();
        let mut reply = vec![0u8; 128];
        let n = client.read(&mut reply).await.unwrap();
        assert!(String::from_utf8_lossy(&reply[..n]).contains("200"));
        client.write_all(b"ping").await.unwrap();
        let mut echoed = [0u8; 4];
        client.read_exact(&mut echoed).await.unwrap();
        assert_eq!(&echoed, b"ping");
    }

    #[test]
    fn parses_socks_scheme() {
        let proxy = parse_line("socks5://user:pass@10.0.0.3:1080").unwrap();
        assert_eq!(proxy.scheme, Scheme::Socks5);
        assert_eq!(proxy.port, 1080);
        assert_eq!(proxy.user, "user");
        let plain = parse_line("10.0.0.4:8080").unwrap();
        assert_eq!(plain.scheme, Scheme::Http);
    }

    #[tokio::test]
    async fn relay_speaks_socks5_and_tunnels() {
        let upstream = tokio::net::TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
        let upstream_port = upstream.local_addr().unwrap().port();
        tokio::spawn(async move {
            let (mut socket, _) = upstream.accept().await.unwrap();
            let mut greeting = [0u8; 3];
            socket.read_exact(&mut greeting).await.unwrap();
            assert_eq!(greeting, [0x05, 0x01, 0x00]);
            socket.write_all(&[0x05, 0x00]).await.unwrap();

            let mut head = [0u8; 4];
            socket.read_exact(&mut head).await.unwrap();
            assert_eq!(&head[..3], &[0x05, 0x01, 0x00]);
            assert_eq!(head[3], 0x03);
            let mut len = [0u8; 1];
            socket.read_exact(&mut len).await.unwrap();
            let mut host = vec![0u8; len[0] as usize];
            socket.read_exact(&mut host).await.unwrap();
            assert_eq!(host, b"example.com");
            let mut port = [0u8; 2];
            socket.read_exact(&mut port).await.unwrap();
            assert_eq!(u16::from_be_bytes(port), 443);

            socket
                .write_all(&[0x05, 0x00, 0x00, 0x01, 127, 0, 0, 1, 0, 0])
                .await
                .unwrap();
            let mut buf = vec![0u8; 16];
            let n = socket.read(&mut buf).await.unwrap();
            socket.write_all(&buf[..n]).await.unwrap();
        });

        let proxy = Proxy {
            scheme: Scheme::Socks5,
            host: "127.0.0.1".into(),
            port: upstream_port,
            user: String::new(),
            pass: String::new(),
        };
        let relay = start_relay(proxy).await.unwrap();
        let mut client = TcpStream::connect(("127.0.0.1", relay.port)).await.unwrap();
        client
            .write_all(b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n")
            .await
            .unwrap();
        let mut reply = vec![0u8; 128];
        let n = client.read(&mut reply).await.unwrap();
        assert!(String::from_utf8_lossy(&reply[..n]).contains("200"));
        client.write_all(b"ping").await.unwrap();
        let mut echoed = [0u8; 4];
        client.read_exact(&mut echoed).await.unwrap();
        assert_eq!(&echoed, b"ping");
    }

    #[tokio::test]
    async fn relay_socks5_rewrites_absolute_http_request() {
        let upstream = tokio::net::TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
        let upstream_port = upstream.local_addr().unwrap().port();
        tokio::spawn(async move {
            let (mut socket, _) = upstream.accept().await.unwrap();
            let mut greeting = [0u8; 3];
            socket.read_exact(&mut greeting).await.unwrap();
            socket.write_all(&[0x05, 0x00]).await.unwrap();
            let mut head = [0u8; 4];
            socket.read_exact(&mut head).await.unwrap();
            let mut len = [0u8; 1];
            socket.read_exact(&mut len).await.unwrap();
            let mut host = vec![0u8; len[0] as usize];
            socket.read_exact(&mut host).await.unwrap();
            let mut port = [0u8; 2];
            socket.read_exact(&mut port).await.unwrap();
            assert_eq!(host, b"example.com");
            assert_eq!(u16::from_be_bytes(port), 80);
            socket
                .write_all(&[0x05, 0x00, 0x00, 0x01, 127, 0, 0, 1, 0, 0])
                .await
                .unwrap();

            let mut buf = Vec::new();
            let mut chunk = [0u8; 2048];
            while !buf.windows(4).any(|w| w == b"\r\n\r\n") {
                let n = socket.read(&mut chunk).await.unwrap();
                if n == 0 {
                    break;
                }
                buf.extend_from_slice(&chunk[..n]);
            }
            let request = String::from_utf8_lossy(&buf).to_string();
            assert!(
                request.starts_with("GET /path?q=1 HTTP/1.1\r\n"),
                "rewritten request: {request}"
            );
            assert!(request.contains("Host: example.com"));
            assert!(!request.to_lowercase().contains("proxy-connection"));
            socket
                .write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
                .await
                .unwrap();
        });

        let proxy = Proxy {
            scheme: Scheme::Socks5,
            host: "127.0.0.1".into(),
            port: upstream_port,
            user: String::new(),
            pass: String::new(),
        };
        let relay = start_relay(proxy).await.unwrap();
        let mut client = TcpStream::connect(("127.0.0.1", relay.port)).await.unwrap();
        client
            .write_all(
                b"GET http://example.com/path?q=1 HTTP/1.1\r\nHost: example.com\r\n\
                  Proxy-Connection: keep-alive\r\n\r\n",
            )
            .await
            .unwrap();
        let read = tokio::time::timeout(std::time::Duration::from_secs(5), async {
            let mut reply = Vec::new();
            let mut chunk = [0u8; 512];
            loop {
                let n = client.read(&mut chunk).await.unwrap();
                if n == 0 {
                    break;
                }
                reply.extend_from_slice(&chunk[..n]);
            }
            reply
        })
        .await
        .expect("relay response timed out");
        assert!(String::from_utf8_lossy(&read).contains("ok"));
    }

    #[test]
    fn skips_comments_and_junk() {
        assert!(parse_line("# comment").is_none());
        assert!(parse_line("").is_none());
        assert!(parse_line("nonsense").is_none());
    }

    #[test]
    fn reloads_proxy_file_when_it_changes() {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!(
            "l4m-proxies-{}-{nanos}.txt",
            std::process::id()
        ));
        std::fs::write(&path, "1.1.1.1:8080\n").expect("seed proxies");
        let pool = ProxyPool::from_file(path.clone()).expect("pool");
        assert_eq!(pool.len(), 1);

        std::fs::write(&path, "1.1.1.1:8080\n2.2.2.2:8081\n").expect("update proxies");
        assert_eq!(pool.len(), 2);

        // An editor truncation keeps the live pool instead of leaving workers
        // with no exit.
        std::fs::write(&path, "").expect("truncate");
        assert_eq!(pool.len(), 2);
        let _ = std::fs::remove_file(&path);
    }

    #[tokio::test]
    async fn test_idle_copy_bidirectional_transfers_and_expires_on_idle() {
        use std::time::Duration;
        let listener = tokio::net::TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
        let port = listener.local_addr().unwrap().port();

        let srv = tokio::spawn(async move {
            let (mut a, _) = listener.accept().await.unwrap();
            let mut b = TcpStream::connect(("127.0.0.1", port)).await.unwrap();
            let _ = super::idle_copy_bidirectional(&mut a, &mut b, Duration::from_millis(150)).await;
        });

        let mut client_a = TcpStream::connect(("127.0.0.1", port)).await.unwrap();
        // listener will accept client_a, and server connects client_b back to listener.
        // Wait briefly for server connection
        client_a.write_all(b"ping").await.unwrap();
        tokio::time::sleep(Duration::from_millis(300)).await;
        let _ = srv.await;
    }
}
