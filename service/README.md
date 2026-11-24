# Link Bypass Service — tự host, kiểu vnbypass.com

Dán link khoá → nhận link đích. Chạy nền trên server riêng, có hàng đợi, cache,
API key, UI web và client CLI.

## 1. Thành phần

```
service/
  app.py        API FastAPI + UI (GET /ui)          ← mặt tiền
  worker.py     hàng đợi + worker chạy engine       ← động cơ
  store.py      SQLite (jobs + cache), WAL          ← sổ sách
  providers.py  nhận diện nhà cung cấp + fast-path  ← cửa vào
  config.py     cấu hình từ ENV                     ← bảng điều khiển
  client.py     CLI gọi service                     ← tay sai
  requirements.txt
deploy/
  run.sh              start|stop|restart|status|log (không cần systemd)
  install.sh          cài 1 phát trên server trần (apt + chrome + venv + systemd)
  l4m-bypass.service  systemd unit
  Dockerfile + docker-compose.yml
  nginx-l4m.conf      rate-limit biên
  .env.example
```

Luồng: `POST /api/v1/bypass` → `providers.parse` → cache? → tạo job → `WorkerPool`
→ thread chạy `link4m_engine.bypass_alias` (Chrome CDP) → ghi SQLite → trả link.

## 2. Chạy trên máy này

```bash
cd ~/Link4M-Bypass-Suite
bash deploy/run.sh start      # bật (tự chờ /health)
bash deploy/run.sh status
bash deploy/run.sh log
bash deploy/run.sh stop
```

Mặc định `http://0.0.0.0:8080`. Mở UI: `http://<ip>:8080/ui`.

## 3. Gọi API

```bash
# Chờ tới khi xong rồi trả link (tiện nhất)
curl -s "http://127.0.0.1:8080/api/v1/bypass?url=https://link4m.net/go/2kCcIqn&wait=1"

# Xếp hàng rồi poll
JID=$(curl -s "http://127.0.0.1:8080/api/v1/bypass?url=https://link4m.net/go/2kCcIqn" | jq -r .job_id)
curl -s "http://127.0.0.1:8080/api/v1/jobs/$JID"

# Nhiều link một lần
curl -s -X POST http://127.0.0.1:8080/api/v1/batch \
  -H 'content-type: application/json' \
  -d '{"urls":["https://link4m.net/go/aaa","https://link4m.net/go/bbb"],"wait":true}'
```

CLI:
```bash
.venv/bin/python service/client.py https://link4m.net/go/2kCcIqn
.venv/bin/python service/client.py --base http://1.2.3.4:8080 --key SECRET <url>
```

Kết quả thành công:
```json
{"status":"success","destination_url":"https://...","provider":"link4m",
 "cached":false,"elapsed_ms":200043.9,"job_id":"..."}
```

## 4. Bật bảo vệ (khi mở ra Internet)

```bash
API_KEY=chuoi-bi-mat bash deploy/run.sh restart
# client: -H "X-API-Key: chuoi-bi-mat"  hoặc  ?key=chuoi-bi-mat
```

**Bắt buộc** khi public: đặt `API_KEY`, dựng `nginx-l4m.conf` (rate-limit 20r/m),
và tốt hơn nữa gắn Cloudflare Turnstile ở biên — mỗi lần bypass tốn một Chrome
+ ~3 phút CPU, không chặn thì bị spam cho chết máy.

## 5. Biến môi trường quan trọng

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `PORT` | 8080 | cổng |
| `WORKERS` | 1 | số Chrome song song. **Giữ 1 cho 4GB RAM**; ≥8GB mới tăng |
| `JOB_TIMEOUT` | 240 | giây cho 1 lần bypass |
| `MAX_TRIES` | 2 | số lần thử lại |
| `CACHE_TTL` | 21600 | cache link đích (6 giờ) — cùng alias → cùng đích |
| `MAX_QUEUE` | 300 | chặn ngập hàng đợi (trả 429) |
| `API_KEY` | (rỗng) | rỗng = công khai |
| `L4M_HEADLESS` | 0 | 1 = `--headless=new` khi không có Xvfb |
| `CLEAR_PROXY` | 1 | xoá `*_proxy` khi khởi động (**bắt buộc** với link4m) |

## 6. Vì sao phải đi thẳng, không proxy

Proxy `HTTP_PROXY` của môi trường bị Cloudflare gắn cờ → link4m trả màn
"Just a moment". Engine đã xử lý: `ensure_chrome()` ép `--no-proxy-server` +
`_proxy_free_env()`, và **tự restart Chrome** nếu phát hiện bản đang chạy qua
proxy. Service cũng gọi `clear_proxy_env()` lúc khởi động. Trên server mới chỉ
cần chạy đúng `deploy/run.sh` — không cần cấu hình thêm.

## 7. RAM & độ bền

- Chrome sống giữa các job (`KEEP_BROWSER=1`) cho nhanh, tốn ~300–500MB.
- Box 4GB chỉ nên chạy **1 worker**. Muốn chạy nền lâu dài: `deploy/l4m-bypass.service`
  (systemd tự bật lại khi chết, có Xvfb).
- Job kẹt ở `running` do restart sẽ tự đưa về `queued` lúc khởi động.

## 8. Mở rộng nhà cung cấp

Thêm một mục vào `PROVIDERS` trong `service/providers.py`:

```python
"layma": {"hosts": ("layma.net",), "pattern": re.compile(r"/([A-Za-z0-9_-]+)$"),
          "kind": "browser"},
```

`kind="decode"` cho site giải bằng biến đổi chuỗi (thêm nhánh trong `fast_decode`).
`kind="browser"` thì cần một engine riêng kiểu `link4m_engine` — khai báo trong
`worker._run_job`.
