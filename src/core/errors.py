#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚡ STANDARDIZED ERROR CODES & DIAGNOSTICS FOR LINK4M BYPASS SUITE ⚡
"""

class BypassError(Exception):
    """Base exception for all bypass failures."""
    def __init__(self, code: str, message: str, details: dict = None):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.details = details or {}

class PreFlightFailed(BypassError):
    def __init__(self, message: str, details: dict = None):
        super().__init__("ERR_PREFLIGHT_FAIL", message, details)

class CaptchaBlocked(BypassError):
    def __init__(self, message: str, details: dict = None):
        super().__init__("ERR_CAPTCHA_BLOCKED", message, details)

class CountdownTimeout(BypassError):
    def __init__(self, message: str, details: dict = None):
        super().__init__("ERR_COUNTDOWN_TIMEOUT", message, details)

class SponsorNotFound(BypassError):
    def __init__(self, message: str, details: dict = None):
        super().__init__("ERR_SPONSOR_NOT_FOUND", message, details)

class DestinationNotFound(BypassError):
    def __init__(self, message: str, details: dict = None):
        super().__init__("ERR_DESTINATION_NOT_FOUND", message, details)

class BrowserCrash(BypassError):
    def __init__(self, message: str, details: dict = None):
        super().__init__("ERR_BROWSER_CRASH", message, details)
