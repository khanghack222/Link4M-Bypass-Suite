# l4m-engine (Rust) — Link4M native

Binary Rust chạy trọn flow Link4M trong một process: Chrome qua CDP, đọc form,
giải reCAPTCHA audio bằng whisper.cpp chạy local, trả link đích. Không Playwright,
không Python, không API captcha, không phí mỗi lượt.

```
client ──HTTP──▶ l4m-engine (axum)
                   │  fast_decode (base64/percent)  → trả ngay
                   │  cache theo provider:alias
                   └─▶ worker (Chrome + CDP) ──▶ whisper.cpp ──▶ destination
```

Khác với `server-rs/` (façade HTTP gọi engine Python), crate này **tự lái browser**.
`server-rs/` dùng khi cần đủ 6 provider; crate này chỉ chạy Link4M.

## 1. Yêu cầu

| Thành phần | Ghi chú |
|---|---|
| Rust ≥ 1.75 | `cargo build --release` |
| Chrome/Chromium | bắt buộc, engine mở bằng CDP |
| Model whisper | `models/ggml-tiny.en.bin` (~77 MB); tự tải lần đầu nếu thiếu |
| RAM | mỗi worker ≈ 1 Chrome + model ≈ 700 MB–1 GB |

Model tải từ `https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin`
(`WHISPER_MODEL_URL` đổi được). Đặt sẵn vào `models/` nếu máy không ra internet.

## 2. Build

```bash
cd engine-rs
./build.sh
```

Binary: `target/release/l4m-engine`.

`build.sh` bật `WHISPER_DONT_GENERATE_BINDINGS=1` và tự tìm `cmake`. Lý do:
`whisper-rs-sys` mặc định chạy bindgen, cần `libclang.so` — box slim thường
không có và build chết ở `Unable to find libclang`. Bindings đóng sẵn trong
crate dùng được, chỉ cần `cmake` + `g++` để dịch whisper.cpp.

Build sạch trên box này (Rust 1.9x, cmake từ `pip install cmake`, `g++` 14):
release mất **~3 phút** với LTO, binary **7.1 MB**.

## 2.1 Test

```bash
cd engine-rs
WHISPER_DONT_GENERATE_BINDINGS=1 PATH="$PWD/../.venv/bin:$PATH" cargo test
```

**18 test**, không cần Chrome, không cần model — gồm 5 test HTTP contract dựng
`ApiState` với `asr = None`:

| Test | Nội dung |
|---|---|
| `health_and_supported_need_no_browser` | `/health`, `/api/v1/supported` đủ 7 key |
| `post_decode_and_get_with_lenient_wait` | POST decode + `?wait=1` (không 400) |
| `unknown_host_is_400_and_foreign_provider_is_501` | host lạ 400, GTraffic 501 |
| `auth_accepts_header_and_query_key` | 401 thiếu key, `x-api-key`, `?key=` |
| `missing_job_is_404_and_batch_is_capped` | job lạ 404, batch > 50 → 400 |

`cargo clippy --all-targets` sạch (cần cùng hai biến môi trường như build).

## 3. Chạy

```bash
# kiểm tra Chrome + CDP + whisper, không mở port
./target/release/l4m-engine --check

# chạy một alias, in JSON, không mở server
./target/release/l4m-engine --once https://link4m.net/go/2kCcIqn

# chạy server
PORT=8080 ./target/release/l4m-engine
```

`--check` in `check ok: chrome + cdp + whisper` rồi thoát 0. Trên box này (Chrome
158, model tiny.en, 2 thread) mất ~18 s cho lần đầu (whisper load + Chrome cold
start), các lần sau nhanh hơn.

`--once` in đúng một dòng JSON:

```json
{"status":"success","alias":"2kCcIqn","destination_url":"https://...","elapsed_ms":12345.6}
```

Lỗi:

```json
{"status":"failed","alias":"2kCcIqn","error":"...","kind":"needs_code","elapsed_ms":11844.6}
```

`kind` nhận: `page`, `cdp`, `audio`, `destination`, `needs_code`, `timeout`.

## 4. API

| Method | Path | Ghi chú |
|---|---|---|
| GET | `/` | danh sách endpoint |
| GET | `/health` | workers, cache, uptime |
| GET | `/api/v1/stats` | counters |
| GET | `/api/v1/supported` | bảng provider |
| POST | `/api/v1/bypass` | `{url, wait?, timeout?, code?}` |
| GET | `/api/v1/bypass` | `?url=...&wait=1&timeout=480&key=...` |
| GET | `/api/v1/jobs/{id}` | job đang chạy / vừa xong |
| POST | `/api/v1/batch` | `{urls:[≤50], wait?, timeout?}` |

