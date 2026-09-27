FROM node:20-slim

# Cài đặt Python 3, pip, ffmpeg và các thư viện hệ thống cần thiết cho Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    ffmpeg \
    wget \
    curl \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libc6 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libexpat1 \
    libfontconfig1 \
    libgbm1 \
    libgcc1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libstdc++6 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    lsb-release \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy package specs
COPY package*.json ./
RUN npm install --production

# Cài đặt requirements cho Python và browser headless
COPY requirements.txt ./
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt
RUN python3 -m playwright install chromium

# Copy toàn bộ mã nguồn
COPY . .

# Môi trường chạy
ENV PORT=10000
ENV PYTHONUNBUFFERED=1
ENV PYTHON_PATH=/usr/bin/python3
ENV NODE_ENV=production

EXPOSE 10000

CMD ["node", "bot_discord.js"]
