# l4m-engine (Rust) — Link4M native, tự chủ toàn bộ

Binary Rust chạy trọn flow Link4M trong một process: Chrome qua CDP, đọc form,
OCR ảnh hướng dẫn, tự đi quest lấy mã sponsor, giải reCAPTCHA audio bằng
whisper.cpp chạy local, trả link đích. Không Playwright, không Python, không API
captcha, không phí mỗi lượt, không cần người bấm.

```
client ──HTTP──▶ l4m-engine (axum)
                   │  fast_decode (base64/percent)      → trả ngay
                   │  cache theo provider:alias
                   │  cache mã theo campaign_id (mã đã chứng minh)
                   └─▶ worker (Chrome + CDP)
                         ├─ trang link4m: campaign + ảnh hướng dẫn
                         ├─ OCR (rapidocr sidecar) → sponsor + keyword
                         ├─ probe sponsor → widget key + kiểu referrer
                         ├─ tab sponsor: quest 2 bước → mã KM
                         ├─ whisper.cpp: reCAPTCHA audio → token
                         └─ POST /links/get-link-info → destination
```

Khác với `server-rs/` (façade HTTP gọi engine Python), crate này **tự lái
browser** và chỉ chạy Link4M.

## 1. Yêu cầu

| Thành phần | Ghi chú |
|---|---|
| Rust ≥ 1.75 | `cargo build --release` |
| Chrome/Chromium | bắt buộc; engine mở bằng CDP |
| X display | **bắt buộc** cho quest: widget và reCAPTCHA audio chỉ chạy đúng khi tab thật sự foreground. Dùng Xvfb trên server |
| Model whisper | `models/ggml-tiny.en.bin` (~77 MB), tự tải lần đầu nếu thiếu |
| ASR remote (tuỳ chọn) | `ASR_URL` trỏ whisper.cpp server hoặc endpoint OpenAI-compatible; thay được model local |
| Python venv + rapidocr | sidecar `tools/ocr.py`; chỉ dùng khi campaign giấu hướng dẫn trong ảnh |
| RAM | 1 worker ≈ 1 Chrome headful + whisper ≈ 1.3–1.8 GB |

Model tải từ `https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin`
(`WHISPER_MODEL_URL` đổi được). Đặt sẵn vào `models/` nếu máy không ra internet.
Không muốn build whisper.cpp (máy Windows không MSVC, box ARM, cross-compile)
thì dùng ASR server ngoài — xem mục 2.

OCR sidecar:

```bash
python3 -m venv .venv
.venv/bin/pip install rapidocr_onnxruntime opencv-python-headless pillow
```

## 2. Build

```bash
cd engine-rs
./build.sh
```

Binary: `target/release/l4m-engine`.

Vòng lặp phát triển: `cargo build --profile release-fast` (cùng opt-level 3,
bỏ LTO) — binary `target/release-fast/l4m-engine`, build nhanh hơn nhiều lần;
chỉ dùng `--release` cho bản phát hành.

`build.sh` bật `WHISPER_DONT_GENERATE_BINDINGS=1` và tự tìm `cmake`. Lý do:
`whisper-rs-sys` mặc định chạy bindgen, cần `libclang.so` — box slim thường
không có và build chết ở `Unable to find libclang`. Bindings đóng sẵn trong
crate dùng được, chỉ cần `cmake` + `g++` để dịch whisper.cpp.

Build không có C++ toolchain — chỉ dùng ASR server ngoài:

```bash
# Bỏ whisper.cpp + model; binary chỉ gửi audio tới ASR_URL.
./build.sh --no-default-features
ASR_URL=http://127.0.0.1:8081/inference ./target/release/l4m-engine
```

Đường này đã cross-build thành công `x86_64-pc-windows-gnu` (file `.exe`
7.0 MB) trên Linux; chạy thật trên Windows vẫn cần Chrome + `.venv` OCR và
một ASR server (whisper.cpp server hoặc endpoint OpenAI-compatible).

## 2.1 Test

```bash
cd engine-rs
WHISPER_DONT_GENERATE_BINDINGS=1 PATH="$PWD/../.venv/bin:$PATH" cargo test
```

