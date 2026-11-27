"""Browser sessions with one profile per identity.

patchright is the default: it is Playwright with the CDP `Runtime.enable` leak
patched, which is what most signup forms actually detect. Camoufox is a drop-in
alternative when the target fingerprints harder.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .config import Config


class BrowserError(RuntimeError):
    pass


@dataclass
class Session:
    page: Any
    context: Any
    browser: Any
    profile: Path

    def close(self) -> None:
        for closer in (self.context, self.browser):
            try:
                closer.close()
            except Exception:
                pass

    def __enter__(self) -> "Session":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # --- interaction helpers ------------------------------------------------

    def goto(self, url: str, wait: str = "domcontentloaded", timeout: int = 45000) -> None:
        self.page.goto(url, wait_until=wait, timeout=timeout)

    def type(self, selector: str, text: str, delay: int = 55) -> None:
        locator = self.page.locator(selector).first
        locator.wait_for(state="visible", timeout=20000)
        locator.click()
        locator.fill("")
        locator.type(text, delay=delay)

    def click(self, selector: str, timeout: int = 20000) -> None:
        locator = self.page.locator(selector).first
        locator.wait_for(state="visible", timeout=timeout)
        locator.click()

    def click_text(self, text: str, timeout: int = 20000) -> None:
        locator = self.page.get_by_text(text, exact=False).first
        locator.wait_for(state="visible", timeout=timeout)
        locator.click()

    def click_any(self, selectors: Iterable[str], timeout: int = 20000) -> str:
        deadline = time.monotonic() + timeout / 1000
        while time.monotonic() < deadline:
            for selector in selectors:
                locator = self.page.locator(selector).first
                try:
                    if locator.count() and locator.is_visible():
                        locator.click()
                        return selector
                except Exception:
                    continue
            time.sleep(0.3)
        raise BrowserError(f"none of these became clickable: {list(selectors)}")

    def fill_any(self, selectors: Iterable[str], text: str, timeout: int = 20000) -> str:
        deadline = time.monotonic() + timeout / 1000
        while time.monotonic() < deadline:
            for selector in selectors:
                locator = self.page.locator(selector).first
                try:
                    if locator.count() and locator.is_visible():
                        locator.fill(text)
                        return selector
                except Exception:
                    continue
            time.sleep(0.3)
        raise BrowserError(f"none of these became fillable: {list(selectors)}")

    def text(self) -> str:
        try:
            return self.page.inner_text("body")
        except Exception:
            return ""

    def wait_url(self, fragment: str, timeout: float = 60.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if fragment in self.page.url:
                return
            time.sleep(0.3)
        raise BrowserError(f"url never contained {fragment!r}: {self.page.url}")


def _proxy_settings(proxy: str) -> dict[str, str] | None:
    if not proxy:
        return None
    return {"server": proxy}


def open_session(
    cfg: Config,
    identity_id: str,
    headless: bool | None = None,
    locale: str = "en-US",
    timezone: str = "Asia/Ho_Chi_Minh",
) -> Session:
    profile = cfg.profiles_dir / identity_id
    profile.mkdir(parents=True, exist_ok=True)
    headless = cfg.headless if headless is None else headless
    engine = cfg.browser_engine.lower()

    if engine == "camoufox":
        try:
            from camoufox.sync_api import Camoufox  # type: ignore
        except ImportError as exc:
            raise BrowserError("camoufox is not installed: pip install camoufox[geoip]") from exc
        browser = Camoufox(
            headless=headless,
            persistent_context=True,
            user_data_dir=str(profile),
            locale=locale,
            proxy=_proxy_settings(cfg.proxy),
        ).__enter__()
        context = browser
        page = context.pages[0] if context.pages else context.new_page()
        return Session(page=page, context=context, browser=browser, profile=profile)

    try:
        from patchright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        from playwright.sync_api import sync_playwright  # type: ignore

    playwright = sync_playwright().start()
    launch_args = {
        "user_data_dir": str(profile),
        "headless": headless,
        "locale": locale,
        "timezone_id": timezone,
        "viewport": {"width": 1366, "height": 900},
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
        ],
    }
    if cfg.proxy:
        launch_args["proxy"] = _proxy_settings(cfg.proxy)
    context = playwright.chromium.launch_persistent_context(**launch_args)
    page = context.pages[0] if context.pages else context.new_page()
    return Session(page=page, context=context, browser=playwright, profile=profile)
