//! Provider table mirrored from `src/core/provider_table.py`.
//!
//! This module is intentionally dependency-free apart from `url`: it is the
//! Rust face's only copy of the host map, so classification, `--check` and the
//! `/api/v1/supported` payload cannot drift from each other.

use url::Url;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EngineKind {
    Browser,
    ExternalNode,
    Decode,
}

impl EngineKind {
    pub fn as_str(self) -> &'static str {
        match self {
            EngineKind::Browser => "browser",
            EngineKind::ExternalNode => "external_node",
            EngineKind::Decode => "decode",
        }
    }
}

#[derive(Debug)]
#[allow(dead_code)] // the full table mirrors provider_table.py
pub struct ProviderSpec {
    pub key: &'static str,
    pub aliases: &'static [&'static str],
    pub hosts: &'static [&'static str],
    pub kind: EngineKind,
    pub module: &'static str,
    pub note: &'static str,
}

pub static PROVIDERS: &[ProviderSpec] = &[
    ProviderSpec {
        key: "LINK4M",
        aliases: &["LINK4M", "LINK4", "L4M"],
        hosts: &[
            "link4m.net",
            "link4m.com",
            "link4m.co",
            "link4m.org",
            "link4m.vip",
            "link4m.pro",
            "link4m.me",
            "link4m.app",
        ],
        kind: EngineKind::Browser,
        module: "bypass / link4m_engine",
        note: "sponsor OCR + reCAPTCHA audio",
    },
    ProviderSpec {
        key: "BBMKTS",
        aliases: &["BBMKTS", "BBMKT", "YOUMONEY", "YEUMONEY"],
        hosts: &["bbmkts.com", "yeumoney.com"],
        kind: EngineKind::Browser,
        module: "bbmkts_runner",
        note: "dual-tab countdown + route patch",
    },
    ProviderSpec {
        key: "GTRAFFIC",
        aliases: &["GTRAFFIC", "G-TRAFFIC", "DIRECT_GTRAFFIC"],
        hosts: &[
            "gtraffic.io",
            "direct.gtraffic.io",
            "dr-client.gtraffic.io",
            "client.gtraffic.io",
        ],
        kind: EngineKind::Browser,
        module: "gtraffic_runner",
        note: "mobile viewport + API leak",
    },
    ProviderSpec {
        key: "LAYMA",
        aliases: &["LAYMA", "LAYMA.NET"],
        hosts: &["layma.net"],
        kind: EngineKind::Browser,
        module: "layma_runner",
        note: "qcaptcha stealth + HSV vision",
    },
    ProviderSpec {
        key: "TRAFFICVN",
        aliases: &["TRAFFICVN", "TRAFFIC_VN", "IATUM"],
        hosts: &["trafficvn.com", "trafficvn.net"],
        kind: EngineKind::Browser,
        module: "trafficvn_runner",
        note: "countdown + activation code",
    },
    ProviderSpec {
        key: "OCTOLINK",
        aliases: &[
            "OCTOLINK",
            "OCTO",
            "LINK999",
            "UPTOLINK",
            "LINKHUONGDAN",
            "SHORTEARN",
        ],
        // Trailing dots are prefix entries: uptolink.* / linkhuongdan.*
        hosts: &[
            "octolink.vip",
            "link999.app",
            "link999.com",
            "uptolink.",
            "linkhuongdan.",
            "shortearn.net",
        ],
        kind: EngineKind::ExternalNode,
        module: "octolink_runner.js",
        note: "canvas physics + hold captcha",
    },
    ProviderSpec {
        key: "DECODE",
        aliases: &["DECODE", "BASE64", "FASTPATH"],
        hosts: &[],
        kind: EngineKind::Decode,
        module: "fast_decode",
        note: "base64/pct fast path, no browser",
    },
];

#[allow(dead_code)]
pub const GENERIC_KEY: &str = "GENERIC";

pub fn normalize_url(raw: &str) -> String {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return String::new();
    }
    if trimmed.contains("://") {
        trimmed.to_string()
    } else {
        format!("https://{}", trimmed.trim_start_matches('/'))
    }
}

pub fn host_of(raw: &str) -> Option<String> {
    let normalized = normalize_url(raw);
    if normalized.is_empty() {
        return None;
    }
    let host = Url::parse(&normalized).ok()?.host_str()?.to_lowercase();
    let host = host.trim_end_matches('.').to_string();
    Some(host.strip_prefix("www.").unwrap_or(&host).to_string())
}

pub fn host_matches(host: &str, pattern: &str) -> bool {
    if host.is_empty() || pattern.is_empty() {
        return false;
    }
    if let Some(base) = pattern.strip_suffix('.') {
        return host.starts_with(base);
    }
    host == pattern || host.ends_with(&format!(".{pattern}"))
}

pub fn detect(raw: &str) -> Option<&'static ProviderSpec> {
    let host = host_of(raw)?;
    PROVIDERS.iter().find(|spec| {
        spec.kind != EngineKind::Decode && spec.hosts.iter().any(|h| host_matches(&host, h))
    })
}

#[allow(dead_code)]
pub fn classify(raw: &str) -> &'static str {
    detect(raw).map(|spec| spec.key).unwrap_or(GENERIC_KEY)
}

#[allow(dead_code)]
pub fn canonical_key(raw: &str) -> Option<&'static str> {
    let needle = raw.trim().to_ascii_uppercase();
    if needle.is_empty() {
        return None;
    }
    PROVIDERS
        .iter()
        .find(|spec| spec.key == needle || spec.aliases.contains(&needle.as_str()))
        .map(|spec| spec.key)
}

