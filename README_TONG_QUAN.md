# Link4M Bypass Suite — Tổng quan

> Cập nhật: 26/11/2026. Tài liệu này viết chung cho mọi máy và mọi hệ điều
> hành. Mọi đường dẫn tính từ **thư mục gốc của repo** (gọi tắt `<repo>`).
> README gốc (`README.md`) là tài liệu bản Python cũ; chi tiết engine Rust ở
> `engine-rs/README.md`, façade đa provider ở `server-rs/README.md`.

## 1. Hệ thống làm gì

Tự động đi hết flow Link4M — đọc campaign, đi quest sponsor lấy mã, giải
reCAPTCHA audio, trả link đích — không cần người bấm, không API captcha trả
phí, chạy trên máy cá nhân hoặc server.

Ba lớp trong repo:

| Lớp | Vai trò | Nền tảng |
|---|---|---|
| `engine-rs/` (`l4m-engine`) | Engine native Rust: tự lái Chrome qua CDP, tự chủ toàn bộ Link4M, whisper.cpp local, OCR sidecar, proxy pool, cache campaign/mã, worker pool | Linux, macOS (WSL2 nếu dùng Windows) |
| `server-rs/` (`bypass-server`) | Façade HTTP Rust (axum) gọi engine Python `src.bypass_api`; giữ nhiều provider (LINK4M, BBMKTS, GTRAFFIC, LAYMA, TRAFFICVN, OCTOLINK) | Linux, macOS, Windows |
| `src/` + `api_server.py` + `auto_bypass.py` (+ `bot_discord.js`) | Engine Python gốc (Playwright), API FastAPI, CLI, bot Discord | Linux, macOS, Windows |

Chọn nhanh:

- Cần throughput Link4M, ít RAM, không phụ thuộc Python runtime → `engine-rs`.
- Cần một endpoint cho nhiều loại link, engine Python đã kiểm chứng → `server-rs`.
- Cần CLI/GUI/bot cũ → Python gốc.

## 2. Yêu cầu theo hệ điều hành

| Thành phần | Linux | macOS | Windows |
|---|---|---|---|
| Rust ≥ 1.75 | `rustup` | `rustup` | `rustup` (native cho `server-rs`; `engine-rs` cần WSL2) |
| Chrome/Chromium | bắt buộc | bắt buộc | bắt buộc (native hoặc trong WSL2) |
| Python 3.11+ | bắt buộc | bắt buộc | bắt buộc |
| Display cho Chrome headful | Xvfb nếu không có desktop | desktop có sẵn | desktop có sẵn (hoặc WSLg) |
| OCR sidecar | rapidocr trong venv | rapidocr trong venv | rapidocr trong venv |
| whisper model | `models/ggml-tiny.en.bin` | cùng | cùng (tải tự động nếu thiếu) |

Ghi chú nền tảng:

- **Linux không có màn hình**: chạy Xvfb và đặt `L4M_HEADLESS=0`. Widget
  sponsor và captcha audio chỉ hoạt động đúng khi Chrome có display thật.
- **macOS**: có desktop, đặt `L4M_HEADLESS=0`; không cần Xvfb.
- **Windows**: `engine-rs` dùng `setsid`/`killpg` của unix nên **build native
  Windows chưa hỗ trợ** — dùng WSL2 (Ubuntu) và làm theo hướng dẫn Linux.
  `server-rs` và engine Python chạy native Windows bình thường.
- Đường dẫn Python trong venv khác nhau:
  - Linux/macOS: `.venv/bin/python`
  - Windows: `.venv\Scripts\python.exe`

## 3. Flow của `engine-rs` (những gì nó tự làm)

1. Mở `https://link4m.net/go/<alias>`, chờ form thật (không nhầm wrapper captcha
   của trang khung), đọc `campaign_id`, `data-code`, tiêu đề.
2. Nếu trang **captcha-only** (Link4M không phục vụ campaign cho IP đó): bỏ qua
   toàn bộ bước sponsor, đi thẳng captcha — 15–40 s/lượt.
3. Đọc block `HƯỚNG DẪN LẤY MÃ`: chữ + ảnh; campaign tìm kiếm giấu domain và
   keyword trong ảnh → OCR (rapidocr sidecar, 800 px).
4. Probe song song các domain ứng viên; chỉ domain có `/widget/…?key=` được
   chọn; đọc `ref_domain_list` để biết cần referrer Google hay điều hướng trần.
5. Tab sponsor: UA mobile, viewport 390×844, touch, chặn
   `disable-devtool`/media/font, giữ tab focus; bấm `LẤY MÃ`, chờ countdown,
   reload, bấm tiếp nếu 2 bước, đọc `Mã KM: XXXXXX`.
