# Solver reCAPTCHA / Turnstile ngoài

## Kết luận nhanh

| Repo | Loại captcha | Dùng được cho Link4M? | Trạng thái |
|---|---|---|---|
| `kaduc966-a11y/recaptcha-vm` | reCAPTCHA v2 (audio + image) | Có. Có sẵn mode `link4m`, sitekey trùng page | Đã nối qua `RC_SOLVER_CMD` |
| `kaduc966-a11y/cloudflare-solver-for-chrome` | Cloudflare Turnstile | Không. Link4M dùng reCAPTCHA v2, không có Turnstile | Không nối |

Link4M render widget `g-recaptcha` với sitekey
`6LcQsTQgAAAAADNQ_pCfukfvS0i9lk4oJTVSs5bZ`; sponsor widget cũng chỉ là
what-on + quest, không có Turnstile. Vì vậy `cloudflare-solver-for-chrome`
không có chỗ cắm trong flow hiện tại. Giữ nó ngoài repo để khỏi kéo BoringSSL
+ VM Turnstile vào một đường không bao giờ chạy.

## recaptcha-vm — cách nối

Engine không copy code của solver. Nó gọi solver như một tiến trình ngoài,
lấy token ở stdout, rồi tiêm token vào đúng page đang mở. Page vẫn là session
Link4M của engine, nên bước POST cuối không đổi.

```
RC_SOLVER_CMD=".venv/bin/python /opt/recaptcha-vm/solve_service.py"
RC_SOLVER_MODEL=tiny.en
RC_SOLVER_ROUNDS=4
RC_SOLVER_TIMEOUT=180
```

- `RC_SOLVER_CMD` rỗng = tắt hoàn toàn, chỉ dùng audio trong page.
- Engine đọc sitekey từ `#captcha-html-wrapper[data-sitekey]` hoặc widget đầu
  tiên; `RC_SOLVER_SITEKEY` là fallback.
- Solver chạy song song với audio trong page. Bên nào ra token trước thì dùng;
  bên còn lại bị abort, child process bị kill theo `kill_on_drop`.
- Solver lỗi/timeout → fallback audio trong page, không làm fail job.

### Cài trên Linux

```bash
git clone https://github.com/kaduc966-a11y/recaptcha-vm /opt/recaptcha-vm
cd /opt/recaptcha-vm
python3 -m venv .venv
.venv/bin/pip install curl_cffi faster-whisper "av==18.1.1"
```

`av==18.1.1` là pin bắt buộc với `faster-whisper 1.2.1`: bản 19 bỏ tham số
`metadata_errors` mà `faster_whisper/audio.py` vẫn truyền, làm transcribe chết
với `open() got an unexpected keyword argument 'metadata_errors'`.

Kiểm tra solver độc lập:

```bash
.venv/bin/python solve_service.py \
  --url https://link4m.net/go/<alias> \
  --sitekey 6LcQsTQgAAAAADNQ_pCfukfvS0i9lk4oJTVSs5bZ \
  --model tiny.en --rounds 4
```

Stdout chỉ có token; log đi stderr. Token sống ~120 s, dùng ngay.

### Dùng `window-vm.exe` (Windows)

Build từ `window-vm/` hoặc dùng binary có sẵn, rồi:

```
RC_SOLVER_CMD=C:\rc\window-vm.exe
RC_SOLVER_SUBCOMMAND=solve
RC_SOLVER_MODEL=base.en
```

Engine chèn `solve --url ... --sitekey ... --model ... --rounds ...` sau
`RC_SOLVER_CMD`, đúng cú pháp CLI của `window-vm`.

## Bằng chứng đã chạy

- Solver độc lập, IP trực tiếp: mint token reCAPTCHA v2 cho Link4M, dài 2212
  ký tự, `userverify 200`, `RC_STEP done token=true`.
- Engine live, headful qua Xvfb, campaign `m.rulobet320.com`:
  - quest 2 bước harvest mã `NCTiGD`;
  - captcha trong page trả token trước solver ngoài (910 ms);
  - destination `https://dash.nvnmc.cloud/earn/callback/...`;
  - `total_ms=156774`, `page_ms=10944`, `code_ms=144196`, `finish_ms=723`.
- Solver ngoài là đường dự phòng khi audio trong page bị Google chặn theo IP;
  nó không bắt buộc cho mọi job.

## Giới hạn

- `solve_service.py` Face A không có proxy plumbing: token mint bằng IP của
  máy chạy solver. Token gắn sitekey + hostname, không gắn IP, và engine tiêm
  vào page session của mình; nhưng nếu Link4M chặn IP đó ở tầng page thì vẫn
  cần page tải được trước.
- Solver ngoài không dùng mode `--mode link4m` trong tích hợp này; engine tự
  POST bằng session của page. Mode đó chỉ hữu ích khi chạy solver như một
  bypass độc lập.
- `cloudflare-solver-for-chrome` cần build BoringSSL + toolchain Rust pinned;
  chỉ nối khi flow gặp Turnstile thật (ví dụ sponsor page đổi widget).
