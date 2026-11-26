//! HTTP face: same contract as the Python FastAPI service and the Rust
//! façade, but the Link4M job runs in-process on the native engine.

use crate::fast_decode::fast_decode;
use crate::flow::extract_alias;
use crate::pool::{Job, Pool};
use crate::providers;
use crate::state::{elapsed_ms, new_job_id, unix_now, Inner, JobView};
use axum::extract::{Path, Query, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use futures_util::stream::{self, StreamExt};
use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::HashMap;
use std::sync::atomic::Ordering;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::oneshot;

#[derive(Clone)]
pub struct ApiState {
    pub inner: Arc<Inner>,
    pub pool: Arc<Pool>,
}

#[derive(Debug, Deserialize)]
pub struct BypassReq {
    pub url: String,
    #[serde(default)]
    pub wait: Option<bool>,
    #[serde(default)]
    pub timeout: Option<u64>,
    #[serde(default)]
    pub code: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct BypassQuery {
    pub url: String,
    #[serde(default, deserialize_with = "lenient_wait")]
    pub wait: Option<bool>,
    #[serde(default)]
    pub timeout: Option<u64>,
    #[serde(default)]
    pub key: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct BatchReq {
    pub urls: Vec<String>,
    #[serde(default)]
    pub wait: Option<bool>,
    #[serde(default)]
    pub timeout: Option<u64>,
}

struct ApiError {
    status: StatusCode,
    detail: String,
}

impl ApiError {
    fn bad(detail: impl Into<String>) -> Self {
        Self { status: StatusCode::BAD_REQUEST, detail: detail.into() }
    }
    fn unauthorized() -> Self {
        Self { status: StatusCode::UNAUTHORIZED, detail: "API key không hợp lệ".into() }
    }
    fn not_found(detail: impl Into<String>) -> Self {
        Self { status: StatusCode::NOT_FOUND, detail: detail.into() }
    }
    fn busy() -> Self {
        Self { status: StatusCode::TOO_MANY_REQUESTS, detail: "Hàng đợi đầy, thử lại sau".into() }
    }
    fn unsupported(detail: impl Into<String>) -> Self {
        Self { status: StatusCode::NOT_IMPLEMENTED, detail: detail.into() }
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (self.status, Json(json!({ "detail": self.detail }))).into_response()
    }
}

/// `?wait=1` / `?wait` are the spellings real clients send; serde's `bool`
/// query parser only takes `true`/`false`, which turned those into a 400.
fn lenient_wait<'de, D>(deserializer: D) -> Result<Option<bool>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    let raw = Option::<String>::deserialize(deserializer)?;
    Ok(raw.map(|value| match value.trim() {
        "" => true,
        v => matches!(v.to_ascii_lowercase().as_str(), "1" | "true" | "yes" | "on"),
    }))
}

fn check_auth(inner: &Inner, headers: &HeaderMap, query_key: Option<&str>) -> Result<(), ApiError> {
    let expected = inner.cfg.api_key.trim();
    if expected.is_empty() {
        return Ok(());
    }
    let header_key = headers.get("x-api-key").and_then(|v| v.to_str().ok());
    let bearer = headers
        .get("authorization")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "));
    if header_key == Some(expected) || bearer == Some(expected) || query_key == Some(expected) {
        Ok(())
    } else {
        Err(ApiError::unauthorized())
    }
}

fn clamp_timeout(value: Option<u64>) -> Duration {
    Duration::from_secs(value.unwrap_or(600).clamp(5, 600))
}

fn envelope(status: &str, url: &str, provider: Option<&str>) -> Value {
    json!({
        "status": status,
        "url": url,
        "destination_url": null,
        "provider": provider,
        "cached": false,
        "elapsed_ms": 0.0,
        "job_id": null,
        "error": null,
    })
}

async fn resolve(
    state: Arc<ApiState>,
    raw_url: String,
    wait: bool,
    timeout: Duration,
    code: Option<String>,
) -> Result<Value, ApiError> {
    let started = Instant::now();
    let url = providers::normalize_url(&raw_url);
    if url.is_empty() {
        return Err(ApiError::bad("url rỗng"));
    }

    // 1) Zero-browser decode.
    if let Some(destination) = fast_decode(&url) {
        state.inner.stats.total.fetch_add(1, Ordering::Relaxed);
        state.inner.stats.successes.fetch_add(1, Ordering::Relaxed);
        let mut response = envelope("success", &url, Some("decode"));
        response["destination_url"] = json!(destination);
        response["elapsed_ms"] = json!(elapsed_ms(started));
        return Ok(response);
    }

    // 2) Provider.
    let Some(spec) = providers::detect(&url) else {
        return Err(ApiError::bad(format!(
            "Không nhận diện được nhà cung cấp. Hỗ trợ: {}",
            providers::supported().join(", ")
        )));
    };
    if spec.key != "LINK4M" {
        return Err(ApiError::unsupported(format!(
            "Engine native chỉ chạy link4m; {} dùng façade Python",
            spec.key
        )));
    }
    let Some(alias) = extract_alias(&url) else {
        return Err(ApiError::bad("Không đọc được alias link4m"));
    };
    let provider = "link4m";
    let key = format!("{provider}:{}", alias.to_lowercase());

    // 3) Cache.
    if let Some(destination) = state.inner.cache_get(&key).await {
        state.inner.stats.total.fetch_add(1, Ordering::Relaxed);
        state.inner.stats.successes.fetch_add(1, Ordering::Relaxed);
        state.inner.stats.cache_hits.fetch_add(1, Ordering::Relaxed);
        let mut response = envelope("success", &url, Some(provider));
        response["destination_url"] = json!(destination);
        response["cached"] = json!(true);
        response["elapsed_ms"] = json!(elapsed_ms(started));
        return Ok(response);
    }

    // 4) Single-flight per key: a burst on one alias runs one browser job.
    let key_lock = state.inner.key_lock(&key).await;
    let _guard = key_lock.lock().await;
    if let Some(destination) = state.inner.cache_get(&key).await {
        state.inner.stats.total.fetch_add(1, Ordering::Relaxed);
        state.inner.stats.successes.fetch_add(1, Ordering::Relaxed);
        state.inner.stats.cache_hits.fetch_add(1, Ordering::Relaxed);
        let mut response = envelope("success", &url, Some(provider));
        response["destination_url"] = json!(destination);
        response["cached"] = json!(true);
        response["elapsed_ms"] = json!(elapsed_ms(started));
        return Ok(response);
    }

    // 5) Queue.
    let req_code = code.filter(|c| !c.trim().is_empty());
    let job_id = new_job_id();
    state
        .inner
        .job_put(JobView {
            job_id: job_id.clone(),
            status: "running".into(),
            url: url.clone(),
            destination_url: None,
            error: None,
            created_at: unix_now(),
            elapsed_ms: 0.0,
        })
        .await;
    let (sender, receiver) = oneshot::channel();
    let job = Job {
        job_id: job_id.clone(),
        key: key.clone(),
        alias,
        url: url.clone(),
        code: req_code,
        respond: sender,
    };
    if state.pool.try_dispatch(job).is_err() {
        state.inner.job_remove(&job_id).await;
        state.inner.stats.errors.fetch_add(1, Ordering::Relaxed);
        return Err(ApiError::busy());
    }
    state.inner.stats.total.fetch_add(1, Ordering::Relaxed);

    let mut response = envelope("queued", &url, Some(provider));
    response["job_id"] = json!(job_id);
    if !wait {
        return Ok(response);
    }

    match tokio::time::timeout(timeout, receiver).await {
        Ok(Ok(outcome)) => {
            let mut done = envelope(
                if outcome.destination.is_some() { "success" } else { "failed" },
                &url,
                Some(provider),
            );
            done["destination_url"] = json!(outcome.destination);
            done["elapsed_ms"] = json!(outcome.elapsed_ms);
            done["job_id"] = json!(job_id);
            done["error"] = json!(outcome.error.map(|e| format!("{}: {}", e.kind, e.message)));
            Ok(done)
        }
        Ok(Err(_)) => {
            response["status"] = json!("failed");
            response["error"] = json!("worker dropped the job");
            Ok(response)
        }
        Err(_) => {
            response["status"] = json!("timeout");
            Ok(response)
        }
    }
}

async fn bypass_post(
    State(state): State<Arc<ApiState>>,
    headers: HeaderMap,
    Json(req): Json<BypassReq>,
) -> Result<Json<Value>, ApiError> {
    check_auth(&state.inner, &headers, None)?;
    let result = resolve(
        state,
        req.url,
        req.wait.unwrap_or(true),
        clamp_timeout(req.timeout),
        req.code,
    )
    .await?;
    Ok(Json(result))
}

async fn bypass_get(
    State(state): State<Arc<ApiState>>,
    headers: HeaderMap,
    Query(query): Query<BypassQuery>,
) -> Result<Json<Value>, ApiError> {
    check_auth(&state.inner, &headers, query.key.as_deref())?;
    let result = resolve(
        state,
        query.url,
        query.wait.unwrap_or(true),
        clamp_timeout(query.timeout),
        None,
    )
    .await?;
    Ok(Json(result))
}

async fn job_get(
    State(state): State<Arc<ApiState>>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Result<Json<Value>, ApiError> {
    check_auth(&state.inner, &headers, None)?;
    match state.inner.job_get(&id).await {
        Some(job) => Ok(Json(serde_json::to_value(job).unwrap_or_else(|_| json!({})))),
        None => Err(ApiError::not_found("Không có job này")),
    }
}

async fn batch(
    State(state): State<Arc<ApiState>>,
    headers: HeaderMap,
    Json(req): Json<BatchReq>,
) -> Result<Json<Value>, ApiError> {
    check_auth(&state.inner, &headers, None)?;
    let cap = state.inner.cfg.max_batch;
    if req.urls.len() > cap {
        return Err(ApiError::bad(format!("Tối đa {cap} URL mỗi batch")));
    }
    let wait = req.wait.unwrap_or(true);
    let timeout = clamp_timeout(req.timeout);
    let concurrency = state.inner.cfg.batch_concurrency;
    let results: Vec<Value> = stream::iter(req.urls.into_iter().map(|url| {
        let state = state.clone();
        async move {
            match resolve(state, url.clone(), wait, timeout, None).await {
                Ok(value) => value,
                Err(error) => json!({
                    "status": "error",
                    "url": url,
                    "destination_url": null,
                    "provider": null,
                    "cached": false,
                    "elapsed_ms": 0.0,
                    "job_id": null,
                    "error": error.detail,
                }),
            }
        }
    }))
    .buffer_unordered(concurrency)
    .collect()
    .await;
    Ok(Json(json!({ "count": results.len(), "results": results })))
}

async fn health(State(state): State<Arc<ApiState>>) -> Json<Value> {
    let cache = state.inner.cache.lock().await.len();
    Json(json!({
        "status": "ok",
        "workers": state.inner.cfg.workers,
        "queued": 0,
        "cached_links": cache,
        "uptime_sec": state.inner.started.elapsed().as_secs(),
    }))
}

async fn stats(State(state): State<Arc<ApiState>>) -> Json<Value> {
    let cache = state.inner.cache.lock().await.len();
    Json(json!({
        "stats": state.inner.stats.snapshot(cache, 0),
        "recent": [],
    }))
}

async fn supported_list() -> Json<Value> {
    Json(json!({ "supported": providers::table_json() }))
}

async fn root() -> Json<Value> {
    Json(json!({
        "service": "Link4M native engine (Rust)",
        "status": "online",
        "engine": "native",
        "captcha": "recaptcha audio + whisper.cpp",
        "endpoints": [
            "POST /api/v1/bypass",
            "GET /api/v1/bypass?url=...",
            "GET /api/v1/jobs/{id}",
            "POST /api/v1/batch",
            "GET /api/v1/stats",
            "GET /api/v1/supported",
            "GET /health",
        ],
    }))
}

pub fn router(state: Arc<ApiState>) -> Router {
    Router::new()
        .route("/", get(root))
        .route("/health", get(health))
        .route("/api/v1/stats", get(stats))
        .route("/api/v1/supported", get(supported_list))
        .route("/api/v1/bypass", post(bypass_post).get(bypass_get))
        .route("/api/v1/jobs/{id}", get(job_get))
        .route("/api/v1/batch", post(batch))
        .with_state(state)
}

#[allow(dead_code)]
fn _query_map(_: HashMap<String, String>) {}

#[cfg(test)]
mod tests {
    //! HTTP contract tests that need no Chrome and no whisper model.
    //!
    //! `Inner.asr` is `None`, so a job that actually reaches a worker fails
    //! with `asr: whisper model not loaded`; every path here resolves before
    //! dispatch (decode, supported, validation, auth).

    use super::*;
    use crate::state::Config;
    use axum::body::Body;
    use axum::http::Request;
    use std::path::PathBuf;
    use tower::ServiceExt;

    fn state(api_key: &str, workers: usize, max_queue: usize) -> Arc<ApiState> {
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0);
        let scratch = std::env::temp_dir().join(format!("l4m-api-test-{stamp}"));
        let cfg = Config {
            host: "127.0.0.1".into(),
            port: 0,
            api_key: api_key.into(),
            workers,
            max_queue,
            max_batch: 50,
            batch_concurrency: 4,
            job_timeout: Duration::from_secs(30),
            cache_ttl: Duration::from_secs(60),
            cache_file: scratch.join("cache.json"),
            cache_enabled: false,
            chrome_bin: "google-chrome".into(),
            headless: true,
            profile_dir: scratch.join("profile"),
            model_path: PathBuf::from("models/ggml-tiny.en.bin"),
            model_url: String::new(),
            asr_threads: 1,
        };
        let inner = Inner::new(cfg, None);
        let pool = Arc::new(Pool::spawn(inner.clone()));
        Arc::new(ApiState { inner, pool })
    }

    async fn call(app: Router, request: Request<Body>) -> (StatusCode, Value) {
        let response = app.oneshot(request).await.expect("router answered");
        let status = response.status();
        let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
            .await
            .expect("body");
        let value = serde_json::from_slice(&bytes).unwrap_or(Value::Null);
        (status, value)
    }

    const DECODE_URL: &str =
        "https://bbmkts.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS94";

    #[tokio::test]
    async fn health_and_supported_need_no_browser() {
        let app = router(state("", 2, 8));
        let (status, body) = call(
            app.clone(),
            Request::builder().uri("/health").body(Body::empty()).unwrap(),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(body["status"], "ok");
        assert_eq!(body["workers"], 2);

        let (status, body) = call(
            app,
            Request::builder()
                .uri("/api/v1/supported")
                .body(Body::empty())
                .unwrap(),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        let keys: Vec<&str> = body["supported"]["supported"]
            .as_array()
            .unwrap()
            .iter()
            .filter_map(Value::as_str)
            .collect();
        // Six browser providers plus the zero-browser DECODE fast path.
        assert_eq!(keys.len(), 7);
        for key in ["LINK4M", "BBMKTS", "GTRAFFIC", "LAYMA", "TRAFFICVN", "OCTOLINK", "DECODE"] {
            assert!(keys.contains(&key), "missing {key} in {keys:?}");
        }
    }

    #[tokio::test]
    async fn post_decode_and_get_with_lenient_wait() {
        let app = router(state("", 1, 8));
        let payload = json!({ "url": DECODE_URL, "wait": true }).to_string();
        let (status, body) = call(
            app.clone(),
            Request::builder()
                .method("POST")
                .uri("/api/v1/bypass")
                .header("content-type", "application/json")
                .body(Body::from(payload))
                .unwrap(),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(body["status"], "success");
        assert_eq!(body["destination_url"], "https://example.com/x");
        assert_eq!(body["provider"], "decode");

        // `wait=1` is what the README documents; serde's bool parser would 400.
        let uri = format!("/api/v1/bypass?url={DECODE_URL}&wait=1");
        let (status, body) = call(
            app,
            Request::builder().uri(uri).body(Body::empty()).unwrap(),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(body["destination_url"], "https://example.com/x");
    }

    #[tokio::test]
    async fn unknown_host_is_400_and_foreign_provider_is_501() {
        let app = router(state("", 1, 8));
        let (status, body) = call(
            app.clone(),
            Request::builder()
                .method("POST")
                .uri("/api/v1/bypass")
                .header("content-type", "application/json")
                .body(Body::from(json!({"url": "https://unknown.invalid/x"}).to_string()))
                .unwrap(),
        )
        .await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert!(body["detail"].as_str().unwrap().contains("Hỗ trợ"));

        let (status, body) = call(
            app,
            Request::builder()
                .method("POST")
                .uri("/api/v1/bypass")
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({"url": "https://gtraffic.io/X3BR2OQ"}).to_string(),
                ))
                .unwrap(),
        )
        .await;
        assert_eq!(status, StatusCode::NOT_IMPLEMENTED);
        assert!(body["detail"].as_str().unwrap().contains("GTRAFFIC"));
    }

    #[tokio::test]
    async fn auth_accepts_header_and_query_key() {
        let app = router(state("secret", 1, 8));
        let payload = json!({ "url": DECODE_URL }).to_string();

        let (status, _) = call(
            app.clone(),
            Request::builder()
                .method("POST")
                .uri("/api/v1/bypass")
                .header("content-type", "application/json")
                .body(Body::from(payload.clone()))
                .unwrap(),
        )
        .await;
        assert_eq!(status, StatusCode::UNAUTHORIZED);

        let (status, _) = call(
            app.clone(),
            Request::builder()
                .method("POST")
                .uri("/api/v1/bypass")
                .header("content-type", "application/json")
                .header("x-api-key", "secret")
                .body(Body::from(payload))
                .unwrap(),
        )
        .await;
        assert_eq!(status, StatusCode::OK);

        let uri = format!("/api/v1/bypass?url={DECODE_URL}&key=secret");
        let (status, _) = call(
            app,
            Request::builder().uri(uri).body(Body::empty()).unwrap(),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
    }

    #[tokio::test]
    async fn missing_job_is_404_and_batch_is_capped() {
        let app = router(state("", 1, 8));
        let (status, _) = call(
            app.clone(),
            Request::builder()
                .uri("/api/v1/jobs/nope")
                .body(Body::empty())
                .unwrap(),
        )
        .await;
        assert_eq!(status, StatusCode::NOT_FOUND);

        let urls: Vec<String> = (0..51).map(|i| format!("{DECODE_URL}-{i}")).collect();
        let (status, body) = call(
            app,
            Request::builder()
                .method("POST")
                .uri("/api/v1/batch")
                .header("content-type", "application/json")
                .body(Body::from(json!({ "urls": urls }).to_string()))
                .unwrap(),
        )
        .await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert!(body["detail"].as_str().unwrap().contains("50"));
    }
}