6. Điền mã vào form, giải reCAPTCHA audio bằng whisper.cpp local.
7. POST form tới `{api}/links/get-link-info`, đọc `url`/`link` trong JSON.
8. Cache: destination theo `provider:alias`; mã theo `campaign_id` chỉ khi đã
   chứng minh ra destination (TTL 900 s, single-flight theo campaign).
9. Campaign chết/sponsor không có widget → re-roll tối đa 3 campaign.

## 4. Cài đặt chung

```bash
cd <repo>

# Python + OCR sidecar
python3 -m venv .venv                     # Windows: py -3 -m venv .venv
.venv/bin/pip install -r requirements.txt # Windows: .venv\Scripts\pip install -r requirements.txt
.venv/bin/python -m playwright install --with-deps chromium

# Rust engine
cd engine-rs
cargo build --release
```

Whisper model: nếu `models/ggml-tiny.en.bin` chưa có, engine tự tải từ
HuggingFace khi khởi động (hoặc đặt `WHISPER_MODEL` trỏ file có sẵn). OCR cần
`rapidocr` import được từ `L4M_PYTHON` (mặc định `.venv/bin/python`).

Linux headless:

```bash
sudo apt install xvfb          # Debian/Ubuntu
export DISPLAY=:99
Xvfb :99 -screen 0 1280x1000x24 &
export L4M_HEADLESS=0
```

## 5. Chạy nhanh

### engine-rs (Linux/macOS/WSL2)

```bash
cd <repo>/engine-rs
export REPO="$(cd .. && pwd)"

# một lượt, có proxy
WORKERS=1 L4M_HEADLESS=0 \
PROXY_LIST='user:pass@1.2.3.4:8000' \
./target/release/l4m-engine --once "https://link4m.org/go/<alias>"

# server
WORKERS=auto L4M_HEADLESS=0 ./target/release/l4m-engine
curl -s localhost:8080/health
curl -s -X POST localhost:8080/api/v1/bypass \
  -H 'content-type: application/json' \
  -d '{"url":"https://link4m.net/go/<alias>","wait":true}'
```

### server-rs (mọi hệ điều hành)

```bash
cd <repo>/server-rs
cargo build --release
./target/release/bypass-server --check        # Windows: target\release\bypass-server.exe --check
PORT=8080 ./target/release/bypass-server      # Windows: $env:PORT=8080; .\target\release\bypass-server.exe
```

`server-rs` cần biết repo Python: đặt `L4M_REPO=<repo>` nếu nó không tự dò
đúng, và `L4M_PYTHON` trỏ interpreter có playwright.

### Python legacy (mọi hệ điều hành)

```bash
cd <repo>
.venv/bin/python -m src.cli --url "https://link4m.net/go/<alias>"
.venv/bin/python api_server.py
# Windows: .venv\Scripts\python -m src.cli --url "..."
```

## 6. API (engine-rs)

| Endpoint | Việc |
|---|---|
| `GET /health` | trạng thái, số worker, cache |
| `GET /api/v1/stats` | đếm tổng/success/error/cache hit |
| `GET /api/v1/supported` | bảng provider |
| `POST /api/v1/bypass` | `{url, wait?, timeout?, code?}` |
| `GET /api/v1/bypass?url=...` | bản GET |
| `GET /api/v1/jobs/{id}` | poll job khi `wait=false` |
| `POST /api/v1/batch` | `{urls: [...], wait?, timeout?}` |

Auth: nếu đặt `API_KEY`, gửi `x-api-key: <key>` hoặc `?key=`.

## 7. Env quan trọng

| Biến | Default | Ý nghĩa |
|---|---|---|
| `WORKERS` | `2` / `auto` | số Chrome song song; `auto` = `(MemAvailable-900)/1400`, kẹp 1–32 |
| `MAX_QUEUE` | `100` | hàng đợi; vượt → 429 |
| `MAX_BATCH` | `50` | URL tối đa mỗi batch (1–500) |
| `BATCH_CONCURRENCY` | `max(4, WORKERS)` | request batch song song (1–64) |
| `PROXY_LIST` / `PROXY_FILE` | rỗng / `data/proxies.txt` | pool proxy |
| `PROXY_ROTATE` | `0` | `1` = đổi exit sau mỗi job |
| `L4M_HEADLESS` | `1` nếu không có `DISPLAY` | **đặt `0`** khi có display/Xvfb |
| `JOB_TIMEOUT` | `480` | giây/lượt |
| `CACHE_ENABLED` / `CACHE_TTL` | `true` / `21600` | cache destination |
| `L4M_CODE_TTL` | `900` | TTL mã sponsor |
| `L4M_CAMPAIGN` | rỗng | ghim campaign (list id, debug) |
| `L4M_CODE` | rỗng | truyền mã có sẵn, bỏ quest |
| `ASR_THREADS` | `2` | thread whisper |