Envelope giống `service/app.py`: `status`, `url`, `destination_url`, `provider`,
`cached`, `elapsed_ms`, `job_id`, `error`. Lỗi trả `{"detail": "..."}` với
400 / 401 / 404 / 429 / 501.

- `401` khi đặt `API_KEY` mà thiếu/sai `x-api-key`, `Authorization: Bearer`, `?key=`.
- `429` khi hàng đợi đầy; job vừa tạo được xoá khỏi bảng job luôn, không để lại
  job "running" ma.
- `501` cho provider khác Link4M — dùng `server-rs/` hoặc
  `python -m src.bypass_api` cho BBMKTS/GTRAFFIC/LAYMA/TRAFFICVN/OCTOLINK.
- `wait` nhận `1/true/yes/on` và `?wait` trần.

Ví dụ:

```bash
curl -s -X POST localhost:8080/api/v1/bypass \
  -H 'content-type: application/json' \
  -d '{"url":"https://bbmkts.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS94","wait":true}'
# → {"status":"success","destination_url":"https://example.com/x","provider":"decode",...}
```

## 5. Cấu hình

| Biến | Default | Ý nghĩa |
|---|---|---|
| `HOST` / `PORT` | `0.0.0.0` / `8080` | bind |
| `API_KEY` | rỗng | bật auth |
| `WORKERS` | `2` | số Chrome chạy song song; mỗi worker ~700 MB |
| `MAX_QUEUE` | `100` | vượt → 429 |
| `JOB_TIMEOUT` | `300` | giây cho một lượt flow |
| `CACHE_ENABLED` / `CACHE_TTL` | `true` / `21600` | cache theo `provider:alias` |
| `CACHE_FILE` | `data/native_cache.json` | cache bền qua restart |
| `CHROME_BIN` | tự dò | `google-chrome`, `chromium`, `/opt/google/chrome/chrome` |
| `L4M_HEADLESS` | `1` khi không có `DISPLAY` | `0` để xem cửa sổ |
| `CHROME_PROFILE` | `data/chrome-profile` | profile riêng, giữ cookie giữa các lượt |
| `WHISPER_MODEL` | `models/ggml-tiny.en.bin` | model ASR |
| `WHISPER_MODEL_URL` | HuggingFace tiny.en | nguồn tải khi thiếu model |
| `ASR_THREADS` | `2` | thread whisper |
| `RUST_LOG` | `l4m_engine=info,engine=info` | mức log |

## 6. Phạm vi hiện tại — đọc trước khi dùng

Engine chạy **fast path**: trang đã ở bước nhập mã (hoặc bước captcha sau khi mã
đã nhập trong phiên trước).

- Trang có ô `input[name=password]` mà request không kèm mã → trả
  `needs_code` trong ~12 s.
- Trang đã sang captcha → giải audio bằng whisper, POST `/links/get-link-info`,
  đọc link đích.
- Trang mới tinh cần chọn sponsor + lấy mã (quest nhiều bước, ảnh hướng dẫn +
  OCR) → **chưa có trong crate này**. Dùng `src/core/link4m_engine.py` cho quest,
  hoặc truyền mã có sẵn:

```bash
L4M_CODE=DTsiYu ./target/release/l4m-engine --once https://link4m.net/go/2kCcIqn
curl -s -X POST localhost:8080/api/v1/bypass \
  -H 'content-type: application/json' \
  -d '{"url":"https://link4m.net/go/2kCcIqn","code":"DTsiYu","wait":true}'
```

Đo trên box này, 2026-11-26:

| Tình huống | Kết quả |
|---|---|
| `--check` | `check ok: chrome + cdp + whisper`, ~18 s |
| `--once 2kCcIqn` (campaign mới, chưa có mã) | `needs_code` sau **10 s** (release) / 11.8 s (debug) |
| Cùng link trước khi sửa nhận diện trang | captcha giải 4 token (2382–2510 ký tự) rồi fail sau **4 m 55 s** — token không thể mở khoá vì thiếu mã |

Lỗi cũ: `#captcha-html-wrapper` xuất hiện cả trên trang khung trước khi form mã
được render, nên engine tưởng đã tới bước captcha. Nay chỉ coi là sẵn sàng khi
`input[name=password]` hiển thị, hoặc form đã có **và** wrapper có mặt.

## 7. Vận hành

- Job treo: `GET /api/v1/jobs/{id}` xem `elapsed_ms`; quá `JOB_TIMEOUT` worker
  huỷ Chrome và trả lỗi timeout.
- Chrome chết: `/health` vẫn 200; lượt sau worker mở lại Chrome.
- Hết RAM: hạ `WORKERS=1`, đặt `MemoryMax` nếu chạy systemd.
- Cache: một alias chỉ chạy một lần trong `CACHE_TTL`; request trùng nhận
  `cached: true`.
