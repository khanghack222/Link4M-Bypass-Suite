# 📖 TÀI LIỆU API HỆ THỐNG GIẢI CAPTCHA (v2.4.0 Omni-Precision)

### 🌐 Thông Tin Cơ Bản & Xác Thực

- **Base URL**: `https://link4m-microservice-api.onrender.com`
- **Interactive Swagger Docs**: `https://link4m-microservice-api.onrender.com/docs`
- **Private API Key**: `sk_sec_fdcad6104ba10090f0b730864b123580`
- **Header xác thực**: `X-API-Key: sk_sec_fdcad6104ba10090f0b730864b123580` (hoặc `Authorization: Bearer <API_KEY>`)

---

### 📌 Danh Sách Endpoints

#### 1. Kiểm tra trạng thái máy chủ (Public)
- **Method**: `GET /health`
- **Response**:
```json
{
  "status": "healthy",
  "ram_used_mb": 94.8,
  "safe_limit": true
}
```

---

#### 2. Giải QCaptcha 9 Ô Hình Học (OpenCV Omni-Precision)
- **Method**: `POST /api/v1/cv/analyze-tiles`
- **Mô tả**: Nhận diện hình học qua Convexity Defects, Circularity, Solidity, ApproxPolyDP.
- **Hình hỗ trợ (`target_shape`)**: `star` (ngôi sao), `circle` (tròn), `triangle` (tam giác), `hexagon` (lục giác), `rectangle` (chữ nhật/vuông), `cross` (chữ thập).
- **Body JSON**:
```json
{
  "tile_urls": [
    "https://example.com/tile_0.png",
    "https://example.com/tile_1.png",
    "https://example.com/tile_2.png",
    "https://example.com/tile_3.png",
    "https://example.com/tile_4.png",
    "https://example.com/tile_5.png",
    "https://example.com/tile_6.png",
    "https://example.com/tile_7.png",
    "https://example.com/tile_8.png"
  ],
  "target_shape": "star",
  "min_confidence": 0.65
}
```
- **Response**:
```json
{
  "target_shape": "star",
  "correct_indices": [2, 7],
  "confidence_map": { "2": 0.98, "7": 0.95 },
  "tiles": [ ... ],
  "elapsed_ms": 145.2,
  "ram_used_mb": 95.0
}
```

---

#### 3. Giải Audio Captcha (DSP Filter + Google Speech + Phonetic Matcher)
- **Method**: `POST /api/v1/audio/transcribe`
- **Mô tả**: Lọc nhiễu dải tần giọng nói (250Hz - 3500Hz), chuẩn hóa âm lượng, phân tích chuỗi số đọc tiếng Anh.
- **Body JSON**:
```json
{
  "audio_url": "https://example.com/audio.mp3",
  "audio_base64": null,
  "language": "en-US",
  "apply_dsp_filter": true
}
```
- **Response**:
```json
{
  "text": "seven two eight four one",
  "digit_text": "72841",
  "raw_text": "seven two eight four one",
  "engine": "google_speech_dsp_enhanced",
  "elapsed_ms": 650.0,
  "ram_used_mb": 95.8
}
```

---

#### 4. Đọc Ảnh Trích Xuất Domain (RapidOCR De-obfuscation)
- **Method**: `POST /api/v1/ocr/resolve-domain`
- **Mô tả**: Đọc text từ ảnh, tự động giải mã chuỗi che giấu ([dot], homoglyphs, text cách dòng).
- **Body JSON**:
```json
{
  "image_url": "https://example.com/screenshot.png",
  "image_base64": null
}
```
- **Response**:
```json
{
  "domains": ["shopeefood.vn", "link4m.com"],
  "raw_text": ["Vào trang shopeefood [dot] vn để lấy mã"],
  "elapsed_ms": 280.0,
  "ram_used_mb": 115.2
}
```

---

#### 5. Giải Cloudflare Turnstile Token
- **Method**: `POST /api/v1/turnstile/solve`
- **Body JSON**:
```json
{
  "url": "https://bbmkts.com",
  "sitekey": "0x4AAAAAAEzmJdRW__FHO9pu",
  "headless": true,
  "timeout_seconds": 25,
  "worker_url": null
}
```
- **Response**:
```json
{
  "status": "success",
  "token": "0.AbCdEf1234567890...",
  "elapsed_seconds": 8.42,
  "engine": "patchright"
}
```

---

### 💻 Mẫu Gọi Code Nhanh (Python Requests)

```python
import requests

API_URL = "https://link4m-microservice-api.onrender.com"
HEADERS = {"X-API-Key": "sk_sec_fdcad6104ba10090f0b730864b123580"}

# Giải 9 ô QCaptcha
def solve_qcaptcha(tile_urls, target="star"):
    res = requests.post(
        f"{API_URL}/api/v1/cv/analyze-tiles",
        json={"tile_urls": tile_urls, "target_shape": target},
        headers=HEADERS
    ).json()
    return res.get("correct_indices", [])

# Giải Audio Captcha
def solve_audio(audio_url):
    res = requests.post(
        f"{API_URL}/api/v1/audio/transcribe",
        json={"audio_url": audio_url, "apply_dsp_filter": True},
        headers=HEADERS
    ).json()
    return res.get("digit_text", "")

# Giải Link4M Shortlink Trực Tiếp (Server-Side Autonomous Microservice)
def bypass_link(shortlink_url: str):
    res = requests.post(
        f"{API_URL}/api/bypass",
        json={"url": shortlink_url, "headless": True},
        headers=HEADERS
    ).json()
    return res.get("destination_url")
```

---

### 🚀 6. Standalone CLI & API Delivery (R3)

#### REST API Endpoint
- **Method**: `POST /api/bypass` (Alias: `POST /api/v1/bypass`)
- **Mô tả**: Tự động vượt link Link4M / shortlink trên máy chủ mà không cần extension hay tương tác từ người dùng.
- **Request Body**:
```json
{
  "url": "https://link4m.net/go/example",
  "headless": true,
  "timeout": 60,
  "proxy": null
}
```
- **Response Success (HTTP 200)**:
```json
{
  "destination_url": "https://final-destination.com/download",
  "time_ms": 1820.5,
  "status": "success",
  "url": "https://link4m.net/go/example"
}
```

#### CLI Command Line Usage
```bash
py -3.11 -m src.cli --url <link4m_url>
# hoặc
python -m src.cli --url https://link4m.net/go/example --headless --timeout 60
```
- **Output (JSON thuần trên stdout)**:
```json
{
  "destination_url": "https://final-destination.com/download",
  "status": "success",
  "time_ms": 1820.5,
  "url": "https://link4m.net/go/example"
}
```

