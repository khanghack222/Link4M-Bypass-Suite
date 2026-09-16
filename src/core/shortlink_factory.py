"""
⚡ SHORTLINK GENERATION FACTORY ⚡
Hỗ trợ tạo shortlink tự động cho các hệ sinh thái rút gọn:
- Link999 / UpToLink (Tên miền mới Link999.app)
- LayMa.net (QuickLink API)
- Link4M.co / Link4M.net
"""

import sys
import os
import json
import urllib.request
import urllib.parse
from typing import Optional

# API Tokens cấu hình mặc định
LINK999_API_TOKEN = os.environ.get("LINK999_API_TOKEN", "b9987ec5d707c668cfeee32ea6492b62bced266c")
LAYMA_API_TOKEN = os.environ.get("LAYMA_API_TOKEN", "050dc0233de6e4566264724bf5c94687")
LINK4M_API_TOKEN = os.environ.get("LINK4M_API_TOKEN", "6a959a071ed1793bdc635c17")

def create_link999_shortlink(destination_url: str, token: str = LINK999_API_TOKEN, campaign_type: int = 2, alias: Optional[str] = None) -> str:
    """
    Tạo shortlink qua Link999.app (UpToLink / Octolink rebranded).
    Campaign types:
      0: No advertising
      1: Social Campaign
      2: Google Search Campaign (Mặc định)
      3: Google Search 3 Step
      4: Google Search 2 Step
      5: Google Search 4 Step
    """
    params = {
        "api": token,
        "url": destination_url,
        "type": str(campaign_type),
        "format": "json"
    }
    if alias:
        params["alias"] = alias
    
    api_url = f"https://link999.app/api?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(api_url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        if data.get("status") == "success" and data.get("shortenedUrl"):
            return data["shortenedUrl"].replace("\\/", "/")
        raise RuntimeError(f"Link999 API Error: {data}")

def create_layma_shortlink(destination_url: str, token: str = LAYMA_API_TOKEN) -> str:
    """Tạo shortlink qua LayMa.net QuickLink API."""
    api_url = f"https://api.layma.net/api/admin/shortlink/quicklink?tokenUser={token}&format=json&url={urllib.parse.quote(destination_url)}&link_du_phong={urllib.parse.quote(destination_url)}"
    req = urllib.request.Request(api_url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        if data.get("success") and data.get("html"):
            return data["html"]
        raise RuntimeError(f"LayMa API Error: {data}")

def create_link4m_shortlink(destination_url: str, token: str = LINK4M_API_TOKEN) -> str:
    """Tạo shortlink Link4M qua API v2."""
    api_url = f"https://link4m.co/api-shorten/v2?api={token}&url={urllib.parse.quote(destination_url)}"
    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") == "success" and data.get("shortenedUrl"):
                return data["shortenedUrl"]
    except Exception:
        pass
    
    # Fallback qua Playwright nếu dính Cloudflare
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(api_url, timeout=15000)
            pre_elem = page.locator("pre")
            content = pre_elem.inner_text().strip() if pre_elem.count() > 0 else page.locator("body").inner_text().strip()
            browser.close()
            data = json.loads(content)
            if data.get("status") == "success" and data.get("shortenedUrl"):
                return data["shortenedUrl"]
    except Exception as e:
        raise RuntimeError(f"Link4M Shortlink creation error: {e}")

if __name__ == "__main__":
    dest = sys.argv[1] if len(sys.argv) > 1 else "https://httpbin.org/get?test=bypass_suite"
    print("=== TẠO LINK RÚT GỌN MẪU ===")
    try:
        l999 = create_link999_shortlink(dest)
        print(f"[+] Link999 / UpToLink: {l999}")
    except Exception as e:
        print(f"[-] Link999 error: {e}")
