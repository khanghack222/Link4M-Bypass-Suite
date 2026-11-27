"""CloudSigma Instant Access: a 60-minute root VM with no account.

Useful for a throwaway build or a quick live test. The box is destroyed when the
session ends, so this adapter is never used by `burn`; it is a separate command.
"""

from __future__ import annotations

import re
import time

from ..browser import Session, open_session
from ..config import Config
from .base import Account, Identity, Provider, ProviderError, VM, VMSpec

START_URL = "https://www.cloudsigma.com/instant-access/"

IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
USER_RE = re.compile(r"(?:username|user)\s*[:=]\s*(\S+)", re.IGNORECASE)
PASS_RE = re.compile(r"(?:password|pass)\s*[:=]\s*(\S+)", re.IGNORECASE)


class CloudSigmaProvider(Provider):
    name = "cloudsigma"
    automated_signup = True

    def instant(self, identity: Identity) -> dict[str, str]:
        with open_session(self.cfg, identity.id) as session:
            session.goto(START_URL, wait="networkidle", timeout=90000)
            session.click_any(
                [
                    'button:has-text("Start")',
                    'button:has-text("Launch")',
                    'a:has-text("Instant Access")',
                    'button:has-text("Instant")',
                ],
                timeout=60000,
            )
            # The page shows a terminal block once the box is up.
            deadline = time.monotonic() + 300
            text = ""
            while time.monotonic() < deadline:
                text = session.text()
                if IP_RE.search(text) and ("password" in text.lower() or "ssh" in text.lower()):
                    break
                time.sleep(5)
            else:
                raise ProviderError("cloudsigma: credentials never appeared")

        ip = IP_RE.search(text)
        user = USER_RE.search(text)
        password = PASS_RE.search(text)
        if not ip:
            raise ProviderError("cloudsigma: no IP in the credentials block")
        return {
            "ip": ip.group(0),
            "user": user.group(1) if user else "root",
            "password": password.group(1) if password else "",
            "raw": text[-2000:],
        }

    def signup(self, identity: Identity, interactive: bool = False) -> Account:
        raise ProviderError("cloudsigma has no persistent account; use `vpsfarm instant`")

    def provision(self, account: Account, spec: VMSpec) -> VM:
        raise ProviderError("cloudsigma instant boxes are not provisioned from an account")
