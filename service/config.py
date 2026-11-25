# -*- coding: utf-8 -*-
"""Cấu hình service đọc từ biến môi trường (mặc định nhẹ cho box 4GB RAM)."""
from __future__ import annotations

import os

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("L4M_REPO") or os.path.dirname(_HERE)

# Engine chọn cho Link4M: "cdp" (Chrome CDP đã kiểm chứng, mặc định service)
# hoặc "legacy" (Playwright tự mở browser).
L4M_ENGINE = os.environ.get("L4M_ENGINE", "cdp").strip().lower()


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def clear_proxy_env() -> None:
    """Bỏ mọi biến *_proxy khỏi tiến trình.

    Cả Cloudflare lẫn patchright đều bị proxy 127.0.0.1:8899 làm hỏng: đi qua
    proxy thì link4m trả màn 'Just a moment', còn connect_over_cdp tới
    127.0.0.1:9222 cũng bị proxy chặn. Đi thẳng là đường đã kiểm chứng.
    """
    for k in [k for k in os.environ if "proxy" in k.lower()]:
        os.environ.pop(k, None)


class Config:
    HOST = os.environ.get("HOST", "0.0.0.0")
    PORT = _int("PORT", 8080)

    # Số Chrome worker chạy song song. Chrome + OCR ăn RAM nên mặc định 1.
    # >1 chỉ nên bật khi RAM >= 8GB (Engine còn dùng chung /tmp + 1 profile).
    WORKERS = max(1, _int("WORKERS", 1))
    SEMAPHORE = max(1, _int("SEMAPHORE", 1))

    # Hàng đợi: chặn spam, tránh treo box.
    MAX_QUEUE = _int("MAX_QUEUE", 300)
    # 480s: engine cần submit + thử 3 sponsor.
    # 240s cũ cắt ngang -> job "timeout" dù engine còn chạy.
    JOB_TIMEOUT = _int("JOB_TIMEOUT", 480)
    MAX_TRIES = _int("MAX_TRIES", 2)
    RETRY_DELAY = _int("RETRY_DELAY", 3)

    # Cache link đích: link4m trả cùng đích cho cùng alias nên cache rất lời.
    CACHE_TTL = _int("CACHE_TTL", 21600)         # 6 giờ
    CACHE_ENABLED = _bool("CACHE_ENABLED", True)

    # Xác thực (tuỳ chọn). Rỗng = công khai.
    API_KEY = os.environ.get("API_KEY", "").strip()

    DB_PATH = os.environ.get("DB_PATH", os.path.join(REPO, "data", "service.db"))
    LOG_PATH = os.environ.get("SERVICE_LOG", os.path.join(REPO, "logs", "service.log"))

    # Xoá proxy env khi bật service.
    CLEAR_PROXY = _bool("CLEAR_PROXY", True)

    # Giữ Chrome sống giữa các job (nhanh hơn nhưng tốn ~300-500MB).
    KEEP_BROWSER = _bool("KEEP_BROWSER", True)


CFG = Config()