#[allow(dead_code)]
pub fn spec_for(key: &str) -> Option<&'static ProviderSpec> {
    let canonical = canonical_key(key)?;
    PROVIDERS.iter().find(|spec| spec.key == canonical)
}

/// First path segment after `prefix`, mirroring the Python regex `([A-Za-z0-9_-]+)`.
fn segment_after<'a>(path: &'a str, prefix: &str) -> Option<&'a str> {
    let rest = path.strip_prefix(prefix)?;
    let seg = rest.split('/').next().unwrap_or("");
    let end = seg
        .find(|c: char| !(c.is_ascii_alphanumeric() || c == '_' || c == '-'))
        .unwrap_or(seg.len());
    let seg = &seg[..end];
    if seg.is_empty() {
        None
    } else {
        Some(seg)
    }
}

fn last_segment(path: &str) -> Option<&str> {
    path.trim_end_matches('/')
        .rsplit('/')
        .find(|seg| !seg.is_empty())
}

fn slug_for(key: &str, path: &str) -> String {
    let slug = match key {
        "LINK4M" | "BBMKTS" => segment_after(path, "/go/"),
        "GTRAFFIC" | "LAYMA" => last_segment(path),
        "TRAFFICVN" => segment_after(path, "/get/").or_else(|| segment_after(path, "/")),
        _ => None,
    };
    slug.unwrap_or("").to_string()
}

/// Canonical provider key plus the cache slug (empty when the brand has none).
pub fn parse_key(raw: &str) -> Option<(&'static str, String)> {
    let spec = detect(raw)?;
    let normalized = normalize_url(raw);
    let path = Url::parse(&normalized)
        .map(|u| u.path().to_string())
        .unwrap_or_default();
    Some((spec.key, slug_for(spec.key, &path)))
}

pub fn supported() -> Vec<&'static str> {
    let mut keys: Vec<&'static str> = PROVIDERS.iter().map(|spec| spec.key).collect();
    keys.sort_unstable();
    keys
}

pub fn table_json() -> serde_json::Value {
    serde_json::json!({
        "supported": supported(),
        "providers": PROVIDERS.iter().map(|spec| serde_json::json!({
            "key": spec.key,
            "kind": spec.kind.as_str(),
            "hosts": spec.hosts,
            "module": spec.module,
            "note": spec.note,
        })).collect::<Vec<_>>(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn classify_matrix() {
        let cases = [
            ("https://link4m.net/go/2kCcIqn", "LINK4M"),
            ("https://link4m.co/xyz", "LINK4M"),
            ("https://www.link4m.org/go/abc", "LINK4M"),
            ("https://bbmkts.com/go/3p82s", "BBMKTS"),
            (
                "https://yeumoney.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbQ==",
                "BBMKTS",
            ),
            ("https://gtraffic.io/X3BR2OQ?ref=test", "GTRAFFIC"),
            ("https://direct.gtraffic.io/dr-client/ABC123", "GTRAFFIC"),
            ("https://layma.net/pohWNZgba", "LAYMA"),
            ("https://trafficvn.net/get/MFGm2tAlcSn", "TRAFFICVN"),
            ("https://octolink.vip/abc", "OCTOLINK"),
            ("https://link999.app/x", "OCTOLINK"),
            ("https://uptolink.biz/abc", "OCTOLINK"),
            ("https://www.uptolink.site/abc", "OCTOLINK"),
            ("https://linkhuongdan.net/abc", "OCTOLINK"),
            ("https://unknownlink.com/123", "GENERIC"),
            ("not-a-url", "GENERIC"),
            ("", "GENERIC"),
        ];
        for (url, expected) in cases {
            assert_eq!(classify(url), expected, "classify({url})");
        }
    }

    #[test]
    fn alias_normalization() {
        let cases = [
            ("LINK999", Some("OCTOLINK")),
            ("uptolink", Some("OCTOLINK")),
            ("octo", Some("OCTOLINK")),
            ("yeumoney", Some("BBMKTS")),
            ("g-traffic", Some("GTRAFFIC")),
            ("traffic_vn", Some("TRAFFICVN")),
            ("l4m", Some("LINK4M")),
            ("nonsense", None),
            ("", None),
        ];
        for (raw, expected) in cases {
            assert_eq!(canonical_key(raw), expected, "canonical_key({raw})");
        }
    }

    #[test]
    fn parse_key_slugs() {
        let cases = [
            ("https://link4m.net/go/2kCcIqn", ("LINK4M", "2kCcIqn")),
            ("https://bbmkts.com/go/3p82s?ref=x", ("BBMKTS", "3p82s")),
            (
                "https://trafficvn.com/get/MFGm2tAlcSn",
                ("TRAFFICVN", "MFGm2tAlcSn"),
            ),
            (
                "https://direct.gtraffic.io/X3BR2OQ",
                ("GTRAFFIC", "X3BR2OQ"),
            ),
            ("https://layma.net/pohWNZgba", ("LAYMA", "pohWNZgba")),
            ("https://octolink.vip/abc", ("OCTOLINK", "")),
        ];
        for (url, expected) in cases {
            let got = parse_key(url).expect("provider");
            assert_eq!(got.0, expected.0, "key for {url}");
            assert_eq!(got.1, expected.1, "slug for {url}");
        }
        assert!(parse_key("https://unknownlink.com/123").is_none());
    }
}
