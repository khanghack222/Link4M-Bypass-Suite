# Quy mô — server bypass chịu tải lớn

Tài liệu này trả lời một câu: engine hiện tại chịu được bao nhiêu job, và muốn
hơn thì phải thêm gì. Số liệu lấy từ lượt chạy thật ngày 26/11/2026 trên box
3.7 GB, Chrome headful, relay proxy nội bộ.

## 1. Thực đo

| Đường đi | Thời gian thật | Ghi chú |
|---|---|---|
| Captcha-only (Link4M không phục vụ campaign) | 15.3 s / 16.5 s / 39.2 s / 39.4 s | phần lớn là chờ anchor + audio challenge |
| Campaign + quest 1 bước (countdown 70 s) | 153.6 s | OCR + probe + quest + captcha |
| Campaign + quest 2 bước | 179.1 s / 186.4 s | countdown 70 s mỗi bước |

Một worker = một Chrome, chạy tuần tự từng job.

## 2. Công thức dung lượng

```
worker      = clamp((MemAvailable_MB - 900) / 1400, 1, 32)
job/giờ     = 3600 / (thời_gian_job + 5 s overhead)
node/box    = worker (mỗi Chrome một tiến trình riêng)
```

Ví dụ:

| Box | Worker | Captcha-only (~25 s) | Campaign (~160 s) |
|---|---|---|---|
| 3.7 GB | 1 | ~120 job/giờ | ~21 job/giờ |
| 8 GB | 4 | ~480 job/giờ | ~84 job/giờ |
| 16 GB | 10 | ~1200 job/giờ | ~210 job/giờ |

Con số trên là trần lý thuyết khi job đến liên tục; thực tế thấp hơn 10–20%
vì captcha fail, campaign chết, re-roll.

## 3. Nút thắt thật, theo thứ tự

1. **RAM mỗi Chrome** — 1.3–1.8 GB. Đây là trần cứng của một box. Muốn hơn:
   thêm box, không phải thêm worker trên cùng box.
2. **IP** — Link4M ngừng phục vụ campaign cho một IP sau ~4 lượt hoàn thành;
   Google cũng bắt đầu trả challenge khó hơn khi một IP giải quá nhiều audio.
   Mỗi node cần exit riêng, hoặc `PROXY_ROTATE=1` để đổi sau mỗi job.
3. **CPU whisper** — tiny.en 2 thread, mỗi clip 2–10 s. Trên box 4 nhân, quá
   ~4 worker đồng thời thì ASR thành hàng đợi. Tăng `ASR_THREADS` hoặc tách
   node ASR.
4. **Queue trong RAM** — `MAX_QUEUE=100`, mất khi restart. Với tải lớn cần
   hàng đợi bền (Redis/SQLite) nếu không muốn mất job khi deploy.
5. **Timeout tính từ lúc nhận request** — batch lớn hơn số worker sẽ có job
   chờ quá `JOB_TIMEOUT` rồi trả `timeout` dù vẫn được chạy sau đó. Với batch
   dài, dùng `"wait": false` rồi poll `/api/v1/jobs/{id}`, hoặc chia lô nhỏ.

## 4. Kiến trúc scale ngang

Mỗi box một instance, mỗi instance một exit proxy:

```bash
# box N
WORKERS=auto \
PROXY_LIST='user:pass@exit-N:8000' \
PROXY_ROTATE=1 \
L4M_HEADLESS=0 \
./target/release/l4m-engine
```

Đặt nginx/Caddy round-robin trước các instance:

```nginx
upstream l4m {
    least_conn;
    server 10.0.0.11:8080;
    server 10.0.0.12:8080;
    server 10.0.0.13:8080;
}
server {
    listen 80;
    location / { proxy_pass http://l4m; proxy_read_timeout 700s; }
}
```

- API key đặt giống nhau trên mọi node.
- Cache `provider:alias` và cache mã campaign là file local: mỗi node tự
  harvest, không cần chia sẻ. Nếu muốn tối ưu, mount chung `data/` hoặc thay
  bằng Redis.
- Health check: `GET /health` trả `workers`, `cached_links`, `uptime_sec`.
- `BATCH_CONCURRENCY` đặt bằng số worker của node để batch lấp đầy pool.

## 5. Kết luận

- **Cỡ nhỏ/vừa (vài trăm job/ngày, 1–2 box): đủ, chạy được ngay.** API, queue,
  cache, proxy, retry, teardown đều đã có và đã chạy thật.
- **Cỡ lớn (nghìn job/giờ): chưa đủ trên một box.** Code không phải nút thắt —
  RAM/Chrome, IP và CPU ASR mới là. Scale ngang theo mục 4, thêm proxy thật và
  hàng đợi bền là lên được.
- Đừng tăng `WORKERS` quá công thức RAM: box 3.7 GB mà đặt 4 worker sẽ OOM
  hoặc swap, job chậm hơn cả chạy 1 worker.
