# Mục lục tài liệu

| File | Nội dung | Đối tượng |
|---|---|---|
| [`../README.md`](../README.md) | Tổng quan toàn repo, trạng thái thành phần, quickstart, API, env, bằng chứng live, giới hạn | Mọi người |
| [`AI_HANDOFF.md`](AI_HANDOFF.md) | Brief dán vào context AI khác: sự thật dự án, hợp đồng, giọng nói, checklist | Người bàn giao cho AI |
| [`API_DOCUMENTATION.md`](API_DOCUMENTATION.md) | API bản Python cũ (FastAPI) | Dev legacy |
| [`TEST_INFRA.md`](TEST_INFRA.md) | Hạ tầng test Python, phân tầng test | Dev legacy |
| [`TEST_READY.md`](TEST_READY.md) | Trạng thái sẵn sàng test | Dev legacy |
| [`DISCORD_BOT_DEPLOY.md`](DISCORD_BOT_DEPLOY.md) | Deploy bot Discord | Ops |
| [`README_PYTHON_LEGACY.md`](README_PYTHON_LEGACY.md) | README bản Python gốc | Dev legacy |
| [`UNIFIED_DISPATCH.md`](UNIFIED_DISPATCH.md) | Thiết kế dispatch hợp nhất | Dev |
| [`../engine-rs/README.md`](../engine-rs/README.md) | Engine native Rust: flow, env, deploy, giới hạn | Dev/Ops |
| [`../engine-rs/docs/SCALE.md`](../engine-rs/docs/SCALE.md) | Công thức dung lượng, nút thắt, scale ngang | Ops |
| [`CAPTCHA_SOLVERS.md`](CAPTCHA_SOLVERS.md) | Solver reCAPTCHA ngoài, đánh giá Turnstile | Dev/Ops |
| [`REMOTE_VPS.md`](REMOTE_VPS.md) | Chạy engine trên Spaces/Codespaces/VPS, client từ xa | Ops |
| [`../server-rs/README.md`](../server-rs/README.md) | Façade HTTP đa provider | Dev/Ops |
| [`../legacy/README.md`](../legacy/README.md) | Mã cũ đã dời; không dùng cho production | Tham khảo |
| [`archive/`](archive/) | Báo cáo nghiên cứu, kế hoạch, tài liệu lịch sử | Tham khảo |

Quy ước:

- Tài liệu đang dùng nằm trong `docs/`, tài liệu lịch sử nằm trong
  `docs/archive/`, không sửa trừ khi cần đối chiếu.
- File cấu hình tool cá nhân (rules, chat history) nằm trong `_local/` và
  không được commit.
- Mọi đường dẫn trong tài liệu tính từ thư mục gốc repo.
