# bypass-server (Rust) — façade HTTP cho Link4M Bypass Suite

Binary Rust thay lớp FastAPI (`service/app.py`) bằng một HTTP server nhẹ, đồng
thời giữ nguyên toàn bộ engine Python đã kiểm chứng. Rust **không** lái browser:
mỗi job được đẩy sang `python -m src.bypass_api --url ... --json`, rồi đọc dòng
`__BYPASS_JSON__{...}` cuối stdout.

```
client ──HTTP──▶ bypass-server (Rust, axum)
                   │  fast_decode (Rust)  → trả ngay, không queue
                   │  provider table       → LINK4M / BBMKTS / GTRAFFIC / LAYMA / TRAFFICVN / OCTOLINK
                   └─▶ python -m src.bypass_api --url ... --json
                          └─▶ registry → engine (Playwright/Chrome CDP)
                                 └─▶ FINAL DESTINATION URL + JSON
```

Vì sao tách như vậy: engine là thứ duy nhất cần Chrome, OCR, whisper. Viết lại
chúng bằng Rust là đổi một mớ đã chạy được lấy rủi ro. Lớp HTTP thì không cần
Python — đổi sang Rust được lợi về RAM, cold start, và cách ly lỗi.

## 1. Yêu cầu

| Thành phần | Ghi chú |
|---|---|
| Rust ≥ 1.75 | `rustup` là đủ; binary build tĩnh gần như hoàn toàn |
| Python 3.11+ | chạy engine, có `.venv` trong repo |
| Chrome/Chromium | engine Link4M cần browser thật, không phải headless-shell |
| Chrome CDP `127.0.0.1:9222` | khi `L4M_ENGINE=cdp` (mặc định), engine tự bật nếu chưa có |

Cài phần Python (nếu máy mới):

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install --with-deps chromium
```

## 2. Build và chạy

```bash
cd server-rs
cargo build --release

# xem cấu hình + bảng provider mà không mở port
./target/release/bypass-server --check

# chạy
PORT=8080 ./target/release/bypass-server
```

Log ra stdout: `host`, `repo`, `python`, `l4m_engine`, `workers`… Nếu `repo` sai,
đặt `L4M_REPO=/duong/dan/repo`.

Kiểm tra sống:

```bash
curl -s localhost:8080/health
curl -s localhost:8080/api/v1/supported
```

## 3. Test

### 3.1 Test Rust (29 test, không cần mạng, không cần Chrome)

```bash
cargo test
```

- 13 unit test: phân loại host, alias (`LINK999 → OCTOLINK`), slug `parse_key`,
  decode base64/percent + chống self-reference, parser stdout kể cả rác.
- 16 integration test (`tests/api_contract.rs`): `/health`, `/api/v1/supported`,
  fast-path decode, provider lạ → 400, URL rỗng → 400, thiếu field → 422, auth
  header/query, batch 51 URL → 400, batch decode, job không tồn tại → 404,
  body > 1MB → 413, JSON hỏng → 400.

### 3.2 Smoke test API (không cần Chrome)

Fast path decode chạy hoàn toàn trong Rust, nên test được ngay cả trên box
không có browser:

```bash
# tự động: 23 check (health, registry, decode, lỗi đầu vào, batch, giới hạn body)
BASE=http://127.0.0.1:8080 ./smoke-test.sh
```

Hoặc gõ tay:

```bash
# decode base64 trong /go/file/
curl -s -X POST localhost:8080/api/v1/bypass \
  -H 'content-type: application/json' \
  -d '{"url":"https://bbmkts.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS9zbW9rZQ==","wait":true}'
# → {"status":"success","destination_url":"https://example.com/smoke","provider":"decode",...}

# provider lạ → 400 kèm danh sách hỗ trợ
curl -s -X POST localhost:8080/api/v1/bypass \
  -H 'content-type: application/json' -d '{"url":"https://unknownlink.com/x"}'

# batch 2 link
curl -s -X POST localhost:8080/api/v1/batch \
  -H 'content-type: application/json' \
  -d '{"urls":["https://bbmkts.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS9h"],"wait":true}'
```

### 3.3 Live test Link4M (cần Chrome + mạng)

Job thật mất 2–5 phút: sponsor OCR → 2 lượt đếm ngược → mã → reCAPTCHA audio.

```bash
time curl -s -m 600 -X POST localhost:8080/api/v1/bypass \
  -H 'content-type: application/json' \
  -d '{"url":"https://link4m.net/go/2kCcIqn","wait":true,"timeout":560}'
