# Chạy engine trên VPS sandbox, máy local chỉ gửi lệnh

Máy 3.7 GB không cần gánh Chrome. Engine đã là một HTTP service độc lập
(`/api/v1/bypass`, `/health`), nên chỉ cần một box Linux có Chrome + Xvfb +
Rust, rồi từ laptop gọi qua SSH. Không mở port ra internet.

## Chọn nhà cung cấp

| Nơi | Free tier | RAM | Chrome headful | Ghi chú |
|---|---|---|---|---|
| **Oracle Cloud Always Free** | 4 OCPU ARM + 24 GB RAM, vĩnh viễn | 24 GB | Có (Xvfb) | Tốt nhất cho chạy 24/7. Cần thẻ để verify, không bị charge |
| **GitHub Codespaces** | 120 core-hours/tháng (2-core/8 GB) | 8 GB | Có (Xvfb) | Không cần thẻ. Sleep sau 30 phút idle, bật lại ~1 phút |
| **GitHub Actions** | 4 vCPU/16 GB mỗi job, 6 h | 16 GB | Có (Xvfb) | Chỉ hợp batch: chạy một lô link rồi tải artifact, không phải service |
| **Hugging Face Spaces** | 2 vCPU/16 GB CPU basic | 16 GB | Có (Docker) | Sleep sau 48 h không truy cập; Space là public, phải đặt `API_KEY` |
| Fly.io / Koyeb / Render free | 256–512 MB | — | Không | Không đủ cho Chrome + whisper |

Với engine 1 worker: Chrome headful ~700 MB + whisper tiny ~200 MB + OCR
sidecar ~145 MB ≈ **1.1–1.5 GB**. Oracle 24 GB chạy được `WORKERS=3` trên 4
OCPU; Codespaces 8 GB để `WORKERS=1` cho quest ổn định.

## Oracle Cloud (khuyến nghị, 24/7)

1. Tạo instance Ampere A1 (4 OCPU, 24 GB), Ubuntu 24.04, mở SSH.
2. Cài:

```bash
git clone https://github.com/khanghack222/Link4M-Bypass-Suite.git /opt/l4m-engine
sudo REPO_URL=https://github.com/khanghack222/Link4M-Bypass-Suite.git \
  /opt/l4m-engine/deploy/remote/bootstrap.sh
```

Script cài Chrome từ repo Google, Xvfb, Rust, RapidOCR, tải model whisper,
build release, tạo user `l4m`, và bật hai unit `l4m-xvfb` + `l4m-engine`
(`HOST=127.0.0.1:8080`).

3. Từ laptop:

```bash
export L4M_REMOTE=ubuntu@<ip>
./scripts/remote-l4m.sh health
./scripts/remote-l4m.sh solve https://link4m.net/go/2kCcIqn
```

`remote-l4m.sh` chạy `curl` **trên VPS** qua SSH, nên API không bao giờ lộ ra
ngoài. Muốn dùng trình duyệt/Postman thì mở tunnel:

```bash
ssh -N -L 8080:127.0.0.1:8080 ubuntu@<ip>
curl -sS http://127.0.0.1:8080/health
```

## GitHub Codespaces (không cần thẻ)

```bash
gh codespace create -R <owner>/Link4M-Bypass-Suite -m basicLinux32gb
gh codespace ssh -c <name>
# trong codespace:
sudo apt-get update && sudo apt-get install -y xvfb
sudo REPO_URL=https://github.com/<owner>/Link4M-Bypass-Suite.git \
  /workspaces/Link4M-Bypass-Suite/deploy/remote/bootstrap.sh
# systemd không chạy trong container → dùng runner foreground:
sudo -u vscode L4M_DIR=/workspaces/Link4M-Bypass-Suite \
  /workspaces/Link4M-Bypass-Suite/deploy/remote/run-foreground.sh
```

Codespace sleep sau 30 phút không tương tác; `gh codespace ssh` đánh thức lại.
Dữ liệu `data/` nằm trong workspace nên queue/board sống qua lần sleep.

## GitHub Actions (batch, không phải service)

Workflow `.github/workflows/engine.yml` đã build + smoke check trên
`windows-latest`. Thêm job batch nếu cần chạy một danh sách link trên runner
16 GB: checkout, chạy `bootstrap.sh` (hoặc chỉ `apt-get install xvfb` + Chrome
có sẵn trên runner), `run-foreground.sh`, gọi API nội bộ, upload JSON. Runner
bị xoá sau job — chỉ dùng cho lô một lần.

## Vận hành

```bash
journalctl -u l4m-engine -f            # log
systemctl restart l4m-engine           # restart
curl -sS http://127.0.0.1:8080/health  # trạng thái + stats
```

- `HOST=0.0.0.0` chỉ khi thật sự cần; luôn kèm `API_KEY` dài và một reverse
  proxy có TLS. Mặc định giữ loopback + SSH.
- Đổi `WORKERS` theo RAM: `(RAM_MB - 900) / 1400`, tối đa bằng số vCPU.
- Oracle ARM: Chrome có build arm64 trong repo Google; bootstrap cài đúng gói.
- Nếu box không có `cmake`/`g++`, build `--no-default-features` và trỏ
  `ASR_URL` sang whisper.cpp server (xem README engine).