Test không cần Chrome, không cần model. Gồm HTTP contract (dựng `ApiState` với
`asr = None`), parser campaign (`instr`), parser mã widget (`quest`), cache mã
(`codes`).

## 2.2 Cập nhật không cần clone

```bash
./scripts/update-engine.sh            # xem trước
./scripts/update-engine.sh --apply    # ghi + build release
```

Script chỉ quản lý `engine-rs/`, so 3 chiều local / manifest / bản mới: file
bạn đã sửa không bị ghi đè, bản mới vào `_local/update-conflicts/`. Build fail
thì rollback. Chi tiết ở `README.md` gốc mục 14.

## 3. Chạy

```bash
# kiểm tra Chrome + CDP + whisper, không mở port
./target/release/l4m-engine --check

# chạy một alias, in JSON, không mở server
L4M_HEADLESS=0 ./target/release/l4m-engine --once https://link4m.net/go/2kCcIqn

# chạy server
PORT=8080 ./target/release/l4m-engine
```

`--once` in đúng một dòng JSON:

```json
{"status":"success","alias":"LQUTiu","destination_url":"https://...","elapsed_ms":245767.8}
```

Lỗi:

```json
{"status":"failed","alias":"LQUTiu","error":"...","kind":"needs_code","elapsed_ms":53397.2}
```

`kind` nhận: `page`, `cdp`, `audio`, `destination`, `needs_code`, `campaign`,
`timeout`.

## 4. Flow thật (những gì engine tự làm)

1. **Trang link4m** — chờ form thật hiện ra (không nhầm
   `#captcha-html-wrapper` của trang khung), đọc `campaign_id`, `data-code`,
   tiêu đề. Nếu trang chỉ có captcha (Link4M không phục vụ campaign cho IP
   này), engine bỏ qua toàn bộ bước 2–6 và đi thẳng captcha — lượt chạy còn
   ~15–40 s.
2. **Lọc campaign** — `L4M_CAMPAIGN=<id>` buộc re-roll tới đúng campaign
   (tối đa 24 lần, nhận danh sách id phân tách bởi dấu phẩy). Không đặt thì
   lấy campaign đang phục vụ. Trang captcha-only không có campaign để khớp nên
   bước ghim tự bỏ qua.
3. **Hướng dẫn** — đọc block `HƯỚNG DẪN LẤY MÃ`: chữ + ảnh. Campaign
   `TRỰC TIẾP` có domain trong chữ; campaign `TÌM KIẾM TỪ KHOÁ` giấu keyword và
   domain trong ảnh → OCR (rapidocr, downscale 800 px, hai lượt: strip bước 1–4
   trước, screenshot sau) rồi cache theo `campaign_id`.
4. **Xác minh sponsor** — mọi domain ứng viên được fetch song song (4 một lô,
   giữ thứ tự OCR); chỉ domain có `/widget/…?key=` mới được chọn. Key + kiểu
   referrer (`ref_domain_list` rỗng → điều hướng trần; danh sách Google → phải
   có referrer Google) lưu vào `data/campaigns.json`.
5. **Quest sponsor** — tab mới, UA mobile, viewport 390×844, touch, chặn
   `disable-devtool` + media/font, `Page.bringToFront` + focus emulation (tab
   background bị throttle timer, countdown 70 s sẽ trôi thành 10 phút).
   Bấm `LẤY MÃ`, chờ hết bước 1, reload, bấm lại, đọc `Mã KM: XXXXXX`.
6. **Điền mã** — set `input[name=password]` + dispatch `input`/`change`.
7. **Captcha** — click anchor, nếu audio challenge mở thì tải clip, whisper.cpp
   giải, điền `audio-response`, verify; token dài > 50 ký tự được chấp nhận.
8. **Chốt** — POST chính form của trang tới `{api}/links/get-link-info`; đọc
   `url`/`link` trong JSON. Không navigate, không race với nút của trang.
9. **Cache mã** — chỉ mã đã tạo ra destination mới được ghi
   `campaign_id → code`; mã bị từ chối (`Mã không hợp lệ`, `Sai url`) bị xoá và
   harvest lại.

