# legacy/ — mã cũ, không dùng cho triển khai mới

Thư mục này chứa mã đã được thay thế bởi `engine-rs/` hoặc `server-rs/`. Mục
đích là giữ tham chiếu lịch sử, **không phải** để chạy production.

Quy tắc:

- Không import từ `legacy/` vào code mới.
- Không sửa trừ khi có yêu cầu cụ thể; nếu sửa, ghi lý do trong commit.
- Đường dẫn trong các script ở đây có thể là Windows cũ và đã lỗi thời.

## Nội dung

| Đường dẫn | Nguồn gốc | Ghi chú |
|---|---|---|
| `api_server_slim.py` | root | Bản API FastAPI rút gọn; chạy độc lập, không được `server-rs` gọi |
| `scripts/` | `scripts/` | `decode_link.py`, `final_bypass_100.py`, `shortlink_factory.py` — công cụ rời |
| `windows/` | root + `scripts/` | `.bat`, `.vbs`, `.ps1`, `Launcher.cs` — build/chạy trên Windows |
| `tools/` | `tools/` | Script khảo sát DOM, benchmark, solver vendored — dùng để nghiên cứu |

## Thay thế

| Việc | Dùng cái mới |
|---|---|
| Chạy Link4M tự động | `engine-rs/` (`l4m-engine`) |
| API đa provider | `server-rs/` (`bypass-server`) |
| CLI | `l4m-engine --once <url>` hoặc `bypass-server` |
| Build Windows | WSL2 + hướng dẫn trong `README.md` |
| Deploy | `engine-rs/deploy/` hoặc `server-rs/` |

Các userscript và extension Chrome cũ đã bị xoá khỏi repo; xem
`README.md` mục "Trạng thái từng thành phần".
