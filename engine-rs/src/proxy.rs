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
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::{Duration, Instant};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpStream};
use tokio::task::JoinHandle;

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

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Proxy {
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
    let mut rest = line;
    if let Some((_, tail)) = rest.split_once("://") {
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
    Some(Proxy { host: host.to_string(), port, user, pass })
}

pub struct ProxyPool {
    entries: Vec<Proxy>,
    next: AtomicUsize,
    cooldown: Mutex<HashMap<String, Instant>>,
}

impl ProxyPool {
    /// Build from `PROXY_LIST` (inline, newline/comma separated) or
    /// `PROXY_FILE` (default `data/proxies.txt`). Empty list → `None`.
    pub fn from_env() -> Option<Arc<ProxyPool>> {
        let raw = match std::env::var("PROXY_LIST") {
            Ok(value) if !value.trim().is_empty() => value,
            _ => {
                let path = std::env::var("PROXY_FILE")
                    .unwrap_or_else(|_| "data/proxies.txt".to_string());
                std::fs::read_to_string(path).ok()?
            }
        };
        let entries: Vec<Proxy> = raw
            .split(['\n', ','])
            .filter_map(parse_line)
            .collect();
        if entries.is_empty() {
            return None;
        }
        Some(Arc::new(Self {
            entries,
            next: AtomicUsize::new(0),
            cooldown: Mutex::new(HashMap::new()),
        }))
    }

    pub fn len(&self) -> usize {
        self.entries.len()
    }

    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    /// Next proxy that is not cooling down. When every entry is cooling, the
    /// oldest one is returned anyway: a bad exit still beats no exit.
    pub fn next(&self) -> Option<Proxy> {
        if self.entries.is_empty() {
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
        for _ in 0..self.entries.len() {
            let index = self.next.fetch_add(1, Ordering::Relaxed) % self.entries.len();
            let candidate = &self.entries[index];
            if !cooling(candidate) {
                return Some(candidate.clone());
            }
        }
        let index = self.next.fetch_add(1, Ordering::Relaxed) % self.entries.len();
        Some(self.entries[index].clone())
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

/// A `ureq` agent that leaves through a pool proxy when one is configured.
/// Used by the sponsor probe and instruction-image download so those requests
/// do not leak the machine's real address.
pub fn agent(timeout: Duration, user_agent: &str) -> ureq::Agent {
    let mut builder = ureq::AgentBuilder::new()
        .timeout(timeout)
        .user_agent(user_agent);
    if let Some(proxy) = shared().and_then(|pool| pool.next()) {
        let url = if proxy.user.is_empty() {
            format!("http://{}:{}", proxy.host, proxy.port)
        } else {
            format!(
                "http://{}:{}@{}:{}",
                proxy.user, proxy.pass, proxy.host, proxy.port
            )
        };
        if let Ok(configured) = ureq::Proxy::new(&url) {
            builder = builder.proxy(configured);
        }
    }
    builder.build()
}

/// Process-wide pool, initialised once from the environment.
pub fn shared() -> Option<Arc<ProxyPool>> {
    static POOL: OnceLock<Option<Arc<ProxyPool>>> = OnceLock::new();
    POOL.get_or_init(ProxyPool::from_env).clone()
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
    let head = read_head(&mut client).await?;
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

    let mut upstream = TcpStream::connect((proxy.host.as_str(), proxy.port)).await?;
    let auth = proxy
        .authorization()
        .map(|value| format!("Proxy-Authorization: Basic {value}\r\n"))
        .unwrap_or_default();

    if method.eq_ignore_ascii_case("CONNECT") {
        let request = format!("CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n{auth}\r\n");
        upstream.write_all(request.as_bytes()).await?;
        let reply = read_head(&mut upstream).await?;
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
        tokio::io::copy_bidirectional(&mut client, &mut upstream).await?;
    } else {
        // Plain HTTP proxying: keep the absolute URI, append credentials.
        upstream.write_all(head).await?;
        upstream.write_all(b"\r\n").await?;
        upstream.write_all(auth.as_bytes()).await?;
        upstream.write_all(b"\r\n").await?;
        tokio::io::copy_bidirectional(&mut client, &mut upstream).await?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{parse_line, start_relay, Proxy};
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
    fn skips_comments_and_junk() {
        assert!(parse_line("# comment").is_none());
        assert!(parse_line("").is_none());
        assert!(parse_line("nonsense").is_none());
    }
}
