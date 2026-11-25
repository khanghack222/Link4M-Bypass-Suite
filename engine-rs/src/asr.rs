//! Local speech-to-text for the reCAPTCHA audio challenge.
//!
//! whisper.cpp (via whisper-rs) runs in-process, CPU only, no API key and no
//! per-request cost. The model is downloaded once at startup when missing.

use anyhow::{anyhow, Context, Result};
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use whisper_rs::{FullParams, SamplingStrategy, WhisperContext, WhisperContextParameters};

pub const DEFAULT_MODEL_URL: &str =
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin";

/// Silence whisper.cpp's stderr chatter; the engine logs what matters.
pub fn silence_backend_logs() {
    unsafe extern "C" fn discard(
        _level: whisper_rs_sys::ggml_log_level,
        _text: *const std::os::raw::c_char,
        _user: *mut std::ffi::c_void,
    ) {
    }
    unsafe {
        whisper_rs_sys::whisper_log_set(Some(discard), std::ptr::null_mut());
    }
}

pub struct Asr {
    context: WhisperContext,
    threads: i32,
}

impl Asr {
    pub fn load(model: &Path, threads: i32) -> Result<Self> {
        let path = model
            .to_str()
            .ok_or_else(|| anyhow!("model path is not valid utf-8"))?;
        let context = WhisperContext::new_with_params(path, WhisperContextParameters::default())
            .with_context(|| format!("load whisper model {path}"))?;
        Ok(Self { context, threads: threads.max(1) })
    }

    pub fn transcribe(&self, pcm_16k: &[f32]) -> Result<String> {
        if pcm_16k.len() < 1600 {
            return Ok(String::new());
        }
        let mut state = self.context.create_state()?;
        let mut params = FullParams::new(SamplingStrategy::Greedy { best_of: 1 });
        params.set_n_threads(self.threads);
        params.set_language(Some("en"));
        params.set_translate(false);
        params.set_print_special(false);
        params.set_print_progress(false);
        params.set_print_realtime(false);
        params.set_print_timestamps(false);
        state.full(params, pcm_16k)?;

        let segments = state.full_n_segments()?;
        let mut text = String::new();
        for index in 0..segments {
            text.push_str(state.full_get_segment_text(index)?.trim());
            text.push(' ');
        }
        Ok(text.trim().to_string())
    }
}

/// Download the model if it is missing or obviously truncated.
pub fn ensure_model(path: &Path, url: &str) -> Result<PathBuf> {
    if let Ok(meta) = std::fs::metadata(path) {
        if meta.len() > 1_000_000 {
            return Ok(path.to_path_buf());
        }
    }
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).ok();
    }
    tracing::info!(target: "engine", "downloading whisper model from {url}");
    let response = ureq::get(url)
        .timeout(std::time::Duration::from_secs(600))
        .call()
        .context("download whisper model")?;
    let tmp = path.with_extension("part");
    {
        let mut reader = response.into_reader();
        let mut file = std::fs::File::create(&tmp).context("create model file")?;
        std::io::copy(&mut reader, &mut file).context("write model file")?;
    }
    std::fs::rename(&tmp, path).context("move model into place")?;
    let size = std::fs::metadata(path).map(|m| m.len()).unwrap_or(0);
    if size < 1_000_000 {
        return Err(anyhow!("downloaded model is too small ({size} bytes)"));
    }
    Ok(path.to_path_buf())
}

/// Shared handle used by the worker pool.
pub type SharedAsr = Arc<Asr>;

/// Read a raw PCM16 little-endian blob into normalized f32 samples.
pub fn pcm16_to_f32(bytes: &[u8]) -> Vec<f32> {
    bytes
        .as_chunks::<2>()
        .0
        .iter()
        .map(|pair| i16::from_le_bytes(*pair) as f32 / 32768.0)
        .collect()
}

/// Small helper used by tests and the `--check` path.
pub fn read_audio_file(path: &Path) -> Result<Vec<f32>> {
    let mut file = std::fs::File::open(path)?;
    let mut buf = Vec::new();
    file.read_to_end(&mut buf)?;
    Ok(pcm16_to_f32(&buf))
}
