# Trạng thái thành phần — cái nào mới, cái nào legacy

Tài liệu này là nguồn sự thật duy nhất về việc **được dùng cái gì** và
**được sửa cái gì**. Đọc trước khi thêm tính năng hoặc nhờ AI sửa repo.

## Định nghĩa trạng thái

| Nhãn | Nghĩa |
|---|---|
| **ACTIVE** | Dùng cho triển khai mới. Được thêm/sửa tính năng. |
| **COMPAT** | Giữ để lớp khác gọi. Được sửa nhưng phải giữ hợp đồng (API/stdout/env). |
| **LEGACY** | Không dùng cho triển khai mới. Chỉ sửa khi có yêu cầu cụ thể. |
| **ARCHIVE** | Chỉ đọc, không sửa. |
| **CONTRACT** | Test đóng băng, không được sửa nội dung. |
| **REMOVED** | Đã xoá khỏi repo; lịch sử còn trong git. |
| **LOCAL** | Nằm trong `_local/`, không commit. |

## Bảng thành phần

### Engine và server

| Thành phần | Trạng thái | Entrypoint / ghi chú | Thay thế |
|---|---|---|---|
| `engine-rs/` | **ACTIVE** | `target/{debug,release}/l4m-engine`; engine native Rust tự lái Chrome/CDP, tự chủ Link4M | — |
| `engine-rs/tools/ocr.py` | **ACTIVE** | Sidecar OCR cho hướng dẫn trong ảnh | — |
| `engine-rs/deploy/` | **ACTIVE** | systemd + Xvfb + env mẫu | — |
| `engine-rs/docs/SCALE.md` | **ACTIVE** | Công thức dung lượng, scale ngang | — |
| `server-rs/` | **ACTIVE** | `target/release/bypass-server`; façade HTTP đa provider | — |
| `src/bypass_api.py`, `src/core/` | **COMPAT** | `server-rs` gọi `python -m src.bypass_api`; giữ stdout `__BYPASS_JSON__{...}` | `engine-rs` (chỉ Link4M) |
| `src/cli.py` | **LEGACY** | CLI Python cũ | `l4m-engine --once` / API |
| `auto_bypass.py` | **LEGACY** | Runner Python cũ | `l4m-engine` |
| `api_server.py` | **LEGACY** | FastAPI cũ | `engine-rs` / `server-rs` |
| `service/` | **LEGACY** | Service FastAPI + SQLite + UI cũ | `server-rs` / `engine-rs` |
| `bot_discord.js` | **ACTIVE** (tuỳ chọn) | Bot Discord; deps ở `package.json` | — |

### Dữ liệu và phụ trợ

| Thành phần | Trạng thái | Ghi chú |
|---|---|---|
| `camps_database.json` | **ACTIVE** | `src/core/trainer.py`, `trafficvn_runner.py`, `octolink_runner.js` đọc |
| `data/bot_brain.json`, `data/dead_domains.json` | **ACTIVE** | Dữ liệu runtime của bot/service cũ, giữ nguyên |
| `data/service.db*`, `data/temp/` | **LOCAL** | Runtime, gitignore |
| `proxies.txt` | **ACTIVE** (placeholder) | Chỉ có comment; proxy thật đặt qua env, không commit |
| `requirements.txt` | **ACTIVE** | Deps Python cho engine/sidecar/legacy |
| `package.json`, `package-lock.json` | **ACTIVE** | Deps Node cho bot |
| `Dockerfile` (root) | **LEGACY** | Image Node+Python của bản cũ |
| `deploy/` (root) | **LEGACY** | Docker/systemd/nginx cho `service/` cũ |

### Test

| Thành phần | Trạng thái | Ghi chú |
|---|---|---|
| `tests/test_fast_paths_and_pool.py` | **CONTRACT** | Không sửa |
| `tests/test_r3_cli_api.py` | **CONTRACT** | Không sửa |
| `tests/test_tier5_cli_api.py` | **CONTRACT** | Không sửa |
| `tests/adversarial_cli_api_stress.py` | **CONTRACT** | Không sửa |
| `tests/test_provider_registry.py` | **CONTRACT** | Không sửa |
| Các test `test_tier1..4`, `test_captcha_frame_pick.py`, script `inspect_*` | **LEGACY** | Chạy được, không phải hợp đồng |
| `engine-rs` test nội bộ | **ACTIVE** | 29 test, chạy bằng `cargo test` |
| `server-rs` test nội bộ | **ACTIVE** | 37 test, chạy bằng `cargo test` |