## 5. API

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
| GET | `/api/v1/links` | snapshot bảng trạng thái |
| GET | `/api/v1/events` | SSE realtime (EventSource) |
| GET | `/status` | trang bảng trạng thái realtime |

Envelope giống `service/app.py`: `status`, `url`, `destination_url`, `provider`,
`cached`, `elapsed_ms`, `job_id`, `error`. Lỗi trả `{"detail": "..."}` với
400 / 401 / 404 / 429 / 501.

- `401` khi đặt `API_KEY` mà thiếu/sai `x-api-key`, `Authorization: Bearer`, `?key=`.
- `429` khi hàng đợi đầy.
- `501` cho provider khác Link4M — dùng `server-rs/` cho BBMKTS/GTRAFFIC/LAYMA/
  TRAFFICVN/OCTOLINK.
- `wait` nhận `1/true/yes/on` và `?wait` trần.

Ví dụ:

```bash
curl -s -X POST localhost:8080/api/v1/bypass \
  -H 'content-type: application/json' \
  -d '{"url":"https://link4m.net/go/2kCcIqn","wait":true}'
# → {"status":"success","destination_url":"https://...","provider":"link4m",...}
```

### 5.1 Bảng trạng thái realtime

`GET /status` là một trang HTML nhúng trong binary, không cần build frontend.
Mỗi request thành một dòng `queued → running → success | failed`, kèm link
đích, provider, cache, thời gian. Dữ liệu đẩy qua `/api/v1/events` (SSE,
snapshot đầu + từng thay đổi); trang tự fallback poll `/api/v1/links` 5 s/lần
khi SSE bị chặn. Giữ 500 link gần nhất trong `data/links.json`; hàng đợi nằm ở
`data/queue.json` và được đẩy lại sau restart (`QUEUE_RESUME=0` để tắt).

Có `API_KEY` thì mở `/status?key=<key>`; endpoint JSON/SSE cũng nhận `?key=`.

## 6. Cấu hình

