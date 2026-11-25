//! HTTP API compatible with `service/app.py`.
//!
//! Same paths, same query/body fields, same result envelope. The only
//! intentional difference is implementation language: jobs run through the
//! Rust queue and shell out to the Python engine façade.

use std::sync::atomic::Ordering;
use std::sync::Arc;
use std::time::{Duration, Instant};

use axum::extract::{DefaultBodyLimit, Path, Query, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use axum::{Json, Router};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tower_http::cors::CorsLayer;
use tower_http::trace::TraceLayer;
use uuid::Uuid;

use crate::config::Config;
use crate::engine;
use crate::fast_decode::fast_decode;
use crate::providers;
use crate::state::{now_secs, AppState, Job};

const DEFAULT_TIMEOUT: u64 = 480;
const MAX_TIMEOUT: u64 = 600;
const MIN_TIMEOUT: u64 = 5;

fn default_timeout() -> u64 {
    DEFAULT_TIMEOUT
}

/// Query strings carry `wait=1` / `wait` in the README and in real clients;
/// serde's bool only takes `true`/`false`, so accept the usual spellings.
fn lenient_bool<'de, D>(deserializer: D) -> Result<bool, D::Error>
where
    D: serde::Deserializer<'de>,
{
    let raw = Option::<String>::deserialize(deserializer)?;
    Ok(match raw.as_deref().map(str::trim) {
        Some("") => true,
        Some(v) => matches!(
            v.to_ascii_lowercase().as_str(),
            "1" | "true" | "yes" | "on"
        ),
        None => false,
    })
}

#[derive(Debug)]
pub struct ApiError {
    status: StatusCode,
    detail: String,
}

impl ApiError {
    fn new(status: StatusCode, detail: impl Into<String>) -> Self {
        ApiError {
            status,
            detail: detail.into(),
        }
    }

    fn bad_request(detail: impl Into<String>) -> Self {
        Self::new(StatusCode::BAD_REQUEST, detail)
    }

    fn unauthorized() -> Self {
        Self::new(StatusCode::UNAUTHORIZED, "API key không đúng")
    }

    fn too_many(detail: impl Into<String>) -> Self {
        Self::new(StatusCode::TOO_MANY_REQUESTS, detail)
    }

    fn not_found(detail: impl Into<String>) -> Self {
        Self::new(StatusCode::NOT_FOUND, detail)
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (self.status, Json(json!({ "detail": self.detail }))).into_response()
    }
}

#[derive(Debug, Deserialize)]
pub struct BypassReq {
    pub url: String,
    #[serde(default)]
    pub wait: bool,
    #[serde(default = "default_timeout")]
    pub timeout: u64,
}

#[derive(Debug, Deserialize)]
pub struct BypassQuery {
    pub url: String,
    #[serde(default, deserialize_with = "lenient_bool")]
    pub wait: bool,
    #[serde(default = "default_timeout")]
    pub timeout: u64,
    pub key: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct BatchReq {
    pub urls: Vec<String>,
    #[serde(default)]
    pub wait: bool,
    #[serde(default = "default_timeout")]
    pub timeout: u64,
}

#[derive(Debug, Serialize)]
struct BypassResponse {
    status: String,
    url: String,
    destination_url: Option<String>,
    provider: Option<String>,
    cached: bool,
    elapsed_ms: f64,
    job_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
}

impl BypassResponse {
    fn new(status: &str, url: &str) -> Self {
        BypassResponse {
            status: status.to_string(),
            url: url.to_string(),
            destination_url: None,
            provider: None,
            cached: false,
            elapsed_ms: 0.0,
            job_id: None,
            error: None,
        }
    }

    fn into_value(self) -> Value {
        serde_json::to_value(self).unwrap_or_else(|_| json!({"status": "error"}))
    }
}

fn client_id(headers: &HeaderMap) -> String {
    headers
        .get("x-client-id")
        .and_then(|value| value.to_str().ok())
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or("api")
        .to_string()
}

fn check_auth(
    state: &AppState,
    headers: &HeaderMap,
    query_key: Option<&str>,
) -> Result<(), ApiError> {
    if state.cfg.api_key.is_empty() {
        return Ok(());
    }
    let header_key = headers
        .get("x-api-key")
        .and_then(|value| value.to_str().ok())
        .map(str::trim);
    let bearer = headers
        .get("authorization")
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.strip_prefix("Bearer "))
        .map(str::trim);
    if header_key == Some(state.cfg.api_key.as_str())
        || bearer == Some(state.cfg.api_key.as_str())
        || query_key == Some(state.cfg.api_key.as_str())
    {
        Ok(())
    } else {
        Err(ApiError::unauthorized())
    }
}

fn normalize_timeout(timeout: u64) -> u64 {
    timeout.clamp(MIN_TIMEOUT, MAX_TIMEOUT)
}

fn job_id() -> String {
    let raw = Uuid::new_v4().simple().to_string();
    raw[..16].to_string()
}

fn response_from_job(job: &Job, url: &str, elapsed_ms: f64) -> Value {
    let mut response = BypassResponse::new(&job.status, url);
    response.destination_url = job.destination.clone();
    response.provider = Some(job.provider.clone());
    response.cached = job.cached;
    response.elapsed_ms = elapsed_ms;
    response.job_id = Some(job.id.clone());
    response.error = job.error.clone();
    response.into_value()
}

async fn do_bypass(
    state: Arc<AppState>,
    raw_url: String,
    wait: bool,
    timeout: u64,
    client: String,
) -> Result<Value, ApiError> {
    let started = Instant::now();
    let url = providers::normalize_url(&raw_url);
    if url.is_empty() {
        return Err(ApiError::bad_request("url rỗng"));
    }

    // 1) Zero-browser decode: instant, no queue slot.
    if let Some(destination) = fast_decode(&url) {
        state.total_jobs.fetch_add(1, Ordering::Relaxed);
        state.successes.fetch_add(1, Ordering::Relaxed);
        let mut response = BypassResponse::new("success", &url);
        response.destination_url = Some(destination);
        response.provider = Some("decode".to_string());
        response.elapsed_ms = started.elapsed().as_secs_f64() * 1000.0;
        return Ok(response.into_value());
    }

    // 2) Provider detection.
    let Some(spec) = providers::detect(&url) else {
        return Err(ApiError::bad_request(format!(
            "Không nhận diện được nhà cung cấp. Hỗ trợ: {}",
            supported_engines().join(", ")
        )));
    };
    let parsed = providers::parse_key(&url).unwrap_or((spec.key, String::new()));
    let cache_key = if parsed.1.is_empty() {
        url.clone()
    } else {
        parsed.1.clone()
    };

    // 3) Cache.
    if let Some(destination) = state.cache_get(&spec.key.to_lowercase(), &cache_key).await {
        state.total_jobs.fetch_add(1, Ordering::Relaxed);
        state.successes.fetch_add(1, Ordering::Relaxed);
        let mut response = BypassResponse::new("success", &url);
        response.destination_url = Some(destination);
        response.provider = Some(spec.key.to_lowercase());
        response.cached = true;
        response.elapsed_ms = started.elapsed().as_secs_f64() * 1000.0;
        return Ok(response.into_value());
    }

    // 4) Queue.
    if state.queue_depth() >= state.cfg.max_queue {
        return Err(ApiError::too_many("Hàng đợi đầy, thử lại sau"));
    }
    let id = job_id();
    let job = Job::new(
        id.clone(),
        url.clone(),
        spec.key.to_lowercase(),
        cache_key,
        client,
    );
    state.insert_job(job).await;
    state.total_jobs.fetch_add(1, Ordering::Relaxed);
    state.queued.fetch_add(1, Ordering::Relaxed);

    let background_state = state.clone();
    let background_id = id.clone();
    tokio::spawn(async move { run_job(background_state, background_id).await });

    if !wait {
        let mut response = BypassResponse::new("queued", &url);
        response.provider = Some(spec.key.to_lowercase());
        response.job_id = Some(id);
        return Ok(response.into_value());
    }

    let deadline = Instant::now() + Duration::from_secs(normalize_timeout(timeout));
    loop {
        if let Some(job) = state.get_job(&id).await {
            if job.is_terminal() {
                return Ok(response_from_job(
                    &job,
                    &url,
                    started.elapsed().as_secs_f64() * 1000.0,
                ));
            }
        }
        if Instant::now() >= deadline {
            let mut response = BypassResponse::new("timeout", &url);
            response.provider = Some(spec.key.to_lowercase());
            response.job_id = Some(id);
            response.elapsed_ms = started.elapsed().as_secs_f64() * 1000.0;
            return Ok(response.into_value());
        }
        tokio::time::sleep(Duration::from_millis(150)).await;
    }
}

/// Native `l4m-engine` only implements Link4M; the other providers have no Rust
/// flow and must keep the Python subprocess.
fn qualifies_for_native(cfg: &Config, provider: &str) -> bool {
    cfg.native.is_some() && provider.eq_ignore_ascii_case("link4m")
}

async fn run_job(state: Arc<AppState>, id: String) {
    let Some(job) = state.get_job(&id).await else {
        return;
    };
    let Ok(_permit) = state.sem.clone().acquire_owned().await else {
        return;
    };

    state.queued.fetch_sub(1, Ordering::Relaxed);
    state.inflight.fetch_add(1, Ordering::Relaxed);
    state
        .update_job(&id, |job| job.status = "running".to_string())
        .await;

    let started = Instant::now();
    let mut last_error = String::from("không lấy được link đích");
    let mut success = false;
    let mut destination = None;

    for attempt in 1..=state.cfg.max_tries {
        state.update_job(&id, |job| job.tries = attempt).await;
        let outcome = if qualifies_for_native(&state.cfg, &job.provider) {
            match engine::run_native(&state.cfg, &job.url, state.cfg.job_timeout).await {
                Ok(outcome) => outcome,
                Err(reason) => {
                    tracing::warn!(reason = %reason, "native engine không dùng được, rơi về Python");
                    engine::run_engine(
                        &state.cfg,
                        &job.url,
                        Some(&job.provider),
                        state.cfg.job_timeout,
                    )
                    .await
                }
            }
        } else {
            engine::run_engine(
                &state.cfg,
                &job.url,
                Some(&job.provider),
                state.cfg.job_timeout,
            )
            .await
        };
        if outcome.success {
            success = true;
            destination = outcome.destination;
            break;
        }
        last_error = outcome
            .error_message
            .or(outcome.error_code)
            .unwrap_or_else(|| "không lấy được link đích".to_string());
        if attempt < state.cfg.max_tries {
            tokio::time::sleep(Duration::from_secs(state.cfg.retry_delay)).await;
        }
    }

    let elapsed_ms = started.elapsed().as_secs_f64() * 1000.0;
    if success {
        if let Some(destination) = destination.clone() {
            state
                .update_job(&id, |job| {
                    job.status = "success".to_string();
                    job.destination = Some(destination.clone());
                    job.error = None;
                    job.elapsed_ms = elapsed_ms;
                })
                .await;
            state.cache_put(&job.provider, &job.key, &destination).await;
            state.successes.fetch_add(1, Ordering::Relaxed);
            state.inflight.fetch_sub(1, Ordering::Relaxed);
            state.finish_job(&id).await;
            return;
        }
    }

    state
        .update_job(&id, |job| {
            job.status = "error".to_string();
            job.error = Some(last_error.clone());
            job.elapsed_ms = elapsed_ms;
        })
        .await;
    state.errors.fetch_add(1, Ordering::Relaxed);
    state.inflight.fetch_sub(1, Ordering::Relaxed);
    state.finish_job(&id).await;
}

fn supported_engines() -> Vec<String> {
    providers::supported()
        .into_iter()
        .filter(|key| *key != "DECODE")
        .map(str::to_lowercase)
        .collect()
}

// ------------------------------------------------------------------ handlers
async fn root(State(state): State<Arc<AppState>>) -> Json<Value> {
    Json(json!({
        "service": "Link Bypass Service (Rust)",
        "status": "online",
        "supported": supported_engines(),
        "docs": "/api/v1/supported",
        "endpoints": [
            "POST /api/v1/bypass",
            "GET /api/v1/bypass",
            "GET /api/v1/jobs/{id}",
            "POST /api/v1/batch",
            "GET /api/v1/stats",
            "GET /health",
        ],
        "uptime_sec": (now_secs() - state.started).round(),
    }))
}

async fn health(State(state): State<Arc<AppState>>) -> Json<Value> {
    let mut stats = state.stats().await;
    if let Some(object) = stats.as_object_mut() {
        object.insert("status".to_string(), json!("ok"));
        object.insert(
            "queued".to_string(),
            json!(state.queued.load(Ordering::Relaxed)),
        );
        object.insert(
            "inflight".to_string(),
            json!(state.inflight.load(Ordering::Relaxed)),
        );
        object.insert("workers".to_string(), json!(state.cfg.workers));
    }
    Json(stats)
}

async fn stats(State(state): State<Arc<AppState>>, Query(query): Query<StatsQuery>) -> Json<Value> {
    let limit = query.limit.clamp(1, 100);
    Json(json!({
        "stats": state.stats().await,
        "queued": state.queued.load(Ordering::Relaxed),
        "inflight": state.inflight.load(Ordering::Relaxed),
        "recent": state.recent(limit).await,
    }))
}

#[derive(Debug, Deserialize)]
pub struct StatsQuery {
    #[serde(default = "default_stats_limit")]
    pub limit: usize,
}

fn default_stats_limit() -> usize {
    15
}

async fn supported_list() -> Json<Value> {
    Json(json!({ "supported": supported_engines() }))
}

async fn bypass_post(
    State(state): State<Arc<AppState>>,
    headers: HeaderMap,
    Json(req): Json<BypassReq>,
) -> Result<Json<Value>, ApiError> {
    check_auth(&state, &headers, None)?;
    let result = do_bypass(
        state,
        req.url,
        req.wait,
        normalize_timeout(req.timeout),
        client_id(&headers),
    )
    .await?;
    Ok(Json(result))
}

async fn bypass_get(
    State(state): State<Arc<AppState>>,
    headers: HeaderMap,
    Query(query): Query<BypassQuery>,
) -> Result<Json<Value>, ApiError> {
    check_auth(&state, &headers, query.key.as_deref())?;
    let result = do_bypass(
        state,
        query.url,
        query.wait,
        normalize_timeout(query.timeout),
        client_id(&headers),
    )
    .await?;
    Ok(Json(result))
}

async fn job_get(
    State(state): State<Arc<AppState>>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Result<Json<Value>, ApiError> {
    check_auth(&state, &headers, None)?;
    match state.get_job(&id).await {
        Some(job) => Ok(Json(
            serde_json::to_value(job).unwrap_or_else(|_| json!({})),
        )),
        None => Err(ApiError::not_found("Không có job này")),
    }
}

async fn batch(
    State(state): State<Arc<AppState>>,
    headers: HeaderMap,
    Json(req): Json<BatchReq>,
) -> Result<Json<Value>, ApiError> {
    check_auth(&state, &headers, None)?;
    if req.urls.len() > 50 {
        return Err(ApiError::bad_request("Tối đa 50 URL mỗi batch"));
    }
    let client = client_id(&headers);
    let mut results = Vec::with_capacity(req.urls.len());
    for url in req.urls {
        match do_bypass(
            state.clone(),
            url,
            req.wait,
            normalize_timeout(req.timeout),
            client.clone(),
        )
        .await
        {
            Ok(value) => results.push(value),
            Err(error) => results.push(json!({
                "status": "error",
                "url": "",
                "destination_url": null,
                "provider": null,
                "cached": false,
                "elapsed_ms": 0.0,
                "job_id": null,
                "error": error.detail,
            })),
        }
    }
    Ok(Json(json!({ "count": results.len(), "results": results })))
}

pub fn router(state: Arc<AppState>) -> Router {
    Router::new()
        .route("/", get(root))
        .route("/health", get(health))
        .route("/api/v1/stats", get(stats))
        .route("/api/v1/supported", get(supported_list))
        .route("/api/v1/bypass", post(bypass_post).get(bypass_get))
        .route("/api/v1/jobs/{job_id}", get(job_get))
        .route("/api/v1/batch", post(batch))
        .layer(DefaultBodyLimit::max(1024 * 1024))
        .layer(CorsLayer::permissive())
        .layer(TraceLayer::new_for_http())
        .with_state(state)
}

pub fn print_check(cfg: &Config) {
    let payload = json!({
        "service": "bypass-server",
        "version": env!("CARGO_PKG_VERSION"),
        "config": cfg.summary(),
        "registry": providers::table_json(),
    });
    println!(
        "{}",
        serde_json::to_string_pretty(&payload).unwrap_or_default()
    );
}