### Tài liệu

| Thành phần | Trạng thái | Ghi chú |
|---|---|---|
| `README.md` | **ACTIVE** | Tổng quan hiện tại |
| `docs/INDEX.md` | **ACTIVE** | Mục lục |
| `docs/COMPONENTS.md` | **ACTIVE** | File này |
| `docs/AI_HANDOFF.md` | **ACTIVE** | Brief cho AI |
| `docs/API_DOCUMENTATION.md` | **LEGACY** | API bản Python |
| `docs/TEST_INFRA.md`, `docs/TEST_READY.md` | **LEGACY** | Test infra bản Python |
| `docs/DISCORD_BOT_DEPLOY.md` | **ACTIVE** | Deploy bot |
| `docs/UNIFIED_DISPATCH.md` | **LEGACY** | Thiết kế dispatch cũ |
| `docs/README_PYTHON_LEGACY.md` | **ARCHIVE** | README bản Python |
| `docs/archive/` | **ARCHIVE** | Báo cáo, kế hoạch, nghiên cứu lịch sử |

### Đã xoá / đã dời

| Thành phần | Trạng thái | Nơi đến |
|---|---|---|
| 5 userscript: `Link4M_Auto_Bypass_Suite.user.js`, `Link4M_Bypass_Promax.user.js`, `link4m_bypass.user.js`, `Link4M_Loader.user.js`, `web_navigator.user.js` | **REMOVED** | Lịch sử git |
| `scripts/bbmkts_bypass.user.js` | **REMOVED** | Lịch sử git |
| `extension/` (Chrome extension thử nghiệm) | **REMOVED** | Lịch sử git |
| `community_bypass.js` (snippet dán console) | **REMOVED** | Lịch sử git |
| `universal_bypass.py` (hardcode `C:\Users\...`, không chạy được) | **REMOVED** | Lịch sử git |
| `api_server_slim.py` | **LEGACY** | `legacy/api_server_slim.py` |
| `scripts/*.ps1`, `scripts/*.bat`, `scripts/Launcher.cs` | **LEGACY** | `legacy/windows/` |
| `scripts/decode_link.py`, `final_bypass_100.py`, `shortlink_factory.py` | **LEGACY** | `legacy/scripts/` |
| `src/core/final_bypass_100.py` (bản trùng của `legacy/scripts/final_bypass_100.py`) | **REMOVED** | Lịch sử git |
| `tools/` (script khảo sát DOM, solver vendored) | **LEGACY** | `legacy/tools/` |
| `.aider*`, `.clinerules`, `.crushrules`, `.crush`, `CONVENTIONS.md`, `AGENTS.md.veta-disabled` | **LOCAL** | `_local/`, gitignore |

## Quy tắc cho người và AI

1. Tính năng mới cho Link4M → `engine-rs/`. Đa provider → `server-rs/`.
2. Không sửa `legacy/`, `docs/archive/`, `docs/README_PYTHON_LEGACY.md` trừ khi
   được yêu cầu rõ ràng.
3. Không sửa 5 file test **CONTRACT**. Sửa code phải giữ chúng xanh.
4. Không xoá `src/` dù là legacy: `server-rs` vẫn gọi `src/bypass_api.py`.
5. Không hồi sinh userscript/extension đã **REMOVED**; nếu cần lại, tạo
   nhánh mới và ghi rõ lý do.
6. File cá nhân đặt trong `_local/`; không commit.
7. Đường dẫn trong tài liệu tính từ thư mục gốc repo, không hardcode máy.
8. Không hardcode API key/token trong code: đọc từ env (`OCILAR_API_KEY`,
   `PASSX_KEY`, `DISCORD_TOKEN`, ...). Key từng lộ trong git phải được thu hồi
   và cấp lại, xoá khỏi code không đủ.
