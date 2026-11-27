# Link4M Bypass Suite — Tổng quan

> Cập nhật: 26/11/2026. Tài liệu này viết chung cho mọi máy và mọi hệ điều
> hành. Mọi đường dẫn tính từ **thư mục gốc của repo** (gọi tắt `<repo>`).
> Bản Python cũ: `docs/README_PYTHON_LEGACY.md`; chi tiết engine Rust ở
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

Trạng thái từng thành phần:

| Nhóm | Trạng thái | Quy tắc |
|---|---|---|
| `engine-rs/`, `server-rs/` | **ACTIVE** | Nơi làm tính năng mới |
| `src/` (engine Python, `src/bypass_api.py`) | **COMPAT** | `server-rs` vẫn gọi; sửa phải giữ stdout `__BYPASS_JSON__{...}` |
| `api_server.py`, `auto_bypass.py`, `src/cli.py`, `service/`, `Dockerfile` gốc, `deploy/` gốc | **LEGACY** | Không ưu tiên sửa; chưa chắc chạy trên máy mới |
| `legacy/`, `docs/archive/` | **ARCHIVE** | Chỉ đọc, không dùng production |
| 5 file test đóng băng | **CONTRACT** | Không sửa nội dung |
| Userscript, `extension/`, `community_bypass.js`, `universal_bypass.py` | **REMOVED** | Đã xoá; lịch sử còn trong git |

Bảng này là nguồn duy nhất về trạng thái thành phần. Legacy chưa được kiểm
tra lại trên máy mới, nên mọi việc mới tập trung vào `engine-rs/` (Link4M).

## 2. Yêu cầu theo hệ điều hành

| Thành phần | Linux | macOS | Windows |
|---|---|---|---|
| Rust ≥ 1.75 | `rustup` | `rustup` | `rustup` (native; `engine-rs` cần MSVC hoặc dùng WSL2) |
| Chrome/Chromium | bắt buộc | bắt buộc | bắt buộc (native hoặc trong WSL2) |
| Python 3.11+ | bắt buộc | bắt buộc | bắt buộc |
| Display cho Chrome headful | Xvfb nếu không có desktop | desktop có sẵn | desktop có sẵn (hoặc WSLg) |
| OCR sidecar | rapidocr trong venv | rapidocr trong venv | rapidocr trong venv |
| whisper model | `models/ggml-tiny.en.bin` | cùng | cùng (tải tự động nếu thiếu) |

Ghi chú nền tảng:

- **Linux không có màn hình**: chạy Xvfb và đặt `L4M_HEADLESS=0`. Widget
  sponsor và captcha audio chỉ hoạt động đúng khi Chrome có display thật.
- **macOS**: có desktop, đặt `L4M_HEADLESS=0`; không cần Xvfb.
- **Windows**: `engine-rs` có cfg Windows đầy đủ (`taskkill /T`, process group,
  CIM sweep, PowerShell/pwsh, `GlobalMemoryStatusEx`). Bản mặc định (whisper
  local) cần MSVC + VS Build Tools; bản `--no-default-features` + `ASR_URL` đã
  cross-build `x86_64-pc-windows-gnu` thành công nhưng chưa chạy live trên máy
  Windows thật. `server-rs` và engine Python chạy native Windows bình thường.
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
| `GET /api/v1/links` | snapshot bảng trạng thái (JSON) |
| `GET /api/v1/events` | SSE realtime cho bảng trạng thái |
| `GET /status` | trang bảng trạng thái realtime |

Auth: nếu đặt `API_KEY`, gửi `x-api-key: <key>` hoặc `?key=`.

## 7. Env quan trọng