| Biến | Default | Ý nghĩa |
|---|---|---|
| `HOST` / `PORT` | `0.0.0.0` / `8080` | bind |
| `API_KEY` | rỗng | bật auth |
| `WORKERS` | `2` | số Chrome song song; mỗi worker ~1.3–1.8 GB. `WORKERS=auto` tự tính từ `MemAvailable` (Linux), nơi khác fallback 1 |
| `MAX_QUEUE` | `100` | vượt → 429 |
| `MAX_BATCH` | `50` | số URL tối đa mỗi `/api/v1/batch` (1–500) |
| `BATCH_CONCURRENCY` | `max(4, WORKERS)` | số request batch chạy song song (1–64) |
| `PROXY_LIST` | rỗng | danh sách proxy inline, phân tách bởi dấu phẩy/xuống dòng |
| `PROXY_FILE` | `data/proxies.txt` | file proxy khi không đặt `PROXY_LIST`; tự reload khi file đổi (mtime/size) |
| `PROXY_ROTATE` | `0` | `1` = đổi IP sau **mỗi job** (relaunch Chrome, ~5 s) |
| `PROXY_ROTATE_AFTER` | `4` | tự đổi exit sau N lượt thành công khi pool có >1 proxy; `0` tắt |
| `PROXY_COOLDOWN` | `300` | giây một exit lỗi bị loại khỏi vòng xoay |
| `JOB_TIMEOUT` | `480` | giây cho một lượt flow (quest 120 s + captcha) |
| `CACHE_ENABLED` / `CACHE_TTL` | `true` / `21600` | cache theo `provider:alias` |
| `CACHE_FILE` | `data/native_cache.json` | cache bền qua restart |
| `QUEUE_FILE` | `data/queue.json` | job chờ, sống qua restart |
| `LINKS_FILE` | `data/links.json` | 500 dòng bảng trạng thái gần nhất |
| `QUEUE_RESUME` | `true` | `0` = không replay job chờ sau restart |
| `QUEUE_RESUME_RUNNING` | `true` | `0` = job đang chạy lúc crash đánh `failed` |
| `L4M_CODE_TTL` | `900` | giây sống của mã sponsor đã chứng minh |
| `L4M_CODE_FILE` | `data/codes.json` | cache mã theo campaign |
| `L4M_CAMPAIGN_CACHE` | `data/campaigns.json` | cache sponsor/key/referrer theo campaign |
| `L4M_CAMPAIGN` | rỗng | buộc một campaign id (debug/repro) |
| `L4M_CODE` | rỗng | truyền mã có sẵn, bỏ qua quest |
| `L4M_HEADLESS` | `1` khi không có `DISPLAY` | **đặt `0`** khi có Xvfb |
| `CHROME_BIN` | tự dò | `google-chrome`, `chromium`, `/opt/google/chrome/chrome` |
| `CHROME_PROFILE` | `data/chrome-profile` | profile gốc; worker > 1 copy sang `-w<N>` |
| `L4M_PYTHON` / `L4M_OCR` | `.venv/bin/python` / `tools/ocr.py` | sidecar OCR |
| `L4M_TESSERACT` | `tesseract` | OCR fallback khi sidecar chết/thiếu |
| `OCR_URL` | rỗng | OCR server ngoài (multipart) ưu tiên hơn sidecar và tesseract |
| `OCR_TIMEOUT` | `30` | giây timeout OCR (probe 5 s, mỗi ảnh 6 s, widget refs 4 s) |
| `OCR_LANGUAGE` | rỗng | ngôn ngữ tesseract (rỗng = mặc định; `L4M_TESSERACT_LANG` ưu tiên hơn) |
| `L4M_OCR_SERVE` | `1` | giữ tiến trình RapidOCR thường trú (nạp model một lần); `0` = tắt |
| `OCR_SERVE_TIMEOUT` | `90` | giây chờ một request OCR qua sidecar thường trú (10–300) |
| `L4M_OCR_CACHE` | `data/ocr-cache.json` | cache bền theo campaign id + hash ảnh (200 entry) |
| `L4M_PREWARM` | `1` | worker giữ sẵn một Chrome boot khi idle; `0` tắt |
| `CHROME_FLAGS` | rỗng | flag thêm vào lệnh launch Chrome |
| `WHISPER_MODEL` | `models/ggml-tiny.en.bin` | model ASR local (bỏ qua khi có `ASR_URL`) |
| `WHISPER_MODEL_URL` | HuggingFace tiny.en | nguồn tải khi thiếu model |
| `ASR_THREADS` | `2` | thread whisper local |
| `ASR_URL` | rỗng | bật ASR remote; bare host tự thêm `/inference`, path cụ thể giữ nguyên |
| `ASR_LANGUAGE` | `en` | ngôn ngữ gửi kèm request ASR remote |
| `ASR_TIMEOUT` | `90` | giây timeout request ASR remote (tối thiểu 5) |
| `RC_SOLVER_CMD` | rỗng | solver reCAPTCHA v2 ngoài; ví dụ `.venv/bin/python /path/recaptcha-vm/solve_service.py`. Rỗng = chỉ dùng audio trong page |
| `RC_SOLVER_SUBCOMMAND` | rỗng | chèn trước args solver, ví dụ `solve` cho `window-vm.exe` |
| `RC_SOLVER_SITEKEY` | rỗng | sitekey dự phòng khi page không có `data-sitekey` |
| `RC_SOLVER_MODEL` | `tiny.en` | model whisper của solver ngoài |
| `RC_SOLVER_ROUNDS` | `4` | số vòng anchor→reload→audio của solver ngoài (1–12) |
| `RC_SOLVER_TIMEOUT` | `180` | giây chờ solver ngoài (30–900) |
| `RUST_LOG` | `l4m_engine=info,engine=info` | mức log |

## 6.1 Proxy — phá giới hạn IP

Link4M và trang sponsor rate-limit theo IP: sau vài captcha từ một địa chỉ, audio
challenge bắt đầu fail và campaign biến mất. Engine có pool proxy, mỗi worker
một exit. `PROXY_ROTATE=1` đổi sau mỗi job; mặc định `PROXY_ROTATE_AFTER=4`
đổi exit sau 4 lượt thành công khi pool có nhiều hơn một proxy. Audio bị Google
báo `automated queries` / `try again later` cũng đánh dấu exit đó cooldown.

