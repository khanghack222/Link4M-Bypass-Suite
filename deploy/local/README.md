# Link4M Local Deployment Guide (Low-RAM Linux 3.7GB)

Hướng dẫn triển khai cụm **Link4M Native Engine (Rust CDP)** + **Discord Bot (Node.js)** bền bỉ trên máy chủ Linux tài nguyên thấp (RAM 3.7 GB / 2-4 vCPU).

---

## 1. Tổng quan Kiến trúc

```
+-------------------------------------------------------------------+
| Linux Host (3.7 GB RAM)                                           |
|                                                                   |
|  +----------------------------+      HTTP      +---------------+  |
|  | Discord Bot (Node.js v18+) | -------------> |  l4m-engine   |  |
|  | (bot_discord.js)           | :8080 /bypass  |  (Rust Daemon)|  |
|  +----------------------------+                +---------------+  |
|                |                                       |          |
|                v                                       v          |
|         Discord Gateway                          Headless Chrome  |
|                                                  + Whisper Audio  |
|                                                  + Proxy Rotator  |
+-------------------------------------------------------------------+
```

### Các thông số tối ưu cho máy RAM 3.7GB:
- **`WORKERS=1`**: Giới hạn tối đa 1 instance Chrome chạy đồng thời (~350–500 MB RAM).
- **`L4M_PREWARM=0`**: Khởi động Chrome dạng *lazy* (chỉ mở khi có link cần bypass, không ngâm Chrome chạy ngầm khi rảnh rỗi).
- **`L4M_JOB_RETRIES=3`**: Tự động thử lại 3 lần qua các proxy khác nhau khi gặp audio captcha block hoặc IP rate limit.
- **`PROXY_ROTATE=1`**: Tự động xoay proxy exit sau mỗi lượt bypass để giữ session sạch.
- **`MemoryHigh` / `MemoryMax`**: Giới hạn cgroup systemd để tránh Linux kernel kích hoạt OOM killer tiêu diệt toàn bộ tiến trình.

---

## 2. Phương pháp 1: Khởi động Trực tiếp (Foreground / Script)

Phù hợp cho chạy kiểm thử, debug hoặc chạy trong `tmux` / `screen`.

```bash
# 1. Cấp quyền thực thi
chmod +x deploy/local/start-stack.sh

# 2. Khởi chạy toàn bộ stack
./deploy/local/start-stack.sh
```

**Tính năng tự động của `start-stack.sh`:**
- Tự động kiểm tra Google Chrome / Chromium và model Whisper (`ggml-tiny.en.bin`), tự tải nếu thiếu.
- Tự động phát hiện binary `l4m-engine` (ưu tiên `release-fast`).
- Khởi chạy daemon `l4m-engine` trên cổng `8080`, chờ endpoint `/health` trả lời `200 OK`.
- Khởi chạy `bot_discord.js` và kết nối trực tiếp vào Rust engine daemon.
- Bẫy tín hiệu (Trap SIGINT/SIGTERM): Dọn dẹp an toàn cả engine lẫn Chrome khi nhấn `Ctrl+C`.

---

## 3. Phương pháp 2: Chạy Service Bền bỉ (systemd `--user`)

Phù hợp cho môi trường Production / VPS, tự động chạy lại khi crash (`Restart=always`) và tự động bật khi reboot máy.

> [!IMPORTANT]
> **Bắt buộc dùng `systemctl --user`**:
> Các unit file `l4m-engine.service` và `l4m-bot.service` sử dụng biến `%h` (trỏ tới `$HOME` của user hiện tại). Không chạy với `sudo systemctl` (vì `%h` sẽ bị trỏ nhầm về `/root`). Luôn sử dụng cờ `--user` và kích hoạt `loginctl enable-linger $USER` để service chạy bền bỉ ngay cả khi ngắt phiên SSH.

### Quy trình Kích hoạt 2 Bước:

#### Bước 1: Sao chép các unit file vào thư mục systemd user
```bash
mkdir -p ~/.config/systemd/user
cp deploy/local/l4m-engine.service ~/.config/systemd/user/
cp deploy/local/l4m-bot.service ~/.config/systemd/user/
```

#### Bước 2: Reload daemon và kích hoạt khởi động ngay
```bash
systemctl --user daemon-reload
systemctl --user enable --now l4m-engine.service l4m-bot.service
```

#### Bước Bổ trợ quan trọng (Cho phép chạy nền khi SSH disconnect):
```bash
loginctl enable-linger $USER
```
*(Lệnh này giúp systemd user services tiếp tục chạy ngay cả khi bạn logout phiên SSH).*

---

## 4. Quản lý & Giám sát

### Kiểm tra trạng thái:
```bash
systemctl --user status l4m-engine.service l4m-bot.service
```

### Xem log thời gian thực:
```bash
# Log của Rust Engine
journalctl --user -u l4m-engine.service -f

# Log của Discord Bot
journalctl --user -u l4m-bot.service -f
```

### Dừng hoặc Khởi động lại:
```bash
# Restart cả 2 dịch vụ
systemctl --user restart l4m-engine.service l4m-bot.service

# Dừng dịch vụ
systemctl --user stop l4m-engine.service l4m-bot.service
```

---

## 5. Cấu hình Biến Môi trường (`.env`)

Tạo file `.env` tại thư mục gốc repository (sao chép từ `.env.example`):
```bash
cp .env.example .env
```

Các biến quan trọng:
```ini
# Discord Credentials
DISCORD_TOKEN=your_bot_token_here
CLIENT_ID=your_client_id_here
MAX_CONCURRENT=2

# Engine Integration
L4M_ENGINE_URL=http://127.0.0.1:8080
L4M_API_KEY=
L4M_JOB_RETRIES=3

# Low-RAM Optimization
WORKERS=1
L4M_PREWARM=0
L4M_HEADLESS=1

# Proxy Pool
PROXY_FILE=proxies.txt
PROXY_ROTATE=1
PROXY_COOLDOWN=300
```
