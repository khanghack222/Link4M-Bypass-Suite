//! HTTP contract tests for the Rust façade.
//!
//! Every case here is handled before an engine process is spawned: fast-path
//! decode, provider rejection, auth, batch limits and job lookup. That keeps the
//! suite offline and fast — the live Link4M flow is covered by README §3.3.

use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

use axum::body::Body;
use axum::http::{Request, StatusCode};
use bypass_server::api;
use bypass_server::config::Config;
use bypass_server::state::AppState;
use http_body_util::BodyExt;
use serde_json::Value;
use tower::ServiceExt;

fn test_config(api_key: &str) -> Config {
    let stamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    Config {
        host: "127.0.0.1".to_string(),
        port: 0,
        api_key: api_key.to_string(),
        workers: 1,
        max_queue: 8,
        job_timeout: 30,
        max_tries: 1,
        retry_delay: 0,
        cache_enabled: false,
        cache_ttl: 60,
        cache_file: PathBuf::from(format!("/tmp/bypass-rs-test-{stamp}.json")),
        repo: PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(".."),
        python: "python3".to_string(),
        l4m_engine: "cdp".to_string(),
        headless: true,
        native: None,
    }
}

fn router(api_key: &str) -> axum::Router {
    api::router(AppState::new(test_config(api_key)))
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap_or(Value::Null)
}

fn post(url: &str, body: &str) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri(url)
        .header("content-type", "application/json")
        .body(Body::from(body.to_string()))
        .unwrap()
}

#[tokio::test]
async fn health_reports_queue_and_counters() {
    let response = router("")
        .oneshot(Request::get("/health").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert_eq!(body["status"], "ok");
    assert_eq!(body["queued"], 0);
    assert_eq!(body["inflight"], 0);
    assert_eq!(body["workers"], 1);
}

#[tokio::test]
async fn supported_excludes_internal_decode() {
    let response = router("")
        .oneshot(
            Request::get("/api/v1/supported")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    let engines: Vec<&str> = body["supported"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(Value::as_str)
        .collect();
    assert!(engines.contains(&"link4m"));
    assert!(engines.contains(&"octolink"));
    assert!(!engines.contains(&"decode"));
}

#[tokio::test]
async fn fast_path_decodes_without_queueing() {
    let request = post(
        "/api/v1/bypass",
        r#"{"url":"https://bbmkts.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS9ycw==","wait":true}"#,
    );
    let response = router("").oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert_eq!(body["status"], "success");
    assert_eq!(body["destination_url"], "https://example.com/rs");
    assert_eq!(body["provider"], "decode");
    assert_eq!(body["cached"], false);
    assert!(body["job_id"].is_null());
}

#[tokio::test]
async fn unknown_provider_is_400() {
    let request = post("/api/v1/bypass", r#"{"url":"https://unknownlink.com/x"}"#);
    let response = router("").oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    let body = body_json(response).await;
    assert!(body["detail"]
        .as_str()
        .unwrap_or_default()
        .contains("link4m"));
}

#[tokio::test]
async fn empty_url_is_400() {
    let request = post("/api/v1/bypass", r#"{"url":"   "}"#);
    let response = router("").oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn missing_url_field_is_422() {
    let request = post("/api/v1/bypass", r#"{"wait":true}"#);
    let response = router("").oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::UNPROCESSABLE_ENTITY);
}

#[tokio::test]
async fn api_key_is_enforced_but_health_stays_open() {
    let app = router("secret");

    let health = app
        .clone()
        .oneshot(Request::get("/health").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(health.status(), StatusCode::OK);

    let denied = app
        .clone()
        .oneshot(post(
            "/api/v1/bypass",
            r#"{"url":"https://bbmkts.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS94"}"#,
        ))
        .await
        .unwrap();
    assert_eq!(denied.status(), StatusCode::UNAUTHORIZED);

    let allowed = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/v1/bypass")
                .header("content-type", "application/json")
                .header("x-api-key", "secret")
                .body(Body::from(
                    r#"{"url":"https://bbmkts.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS94"}"#,
                ))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(allowed.status(), StatusCode::OK);
}

#[tokio::test]
async fn batch_over_fifty_is_rejected() {
    let urls: Vec<String> = (0..51).map(|i| format!("\"https://x.tld/{i}\"")).collect();
    let body = format!(r#"{{"urls":[{}]}}"#, urls.join(","));
    let response = router("")
        .oneshot(post("/api/v1/batch", &body))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn batch_decodes_each_entry() {
    let response = router("")
        .oneshot(post(
            "/api/v1/batch",
            r#"{"urls":["https://bbmkts.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS9h","https://yeumoney.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS9i"],"wait":true}"#,
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert_eq!(body["count"], 2);
    assert_eq!(
        body["results"][0]["destination_url"],
        "https://example.com/a"
    );
    assert_eq!(
        body["results"][1]["destination_url"],
        "https://example.com/b"
    );
}

#[tokio::test]
async fn unknown_job_is_404() {
    let response = router("")
        .oneshot(
            Request::get("/api/v1/jobs/nope")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::NOT_FOUND);
}

#[tokio::test]
async fn get_bypass_accepts_query_key() {
    let response = router("secret")
        .oneshot(
            Request::get(
                "/api/v1/bypass?url=https%3A%2F%2Fbbmkts.com%2Fgo%2Ffile%2FaHR0cHM6Ly9leGFtcGxlLmNvbS9n&key=secret",
            )
            .body(Body::empty())
            .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert_eq!(body["destination_url"], "https://example.com/g");
}

#[tokio::test]
async fn get_bypass_accepts_wait_flag_spellings() {
    for flag in ["wait=1", "wait=true", "wait"] {
        let uri = format!(
            "/api/v1/bypass?url=https%3A%2F%2Fbbmkts.com%2Fgo%2Ffile%2FaHR0cHM6Ly9leGFtcGxlLmNvbS9n&{flag}"
        );
        let response = router("")
            .oneshot(Request::get(uri).body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = body_json(response).await;
        assert_eq!(body["status"], "success");
        assert_eq!(body["destination_url"], "https://example.com/g");
    }
}

#[tokio::test]
async fn stats_starts_empty() {
    let response = router("")
        .oneshot(Request::get("/api/v1/stats").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert_eq!(body["queued"], 0);
    assert!(body["recent"].as_array().unwrap().is_empty());
}

#[tokio::test]
async fn oversized_body_is_rejected() {
    let big = "a".repeat(2 * 1024 * 1024);
    let request = post(
        "/api/v1/bypass",
        &format!(r#"{{"url":"https://x.tld/{big}"}}"#),
    );
    let response = router("").oneshot(request).await.unwrap();
    assert_eq!(response.status(), StatusCode::PAYLOAD_TOO_LARGE);
}

#[tokio::test]
async fn malformed_json_is_400() {
    let response = router("")
        .oneshot(post("/api/v1/bypass", "{not json"))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn root_lists_endpoints() {
    let response = router("")
        .oneshot(Request::get("/").body(Body::empty()).unwrap())
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let body = body_json(response).await;
    assert_eq!(body["status"], "online");
    assert!(body["endpoints"].as_array().unwrap().len() >= 6);
}
