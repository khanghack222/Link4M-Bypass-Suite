"""
⚡ 2CAPTCHA API CLIENT MODULE ⚡
Integrates 2captcha API with automated fallback and balance checking.
"""

import time
import urllib.request
import urllib.parse
import json
from typing import Optional, Dict, Any

# Active key pool with known balance
KEY_POOL = [
    "c77b0e8cbdf802ecf529296bf5bef91c",  # Active verified balance ~ 0.02674 USD
    "a03a99c76ce81813ce26d3bdb68c6e8f"   # Backup
]
DEFAULT_2CAPTCHA_KEY = KEY_POOL[0]

def get_best_key() -> str:
    """Finds the first key in the pool with a positive balance."""
    for key in KEY_POOL:
        bal = get_balance(key)
        if bal > 0.002:  # Enough for at least one reCAPTCHA solve
            return key
    return DEFAULT_2CAPTCHA_KEY

def get_balance(api_key: str = DEFAULT_2CAPTCHA_KEY) -> float:
    try:
        url = f"http://2captcha.com/res.php?key={api_key}&action=getbalance&json=1"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode())
            if data.get("status") == 1:
                return float(data.get("request", 0))
    except Exception:
        pass
    return 0.0

def solve_recaptcha_2captcha(site_key: str, target_url: str, api_key: str = DEFAULT_2CAPTCHA_KEY, max_wait: float = 60.0) -> Optional[str]:
    """Solves reCAPTCHA v2 using 2captcha API."""
    try:
        # Step 1: Request in.php
        params = {
            "key": api_key,
            "method": "userrecaptcha",
            "googlekey": site_key,
            "pageurl": target_url,
            "json": 1
        }
        in_url = "http://2captcha.com/in.php?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(in_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            res = json.loads(r.read().decode())

        if res.get("status") != 1:
            print(f"[!] 2captcha in.php error: {res.get('request')}", flush=True)
            return None

        captcha_id = res.get("request")
        print(f"[*] 2captcha task created: {captcha_id}. Polling result...", flush=True)

        # Step 2: Poll res.php
        t0 = time.time()
        time.sleep(12)  # initial wait
        while time.time() - t0 < max_wait:
            res_url = f"http://2captcha.com/res.php?key={api_key}&action=get&id={captcha_id}&json=1"
            req2 = urllib.request.Request(res_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req2, timeout=10) as r2:
                resp = json.loads(r2.read().decode())

            if resp.get("status") == 1:
                token = resp.get("request")
                print(f"[+] 2captcha token received in {round(time.time() - t0, 2)}s", flush=True)
                return token

            if resp.get("request") != "CAPCHA_NOT_READY":
                print(f"[!] 2captcha error: {resp.get('request')}", flush=True)
                break

            time.sleep(4)
    except Exception as e:
        print(f"[!] 2captcha exception: {e}", flush=True)
    return None

if __name__ == "__main__":
    bal = get_balance()
    print("2captcha Balance:", bal)