Định dạng mỗi dòng (hoặc mỗi mục trong `PROXY_LIST`):

```
host:port
user:pass@host:port
http://user:pass@host:port
host:port:user:pass
socks5://user:pass@host:port
socks5h://host:port
```

HTTP và SOCKS5 đều đi qua relay loopback. SOCKS5 được relay tự bắt tay
(no-auth hoặc user/pass) và nói chuyện trực tiếp với đích; request HTTP tuyệt
đối được đổi về origin-form trước khi gửi. Với proxy bật, Chrome còn bị khoá
WebRTC UDP và QUIC để không lộ IP thật ra ngoài tunnel.

`PROXY_FILE` được đọc lại khi mtime/size đổi: thêm hoặc thay exit không cần
restart. File bị editor cắt rỗng giữ nguyên pool cũ thay vì xoá sạch.

Chrome không nhận credential trong `--proxy-server`, nên engine dựng một relay
127.0.0.1 cho mỗi session: Chrome → relay → proxy thật, relay chèn
`Proxy-Authorization`. Relay chết cùng session, không mở ra ngoài loopback.

```bash
PROXY_LIST='user:pass@1.2.3.4:8000,5.6.7.8:3128' PROXY_ROTATE=1 \
  L4M_HEADLESS=0 ./target/release/l4m-engine --once https://link4m.org/go/<alias>
```

Exit lỗi (`cdp`, `browser`, `timeout`) bị đánh dấu cooldown 300 s; exit thành
công được xoá cooldown. Khi tất cả đang cooldown, engine vẫn dùng entry cũ nhất
thay vì dừng — một exit xấu vẫn hơn không có exit.

Đo trên box này: Chrome thật đi qua relay, log upstream ghi
`CONNECT link4m.net:443`, `CONNECT www.google.com:443`, quest + captcha chạy
bình thường.

## 7. Cache mã sponsor

Mã `Mã KM` do widget phát **theo campaign**, không theo visitor: cùng một
campaign phục vụ nhiều alias và cùng một mã. Vì vậy sau khi một mã mở được
destination, engine ghi `campaign_id → code` và các alias sau trên campaign đó
bỏ qua toàn bộ quest (tiết kiệm ~2–3 phút/lượt).

- Chỉ mã **đã chứng minh** mới vào cache (`put` sau khi có destination).
- TTL `L4M_CODE_TTL` (mặc định 900 s); hết hạn thì harvest lại.
- Single-flight: `lock_for(campaign)` — nhiều job cùng campaign chỉ chạy một
  quest, các job còn lại chờ rồi đọc cache.
- Mã bị từ chối → `invalidate(campaign)`, xoá `self.code`, harvest lại trong
  cùng job.
- Sponsor trong cache chết (quest báo `widget`) → entry campaign bị xoá khỏi
  `data/campaigns.json`; job sau chạy lại discovery và có thể chọn domain khác,
  không kẹt vào sponsor cũ.

## 8. RAM, worker và vòng đời Chrome

Box 3.7 GB từng bị OOM vì Chrome sống sót sau khi engine bị `timeout` giết.
Đã xử lý ba lớp:

1. Chrome chạy trong session riêng (`setsid`); `Drop` gửi `SIGKILL` vào cả
   process group.
2. `chrome::sweep()` lúc khởi động: quét `/proc`, chỉ giết Chrome **orphan**
   (ppid = 1 hoặc cha không còn là `l4m-engine`) có `--user-data-dir` dưới
   `data/`. Engine khác đang chạy không bị đụng.
3. systemd `KillMode=control-group` + `MemoryMax` là lưới ngoài cùng.

Khuyến nghị: `WORKERS=1` trên 4 GB, `WORKERS=2` trên 8 GB. Trên box 3.7 GB đặt
`WORKERS=auto`: engine đọc `MemAvailable` (Linux), `vm_stat` (macOS) hoặc
`GlobalMemoryStatusEx` (Windows), trừ 900 MB cho hệ thống, chia 1.4 GB mỗi
worker, kẹp 1–32. Tab sponsor chặn ảnh/video/font; tab campaign chỉ chặn media
và font (captcha cần ảnh).

