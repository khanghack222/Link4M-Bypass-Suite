# Chạy engine trên sandbox miễn phí, máy local chỉ gửi lệnh

Engine là HTTP service độc lập (`/api/v1/bypass`, `/health`). Máy 3.7 GB chỉ
cần `curl` hoặc `ssh`; Chrome + whisper chạy trên box khác.

## Chọn nơi không cần thẻ

| Nơi | Không cần thẻ | Free tier | RAM | Thức 24/7 | Ghi chú |
|---|---|---|---|---|---|
| **GitHub Actions (batch)** | ✔ | 4 vCPU / 16 GB mỗi job, repo public không giới hạn phút | 16 GB | chạy theo cron 6 h | **Khuyến nghị hiện tại**. Xử lý danh sách link, kết quả commit lại repo |
| **Colab / Kaggle / SageMaker** | ✔ | VM CPU 12–16 GB, phiên ~12 h | 12–16 GB | ✘ (chạy lại mỗi phiên) | Dựng engine + cloudflared tunnel, có URL public, hợp test headful |
| **GitHub Codespaces** | ✔ | 120 core-hours/tháng | 8 GB | ✘ | 2-core ≈ 60 giờ/tháng, sleep 30 phút |
| Hugging Face Spaces | ✘ (Pro) | — | — | — | Free tier đã siết về Pro, bỏ |
| Oracle Cloud Always Free | ✘ cần thẻ verify | 4 OCPU / 24 GB | 24 GB | ✔ | Rẻ nhất về RAM nhưng chặn ở bước thẻ |
| Fly.io / Koyeb / Render free | — | 256–512 MB | — | — | Không đủ cho Chrome |

RAM thực tế 1 worker: Chrome headful ~700 MB + whisper tiny ~200 MB + OCR
sidecar ~145 MB ≈ **1.1–1.5 GB**. Spaces 16 GB thoải mái `WORKERS=1`; đừng đẩy
`WORKERS` cao vì chỉ có 2 vCPU.

## GitHub Actions batch (khuyến nghị, không cần thẻ)

Runner GitHub: 4 vCPU / 16 GB, Chrome cài sẵn, repo public không giới hạn phút.
Đây là chỗ duy nhất free mà mạnh hơn máy này nhiều lần.

1. Thêm link vào `data/batch.txt` (mỗi dòng một URL) rồi commit.
2. Workflow `.github/workflows/batch.yml` chạy lúc 23 phút mỗi 6 giờ
   (hoặc bấm tay):

```bash
gh workflow run batch
gh run watch
```

3. Kết quả: `data/batch-results.jsonl` được commit lại repo, log ở
   `data/batch-engine.log`, artifact `batch-results` trong run.

Cách hoạt động: workflow build engine (cache Rust + model whisper), cài
`xvfb`, chạy `deploy/remote/batch-run.sh` — script bật engine loopback, POST
từng URL vào `/api/v1/bypass`, ghi JSONL. Một link mất ~2–3 phút (quest 75 s
là timer của site), nên một job 5,5 h xử lý được ~100 link.

Giới hạn: runner bị xoá sau job nên queue/board không sống qua lần chạy; muốn
giữ thì commit `data/` như trên. Job tối đa 6 h.

## Colab / Kaggle / SageMaker (phiên ~12 h, có URL public)

Không cần thẻ, VM CPU 12–16 GB. Dùng khi cần chạy headful liên tục vài giờ
hoặc debug quest.

Bước một lần: tạo release có binary sẵn để phiên sau khỏi build lại:

```bash
gh workflow run release -f tag=engine-latest
```

Trong notebook:

```python
!git clone https://github.com/khanghack222/Link4M-Bypass-Suite.git /content/l4m
!bash /content/l4m/deploy/remote/colab-start.sh
```

Script cài Chrome + Xvfb + cloudflared, tải tarball release, dựng engine và
in ra:

```
public  : https://<random>.trycloudflare.com
api key : <random>
```

Trên laptop:

```bash
export L4M_REMOTE=https://<random>.trycloudflare.com
export L4M_API_KEY=<random>
./scripts/remote-l4m.sh health
./scripts/remote-l4m.sh solve https://link4m.net/go/2kCcIqn
```

Giữ cell chạy. Colab free ngắt sau ~12 h (hoặc sớm hơn nếu idle lâu); chạy
lại hai dòng là có tunnel mới. Tunnel URL đổi mỗi phiên. Kaggle/SageMaker
cùng script, cùng cách.

## Hugging Face Spaces

Free tier giờ chỉ còn cho Pro. `Dockerfile` ở gốc vẫn dùng được nếu có Pro
hoặc tự host Docker; với tài khoản free thì bỏ qua mục này.

## GitHub Codespaces — sandbox code (không cần thẻ)

Đây là chỗ để **code và test**, không phải service treo 24/7. Repo có sẵn
`.devcontainer/` nên Codespace tự cài Chrome, Xvfb, Rust, RapidOCR, model
whisper và build sẵn engine.

```bash
gh codespace create -R <owner>/Link4M-Bypass-Suite -m basicLinux32gb
gh codespace code -c <name>
```

Lần tạo đầu chạy `postCreateCommand` ~5–8 phút. Sau đó trong terminal của
Codespace:

```bash
Xvfb :99 -screen 0 1280x1000x24 -ac &
export DISPLAY=:99
cd engine-rs
WHISPER_DONT_GENERATE_BINDINGS=1 PATH="$PWD/../.venv/bin:$PATH" cargo test
./target/release-fast/l4m-engine --once https://link4m.net/go/<alias>
```

Máy này chỉ mở VS Code nối vào Codespace; mọi thứ nặng chạy bên kia.

Giới hạn free: 120 core-hours/tháng (2-core ≈ 60 giờ), sleep sau 30 phút
không tương tác, `gh codespace ssh` đánh thức. Không dùng để treo 24/7 — việc
đó để workflow `batch` lo.

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