| Biến | Default | Ý nghĩa |
|---|---|---|
| `WORKERS` | `2` / `auto` | số Chrome song song; `auto` = `(MemAvailable-900)/1400` (Linux; nơi khác fallback 1), kẹp 1–32 |
| `MAX_QUEUE` | `100` | hàng đợi; vượt → 429 |
| `MAX_BATCH` | `50` | URL tối đa mỗi batch (1–500) |
| `BATCH_CONCURRENCY` | `max(4, WORKERS)` | request batch song song (1–64) |
| `PROXY_LIST` / `PROXY_FILE` | rỗng / `data/proxies.txt` | pool proxy; file tự reload khi đổi |
| `PROXY_ROTATE` | `0` | `1` = đổi exit sau mỗi job |
| `L4M_HEADLESS` | `1` nếu không có `DISPLAY` | **đặt `0`** khi có display/Xvfb |
| `JOB_TIMEOUT` | `480` | giây/lượt |
| `CACHE_ENABLED` / `CACHE_TTL` | `true` / `21600` | cache destination |
| `QUEUE_FILE` | `data/queue.json` | job đang chờ, sống qua restart |
| `LINKS_FILE` | `data/links.json` | 500 dòng bảng trạng thái gần nhất |
| `QUEUE_RESUME` | `true` | `0` = không chạy lại job chờ sau restart |
| `QUEUE_RESUME_RUNNING` | `true` | `0` = job đang chạy lúc crash đánh `failed` thay vì chạy lại |
| `PROXY_ROTATE_AFTER` | `4` | tự đổi exit sau N lượt thành công khi pool có >1 proxy; `0` tắt |
| `PROXY_COOLDOWN` | `300` | giây một exit lỗi bị loại khỏi vòng xoay |
| `L4M_TESSERACT` | `tesseract` | OCR fallback khi thiếu RapidOCR sidecar |
| `OCR_URL` | rỗng | OCR server ngoài (multipart) thay sidecar/tesseract |
| `OCR_TIMEOUT` | `30` | giây timeout OCR (probe 5 s / ảnh 6 s) |
| `OCR_LANGUAGE` | rỗng | ngôn ngữ tesseract (rỗng = mặc định; `L4M_TESSERACT_LANG` ưu tiên hơn) |
| `L4M_OCR_CACHE` | `data/ocr-cache.json` | cache kết quả OCR theo campaign + hash ảnh |
| `L4M_PREWARM` | `1` | giữ sẵn một Chrome boot khi worker idle; `0` tắt |
| `CHROME_FLAGS` | rỗng | flag thêm vào lệnh launch Chrome |
| `L4M_CODE_TTL` | `900` | TTL mã sponsor |
| `L4M_CAMPAIGN` | rỗng | ghim campaign (list id, debug) |
| `L4M_CODE` | rỗng | truyền mã có sẵn, bỏ quest |
| `ASR_THREADS` | `2` | thread whisper local |
| `ASR_URL` / `ASR_LANGUAGE` / `ASR_TIMEOUT` | rỗng / `en` / `90` | dùng ASR server ngoài thay whisper local |
| `RC_SOLVER_CMD` | rỗng | solver reCAPTCHA v2 ngoài (vd `.venv/bin/python solve_service.py`); rỗng = tắt |
| `RC_SOLVER_SUBCOMMAND` | rỗng | chèn trước args solver, vd `solve` cho `window-vm.exe` |
| `RC_SOLVER_SITEKEY` | rỗng | sitekey dự phòng khi không đọc được từ page |
| `RC_SOLVER_MODEL` / `RC_SOLVER_ROUNDS` / `RC_SOLVER_TIMEOUT` | `tiny.en` / `4` / `180` | cấu hình solver ngoài |

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
# engine-rs — 58 test (Linux/macOS/WSL2)
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
  alias trả captcha-only. Đường captcha-only vẫn ra destination. Có pool proxy
  thì engine tự đổi exit sau `PROXY_ROTATE_AFTER` lượt; không có proxy thì
  không có exit khác để đổi.
- Máy 4 GB chỉ nên chạy 1 worker headful (Chrome 1.3–1.8 GB). `WORKERS=auto`
  đọc RAM trống theo từng hệ (`MemAvailable` / `vm_stat` /
  `GlobalMemoryStatusEx`, `(available-900)/1400`, kẹp 1–32).
- reCAPTCHA audio bị chặn theo IP/profile: engine reload lấy anchor mới trong
  budget. Khi Google báo `automated queries` / `try again later`, engine đánh
  dấu exit đó là xấu và relaunch Chrome sang exit kế tiếp nếu có pool.
- Campaign không có widget sống: engine thử campaign khác rồi tự lùi về trang
  captcha-only thay vì trả `needs_code`.
- OCR là sidecar rapidocr; thiếu nó thì engine thử `tesseract` nếu có trong
  PATH (`L4M_TESSERACT`). Thiếu cả hai thì campaign `TÌM KIẾM` không đọc được
  domain từ ảnh (campaign `TRỰC TIẾP` vẫn chạy).
- Job đang chạy lúc process chết được chạy lại từ đầu (`QUEUE_RESUME_RUNNING=1`,
  mặc định); đặt `0` nếu muốn đánh `failed` để tránh chạy đôi một lượt đã qua
  captcha.
- `engine-rs` có cfg Windows đầy đủ (taskkill + `CREATE_NEW_PROCESS_GROUP`);
  bản `--no-default-features` + `ASR_URL` đã cross-build
  `x86_64-pc-windows-gnu` nhưng chưa chạy live trên Windows thật. Bản mặc định
  (whisper local) cần MSVC; cross-check mingw fail ở bindgen `whisper-rs-sys`
  (dependency), không phải code engine.

## 12. Bản đồ repo