## 9. Deploy (systemd + Xvfb)

```bash
sudo useradd -r -m -d /opt/l4m-engine l4m
sudo rsync -a engine-rs/ /opt/l4m-engine/
cd /opt/l4m-engine && ./build.sh

sudo cp deploy/l4m-engine.service /etc/systemd/system/
sudo cp deploy/l4m-engine.env.example /etc/l4m-engine.env
sudo editor /etc/l4m-engine.env

sudo systemctl daemon-reload
sudo systemctl enable --now l4m-engine
journalctl -u l4m-engine -f
```

Unit đã bọc `xvfb-run -a -s "-screen 0 1280x1000x24"` và đặt
`L4M_HEADLESS=0`. Không có display thì widget không render nút và countdown bị
throttle — quest sẽ fail dù mọi thứ khác đúng.

Kiểm tra nhanh sau deploy:

```bash
curl -s localhost:8080/health | jq
curl -s -X POST localhost:8080/api/v1/bypass \
  -H 'content-type: application/json' \
  -d '{"url":"https://link4m.net/go/<alias>","wait":true}' | jq
```

## 10. Giới hạn đã biết

- Campaign đổi theo từng lần fetch; alias có thể rơi vào campaign khác giữa hai
  lần reload. `L4M_CAMPAIGN` dùng để ghim khi cần tái lập.
- Link4M ngừng phục vụ campaign cho một IP sau vài lượt hoàn thành: từ lúc đó
  mọi alias trả trang captcha-only. Engine vẫn lấy được destination (đường tắt
  ở mục 4). Có pool proxy thì tự đổi exit sau `PROXY_ROTATE_AFTER` lượt thành
  công; không có proxy thì không có exit khác để đổi.
- Sponsor không có widget (hoặc widget chết) → probe loại domain đó và thử ứng
  viên kế tiếp; hết ứng viên thì tự lùi về trang captcha-only thay vì trả
  `needs_code`.
- reCAPTCHA audio bị chặn theo IP/profile: reload lấy anchor mới, thử lại trong
  budget. Khi Google trả `automated queries` / `try again later`, engine đánh
  dấu exit proxy đó là xấu và relaunch Chrome sang exit kế tiếp (nếu có pool).
- Job còn trong hàng đợi hoặc đang chạy lúc process chết đều được chạy lại sau
  restart; `QUEUE_RESUME_RUNNING=0` đổi job đang chạy thành `failed` nếu muốn
  tránh chạy đôi một lượt đã qua captcha.
- OCR ưu tiên sidecar RapidOCR; sidecar chết/thiếu thì thử `tesseract`
  (`L4M_TESSERACT`). Thiếu cả hai thì campaign `TÌM KIẾM` không đọc được domain
  từ ảnh (campaign `TRỰC TIẾP` vẫn chạy).
- Một campaign chỉ có một mã tại một thời điểm; mã cũ hết hạn sẽ bị từ chối và
  engine tự harvest lại.
- `engine-rs` có cfg Windows đầy đủ (`taskkill /T`, `CREATE_NEW_PROCESS_GROUP`,
  CIM + PowerShell/pwsh sweep). Bản `--no-default-features` + `ASR_URL` đã
  cross-build thành công `x86_64-pc-windows-gnu` trên Linux, nhưng chưa chạy
  live trên máy Windows thật. Bản mặc định (whisper local) vẫn cần toolchain
  MSVC + Visual Studio Build Tools; cross-check mingw fail ở bindgen của
  `whisper-rs-sys`, không phải code engine. Linux/WSL2 là môi trường đã chạy
  live nhiều nhất.
- ASR remote: đặt `ASR_URL` (whisper.cpp `/inference` hoặc endpoint
  OpenAI-compatible). Audio captcha đi qua endpoint đó thay vì whisper local;
  build `--no-default-features` bỏ hẳn whisper.cpp/cmake/model.