```

Kỳ vọng:

```json
{
  "status": "success",
  "destination_url": "https://dash.nvnmc.cloud/earn/callback/...",
  "provider": "link4m",
  "cached": false,
  "elapsed_ms": 214000.0,
  "job_id": "..."
}
```

Chạy lại cùng link trong `CACHE_TTL` sẽ trả `"cached": true` gần như tức thì —
cache khoá theo `provider:slug`, không theo URL đầy đủ.

Kết quả đã kiểm chứng trên link thật (mặc định `L4M_ENGINE=cdp`, `L4M_HEADLESS=1`):

| Link | Đường đi | Thời gian engine | Kết quả |
|---|---|---|---|
| `link4m.org/go/mNkqHg2` | CDP, vào thẳng captcha | 57 789 ms | `success`, destination `dash.nvnmc.cloud/earn/callback/...` |
| `link4m.org/go/mNkqHg2` (qua Rust façade) | CDP | 59 267 ms | `success`, `job_id 8c65ec55546a4bf0` |
| `link4m.org/go/LQUTiu` | CDP | 73 021 ms | `success` |
| `link4m.net/go/2kCcIqn` (legacy cũ) | CDP + full quest | 254 957 ms | `success` |
| Đọc lại từ cache (`mNkqHg2`) | cache | 0.03 ms | `"cached": true` |

Đường nhanh: engine mở link bằng CDP, nếu `#main-form` không có ô mật khẩu thì
link đã đi qua quest (phiên trước đã nhập mã), engine kiểm tra
`#captcha-html-wrapper` rồi bấm captcha luôn — 50–75 giây thay vì 3–6 phút.
`runners.py` giờ mặc định nhánh `cdp`; đặt `L4M_ENGINE=legacy` mới quay lại
engine cũ.

Không có người ngồi trước màn hình thì lưới ảnh reCAPTCHA là ngõ cụt (chờ index
5 phút = treo job). Vì vậy khi `L4M_HEADLESS=1`, `solve_challenge` bỏ qua lưới
ảnh và trả thất bại nhanh để retry/chuyển tier khác; bật lại bằng
`L4M_MANUAL_GRID=1` nếu có người giải tay qua `/tmp/grid_engine.png`.

Với job dài, đừng giữ HTTP connection: gửi `wait: false`, nhận `job_id`, rồi
poll `/api/v1/jobs/{id}`. `timeout` của request chỉ giới hạn thời gian **client
chờ**, không huỷ job — job vẫn chạy tiếp và ghi cache. Nhớ rằng `MAX_TRIES=2`
có thể khiến tổng thời gian lên tới `2 × JOB_TIMEOUT`.

### 3.4 Test không dùng `wait`

```bash
# trả job_id ngay
curl -s -X POST localhost:8080/api/v1/bypass \
  -H 'content-type: application/json' \
  -d '{"url":"https://link4m.net/go/2kCcIqn"}'
# {"status":"queued","job_id":"..."}

# poll
curl -s localhost:8080/api/v1/jobs/<job_id>
```

### 3.5 Test auth

```bash
API_KEY=secret ./target/release/bypass-server &
curl -s -o /dev/null -w '%{http_code}\n' localhost:8080/health                     # 200 (health mở)
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8080/api/v1/bypass \
  -H 'content-type: application/json' -d '{"url":"https://bbmkts.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS94"}'   # 401
curl -s -X POST localhost:8080/api/v1/bypass \
  -H 'x-api-key: secret' -H 'content-type: application/json' \
  -d '{"url":"https://bbmkts.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbS94"}'          # 200
```

## 4. API

| Method | Path | Ghi chú |
|---|---|---|
| GET | `/` | service, supported, endpoints |
| GET | `/health` | status, queue depth, uptime, counters |
| GET | `/api/v1/supported` | danh sách engine |
| GET | `/api/v1/stats?limit=15` | counters + recent jobs |
| POST | `/api/v1/bypass` | `{url, wait?, timeout?}` |
| GET | `/api/v1/bypass?url=...&wait=1&key=...` | bản GET, `key` dùng được thay header |
| GET | `/api/v1/jobs/{id}` | trạng thái job |
| POST | `/api/v1/batch` | `{urls:[≤50], wait?, timeout?}` |

Envelope giống `service/app.py`: `status`, `url`, `destination_url`, `provider`,
`cached`, `elapsed_ms`, `job_id`, `error`. Lỗi trả `{"detail": "..."}` với 400 /
401 / 404 / 429 / 500.