## 8. Bằng chứng live (26/11/2026, Linux 3.7 GB, qua proxy relay)

| Giờ | Alias | Đường đi | Kết quả | Thời gian |
|---|---|---|---|---|
| 13:40:57 | LQUTiu | campaign `63d8e3e5...` / trafficseo.net / widget `8Duv3ox` → mã `JWgE8i` | `nmkiosvn-api...` | 153.6 s |
| 13:45:18 | LQUTiu | captcha-only | `nmkiosvn-api...` | 39.4 s |
| 13:46:47 | 2kCcIqn | captcha-only | `dash.nvnmc.cloud...` | 16.5 s |
| 13:48:29 | rrAhXyr | captcha-only | `dash.nvnmc.cloud...` | 39.2 s |
| 13:51:15 | 68pw167Y | ghim campaign + trang captcha-only → bỏ ghim | `dash.nvnmc.cloud...` | 15.3 s |

Ba lượt campaign trước đó (05:31–05:55 UTC): `LiLEvK`, `taPzez`, `QmmQ3M`, đều
ra `nmkiosvn-api.nmk87201.workers.dev/claim?...`.

## 9. Test

```bash
# engine-rs — 29 test (Linux/macOS/WSL2)
cd <repo>/engine-rs
WHISPER_DONT_GENERATE_BINDINGS=1 PATH="$PWD/../.venv/bin:$PATH" cargo test

# server-rs — 37 test (mọi hệ điều hành)
cd <repo>/server-rs && cargo test

# Python contract tests (đóng băng, không sửa)
cd <repo>
.venv/bin/python tests/test_fast_paths_and_pool.py
.venv/bin/python tests/test_r3_cli_api.py
.venv/bin/python tests/test_tier5_cli_api.py
.venv/bin/python tests/adversarial_cli_api_stress.py
.venv/bin/python tests/test_provider_registry.py
```

Năm file Python trên là **hợp đồng đóng băng**: sửa code phải giữ chúng xanh,
không được sửa nội dung test.

## 10. Deploy

- `engine-rs/deploy/l4m-engine.service` — systemd + `xvfb-run`, `MemoryHigh/Max`,
  `KillMode=control-group` để dọn Chrome kể cả khi bị SIGKILL.
- `engine-rs/deploy/l4m-engine.env.example` — mẫu env đầy đủ.
- `engine-rs/docs/SCALE.md` — công thức dung lượng, nút thắt, kiến trúc scale
  ngang + nginx.
- macOS/Windows: chạy trực tiếp binary hoặc qua Docker/WSL2; không dùng systemd.

## 11. Giới hạn đã biết

- Link4M ngừng phục vụ campaign cho một IP sau ~4 lượt hoàn thành; từ đó mọi
  alias trả captcha-only. Đường captcha-only vẫn ra destination; muốn có lại
  đường sponsor phải đổi exit (`PROXY_LIST` / `PROXY_ROTATE`).
- Máy 4 GB chỉ nên chạy 1 worker headful (Chrome 1.3–1.8 GB).
- reCAPTCHA audio bị chặn theo IP/profile: engine reload lấy anchor mới trong
  budget; proxy xoay là cách giảm tỉ lệ.
- OCR là sidecar rapidocr; thiếu nó thì campaign tìm kiếm không đọc được domain
  từ ảnh (campaign trực tiếp vẫn chạy).
- Queue nằm trong RAM: restart mất job đang chờ.
- `engine-rs` native Windows chưa hỗ trợ (phụ thuộc `setsid`/`killpg`); dùng
  WSL2.

## 12. Bản đồ repo

```
engine-rs/            engine native Rust (chính)
  src/proxy.rs        pool + relay + agent proxy
  src/pool.rs         worker pool, session Chrome/CDP/relay
  src/chrome.rs       launch args, setsid, killpg, sweep orphan
  src/flow.rs         flow Link4M, cache mã, re-roll campaign
  src/quest.rs        driver tab sponsor, countdown, parse mã
  src/instr.rs        OCR hướng dẫn, probe sponsor, cache campaign
  src/codes.rs        cache mã đã chứng minh
  src/state.rs        Config, worker auto, batch
  src/api.rs          HTTP API
  deploy/             systemd, env mẫu
  docs/SCALE.md       dung lượng + scale ngang
server-rs/            façade HTTP Rust gọi engine Python
src/                  engine Python gốc (Playwright), registry provider
tests/                contract tests Python (đóng băng)
service/, deploy/, scripts/, tools/, extension/
api_server.py         REST API Python cũ
auto_bypass.py        CLI Python cũ
bot_discord.js        bot Discord
```
