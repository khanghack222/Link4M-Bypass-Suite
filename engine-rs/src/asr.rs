//! Speech-to-text for the reCAPTCHA audio challenge.
//!
//! Two backends:
//! - `local` (default feature): whisper.cpp via `whisper-rs`, CPU only, no API
//!   key and no per-request cost. The model is downloaded once at startup.
//! - `remote`: any whisper.cpp server or OpenAI-compatible endpoint. Set
//!   `ASR_URL`; the engine uploads a 16 kHz mono WAV and reads `text` back.
//!
//! A build with `--no-default-features` drops the C++ toolchain entirely and
//! keeps only the remote backend, which is what a Windows box without MSVC or
//! a cross-compile job needs.

use anyhow::{anyhow, Result};
use std::io::Read;
use std::path::Path;
#[cfg(feature = "local-asr")]
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;
#[cfg(feature = "local-asr")]
use anyhow::Context;
#[cfg(feature = "local-asr")]
use whisper_rs::{FullParams, SamplingStrategy, WhisperContext, WhisperContextParameters};

pub const DEFAULT_MODEL_URL: &str =
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin";

/// Silence whisper.cpp's stderr chatter; the engine logs what matters.
#[cfg(feature = "local-asr")]
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

#[cfg(not(feature = "local-asr"))]
pub fn silence_backend_logs() {}

pub struct Asr {
    backend: Backend,
}

enum Backend {
    #[cfg(feature = "local-asr")]
    Local { context: WhisperContext, threads: i32 },
    Remote {
        url: String,
        language: String,
        timeout: Duration,
        /// Keep-alive agent: an ASR host on the LAN or a HTTPS endpoint pays a
        /// fresh TCP/TLS handshake on every clip otherwise.
        agent: ureq::Agent,
    },
}

impl Asr {
    #[cfg(feature = "local-asr")]
    pub fn load(model: &Path, threads: i32) -> Result<Self> {
        let path = model
            .to_str()
            .ok_or_else(|| anyhow!("model path is not valid utf-8"))?;
        let context = WhisperContext::new_with_params(path, WhisperContextParameters::default())
            .map_err(|err| anyhow!("load whisper model {path}: {err}"))?;
        Ok(Self {
            backend: Backend::Local {
                context,
                threads: threads.max(1),
            },
        })
    }

    /// `ASR_URL` can point straight at a whisper.cpp `/inference` endpoint, at
    /// an OpenAI-compatible `/v1/audio/transcriptions`, or at a bare host —
    /// `/inference` is appended only for a bare host.
    pub fn remote(raw: &str) -> Result<Self> {
        let mut url = raw.trim().to_string();
        if url.is_empty() {
            return Err(anyhow!("ASR_URL is empty"));
        }
        if !url.starts_with("http://") && !url.starts_with("https://") {
            return Err(anyhow!("ASR_URL must start with http:// or https://"));
        }
        let bare = url
            .parse::<url::Url>()
            .map(|parsed| parsed.path().is_empty() || parsed.path() == "/")
            .unwrap_or(false);
        if bare {
            url = url.trim_end_matches('/').to_string() + "/inference";
        }
        let language = std::env::var("ASR_LANGUAGE")
            .ok()
            .filter(|value| !value.trim().is_empty())
            .unwrap_or_else(|| "en".into());
        let timeout = Duration::from_secs(
            std::env::var("ASR_TIMEOUT")
                .ok()
                .and_then(|value| value.trim().parse::<u64>().ok())
                .filter(|secs| *secs >= 5)
                .unwrap_or(90),
        );
        Ok(Self {
            backend: Backend::Remote {
                url,
                language,
                timeout,
                agent: ureq::AgentBuilder::new().timeout(timeout).build(),
            },
        })
    }

    pub fn label(&self) -> &'static str {
        match &self.backend {
            #[cfg(feature = "local-asr")]
            Backend::Local { .. } => "whisper.cpp (local)",
            Backend::Remote { .. } => "remote ASR",
        }
    }

    pub fn transcribe(&self, pcm_16k: &[f32]) -> Result<String> {
        if pcm_16k.len() < 1600 {
            return Ok(String::new());
        }
        match &self.backend {
            #[cfg(feature = "local-asr")]
            Backend::Local { context, threads } => transcribe_local(context, *threads, pcm_16k),
            Backend::Remote {
                url,
                language,
                timeout,
                agent,
            } => transcribe_remote(agent, url, language, *timeout, pcm_16k),
        }
    }
}

