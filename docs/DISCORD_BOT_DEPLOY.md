# 🤖 Hướng dẫn Triển Khai Discord Bot Bypass (Node.js)

Bot được viết hoàn toàn bằng **Node.js (Discord.js v14)** kết hợp bộ động cơ **Unified Autonomous Bypass Suite (Python Playwright)**.

---

## 1. Cấu hình Biến Môi Trường (Environment Variables)

Khi triển khai lên các dịch vụ Hosting (Render, Railway, VPS, Heroku, v.v.), hãy điền các biến môi trường sau:

| Tên biến | Giá trị mẫu | Mô tả |
| :--- | :--- | :--- |
| `DISCORD_TOKEN` | `a954fe8b53ae4af9495901f07affb5d297afb676ecdbf36aee6ceae580dda2c5` | Token của Bot Discord |
| `CLIENT_ID` | `1182983270556774420` | Application ID của Bot |
| `MAX_CONCURRENT` | `2` | Số lượt bypass tối đa xử lý cùng lúc (tránh quá tải CPU/RAM) |
| `PYTHON_PATH` | `/usr/bin/python3` hoặc bỏ trống | Đường dẫn Python trên máy chủ |

---

## 2. Cách chạy trên Máy chủ / VPS

### Cài đặt môi trường (Linux Ubuntu/Debian):
```bash
# 1. Cập nhật hệ thống & cài Node.js, Python, FFmpeg
sudo apt update && sudo apt install -y nodejs npm python3 python3-pip ffmpeg

# 2. Cài đặt các thư viện Node.js
npm install

# 3. Cài đặt thư viện Python & Playwright
pip install -r requirements.txt
playwright install --with-deps chromium

# 4. Khởi chạy Bot
npm run bot
```

---

## 3. Lệnh sử dụng trong Discord

- **Slash Command**:
  - `/bypass url:https://link4m.net/go/ry3A0` : Vượt link tự động và nhận kết quả embed đẹp mắt kèm nút bấm mở link.
  - `/status` : Kiểm tra tình trạng hoạt động và số lượng link trong hàng đợi.

- **Prefix Command**:
  - `!bypass https://link4m.net/go/ry3A0`
  - `!link4m https://link4m.net/go/ry3A0`