Auth: `x-api-key`, `Authorization: Bearer`, hoặc `?key=`. Bỏ trống `API_KEY` =
không cần auth.

## 5. Cấu hình

| Biến | Default | Ý nghĩa |
|---|---|---|
| `HOST` / `PORT` | `0.0.0.0` / `8080` | bind |
| `API_KEY` | rỗng | bật auth |
| `L4M_REPO` | tự dò | gốc repo Python |
| `PYTHON` | `<repo>/.venv/bin/python` → `python3` | interpreter chạy engine |
| `L4M_ENGINE` | `cdp` | `cdp` (Chrome sẵn) hoặc `legacy` (Playwright) |
| `L4M_HEADLESS` | `1` | thêm `--headless=new` cho Chrome |
| `L4M_MANUAL_GRID` | `0` | `1` = cho phép chờ index lưới captcha thủ công khi headless |
| `WORKERS` | `1` | số engine chạy song song; **mỗi worker = 1 Chrome + ~700MB** |
| `MAX_QUEUE` | `300` | vượt → 429 |
| `JOB_TIMEOUT` | `480` | giây; Link4M thật cần ≥ 300 |
| `MAX_TRIES` | `2` | số lần thử lại |
| `CACHE_ENABLED` / `CACHE_TTL` | `true` / `21600` | cache theo `provider:slug` |
| `CACHE_FILE` | `<repo>/data/rust_cache.json` | cache bền qua restart |
| `RUST_LOG` | `bypass_server=info` | mức log |

`WORKERS` > 1 chỉ nên bật khi RAM đủ và mỗi engine có Chrome riêng. Trên box 2GB
để `1`.

## 6. Deploy

### 6.1 Docker (khuyến nghị)

Context phải là **repo root** vì image cần cây Python:

```bash
cp server-rs/deploy/.env.example server-rs/deploy/.env
# sửa API_KEY nếu mở ra internet
docker compose -f server-rs/deploy/docker-compose.yml up -d --build
curl -s localhost:8080/health
```

Image 2 stage: Rust build → runtime `node:20-slim` + Python deps + Chrome.
`shm_size: 1gb` và `seccomp:unconfined` là bắt buộc thực tế cho Chrome trong
container; thiếu `/dev/shm` Chrome chết giữa phiên.

### 6.2 systemd + binary

```bash
cd server-rs
cargo build --release
sudo ./deploy/install.sh /opt/link4m
sudoedit /opt/link4m/server-rs/.env
sudo systemctl restart l4m-bypass-rs
journalctl -u l4m-bypass-rs -f
```

Unit đặt `MemoryMax=2G`, `Restart=always`, chờ 3s. `TimeoutStopSec=20` đủ để
huỷ subprocess engine.

### 6.3 Nginx

```bash
sudo cp server-rs/deploy/nginx-l4m-rs.conf /etc/nginx/sites-available/bypass-rs
sudo ln -s /etc/nginx/sites-available/bypass-rs /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

`proxy_read_timeout 600s` — mặc định 60s sẽ cắt ngang job Link4M.

## 7. Vận hành

- **Job treo**: `GET /api/v1/jobs/{id}` xem `tries`/`elapsed_ms`. Quá
  `JOB_TIMEOUT` engine bị kill và trả `ERR_ENGINE_TIMEOUT`.
- **Chrome chết**: `/health` vẫn 200 (Rust sống), job trả lỗi engine. Kiểm tra
  `curl 127.0.0.1:9222/json/version`; `ensure_chrome()` tự bật lại ở job sau.
- **Sai repo**: `--check` in ra `repo=` — nếu trỏ sai, engine chạy sai thư mục và
  không thấy `src/bypass_api.py`.
- **Hết RAM**: hạ `WORKERS=1`, đặt `MemoryMax`, và đảm bảo Chrome dùng
  `--renderer-process-limit=3` (engine đã set).
- **429**: hàng đợi đầy — tăng `MAX_QUEUE` chỉ khi đã tăng `WORKERS`.

## 8. Khác biệt so với `service/app.py`

| | FastAPI | Rust |
|---|---|---|
| Queue | thread + SQLite | tokio task + semaphore, in-memory |
| Lịch sử job | SQLite bền | ring 100 job trong RAM + cache JSON |
| Cache | SQLite | HashMap + file JSON |
| `/ui` | có | không (dùng client ngoài) |
| Envelope/route | — | giữ nguyên |

Nếu cần lịch sử job bền qua restart, giữ FastAPI; nếu cần một cửa HTTP gọn để
scale ngang, dùng Rust và để cache lo phần lặp lại.
