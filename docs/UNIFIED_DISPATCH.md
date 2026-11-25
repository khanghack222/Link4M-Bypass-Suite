# Unified dispatch — registry, entry points, env

Mọi mặt (CLI, JSON API, Discord bot, menu TUI, service HTTP) đi qua **một** chỗ:
`src/core/runner_registry.execute()`. Bảng provider nằm ở
`src/core/provider_table.py`; shim gọi engine nằm ở `src/core/engine_adapters.py`.
Không mặt nào giữ bảng host riêng nữa.

## Canonical keys

| Key | Host tiêu biểu | Kiểu | Engine |
|---|---|---|---|
| `LINK4M` | link4m.net/.co/.com/.org | browser | `bypass.py` (mặc định) hoặc `link4m_engine.py` khi `L4M_ENGINE=cdp` |
| `BBMKTS` | bbmkts.com, yeumoney.com | browser + pre-flight | `bbmkts_runner.py` |
| `GTRAFFIC` | gtraffic.io, client/direct.gtraffic.io | browser | `gtraffic_runner.py` |
| `LAYMA` | layma.net | browser | `layma_runner.py` |
| `TRAFFICVN` | trafficvn.net/.com | browser | `trafficvn_runner.py` |
| `OCTOLINK` | octolink.vip, link999.*, uptolink.*, linkhuongdan.* | Node | `octolink_runner.js` |
| `DECODE` | — (payload base64 trong URL) | offline | `fast_decode.py` |

`link999` là alias cũ của `OCTOLINK`. Alias được chuẩn hoá qua
`provider_table.PROVIDER_ALIASES` / `canonical_key()`; mọi so sánh mới dùng key
canonical. Host lạ trả `GENERIC` và bị từ chối với `ERR_PROVIDER_UNKNOWN`
(riêng `auto_bypass.py` và `brain.determine_best_engine()` vẫn map
`GENERIC → LINK4M` để giữ hành vi cũ).

## Entry points

```bash
# liệt kê provider, không import engine (không khởi động lại interpreter)
python -m src.bypass_api --list

# chạy một link, engine tự nhận
python -m src.bypass_api --url https://link4m.net/go/2kCcIqn

# ép engine + xuất JSON máy đọc
python -m src.bypass_api --engine OCTOLINK --json --url https://octolink.vip/abc

# npm (script gọi `python` trên PATH — kích hoạt .venv trước)
npm run list
npm run bypass -- --url https://bbmkts.com/go/3p82s --timeout 480
```

`--json` in thêm dòng `__BYPASS_JSON__{...}` sau output engine; menu, bot và
service đọc dòng đó thay vì đọc `destination_url.txt`.

Exit code: `0` thành công, `1` bypass thất bại, `2` thiếu tham số.

## Env

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `L4M_ENGINE` | `cdp` | `cdp` (hoặc bất kỳ giá trị khác) → `link4m_engine.py` qua Chrome CDP; `legacy` → Playwright engine cũ `bypass.py` |
| `L4M_REPO` | thư mục gốc tính từ `__file__` | ghi đè root khi chạy service từ ngoài repo |
| `BYPASS_RUN_ID` | rỗng | tách kết quả giữa các lần chạy song song: `destination_url-<id>.txt`, `last_run-<id>.json` |
| `BYPASS_API_JSON` | `0` | `1` → luôn in `__BYPASS_JSON__` |
| `JOB_TIMEOUT` | `480` | ngân sách mỗi job của service; engine browser cần ≥ 480 s |

## Kết quả

`BypassResult` (`src/core/base_runner.py`) là shape duy nhất:
`success`, `destination_url`, `engine`, `provider`, `stage`, `error_code`,
`error_message`, `duration_ms`, `metadata`. `to_dict()` dùng cho JSON.
Lỗi pre-flight trả `stage="pre_flight"`; Chrome hỏng trả `ERR_BROWSER_CRASH`.

## Node + Chrome cho Turnstile (BBMKTS)

BBMKTS chặn ở Cloudflare Turnstile; `src/core/turnstile_solver.js` là đường
giải chính. Nó cần hai thứ ngoài Python:

```bash
npm install                      # patchright đã khai báo trong package.json
npx patchright install chromium  # hoặc để trống và dùng Chrome hệ thống
```

Solver tự dò Chrome theo thứ tự `CHROME_BIN` → `/usr/bin/google-chrome` →
`/usr/bin/chromium` → `/opt/google/chrome/chrome` → đường dẫn Windows mặc định.
Trên box bị chặn tải browser của patchright, Chrome hệ thống là đủ.

- Node solve đo được **16.7–22.8 s**; budget trong `turnstile_solver.py` là
  **45 s** (25 s cũ cắt ngang cold start và để lại browser mồ côi).
- `get_turnstile_token()` tự chạy trong thread riêng khi phát hiện event loop,
  vì BBMKTS runner đã giữ một sync Playwright context — mở context thứ hai
  trong cùng thread sẽ ném `Sync API inside the asyncio loop`.
- Ocilar cloud API (`api.ocilar.com`) là fallback; box nào chặn IP đó thì bỏ
  qua, solver vẫn chạy bằng Node + Chrome local.
