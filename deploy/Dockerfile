# Build từ gốc repo:  docker build -f deploy/Dockerfile -t linkbypass .
FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    MALLOC_ARENA_MAX=2 \
    OMP_NUM_THREADS=2 \
    HOST=0.0.0.0 \
    PORT=8080

# Chrome + thư viện cho opencv/onnxruntime + sox (giải mã audio) + xvfb
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates wget gnupg sox ffmpeg xvfb \
      libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 libnss3 libatk1.0-0 \
      libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
      libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 \
    && wget -q -O /tmp/chrome.deb \
       https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y --no-install-recommends /tmp/chrome.deb \
    && rm -f /tmp/chrome.deb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY service/requirements.txt service/requirements.txt
RUN pip install --no-cache-dir -r service/requirements.txt

COPY . .

EXPOSE 8080
# Xvfb để Chrome chạy "có màn hình"; L4M_HEADLESS=0 vì đã có display ảo.
ENV L4M_HEADLESS=0
CMD ["xvfb-run", "-a", "--server-args=-screen 0 1280x1000x24", "python", "-m", "service"]