#[cfg(feature = "local-asr")]
fn transcribe_local(context: &WhisperContext, threads: i32, pcm_16k: &[f32]) -> Result<String> {
    let mut state = context.create_state()?;
    let mut params = FullParams::new(SamplingStrategy::Greedy { best_of: 1 });
    params.set_n_threads(threads);
    params.set_language(Some("en"));
    params.set_translate(false);
    // A captcha clip is one short phrase. Carrying decoder context between
    // clips and splitting the output into segments only adds work.
    params.set_no_context(true);
    params.set_single_segment(true);
    params.set_suppress_blank(true);
    params.set_temperature(0.0);
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

/// Encode normalized f32 samples as a 16 kHz mono PCM16 WAV. Both whisper.cpp
/// and OpenAI-compatible servers accept a plain WAV upload.
fn wav_bytes(pcm_16k: &[f32]) -> Vec<u8> {
    let data_len = (pcm_16k.len() * 2) as u32;
    let mut out = Vec::with_capacity(44 + data_len as usize);
    out.extend_from_slice(b"RIFF");
    out.extend_from_slice(&(36 + data_len).to_le_bytes());
    out.extend_from_slice(b"WAVEfmt ");
    out.extend_from_slice(&16u32.to_le_bytes());
    out.extend_from_slice(&1u16.to_le_bytes()); // PCM
    out.extend_from_slice(&1u16.to_le_bytes()); // mono
    out.extend_from_slice(&16_000u32.to_le_bytes());
    out.extend_from_slice(&32_000u32.to_le_bytes()); // byte rate
    out.extend_from_slice(&2u16.to_le_bytes()); // block align
    out.extend_from_slice(&16u16.to_le_bytes()); // bits per sample
    out.extend_from_slice(b"data");
    out.extend_from_slice(&data_len.to_le_bytes());
    for sample in pcm_16k {
        let value = (sample.clamp(-1.0, 1.0) * 32767.0) as i16;
        out.extend_from_slice(&value.to_le_bytes());
    }
    out
}

fn transcribe_remote(
    agent: &ureq::Agent,
    url: &str,
    language: &str,
    timeout: Duration,
    pcm_16k: &[f32],
) -> Result<String> {
    let wav = wav_bytes(pcm_16k);
    let boundary = format!("l4m-asr-{}", std::process::id());
    let mut body = Vec::with_capacity(wav.len() + 1024);
    body.extend_from_slice(
        format!(
            "--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; \
             filename=\"audio.wav\"\r\nContent-Type: audio/wav\r\n\r\n"
        )
        .as_bytes(),
    );
    body.extend_from_slice(&wav);
    body.extend_from_slice(b"\r\n");
    for (name, value) in [
        ("response_format", "json"),
        ("language", language),
        ("temperature", "0"),
    ] {
        body.extend_from_slice(
            format!(
                "--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n"
            )
            .as_bytes(),
        );
    }
    body.extend_from_slice(format!("--{boundary}--\r\n").as_bytes());

    let response = agent
        .post(url)
        .timeout(timeout)
        .set(
            "Content-Type",
            &format!("multipart/form-data; boundary={boundary}"),
        )
        .send_bytes(&body)
        .map_err(|err| anyhow!("ASR request failed: {err}"))?;
    let raw = response
        .into_string()
        .map_err(|err| anyhow!("read ASR response: {err}"))?;
    let value: serde_json::Value = serde_json::from_str(&raw)
        .unwrap_or_else(|_| serde_json::json!({ "text": raw.as_str() }));
    let text = value
        .get("text")
        .or_else(|| value.get("transcription"))
        .and_then(serde_json::Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string();
    Ok(text)
}

/// Download the model if it is missing or obviously truncated.
#[cfg(feature = "local-asr")]
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn wav_header_is_canonical() {
        let wav = wav_bytes(&[0.0, 0.5, -0.5, 1.0]);
        assert_eq!(&wav[0..4], b"RIFF");
        assert_eq!(&wav[8..12], b"WAVE");
        assert_eq!(u32::from_le_bytes(wav[24..28].try_into().unwrap()), 16_000);
        assert_eq!(u16::from_le_bytes(wav[22..24].try_into().unwrap()), 1);
        assert_eq!(u32::from_le_bytes(wav[40..44].try_into().unwrap()), 8);
        assert_eq!(wav.len(), 44 + 8);
    }

    #[test]
    fn remote_rejects_non_http() {
        assert!(Asr::remote("127.0.0.1:8081").is_err());
        assert!(Asr::remote("").is_err());
    }

    #[test]
    fn remote_appends_inference_to_bare_host() {
        let asr = Asr::remote("http://127.0.0.1:8081").expect("remote config");
        match asr.backend {
            Backend::Remote { url, .. } => assert_eq!(url, "http://127.0.0.1:8081/inference"),
            #[cfg(feature = "local-asr")]
            Backend::Local { .. } => unreachable!(),
        }
    }

    #[test]
    fn remote_backend_uploads_wav_and_reads_text() {
        use std::io::{Read, Write};
        let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("bind");
        let port = listener.local_addr().unwrap().port();
        let server = std::thread::spawn(move || {
            let (mut socket, _) = listener.accept().expect("accept");
            socket
                .set_read_timeout(Some(Duration::from_secs(10)))
                .unwrap();
            let mut buf = Vec::new();
            let mut chunk = [0u8; 4096];
            let header_end = loop {
                let n = socket.read(&mut chunk).expect("read head");
                assert!(n > 0, "client closed before headers");
                buf.extend_from_slice(&chunk[..n]);
                if let Some(pos) = buf.windows(4).position(|w| w == b"\r\n\r\n") {
                    break pos + 4;
                }
            };
            let head = String::from_utf8_lossy(&buf[..header_end]).to_lowercase();
            let length: usize = head
                .lines()
                .find_map(|line| line.strip_prefix("content-length:"))
                .and_then(|value| value.trim().parse().ok())
                .expect("content-length");
            while buf.len() < header_end + length {
                let n = socket.read(&mut chunk).expect("read body");
                if n == 0 {
                    break;
                }
                buf.extend_from_slice(&chunk[..n]);
            }
            let body = String::from_utf8_lossy(&buf[header_end..]).to_string();
            assert!(body.contains("filename=\"audio.wav\""));
            assert!(body.contains("RIFF"));
            let payload = "{\"text\":\"hello\"}";
            let reply = format!(
                "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n{payload}",
                payload.len()
            );
            socket.write_all(reply.as_bytes()).expect("write reply");
        });

        let asr = Asr::remote(&format!("http://127.0.0.1:{port}/inference")).expect("remote");
        let text = asr.transcribe(&vec![0.25f32; 1600]).expect("transcribe");
        assert_eq!(text, "hello");
        server.join().expect("server");
    }
}
