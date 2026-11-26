//! Rust port of `src/core/fast_decode.py`.
//!
//! Zero-browser resolution for `/go/file/<base64|percent>` and base64 payloads
//! in query/fragment values. Self-references (shortlink hosts) are rejected so
//! a shortlink can never be returned as its own destination.

use base64::engine::general_purpose::STANDARD;
use base64::Engine as _;
use url::Url;

use crate::providers::normalize_url;

const SELF_REF: [&str; 4] = ["link4m", "bbmkts", "trafficvn", "yeumoney"];

fn is_self_reference(url: &str) -> bool {
    let lower = url.to_lowercase();
    SELF_REF.iter().any(|needle| lower.contains(needle))
}

fn percent_decode(input: &str) -> String {
    let bytes = input.as_bytes();
    let mut out: Vec<u8> = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            let hex = std::str::from_utf8(&bytes[i + 1..i + 3]).ok();
            if let Some(value) = hex.and_then(|h| u8::from_str_radix(h, 16).ok()) {
                out.push(value);
                i += 3;
                continue;
            }
        }
        out.push(bytes[i]);
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

fn looks_like_url(value: &str) -> bool {
    value.starts_with("http://") || value.starts_with("https://")
}

fn try_base64(value: &str) -> Option<String> {
    let mut candidate = value.trim().to_string();
    if candidate.is_empty() {
        return None;
    }
    let pad = (4 - candidate.len() % 4) % 4;
    candidate.push_str(&"=".repeat(pad));
    let decoded = STANDARD.decode(candidate.as_bytes()).ok()?;
    let text = String::from_utf8_lossy(&decoded).into_owned();
    if looks_like_url(&text) {
        Some(text)
    } else {
        None
    }
}

pub fn fast_decode(raw: &str) -> Option<String> {
    let url = normalize_url(raw);
    if url.is_empty() {
        return None;
    }

    if let Some(pos) = url.find("/go/file/") {
        let rest = &url[pos + "/go/file/".len()..];
        let part = rest.split(['?', '#']).next().unwrap_or("");
        let once = percent_decode(part);
        let twice = percent_decode(&once);
        for candidate in [once, twice] {
            if let Some(destination) = try_base64(&candidate) {
                if !is_self_reference(&destination) {
                    return Some(destination);
                }
            }
            if looks_like_url(&candidate) && !is_self_reference(&candidate) {
                return Some(candidate);
            }
        }
    }

    let parsed = Url::parse(&url).ok()?;
    let mut values: Vec<String> = parsed
        .query_pairs()
        .map(|(_, value)| value.into_owned())
        .collect();
    if let Some(fragment) = parsed.fragment() {
        values.push(fragment.to_string());
    }
    for value in values {
        if value.len() <= 16 {
            continue;
        }
        if let Some(destination) = try_base64(&value) {
            if !is_self_reference(&destination) {
                return Some(destination);
            }
        }
        // Some shortlinks put the destination in plain text, already decoded
        // by `Url::parse` (`?url=https://...` or `#https://...`).
        if looks_like_url(&value) && !is_self_reference(&value) {
            return Some(value);
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn decodes_go_file_base64() {
        assert_eq!(
            fast_decode("https://yeumoney.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS94").as_deref(),
            Some("https://example.com/x")
        );
    }

    #[test]
    fn decodes_percent_encoded_plain_url() {
        let encoded = "https%3A%2F%2Fexample.com%2Ftarget";
        assert_eq!(
            fast_decode(&format!("https://bbmkts.com/go/file/{encoded}")).as_deref(),
            Some("https://example.com/target")
        );
    }

    #[test]
    fn decodes_double_percent_encoded_url() {
        let encoded = "https%253A%252F%252Fexample.com%252Fdouble";
        assert_eq!(
            fast_decode(&format!("https://bbmkts.com/go/file/{encoded}")).as_deref(),
            Some("https://example.com/double")
        );
    }

    #[test]
    fn does_not_return_half_decoded_url() {
        // "https%3A..." must not pass as a destination; only a real scheme does.
        let encoded = "https%253A%252F%252Fexample.com%252Fhalf";
        let got = fast_decode(&format!("https://bbmkts.com/go/file/{encoded}"));
        assert_eq!(got.as_deref(), Some("https://example.com/half"));
    }

    #[test]
    fn rejects_self_reference() {
        // base64("https://link4m.net/go/abc")
        assert!(
            fast_decode("https://yeumoney.com/go/file/aHR0cHM6Ly9saW5rNG0ubmV0L2dvL2FiYw==")
                .is_none()
        );
    }

    #[test]
    fn decodes_query_payload() {
        let payload = STANDARD.encode("https://example.com/from-query");
        let url = format!("https://example.com/redirect?u={payload}");
        assert_eq!(
            fast_decode(&url).as_deref(),
            Some("https://example.com/from-query")
        );
    }

    #[test]
    fn decodes_plain_query_url() {
        let url = "https://example.com/redirect?url=https%3A%2F%2Fexample.com%2Fplain";
        assert_eq!(
            fast_decode(url).as_deref(),
            Some("https://example.com/plain")
        );
    }

    #[test]
    fn plain_query_does_not_return_a_shortlink() {
        let url = "https://example.com/redirect?url=https%3A%2F%2Flink4m.net%2Fgo%2Fabc";
        assert!(fast_decode(url).is_none());
    }
}
