"""Captcha solving through a paid API, with a local hook for self-hosted
Turnstile/hCaptcha solvers.

Only the createTask/poll shape differs per vendor; :class:`Solver` normalises
it so provider adapters just call ``solve_recaptcha_v2`` or ``solve_turnstile``.
"""

from __future__ import annotations

import time

import httpx

from .config import Config


class CaptchaError(RuntimeError):
    pass


class Solver:
    name = "base"

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def _key(self) -> str:
        if not self.cfg.captcha_key:
            raise CaptchaError("captcha_key is required")
        return self.cfg.captcha_key

    def solve(self, task: dict, timeout: float = 180.0) -> str:
        raise NotImplementedError

    def solve_recaptcha_v2(self, sitekey: str, url: str, timeout: float = 180.0) -> str:
        return self.solve(
            {"type": "ReCaptchaV2TaskProxyLess", "websiteURL": url, "websiteKey": sitekey},
            timeout,
        )

    def solve_recaptcha_v3(
        self, sitekey: str, url: str, action: str = "verify", timeout: float = 180.0
    ) -> str:
        return self.solve(
            {
                "type": "ReCaptchaV3TaskProxyLess",
                "websiteURL": url,
                "websiteKey": sitekey,
                "pageAction": action,
            },
            timeout,
        )

    def solve_turnstile(self, sitekey: str, url: str, timeout: float = 180.0) -> str:
        return self.solve(
            {"type": "AntiTurnstileTaskProxyLess", "websiteURL": url, "websiteKey": sitekey},
            timeout,
        )

    def solve_hcaptcha(self, sitekey: str, url: str, timeout: float = 180.0) -> str:
        return self.solve(
            {"type": "HCaptchaTaskProxyLess", "websiteURL": url, "websiteKey": sitekey},
            timeout,
        )


class CapSolver(Solver):
    name = "capsolver"
    base = "https://api.capsolver.com"

    def solve(self, task: dict, timeout: float = 180.0) -> str:
        payload = {"clientKey": self._key(), "task": task}
        with httpx.Client(timeout=60) as client:
            created = client.post(f"{self.base}/createTask", json=payload).json()
            if created.get("errorId"):
                raise CaptchaError(f"capsolver: {created.get('errorDescription')}")
            task_id = created.get("taskId")
            if not task_id:
                raise CaptchaError(f"capsolver: no taskId in {created}")
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                time.sleep(4)
                result = client.post(
                    f"{self.base}/getTaskResult",
                    json={"clientKey": self._key(), "taskId": task_id},
                ).json()
                if result.get("errorId"):
                    raise CaptchaError(f"capsolver: {result.get('errorDescription')}")
                if result.get("status") == "ready":
                    solution = result.get("solution") or {}
                    token = solution.get("gRecaptchaResponse") or solution.get(
                        "token"
                    ) or solution.get("captcha")
                    if token:
                        return token
                    raise CaptchaError(f"capsolver: empty solution {solution}")
        raise CaptchaError("capsolver: timeout")


class TwoCaptcha(Solver):
    name = "2captcha"
    base = "https://2captcha.com"

    _TYPE_MAP = {
        "ReCaptchaV2TaskProxyLess": "userrecaptcha",
        "ReCaptchaV3TaskProxyLess": "userrecaptcha",
        "AntiTurnstileTaskProxyLess": "turnstile",
        "HCaptchaTaskProxyLess": "hcaptcha",
    }

    def solve(self, task: dict, timeout: float = 180.0) -> str:
        method = self._TYPE_MAP.get(task["type"])
        if not method:
            raise CaptchaError(f"2captcha: unsupported task {task['type']}")
        params = {
            "key": self._key(),
            "method": method,
            "pageurl": task["websiteURL"],
            "json": 1,
        }
        if method == "userrecaptcha":
            params["googlekey"] = task["websiteKey"]
            if task["type"] == "ReCaptchaV3TaskProxyLess":
                params["version"] = "v3"
                params["action"] = task.get("pageAction", "verify")
        elif method == "turnstile":
            params["sitekey"] = task["websiteKey"]
        else:
            params["sitekey"] = task["websiteKey"]

        with httpx.Client(timeout=60) as client:
            created = client.post(f"{self.base}/in.php", data=params).json()
            if created.get("status") != 1:
                raise CaptchaError(f"2captcha: {created.get('request')}")
            task_id = created["request"]
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                time.sleep(5)
                result = client.get(
                    f"{self.base}/res.php",
                    params={"key": self._key(), "action": "get", "id": task_id, "json": 1},
                ).json()
                if result.get("status") == 1:
                    return result["request"]
                if result.get("request") not in {"CAPCHA_NOT_READY", "CAPTCHA_NOT_READY"}:
                    raise CaptchaError(f"2captcha: {result.get('request')}")
        raise CaptchaError("2captcha: timeout")


class YesCaptcha(Solver):
    name = "yescaptcha"
    base = "https://api.yescaptcha.com"

    def solve(self, task: dict, timeout: float = 180.0) -> str:
        payload = {"clientKey": self._key(), "task": task}
        with httpx.Client(timeout=60) as client:
            created = client.post(f"{self.base}/createTask", json=payload).json()
            if created.get("errorId"):
                raise CaptchaError(f"yescaptcha: {created.get('errorDescription')}")
            task_id = created.get("taskId")
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                time.sleep(4)
                result = client.post(
                    f"{self.base}/getTaskResult",
                    json={"clientKey": self._key(), "taskId": task_id},
                ).json()
                if result.get("status") == "ready":
                    solution = result.get("solution") or {}
                    token = solution.get("gRecaptchaResponse") or solution.get("token")
                    if token:
                        return token
                if result.get("errorId"):
                    raise CaptchaError(f"yescaptcha: {result.get('errorDescription')}")
        raise CaptchaError("yescaptcha: timeout")


class NopeCHA(Solver):
    name = "nopecha"
    base = "https://api.nopecha.com"

    _TYPE_MAP = {
        "ReCaptchaV2TaskProxyLess": "recaptcha2",
        "ReCaptchaV3TaskProxyLess": "recaptcha3",
        "AntiTurnstileTaskProxyLess": "turnstile",
        "HCaptchaTaskProxyLess": "hcaptcha",
    }

    def solve(self, task: dict, timeout: float = 180.0) -> str:
        kind = self._TYPE_MAP.get(task["type"])
        if not kind:
            raise CaptchaError(f"nopecha: unsupported task {task['type']}")
        body = {
            "type": kind,
            "sitekey": task["websiteKey"],
            "url": task["websiteURL"],
            "key": self._key(),
        }
        with httpx.Client(timeout=60) as client:
            created = client.post(self.base, json=body).json()
            if created.get("error"):
                raise CaptchaError(f"nopecha: {created['error']}")
            task_id = created.get("data")
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                time.sleep(4)
                result = client.post(
                    self.base, json={"key": self._key(), "id": task_id}
                ).json()
                if result.get("data") and isinstance(result["data"], str):
                    return result["data"]
                if result.get("error") and result["error"] not in (11, 12):
                    raise CaptchaError(f"nopecha: {result['error']}")
        raise CaptchaError("nopecha: timeout")


_PROVIDERS = {
    "capsolver": CapSolver,
    "2captcha": TwoCaptcha,
    "yescaptcha": YesCaptcha,
    "nopecha": NopeCHA,
}


def provider(cfg: Config, name: str | None = None) -> Solver:
    key = (name or cfg.captcha_provider).lower()
    if key not in _PROVIDERS:
        raise CaptchaError(f"unknown captcha provider: {key}")
    return _PROVIDERS[key](cfg)
