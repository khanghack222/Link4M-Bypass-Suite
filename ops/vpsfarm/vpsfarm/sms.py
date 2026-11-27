"""SMS verification: 5sim and sms-activate."""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from .config import Config


class SmsError(RuntimeError):
    pass


@dataclass
class Activation:
    provider: str
    ident: str
    phone: str
    price: str = ""


class SmsProvider:
    name = "base"

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def buy(self, product: str | None = None, country: str | None = None) -> Activation:
        raise NotImplementedError

    def wait_code(self, activation: Activation, timeout: float = 300.0) -> str:
        raise NotImplementedError

    def finish(self, activation: Activation) -> None:
        raise NotImplementedError

    def cancel(self, activation: Activation) -> None:
        raise NotImplementedError


class FiveSim(SmsProvider):
    name = "5sim"
    base = "https://5sim.net/v1"

    def _headers(self) -> dict[str, str]:
        if not self.cfg.sms_key:
            raise SmsError("sms_key is required for 5sim")
        return {"authorization": f"Bearer {self.cfg.sms_key}", "accept": "application/json"}

    def buy(self, product: str | None = None, country: str | None = None) -> Activation:
        product = product or self.cfg.sms_product
        country = country or self.cfg.sms_country
        # `any` lets 5sim pick the cheapest operator with stock.
        url = f"{self.base}/user/buy/activation/{country}/any/{product}"
        with httpx.Client(timeout=30) as client:
            response = client.get(url, headers=self._headers())
        if response.status_code != 200:
            raise SmsError(f"5sim buy failed: {response.status_code} {response.text[:200]}")
        payload = response.json()
        return Activation(
            provider=self.name,
            ident=str(payload["id"]),
            phone=str(payload["phone"]),
            price=str(payload.get("price", "")),
        )

    def wait_code(self, activation: Activation, timeout: float = 300.0) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with httpx.Client(timeout=30) as client:
                response = client.get(
                    f"{self.base}/user/check/{activation.ident}", headers=self._headers()
                )
            if response.status_code == 200:
                payload = response.json()
                for sms in payload.get("sms", []) or []:
                    code = str(sms.get("code", "")).strip()
                    if code:
                        return code
            time.sleep(5)
        raise SmsError(f"5sim: no SMS for {activation.phone} in {timeout:.0f}s")

    def finish(self, activation: Activation) -> None:
        with httpx.Client(timeout=30) as client:
            client.get(f"{self.base}/user/finish/{activation.ident}", headers=self._headers())

    def cancel(self, activation: Activation) -> None:
        with httpx.Client(timeout=30) as client:
            client.get(f"{self.base}/user/cancel/{activation.ident}", headers=self._headers())


class SmsActivate(SmsProvider):
    name = "sms-activate"
    base = "https://api.sms-activate.org/stubs/handler_api.php"

    def _call(self, **params: str) -> str:
        if not self.cfg.sms_key:
            raise SmsError("sms_key is required for sms-activate")
        params["api_key"] = self.cfg.sms_key
        with httpx.Client(timeout=30) as client:
            response = client.get(self.base, params=params)
        response.raise_for_status()
        return response.text.strip()

    def buy(self, product: str | None = None, country: str | None = None) -> Activation:
        text = self._call(
            action="getNumber",
            service=product or self.cfg.sms_product,
            country=country or "0",
        )
        if not text.startswith("ACCESS_NUMBER"):
            raise SmsError(f"sms-activate buy failed: {text[:120]}")
        _, ident, phone = text.split(":", 2)
        return Activation(provider=self.name, ident=ident, phone=phone)

    def wait_code(self, activation: Activation, timeout: float = 300.0) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            text = self._call(action="getStatus", id=activation.ident)
            if text.startswith("STATUS_OK"):
                return text.split(":", 1)[1]
            time.sleep(5)
        raise SmsError(f"sms-activate: no SMS for {activation.phone} in {timeout:.0f}s")

    def finish(self, activation: Activation) -> None:
        self._call(action="setStatus", status="6", id=activation.ident)

    def cancel(self, activation: Activation) -> None:
        self._call(action="setStatus", status="8", id=activation.ident)


_PROVIDERS = {"5sim": FiveSim, "sms-activate": SmsActivate}


def provider(cfg: Config, name: str | None = None) -> SmsProvider:
    key = (name or cfg.sms_provider).lower()
    if key not in _PROVIDERS:
        raise SmsError(f"unknown sms provider: {key}")
    return _PROVIDERS[key](cfg)
