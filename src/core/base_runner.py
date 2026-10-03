#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚡ UNIFIED BASE RUNNER CONTRACT FOR LINK4M BYPASS SUITE ⚡
Provides standard interfaces, lifecycle management, and result envelopes.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
import time

try:
    from playwright.sync_api import BrowserContext, Page
except ImportError:
    try:
        from patchright.sync_api import BrowserContext, Page
    except ImportError:
        BrowserContext = Any
        Page = Any

from errors import BypassError, DestinationNotFound

@dataclass
class BypassResult:
    success: bool
    destination_url: Optional[str] = None
    engine: str = "UNKNOWN"
    duration_ms: float = 0.0
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "destination_url": self.destination_url,
            "engine": self.engine,
            "duration_ms": round(self.duration_ms, 2),
            "error_code": self.error_code,
            "error_message": self.error_message,
            "metadata": self.metadata
        }

class BaseBypassRunner(ABC):
    """
    Abstract base runner providing standardized lifecycle hooks:
    1. pre_flight(): Zero-browser instant fast path resolution.
    2. execute_flow(): Full browser execution with event-driven DOM handling.
    """
    engine_name: str = "BASE"

    # Known ads/intermediary domains that are NOT destination URLs
    BLOCKED_DESTINATION_PATTERNS: List[str] = [
        "about:blank", "javascript:", "link4m", "bbmkts.com", "layma.net",
        "trafficvn", "gtraffic.io", "yeumoney.com", "octolink", "link999",
        "website-analytics", "what-on", "iatum", "traffic.com.vn", "best-traffic",
        "doubleclick", "googlesyndication", "googleads", "facebook.com/tr",
        "zbet", "shbet", "keonhacai", "bet88", "fb88", "fun88", "w88", "bk8",
        "ku789", "sunwin", "go88", "hitclub", "b52", "rikvip", "789club"
    ]

    def pre_flight(self, target_url: str) -> Optional[str]:
        """
        Subclasses override this to resolve final link in sub-seconds
        without launching a Chromium browser.
        Returns:
            Destination URL string if fast-path succeeds, else None.
        """
        return None

    @abstractmethod
    def execute_flow(self, page: Page, context: BrowserContext, target_url: str) -> str:
        """
        Subclasses implement their specific browser DOM navigation, captcha,
        and quest resolution logic.
        Returns:
            Final destination URL string.
        """
        pass

    def is_valid_destination(self, url: Optional[str]) -> bool:
        """Checks if a URL is a legitimate final destination."""
        if not url or not isinstance(url, str):
            return False
        url_clean = url.strip()
        if not (url_clean.startswith("http://") or url_clean.startswith("https://")):
            return False
        url_lower = url_clean.lower()
        return not any(pattern in url_lower for pattern in self.BLOCKED_DESTINATION_PATTERNS)

    def run(self, target_url: str, context: Optional[BrowserContext] = None, page: Optional[Page] = None) -> BypassResult:
        """
        Template method executing the complete bypass pipeline.
        """
        start_time = time.perf_counter()

        # Step 1: Pre-flight check (0.001s - 0.2s)
        try:
            fast_dest = self.pre_flight(target_url)
            if fast_dest and self.is_valid_destination(fast_dest):
                duration = (time.perf_counter() - start_time) * 1000
                return BypassResult(
                    success=True,
                    destination_url=fast_dest.strip(),
                    engine=self.engine_name,
                    duration_ms=duration,
                    metadata={"fast_path": True}
                )
        except Exception as e:
            # Pre-flight is best effort, fallback to browser
            pass

        # Step 2: Full browser execution
        if context is None or page is None:
            # Import pool dynamically to avoid circular references
            from browser_pool import BrowserPool
            pool = BrowserPool.get_instance()
            managed_context = pool.acquire_context(block_media=False)
            managed_page = managed_context.new_page()
            should_cleanup = True
        else:
            managed_context = context
            managed_page = page
            should_cleanup = False

        # Fast-Exit response interceptor: bắt ngay link đích khi có response redirect hoặc JSON chứa url
        captured_dest = []
        def _check_response(response):
            try:
                # 1. Bắt Location header redirect (301, 302, 307, 308)
                loc = response.headers.get("location")
                if loc and self.is_valid_destination(loc):
                    captured_dest.append(loc)
                    return
                # 2. Bắt JSON response payload nếu có trường data_link hoặc url hợp lệ
                ct = response.headers.get("content-type", "")
                if "application/json" in ct:
                    try:
                        data = response.json()
                        if isinstance(data, dict):
                            for k in ["destination", "target_url", "redirect", "original_url"]:
                                val = data.get(k)
                                if isinstance(val, str) and self.is_valid_destination(val):
                                    captured_dest.append(val)
                                    return
                    except Exception:
                        pass
            except Exception:
                pass

        managed_page.on("response", _check_response)

        try:
            dest = self.execute_flow(managed_page, managed_context, target_url)
            if not self.is_valid_destination(dest):
                if captured_dest and self.is_valid_destination(captured_dest[0]):
                    dest = captured_dest[0]
                else:
                    raise DestinationNotFound(f"Destination extracted is invalid or an ad: {dest}")

            duration = (time.perf_counter() - start_time) * 1000
            return BypassResult(
                success=True,
                destination_url=dest.strip(),
                engine=self.engine_name,
                duration_ms=duration,
                metadata={"fast_path": False}
            )
        except BypassError as be:
            duration = (time.perf_counter() - start_time) * 1000
            return BypassResult(
                success=False,
                engine=self.engine_name,
                duration_ms=duration,
                error_code=be.code,
                error_message=be.message,
                metadata=be.details
            )
        except Exception as e:
            duration = (time.perf_counter() - start_time) * 1000
            return BypassResult(
                success=False,
                engine=self.engine_name,
                duration_ms=duration,
                error_code="ERR_UNEXPECTED",
                error_message=str(e)
            )
        finally:
            if should_cleanup:
                try:
                    managed_page.close()
                except Exception:
                    pass
                try:
                    managed_context.close()
                except Exception:
                    pass
