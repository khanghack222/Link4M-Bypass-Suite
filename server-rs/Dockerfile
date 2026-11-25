# Build context = repository root:
#   docker build -f server-rs/Dockerfile -t bypass-server:rs .

# ---------- stage 1: Rust binary ----------
FROM rust:1-slim-bookworm AS build
WORKDIR /build
COPY server-rs/Cargo.toml server-rs/Cargo.lock ./
RUN mkdir -p src && printf 'fn main() {}\n' > src/main.rs && cargo build --release
COPY server-rs/src ./src
RUN touch src/main.rs && cargo build --release

# ---------- stage 2: runtime with Python engines + Chrome ----------
FROM node:20-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    ffmpeg wget curl gnupg ca-certificates \
    fonts-liberation libasound2 libatk-bridge2.0-0 libatk1.0-0 libc6 \
    libcairo2 libcups2 libdbus-1-3 libexpat1 libfontconfig1 libgbm1 \
    libglib2.0-0 libgtk-3-0 libnspr4 libnss3 libpango-1.0-0 \
    libpangocairo-1.0-0 libstdc++6 libx11-6 libx11-xcb1 libxcb1 \
    libxcomposite1 libxcursor1 libxdamage1 libxext6 libxfixes3 libxi6 \
    libxrandr2 libxrender1 libxss1 libxtst6 lsb-release xdg-utils \
    && wget -q -O /tmp/chrome.deb \
       https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y --no-install-recommends /tmp/chrome.deb \
    && rm -f /tmp/chrome.deb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package*.json ./
RUN npm install --production || npm install

COPY requirements.txt ./
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt \
    && python3 -m playwright install --with-deps chromium

COPY . .
COPY --from=build /build/target/release/bypass-server /usr/local/bin/bypass-server

ENV HOST=0.0.0.0 \
    PORT=8080 \
    L4M_REPO=/app \
    L4M_ENGINE=cdp \
    L4M_HEADLESS=1 \
    PYTHON=/usr/bin/python3 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    NODE_ENV=production

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/health || exit 1

CMD ["bypass-server"]
