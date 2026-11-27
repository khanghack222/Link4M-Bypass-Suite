# Chạy engine trên sandbox miễn phí, máy local chỉ gửi lệnh

Engine là HTTP service độc lập (`/api/v1/bypass`, `/health`). Máy 3.7 GB chỉ
cần `curl` hoặc `ssh`; Chrome + whisper chạy trên box khác.

## Chọn nơi không cần thẻ

| Nơi | Không cần thẻ | Free tier | RAM | Thức 24/7 | Ghi chú |
|---|---|---|---|---|---|
| **Hugging Face Spaces** | ✔ | 2 vCPU / 16 GB, CPU basic | 16 GB | ✔ nhờ ping 6 h/lần | **Khuyến nghị**. Docker, có URL công khai, sleep sau 48 h không truy cập |
| **GitHub Codespaces** | ✔ | 120 core-hours/tháng | 8 GB | ✘ (sleep 30 phút, hết giờ là dừng) | 2-core ≈ 60 giờ/tháng; tốt để test, không chạy liên tục |
| **GitHub Actions** | ✔ | 4 vCPU / 16 GB mỗi job | 16 GB | ✘ | Batch một lô link rồi tải artifact; job tối đa 6 h |
| Oracle Cloud Always Free | ✘ cần thẻ verify | 4 OCPU / 24 GB | 24 GB | ✔ | Rẻ nhất về RAM nhưng chặn ở bước thẻ |
| Fly.io / Koyeb / Render free | — | 256–512 MB | — | — | Không đủ cho Chrome |

RAM thực tế 1 worker: Chrome headful ~700 MB + whisper tiny ~200 MB + OCR
sidecar ~145 MB ≈ **1.1–1.5 GB**. Spaces 16 GB thoải mái `WORKERS=1`; đừng đẩy
`WORKERS` cao vì chỉ có 2 vCPU.

## Hugging Face Spaces (khuyến nghị)

Repo đã có `Dockerfile` ở gốc và `.dockerignore`; image tự build engine, Chrome,
Xvfb, RapidOCR, model whisper. Không cần cài gì trên máy.

1. Tạo Space: **New Space → Docker → Blank**, tên `l4m-engine`, public.
2. Đẩy repo lên Space:

```bash
git remote add space https://huggingface.co/spaces/<user>/l4m-engine
git push space main
```

3. Trong **Settings → Variables and secrets**:

| Tên | Giá trị |
|---|---|
| `API_KEY` (secret) | chuỗi dài bất kỳ, bắt buộc vì URL công khai |
| `WORKERS` | `1` |

`app_port` mặc định 7860, Dockerfile đã `EXPOSE 7860`.

4. Chờ build (~10–15 phút), rồi từ laptop:

```bash
export L4M_REMOTE=https://<user>-l4m-engine.hf.space
export L4M_API_KEY=<chuỗi ở trên>
./scripts/remote-l4m.sh health
./scripts/remote-l4m.sh solve https://link4m.net/go/2kCcIqn
./scripts/remote-l4m.sh batch links.txt
```

5. Giữ Space thức: Space free ngủ sau 48 h không có request. Workflow
`.github/workflows/keepalive.yml` ping `/health` mỗi 6 h — thêm secret
`L4M_SPACE_URL` = URL Space trong repo GitHub là xong. Cron của Actions miễn
phí trên repo public.

Lưu ý: URL Space là công khai, nên `API_KEY` không được để rỗng. Không đặt
`HOST` khác `0.0.0.0` trong Space — HF cần container lắng nghe trên cổng 7860.
Mỗi lần push code mới, Space rebuild image (queue vài phút).

## GitHub Codespaces (không cần thẻ, giờ có hạn)

```bash
gh codespace create -R <owner>/Link4M-Bypass-Suite -m basicLinux32gb
gh codespace ssh -c <name>
# trong codespace:
sudo apt-get update && sudo apt-get install -y xvfb
sudo REPO_URL=https://github.com/<owner>/Link4M-Bypass-Suite.git \
  /workspaces/Link4M-Bypass-Suite/deploy/remote/bootstrap.sh
sudo -u vscode L4M_DIR=/workspaces/Link4M-Bypass-Suite \
  /workspaces/Link4M-Bypass-Suite/deploy/remote/run-foreground.sh
```

120 core-hours/tháng = 60 giờ ở máy 2-core. Codespace sleep sau 30 phút không
tương tác; `gh codespace ssh` đánh thức. Hợp để test headful/quest, không hợp
treo 24/7.

## Oracle Cloud (có thẻ, nếu sau này có)

```bash
sudo REPO_URL=https://github.com/khanghack222/Link4M-Bypass-Suite.git \
  /opt/l4m-engine/deploy/remote/bootstrap.sh
```

Script cài Chrome từ repo Google, Xvfb, Rust, RapidOCR, model whisper, build
release, tạo user `l4m`, bật `l4m-xvfb` + `l4m-engine` (loopback 8080). Dùng
`L4M_REMOTE=ubuntu@<ip>` với `remote-l4m.sh`.

## Docker ở bất kỳ đâu

```bash
docker build -t l4m-engine .
docker run -d --shm-size=1g -p 7860:7860 -e API_KEY=change-me l4m-engine
```

`--shm-size=1g` là bắt buộc trên nhiều host: Chrome chết tab khi `/dev/shm`
mặc định 64 MB.

## Vận hành

```bash
journalctl -u l4m-engine -f            # VPS systemd
curl -sS "$L4M_REMOTE/health" -H "x-api-key: $L4M_API_KEY"
```

- `WORKERS` = `(RAM_MB - 900) / 1400`, nhưng không vượt số vCPU.
- Box không có `cmake`/`g++`: build `--no-default-features` và trỏ `ASR_URL`
  sang whisper.cpp server (xem README engine).
- Space free bị rebuild sẽ mất `data/` tạm thời (queue/board nằm trong image
  layer, không persistent). Muốn giữ queue/board lâu dài thì dùng VPS có đĩa.
