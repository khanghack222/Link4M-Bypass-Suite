"""Inbox providers used for signup verification.

Every provider returns an :class:`Inbox`; :func:`wait_for_code` polls until a
verification code or link matching the pattern shows up. The Cloudflare Worker
backed provider is the only one that survives serious signup forms, because it
lives on a domain that is not on any disposable list.
"""

from __future__ import annotations

import re
import secrets
import string
import time
from dataclasses import dataclass
from typing import Callable, Iterable

import httpx

from .config import Config

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/158.0.0.0 Safari/537.36"
)

CODE_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
LINK_RE = re.compile(r"https?://[^\s\"'<>]+")


@dataclass
class Inbox:
    address: str
    provider: str
    token: str = ""


class MailError(RuntimeError):
    pass


def random_local(length: int = 10) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def random_password(length: int = 18) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


class MailProvider:
    name = "base"

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def create(self, local: str | None = None) -> Inbox:
        raise NotImplementedError

    def messages(self, inbox: Inbox) -> list[str]:
        """Return message bodies, newest first."""
        raise NotImplementedError

    def wait_for_code(self, inbox: Inbox, timeout: float = 180.0) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for body in self.messages(inbox):
                match = CODE_RE.search(body)
                if match:
                    return match.group(1)
            time.sleep(3)
        raise MailError(f"no verification code for {inbox.address} in {timeout:.0f}s")

    def wait_for_link(self, inbox: Inbox, timeout: float = 180.0) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for body in self.messages(inbox):
                for link in LINK_RE.findall(body):
                    if "unsubscribe" in link.lower():
                        continue
                    return link
            time.sleep(3)
        raise MailError(f"no verification link for {inbox.address} in {timeout:.0f}s")


class CloudflareMail(MailProvider):
    """Catch-all on your own domain, backed by workers/email-router.

    The Worker exposes ``GET /inbox?to=<address>`` returning JSON
    ``{"messages": [{"subject": ..., "text": ...}]}`` and is guarded by
    ``Authorization: Bearer <mail_secret>``.
    """

    name = "cloudflare"

    def _client(self) -> httpx.Client:
        if not self.cfg.mail_worker_url or not self.cfg.mail_secret:
            raise MailError("mail_worker_url and mail_secret are required")
        return httpx.Client(
            base_url=self.cfg.mail_worker_url.rstrip("/"),
            headers={"authorization": f"Bearer {self.cfg.mail_secret}"},
            timeout=30,
            follow_redirects=True,
        )

    def create(self, local: str | None = None) -> Inbox:
        if not self.cfg.mail_domain:
            raise MailError("mail_domain is required for the cloudflare provider")
        address = f"{local or random_local()}@{self.cfg.mail_domain}"
        return Inbox(address=address, provider=self.name)

    def messages(self, inbox: Inbox) -> list[str]:
        with self._client() as client:
            response = client.get("/inbox", params={"to": inbox.address})
            response.raise_for_status()
            payload = response.json()
        bodies: list[str] = []
        for item in payload.get("messages", []):
            parts = [item.get("subject", ""), item.get("text", "")]
            parts.extend(item.get("links", []) or [])
            bodies.append("\n".join(part for part in parts if part))
        return bodies


class MaildropMail(MailProvider):
    """maildrop.cc GraphQL, no key. Domains are widely blocklisted."""

    name = "maildrop"
    endpoint = "https://api.maildrop.cc/graphql"

    def create(self, local: str | None = None) -> Inbox:
        return Inbox(address=local or random_local(12), provider=self.name)

    def _query(self, query: str, variables: dict) -> dict:
        with httpx.Client(timeout=30) as client:
            response = client.post(
                self.endpoint,
                json={"query": query, "variables": variables},
                headers={
                    "content-type": "application/json",
                    "x-apollo-operation-name": "inbox",
                    "user-agent": UA,
                },
            )
            response.raise_for_status()
            return response.json()

    def messages(self, inbox: Inbox) -> list[str]:
        listing = self._query(
            "query($m:String!){inbox(mailbox:$m){id subject}}",
            {"m": inbox.address},
        )
        rows = (listing.get("data") or {}).get("inbox") or []
        bodies: list[str] = []
        for row in rows[:10]:
            detail = self._query(
                "query($m:String!,$id:String!){message(mailbox:$m,id:$id){data}}",
                {"m": inbox.address, "id": row["id"]},
            )
            data = ((detail.get("data") or {}).get("message") or {}).get("data")
            if data:
                bodies.append(str(data))
        return bodies


