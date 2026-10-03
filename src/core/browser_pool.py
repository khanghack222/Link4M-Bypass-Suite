#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚡ PRE-WARMED CHROMIUM BROWSER POOL SINGLETON ⚡
Eliminates 3.5s - 5s browser cold-start latency.
Allocates isolated ephemeral contexts in ~20ms.
"""

import sys
import os
import atexit
import threading
from typing import Optional

try:
    from patchright.sync_api import sync_playwright, Browser, BrowserContext
    IS_PATCHRIGHT = True
except ImportError:
    from playwright.sync_api import sync_playwright, Browser, BrowserContext
    IS_PATCHRIGHT = False

from config import STEALTH_INIT_SCRIPT

class BrowserPool:
    _instance: Optional["BrowserPool"] = None
    _lock = threading.Lock()

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._pw = sync_playwright().start()

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-ipc-flooding-protection",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--disable-extensions",
            "--disable-component-update",
            "--blink-settings=imagesEnabled=true"
        ]

        try:
            self.browser: Browser = self._pw.chromium.launch(
                headless=headless,
                args=launch_args
            )
        except Exception:
            # Fallback if standard launch options fail
            self.browser = self._pw.chromium.launch(headless=headless)

        atexit.register(self.shutdown)

    @classmethod
    def get_instance(cls, headless: bool = True) -> "BrowserPool":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(headless=headless)
            return cls._instance

    def acquire_context(self, block_media: bool = False) -> BrowserContext:
        """
        Creates an isolated ephemeral context in ~20ms with stealth scripts.
        """
        context = self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
            device_scale_factor=1,
            ignore_https_errors=True,
            locale="vi-VN",
            timezone_id="Asia/Ho_Chi_Minh"
        )
        context.add_init_script(STEALTH_INIT_SCRIPT)

        # Chặn các domain quảng cáo / tracking rác làm chậm tiến trình
        AD_DOMAINS = [
            "doubleclick.net", "googlesyndication.com", "adservice.google",
            "adsterra.com", "propellerads.com", "popads.net", "onclickads.net",
            "adcash.com", "exoclick.com", "histats.com", "google-analytics.com",
            "clarity.ms", "hotjar.com", "mc.yandex.ru"
        ]

        def _route_filter(route):
            req = route.request
            u = req.url.lower()
            if any(ad in u for ad in AD_DOMAINS):
                route.abort()
                return
            # Allow captcha images and audio payloads needed for solving
            if "recaptcha" in u or "turnstile" in u or "captcha" in u:
                route.continue_()
                return
            if block_media and req.resource_type in ["image", "media", "font"]:
                route.abort()
                return
            route.continue_()

        context.route("**/*", _route_filter)
        return context


    def shutdown(self):
        try:
            if hasattr(self, "browser") and self.browser:
                self.browser.close()
        except Exception:
            pass
        try:
            if hasattr(self, "_pw") and self._pw:
                self._pw.stop()
        except Exception:
            pass
        BrowserPool._instance = None
