# Link4M engine image: Chrome + Xvfb + whisper, no host dependencies.
#
#   docker build -t l4m-engine .
#   docker run -d --shm-size=1g -p 7860:7860 \
#     -e API_KEY=change-me -e WORKERS=1 l4m-engine
#
# The browser needs more than the default 64 MB of /dev/shm, hence --shm-size.

FROM ubuntu:24.04 AS build

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git build-essential cmake pkg-config \
    && rm -rf /var/lib/apt/lists/*

ENV RUSTUP_HOME=/usr/local/rustup CARGO_HOME=/usr/local/cargo
RUN curl -fsSL https://sh.rustup.rs | sh -s -- -y --profile minimal
ENV PATH=/usr/local/cargo/bin:$PATH

WORKDIR /src
COPY engine-rs ./engine-rs
RUN cd engine-rs \
    && WHISPER_DONT_GENERATE_BINDINGS=1 cargo build --release \
    && mkdir -p /out/models \
    && cp target/release/l4m-engine /out/l4m-engine \
    && cp -r tools /out/tools \
    && curl -fL --retry 3 \
       https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin \
       -o /out/models/ggml-tiny.en.bin

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl xvfb x11-utils \
      python3 python3-venv python3-pip \
      fonts-dejavu-core libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
      libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
      libgbm1 libasound2t64 libpango-1.0-0 libcairo2 libatspi2.0-0 \
    && install -d -m 0755 /etc/apt/keyrings \
    && curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
       -o /etc/apt/keyrings/google-chrome.asc \
    && echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.asc] \
https://dl.google.com/linux/chrome/deb/ stable main" \
       > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /app/.venv \
    && /app/.venv/bin/pip install --no-cache-dir --upgrade pip \
    && /app/.venv/bin/pip install --no-cache-dir \
       rapidocr_onnxruntime opencv-python-headless pillow

WORKDIR /app
COPY --from=build /out/l4m-engine /app/engine-rs/target/release/l4m-engine
COPY --from=build /out/tools /app/engine-rs/tools
COPY --from=build /out/models /app/engine-rs/models

ENV HOST=0.0.0.0 \
    PORT=7860 \
    WORKERS=1 \
    L4M_HEADLESS=0 \
    L4M_PREWARM=1 \
    L4M_OCR_SERVE=1 \
    WHISPER_MODEL=models/ggml-tiny.en.bin \
    RUST_LOG=engine=info \
    L4M_DIR=/app

COPY deploy/remote/run-foreground.sh /app/run-foreground.sh
RUN chmod +x /app/run-foreground.sh

EXPOSE 7860
ENTRYPOINT ["/app/run-foreground.sh"]
