//! Environment-driven configuration. Mirrors `service/config.py` names so an
//! existing deployment `.env` keeps working when the Rust façade replaces the
//! FastAPI service.

use std::env;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone)]
pub struct Config {
    pub host: String,
    pub port: u16,
    pub api_key: String,
    pub workers: usize,
    pub max_queue: usize,
    pub job_timeout: u64,
    pub max_tries: u32,
    pub retry_delay: u64,
    pub cache_enabled: bool,
    pub cache_ttl: u64,
    pub cache_file: PathBuf,
    pub repo: PathBuf,
    pub python: String,
    pub l4m_engine: String,
    pub headless: bool,
    /// `L4M_NATIVE_URL` — base URL of a running `l4m-engine`. `None` leaves
    /// every job on the Python subprocess path, which stays the default.
    pub native: Option<crate::native::NativeClient>,
}

fn env_string(name: &str, default: &str) -> String {
    env::var(name).unwrap_or_else(|_| default.to_string())
}

fn env_int<T>(name: &str, default: T) -> T
where
    T: std::str::FromStr + Copy,
{
    env::var(name)
        .ok()
        .and_then(|value| value.trim().parse::<T>().ok())
        .unwrap_or(default)
}

fn env_bool(name: &str, default: bool) -> bool {
    match env::var(name) {
        Ok(value) => matches!(
            value.trim().to_lowercase().as_str(),
            "1" | "true" | "yes" | "on"
        ),
        Err(_) => default,
    }
}

/// Locate the repository root: explicit env first, then walk up from CWD
/// looking for `src/bypass_api.py`, then fall back to the parent of the crate.
pub fn find_repo() -> PathBuf {
    if let Ok(explicit) = env::var("L4M_REPO") {
        if !explicit.trim().is_empty() {
            return PathBuf::from(explicit);
        }
    }
    if let Ok(cwd) = env::current_dir() {
        for ancestor in cwd.ancestors() {
            if ancestor.join("src").join("bypass_api.py").is_file() {
                return ancestor.to_path_buf();
            }
        }
    }
    if let Ok(exe) = env::current_exe() {
        if let Some(bin_dir) = exe.parent() {
            for ancestor in bin_dir.ancestors() {
                if ancestor.join("src").join("bypass_api.py").is_file() {
                    return ancestor.to_path_buf();
                }
            }
        }
    }
    PathBuf::from("..")
}

fn find_python(repo: &Path) -> String {
    if let Ok(explicit) = env::var("PYTHON") {
        if !explicit.trim().is_empty() {
            return explicit;
        }
    }
    let venv = repo.join(".venv").join("bin").join("python");
    if venv.is_file() {
        return venv.to_string_lossy().into_owned();
    }
    let venv_python3 = repo.join(".venv").join("bin").join("python3");
    if venv_python3.is_file() {
        return venv_python3.to_string_lossy().into_owned();
    }
    "python3".to_string()
}

impl Config {
    pub fn from_env() -> Self {
        let repo = find_repo();
        let python = find_python(&repo);
        let cache_file = env::var("CACHE_FILE")
            .map(PathBuf::from)
            .unwrap_or_else(|_| repo.join("data").join("rust_cache.json"));
        Config {
            host: env_string("HOST", "0.0.0.0"),
            port: env_int("PORT", 8080u16),
            api_key: env_string("API_KEY", "").trim().to_string(),
            workers: env_int::<usize>("WORKERS", 1).max(1),
            max_queue: env_int::<usize>("MAX_QUEUE", 300).max(1),
            job_timeout: env_int::<u64>("JOB_TIMEOUT", 480).max(5),
            max_tries: env_int::<u32>("MAX_TRIES", 2).max(1),
            retry_delay: env_int::<u64>("RETRY_DELAY", 3),
            cache_enabled: env_bool("CACHE_ENABLED", true),
            cache_ttl: env_int::<u64>("CACHE_TTL", 21_600),
            cache_file,
            repo,
            python,
            l4m_engine: env_string("L4M_ENGINE", "cdp").to_lowercase(),
            headless: env_bool("HEADLESS", true),
            native: crate::native::NativeClient::from_env_value(
                &env_string("L4M_NATIVE_URL", ""),
                &env_string("NATIVE_API_KEY", &env_string("API_KEY", "")),
            ),
        }
    }

    /// One line per important setting, printed by `--check`.
    pub fn summary(&self) -> Vec<String> {
        vec![
            format!("host={}:{}", self.host, self.port),
            format!("repo={}", self.repo.display()),
            format!("python={}", self.python),
            format!("l4m_engine={}", self.l4m_engine),
            format!("l4m_native={}", self.native.as_ref().map_or_else(|| "off".to_string(), |client| client.base())),
            format!("workers={}", self.workers),
            format!("job_timeout={}s", self.job_timeout),
            format!("max_tries={}", self.max_tries),
            format!("max_queue={}", self.max_queue),
            format!("cache_enabled={}", self.cache_enabled),
            format!("cache_file={}", self.cache_file.display()),
            format!("api_key_set={}", !self.api_key.is_empty()),
            format!("headless={}", self.headless),
        ]
    }
}