```
engine-rs/            engine native Rust (chính)
  src/proxy.rs        pool + relay + agent proxy
  src/pool.rs         worker pool, session Chrome/CDP/relay
  src/chrome.rs       launch args, process group/tree, sweep orphan Chrome
  src/flow.rs         flow Link4M, cache mã, re-roll campaign
  src/quest.rs        driver tab sponsor, countdown, parse mã
  src/instr.rs        OCR hướng dẫn, probe sponsor, cache campaign
  src/codes.rs        cache mã đã chứng minh
  src/state.rs        Config, worker auto, batch, lịch sử link cho bảng
  src/api.rs          HTTP API + SSE + trang /status
  web/status.html     bảng trạng thái realtime
  deploy/             systemd, env mẫu
  docs/SCALE.md       dung lượng + scale ngang
server-rs/            façade HTTP Rust gọi engine Python
src/                  engine Python gốc (Playwright), registry provider — COMPAT
tests/                contract tests Python (đóng băng)
service/, deploy/     service FastAPI + Docker/systemd cũ — LEGACY
legacy/               mã cũ đã dời: api_server_slim, windows/, scripts/, tools/
scripts/              update-engine.sh — cập nhật không clone
docs/                 tài liệu dự án
  README_PYTHON_LEGACY.md   bản Python cũ
  AI_HANDOFF.md             brief cho AI bên thứ ba
  API_DOCUMENTATION.md      API Python cũ
  TEST_INFRA.md / TEST_READY.md
  archive/                  báo cáo, kế hoạch, tài liệu lịch sử
_local/               file cấu hình tool cá nhân (gitignore, không commit)
api_server.py         REST API Python cũ
auto_bypass.py        CLI Python cũ
bot_discord.js        bot Discord
```

Mục lục tài liệu: `docs/INDEX.md`.

## 13. Bảng trạng thái realtime

Mở `http://<host>:8080/status` (thêm `?key=<API_KEY>` nếu engine có `API_KEY`).

- Mỗi request hiện thành một dòng: `queued` → `running` → `success` hoặc
  `failed`; kèm link gốc, link đích, provider, cache hit, thời gian chạy.
- Cập nhật bằng SSE `/api/v1/events`; snapshot đầu tiên là toàn bộ 500 link
  gần nhất. SSE bị proxy chặn thì trang tự fallback poll `/api/v1/links` 5 s/lần.
- Cache hit và fast decode cũng lên bảng; lỗi hiện nguyên văn bên dưới link.
- Bảng và hàng đợi sống qua restart: `data/links.json` giữ 500 dòng gần nhất,
  `data/queue.json` giữ cả job chờ lẫn job đang chạy. Job bị crash giữa chừng
  được đẩy lại worker từ đầu; đặt `QUEUE_RESUME_RUNNING=0` nếu muốn đánh
  `failed` thay vì chạy lại.
- `/api/v1/stats` trả `recent` (20 dòng cuối) và số `queued` thật, không còn 0
  cố định.

## 14. Cập nhật không cần clone

`scripts/update-engine.sh` tải mã mới từ GitHub và chỉ quản lý `engine-rs/`.
Không chạm `data/`, `models/`, `target/`, `legacy/`, `src/`, `service/`,
`.env`, `proxies.txt`.

Cơ chế 3 chiều, chống đè file bạn đã sửa:

| Tình huống | Hành động |
|---|---|
| File local giống bản mới | bỏ qua |
| File local giống manifest (bạn chưa sửa) | ghi đè, có backup |
| File local khác manifest (bạn đã sửa) | **giữ nguyên**, bản mới vào `_local/update-conflicts/<thời-gian>/` |
| File bạn tự tạo ngoài manifest | không đụng |

```bash
./scripts/update-engine.sh                 # xem trước, không ghi
./scripts/update-engine.sh --apply         # ghi + build release
./scripts/update-engine.sh --apply -y      # không hỏi
./scripts/update-engine.sh --check         # cron: exit 10 nếu có bản mới
./scripts/update-engine.sh --apply --restart --no-build
```

- Trước khi ghi, file bị thay đổi được backup vào
  `_local/update-backup/<thời-gian>/`.
- Build release fail → tự rollback các file vừa ghi, `.l4m-version` giữ nguyên.
- Manifest `.l4m-engine-manifest` và mốc `.l4m-version` nằm ở gốc repo, được
  cập nhật sau khi apply thành công.
- Lần đầu chưa có manifest: file đã sửa được coi là xung đột và giữ nguyên,
  không có chuyện ghi đè mù.
- Windows: script là bash; chạy trong WSL2/Git Bash. Engine native Windows giờ
  build được bằng `--no-default-features` + `ASR_URL`, nhưng script cập nhật
  vẫn cần môi trường bash.