class DropmailMail(MailProvider):
    """dropmail.me GraphQL, no key. Session token is generated client side."""

    name = "dropmail"

    def __init__(self, cfg: Config) -> None:
        super().__init__(cfg)
        self._session = "web-test-" + secrets.token_hex(8)

    @property
    def endpoint(self) -> str:
        return f"https://dropmail.me/api/graphql/{self._session}"

    def create(self, local: str | None = None) -> Inbox:
        query = "mutation{introduceSession{id,addresses{address}}}"
        with httpx.Client(timeout=30) as client:
            response = client.post(self.endpoint, json={"query": query})
            response.raise_for_status()
            payload = response.json()
        session = ((payload.get("data") or {}).get("introduceSession")) or {}
        addresses = session.get("addresses") or []
        if not addresses:
            raise MailError("dropmail did not return an address")
        return Inbox(
            address=addresses[0]["address"],
            provider=self.name,
            token=session.get("id", ""),
        )

    def messages(self, inbox: Inbox) -> list[str]:
        query = (
            "query($id:ID!){session(id:$id){mails{rawHeader,text,"
            "headerFrom,subject}}}"
        )
        with httpx.Client(timeout=30) as client:
            response = client.post(
                self.endpoint, json={"query": query, "variables": {"id": inbox.token}}
            )
            response.raise_for_status()
            payload = response.json()
        mails = (((payload.get("data") or {}).get("session")) or {}).get("mails") or []
        bodies: list[str] = []
        for mail in mails:
            bodies.append(
                "\n".join(
                    str(mail.get(key) or "")
                    for key in ("subject", "text", "rawHeader")
                )
            )
        return bodies


class GuerrillaMail(MailProvider):
    """guerrillamail.com ajax API, no key, 1 h address lifetime."""

    name = "guerrilla"
    endpoint = "https://api.guerrillamail.com/ajax.php"

    def create(self, local: str | None = None) -> Inbox:
        with httpx.Client(timeout=30) as client:
            response = client.get(
                self.endpoint,
                params={"f": "get_email_address"},
                headers={"user-agent": UA},
            )
            response.raise_for_status()
            payload = response.json()
        address = payload.get("email_addr")
        if not address:
            raise MailError("guerrilla did not return an address")
        return Inbox(
            address=address, provider=self.name, token=payload.get("sid_token", "")
        )

    def messages(self, inbox: Inbox) -> list[str]:
        with httpx.Client(timeout=30) as client:
            listing = client.get(
                self.endpoint,
                params={
                    "f": "check_email",
                    "seq": 0,
                    "sid_token": inbox.token,
                },
                headers={"user-agent": UA},
            )
            listing.raise_for_status()
            rows = listing.json().get("list") or []
            bodies: list[str] = []
            for row in rows[:10]:
                detail = client.get(
                    self.endpoint,
                    params={
                        "f": "fetch_email",
                        "email_id": row.get("mail_id"),
                        "sid_token": inbox.token,
                    },
                    headers={"user-agent": UA},
                )
                detail.raise_for_status()
                payload = detail.json()
                bodies.append(
                    "\n".join(
                        str(payload.get(key) or "")
                        for key in ("mail_subject", "mail_body")
                    )
                )
            return bodies


_PROVIDERS: dict[str, Callable[[Config], MailProvider]] = {
    "cloudflare": CloudflareMail,
    "maildrop": MaildropMail,
    "dropmail": DropmailMail,
    "guerrilla": GuerrillaMail,
}


def provider(cfg: Config, name: str | None = None) -> MailProvider:
    key = (name or cfg.mail_provider).lower()
    try:
        factory = _PROVIDERS[key]
    except KeyError:
        raise MailError(f"unknown mail provider: {key}") from None
    return factory(cfg)


def extract_codes(bodies: Iterable[str]) -> list[str]:
    return [match.group(1) for body in bodies for match in CODE_RE.finditer(body)]
