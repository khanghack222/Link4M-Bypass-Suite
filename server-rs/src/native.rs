//! Loopback client for the native `l4m-engine` (crate `engine-rs`).
//!
//! The façade always reaches Python through a subprocess; the native engine is
//! an HTTP service instead, so this module speaks just enough HTTP/1.1 to POST
//! one JSON job and read one JSON reply. No client crate is pulled in: the call
//! is always loopback, `Connection: close`, and the body is bounded.
//!
//! `Server: l4m-engine` answers `{status, url, destination_url, provider,
//! cached, elapsed_ms, job_id, error}`. `status` is the only field worth
//! branching on; everything else is forwarded for logging.

use std::time::Duration;

use serde_json::Value;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;

/// A native engine reply is a few hundred bytes; anything near this size is a
/// misrouted response (an HTML error page, a proxy banner) and must not be
/// parsed as a job result.
const MAX_BODY: usize = 1024 * 1024;
const MAX_HEADER: usize = 64 * 1024;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NativeClient {
    host: String,
    port: u16,
    prefix: String,
    api_key: String,
}

/// Parse `L4M_NATIVE_URL`. Accepts `host:port`, `http://host:port` and an
/// optional path prefix (`http://127.0.0.1:8080/native`). Any scheme other than
/// `http` is rejected rather than silently downgraded.
pub fn parse_base(raw: &str) -> Option<(String, u16, String)> {
    let raw = raw.trim();
    if raw.is_empty() {
        return None;
    }
    let without_scheme = match raw.split_once("://") {
        Some((scheme, rest)) => {
            if !scheme.eq_ignore_ascii_case("http") {
                return None;
            }
            rest
        }
        None => raw,
    };
    let (authority, path) = match without_scheme.find('/') {
        Some(index) => (&without_scheme[..index], &without_scheme[index..]),
        None => (without_scheme, ""),
    };
    if authority.is_empty() {
        return None;
    }
    let (host, port) = match authority.rsplit_once(':') {
        Some((host, port)) => {
            let port = port.parse::<u16>().ok()?;
            (host.to_string(), port)
        }
        None => (authority.to_string(), 80),
    };
    if host.is_empty() {
        return None;
    }
    let prefix = path.trim_end_matches('/').to_string();
    Some((host, port, prefix))
}

impl NativeClient {
    /// `None` when the variable is unset or unusable — the caller then keeps
    /// using the Python engine, which is the historic behaviour.
    pub fn from_env_value(raw: &str, api_key: &str) -> Option<Self> {
        let (host, port, prefix) = parse_base(raw)?;
        Some(NativeClient {
            host,
            port,
            prefix,
            api_key: api_key.trim().to_string(),
        })
    }

    pub fn base(&self) -> String {
        format!("http://{}:{}{}", self.host, self.port, self.prefix)
    }

    /// POST one job to the native engine and return the decoded JSON envelope.
    /// Every transport problem is an `Err` so the caller can fall back.
    pub async fn bypass(&self, url: &str, timeout_secs: u64) -> Result<Value, String> {
        let payload = serde_json::json!({
            "url": url,
            "wait": true,
            "timeout": timeout_secs,
        });
        let body = payload.to_string();
        let path = format!("{}/api/v1/bypass", self.prefix);
        let mut request = format!(
            "POST {path} HTTP/1.1\r\nHost: {host}:{port}\r\nContent-Type: application/json\r\n\
             Content-Length: {len}\r\nConnection: close\r\n",
            path = path,
            host = self.host,
            port = self.port,
            len = body.len(),
        );
        if !self.api_key.is_empty() {
            request.push_str(&format!("X-API-Key: {}\r\n", self.api_key));
        }
        request.push_str("\r\n");
        request.push_str(&body);

        // Native jobs run under the same budget as the Python engine; the extra
        // second covers connect + JSON parse and keeps the outer timeout the
        // one that reports ERR_ENGINE_TIMEOUT.
        let exchange = exchange(&self.host, self.port, &request, Duration::from_secs(timeout_secs + 1));
        let raw = tokio::time::timeout(Duration::from_secs(timeout_secs + 2), exchange)
            .await
            .map_err(|_| format!("native engine không trả lời trong {}s", timeout_secs))?
            .map_err(|error| format!("native engine: {error}"))?;
        parse_response(&raw)
    }
}

