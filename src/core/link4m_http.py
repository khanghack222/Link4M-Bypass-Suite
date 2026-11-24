#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Link4M HTTP client (không Chrome).

Phần chạy được HOÀN TOÀN bằng HTTP:
    1) GET  https://link4m.net/go/<alias>          -> alias, code, api_domain
    2) POST {api}/api/campaign/get-advertise       -> form + quest (run/html)
    4) POST {api}/links/get-link-info              -> url đích  (CẦN token captcha)

Phần KHÔNG thể làm bằng HTTP (đã kiểm chứng): lấy g-recaptcha-response.
reCAPTCHA v2 ở đây verify phía server (Google), và trên IP sạch, Google chỉ
phát token cho *vân tay trình duyệt* — requests luôn bị đẩy sang challenge ảnh
(pmeta) trong khi Chrome thật pass checkbox không cần challenge.

Vì vậy client này nhận `token_provider` — một hàm trả về token thật
(từ một Chrome ấm, hoặc từ dịch vụ giải captcha). Mọi thứ còn lại thuần HTTP.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

GO_URL = "https://link4m.net/go/{alias}"
RE_ALIAS = re.compile(r"data-alias\s*=\s*'([^']+)'")
RE_CODE = re.compile(r'data-code\s*=\s*"([^"]+)"')
RE_API = re.compile(r"var api_domain\s*=\s*'([^']+)'")
RE_INPUT = re.compile(r"<input[^>]*>")
RE_NAME = re.compile(r'name=["\']([^"\']+)["\']')
RE_VALUE = re.compile(r'value=["\']([^"\']*)["\']')
RE_RKEY = re.compile(r"recaptcha_key\s*=\s*'([^']+)'")


class Link4MError(RuntimeError):
    """Lỗi có ngữ cảnh: bước nào, phản hồi ra sao."""

    def __init__(self, stage: str, info: str, payload=None):
        super().__init__(f"{stage}: {info}")
        self.stage = stage
        self.info = info
        self.payload = payload


@dataclass
class Quest:
    campaign_id: str = ""
    display_id: str = ""
    code: str = ""
    endpoint: str = ""
    recaptcha_key: str = ""
    raw_js: str = ""


@dataclass
class Session:
    """Một phiên HTTP cho một alias. Không dùng proxy môi trường."""

    alias: str
    api: str = ""
    code: str = ""
    html: str = ""
    form: dict = field(default_factory=dict)
    quest: Quest = field(default_factory=Quest)
    recaptcha_key: str = ""

    def __post_init__(self):
        self.http = requests.Session()
        self.http.trust_env = False          # bỏ mọi *_proxy
        self.http.headers.update({"User-Agent": UA,
                                  "Accept-Language": "vi-VN,vi;q=0.9"})

    # ---------------------------------------------------------------- helpers
    def _post_json(self, path: str, data: dict, stage: str) -> dict:
        r = self.http.post(
            f"{self.api}{path}", data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                     "X-Requested-With": "XMLHttpRequest",
                     "Origin": "https://link4m.net",
                     "Referer": GO_URL.format(alias=self.alias)},
            timeout=30)
        try:
            return r.json()
        except ValueError:
            raise Link4MError(stage, f"HTTP {r.status_code} không phải JSON", r.text[:300])

    # ------------------------------------------------------------------ buoc 1
    def open(self) -> "Session":
        r = self.http.get(GO_URL.format(alias=self.alias), timeout=25)
        if r.status_code != 200:
            raise Link4MError("open", f"GET /go/{self.alias} -> HTTP {r.status_code}")
        h = r.text
        self.html = h
        m = RE_ALIAS.search(h)
        if not m:
            raise Link4MError("open", "không thấy data-alias (link hỏng / giao diện đổi)")
        self.alias = m.group(1)
        self.code = (RE_CODE.search(h) or [None, ""])[1]
        self.api = (RE_API.search(h) or [None, ""])[1]
        self.recaptcha_key = (RE_RKEY.search(h) or [None, ""])[1]
        if not self.api:
            raise Link4MError("open", "không thấy api_domain")
        return self

    # ------------------------------------------------------------------ buoc 2
    def advertise(self) -> dict:
        j = self._post_json("/api/campaign/get-advertise",
                            {"alias": self.alias, "codes": self.code}, "advertise")
        if not j.get("success"):
            raise Link4MError("advertise", j.get("info", "?"), j)
        self.form = parse_form(j.get("form", ""))
        self.quest = parse_quest(j.get("run", ""))
        if self.quest.recaptcha_key:
            self.recaptcha_key = self.quest.recaptcha_key
        return j

    # ------------------------------------------------------------------ buoc 4
    def get_link(self, token: str, password: str = "") -> dict:
        data = dict(self.form)
        data["password"] = password
        data["g-recaptcha-response"] = token
        return self._post_json("/links/get-link-info", data, "get-link-info")

    # ------------------------------------------------------------- quest phụ
    def click_task(self) -> dict:
        q = self.quest
        if not q.endpoint:
            raise Link4MError("click", "campaign này không phải nhiệm vụ click")
        return self._post_json(q.endpoint.replace("//s1.link4m.app", ""),
                               {"campaign_id": q.campaign_id,
                                "display_id": q.display_id, "code": q.code}, "click")


# --------------------------------------------------------------------- parse
def parse_form(html: str) -> dict:
    out = {}
    for tag in RE_INPUT.findall(html or ""):
        n = RE_NAME.search(tag)
        if not n:
            continue
        v = RE_VALUE.search(tag)
        out[n.group(1)] = v.group(1) if v else ""
    return out


def _unescape(s: str) -> str:
    try:
        return s.encode("latin-1", "backslashreplace").decode("unicode_escape")
    except Exception:
        return s


def parse_quest(run_js: str) -> Quest:
    """Bóc quest từ field `run` (JS bị làm rối, nhưng mảng chuỗi lộ hết)."""
    q = Quest(raw_js=run_js or "")
    if not run_js:
        return q
    arr = [_unescape(x) for x in re.findall(r'"((?:[^"\\]|\\.)*)"', run_js)]
    # mẫu: [time, campaign_id, display_id, code, url, method, ...]
    if len(arr) >= 7 and arr[4].endswith("click.html"):
        q.campaign_id, q.display_id, q.code, q.endpoint = arr[1], arr[2], arr[3], arr[4]
    m = RE_RKEY.search(run_js)
    if m:
        q.recaptcha_key = m.group(1)
    return q


def bypass(alias: str, token_provider=None, password: str = "") -> dict:
    """Chạy trọn flow tới mức HTTP cho phép.

    token_provider(): trả về g-recaptcha-response thật. Bỏ trống -> dừng ở buoc 2
    và trả về form + quest để lớp trên tự lo token.
    """
    s = Session(alias).open()
    adv = s.advertise()
    out = {"alias": s.alias, "api": s.api, "form": s.form,
           "quest": vars(s.quest), "recaptcha_key": s.recaptcha_key,
           "info": adv.get("info")}
    if not token_provider:
        out["need"] = "g-recaptcha-response"
        return out
    token = token_provider()
    res = s.get_link(token, password)
    out["token_len"] = len(token or "")
    out["result"] = res
    if res.get("success") and res.get("url"):
        out["ok"] = True
        out["url"] = res["url"]
    return out


if __name__ == "__main__":
    import sys
    import time
    a = sys.argv[1] if len(sys.argv) > 1 else "2kCcIqn"
    t0 = time.time()
    r = bypass(a)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    print(f"[t] {time.time() - t0:.2f}s")