async fn exchange(host: &str, port: u16, request: &str, budget: Duration) -> Result<Vec<u8>, String> {
    let connect = tokio::time::timeout(budget, TcpStream::connect((host, port)))
        .await
        .map_err(|_| format!("connect {host}:{port} hết giờ"))?
        .map_err(|error| format!("connect {host}:{port}: {error}"))?;
    let mut stream = connect;
    stream
        .write_all(request.as_bytes())
        .await
        .map_err(|error| format!("write: {error}"))?;
    stream.flush().await.map_err(|error| format!("flush: {error}"))?;

    let mut buffer = Vec::with_capacity(4096);
    let mut chunk = [0u8; 8192];
    loop {
        if buffer.len() > MAX_BODY + MAX_HEADER {
            return Err("response quá lớn".into());
        }
        let read = tokio::time::timeout(budget, stream.read(&mut chunk))
            .await
            .map_err(|_| "read hết giờ".to_string())?
            .map_err(|error| format!("read: {error}"))?;
        if read == 0 {
            break;
        }
        buffer.extend_from_slice(&chunk[..read]);
    }
    Ok(buffer)
}

fn find_header_end(raw: &[u8]) -> Option<usize> {
    raw.windows(4).position(|window| window == b"\r\n\r\n")
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RawResponse {
    pub status: u16,
    pub headers: Vec<(String, String)>,
    pub body: Vec<u8>,
}

/// Split an HTTP/1.1 response, undoing chunked framing when present. Exposed
/// for tests.
pub fn split_response(raw: &[u8]) -> Result<RawResponse, String> {
    let end = find_header_end(raw).ok_or("thiếu header terminator")?;
    let head = std::str::from_utf8(&raw[..end]).map_err(|_| "header không phải UTF-8")?;
    let mut lines = head.split("\r\n");
    let status_line = lines.next().unwrap_or_default();
    let status = status_line
        .split_whitespace()
        .nth(1)
        .and_then(|code| code.parse::<u16>().ok())
        .ok_or_else(|| format!("status line lạ: {status_line}"))?;
    let headers: Vec<(String, String)> = lines
        .filter_map(|line| line.split_once(':'))
        .map(|(name, value)| (name.trim().to_ascii_lowercase(), value.trim().to_string()))
        .collect();
    let rest = &raw[end + 4..];
    let chunked = headers.iter().any(|(name, value)| {
        name == "transfer-encoding" && value.to_ascii_lowercase().contains("chunked")
    });
    let body = if chunked {
        dechunk(rest)?
    } else if let Some(length) = headers
        .iter()
        .find(|(name, _)| name == "content-length")
        .and_then(|(_, value)| value.parse::<usize>().ok())
    {
        rest.get(..length).unwrap_or(rest).to_vec()
    } else {
        rest.to_vec()
    };
    Ok(RawResponse { status, headers, body })
}

fn dechunk(raw: &[u8]) -> Result<Vec<u8>, String> {
    let mut out = Vec::new();
    let mut rest = raw;
    loop {
        let line_end = rest
            .windows(2)
            .position(|window| window == b"\r\n")
            .ok_or("chunk thiếu CRLF")?;
        let size_line = std::str::from_utf8(&rest[..line_end]).map_err(|_| "chunk size không UTF-8")?;
        let size = usize::from_str_radix(size_line.split(';').next().unwrap_or("").trim(), 16)
            .map_err(|_| format!("chunk size lạ: {size_line}"))?;
        rest = &rest[line_end + 2..];
        if size == 0 {
            break;
        }
        if rest.len() < size + 2 {
            return Err("chunk ngắn hơn khai báo".into());
        }
        out.extend_from_slice(&rest[..size]);
        rest = &rest[size + 2..];
        if out.len() > MAX_BODY {
            return Err("body vượt giới hạn".into());
        }
    }
    Ok(out)
}

pub fn parse_response(raw: &[u8]) -> Result<Value, String> {
    let response = split_response(raw)?;
    if response.body.len() > MAX_BODY {
        return Err("body vượt giới hạn".into());
    }
    let text = String::from_utf8_lossy(&response.body);
    if !(200..300).contains(&response.status) {
        return Err(format!(
            "native HTTP {}: {}",
            response.status,
            text.trim().chars().take(300).collect::<String>()
        ));
    }
    serde_json::from_str(text.trim()).map_err(|error| format!("JSON lỗi: {error}"))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_url_forms() {
        assert_eq!(parse_base("127.0.0.1:8080"), Some(("127.0.0.1".into(), 8080, String::new())));
        assert_eq!(
            parse_base("http://127.0.0.1:8080/"),
            Some(("127.0.0.1".into(), 8080, String::new()))
        );
        assert_eq!(
            parse_base("http://127.0.0.1:8080/native/"),
            Some(("127.0.0.1".into(), 8080, "/native".into()))
        );
        assert_eq!(
            parse_base("http://localhost"),
            Some(("localhost".into(), 80, String::new()))
        );
        assert_eq!(parse_base("https://127.0.0.1:8080"), None);
        assert_eq!(parse_base(""), None);
        assert_eq!(parse_base("127.0.0.1:notaport"), None);
    }

    #[test]
    fn splits_content_length_and_chunked() {
        let plain = b"HTTP/1.1 200 OK\r\ncontent-length: 5\r\n\r\nhello";
        let parsed = split_response(plain).unwrap();
        assert_eq!(parsed.status, 200);
        assert_eq!(parsed.body, b"hello");

        let chunked = b"HTTP/1.1 200 OK\r\ntransfer-encoding: chunked\r\n\r\n5\r\nhello\r\n0\r\n\r\n";
        assert_eq!(split_response(chunked).unwrap().body, b"hello");
    }

    #[test]
    fn rejects_non_2xx_and_garbage() {
        let missing = b"HTTP/1.1 501 Not Implemented\r\ncontent-length: 7\r\n\r\n{\"a\":1}";
        assert!(parse_response(missing).unwrap_err().contains("501"));
        assert!(parse_response(b"nonsense").is_err());
    }

    #[tokio::test]
    async fn posts_and_reads_json_over_loopback() {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let port = listener.local_addr().unwrap().port();
        let server = tokio::spawn(async move {
            let (mut socket, _) = listener.accept().await.unwrap();
            let mut buffer = Vec::new();
            let mut chunk = [0u8; 1024];
            loop {
                let read = socket.read(&mut chunk).await.unwrap();
                if read == 0 {
                    break;
                }
                buffer.extend_from_slice(&chunk[..read]);
                if buffer.windows(4).any(|window| window == b"\r\n\r\n") {
                    break;
                }
            }
            let request = String::from_utf8_lossy(&buffer).to_string();
            let reply = r#"{"status":"success","destination_url":"https://example.com/x","provider":"link4m"}"#;
            let response = format!(
                "HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: {}\r\n\r\n{}",
                reply.len(),
                reply
            );
            socket.write_all(response.as_bytes()).await.unwrap();
            socket.flush().await.unwrap();
            request
        });

        let client = NativeClient::from_env_value(&format!("127.0.0.1:{port}"), "").unwrap();
        let value = client.bypass("https://link4m.net/go/abc", 30).await.unwrap();
        assert_eq!(value["status"], "success");
        assert_eq!(value["destination_url"], "https://example.com/x");

        let request = server.await.unwrap();
        assert!(request.starts_with("POST /api/v1/bypass HTTP/1.1"));
        assert!(request.contains("https://link4m.net/go/abc"));
        assert!(request.contains("\"wait\":true"));
    }

    #[tokio::test]
    async fn connection_refused_is_an_error_not_a_hang() {
        // Bind then drop so the port is almost certainly closed.
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let port = listener.local_addr().unwrap().port();
        drop(listener);
        let client = NativeClient::from_env_value(&format!("127.0.0.1:{port}"), "").unwrap();
        let error = client.bypass("https://link4m.net/go/abc", 5).await.unwrap_err();
        assert!(error.contains("native engine"), "unexpected error: {error}");
    }
}
