import sys
import json
import urllib.parse
from playwright.sync_api import sync_playwright

LINK4M_API_TOKEN = "6a959a071ed1793bdc635c17"

def create_link4m_shortlink(destination_url: str, token: str = LINK4M_API_TOKEN) -> str:
    """Tạo shortlink Link4M qua API v2 và vượt Cloudflare tự động."""
    api_url = f"https://link4m.co/api-shorten/v2?api={token}&url={urllib.parse.quote(destination_url)}"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(api_url, timeout=15000)
        pre_elem = page.locator("pre")
        if pre_elem.count() > 0:
            content = pre_elem.inner_text().strip()
        else:
            content = page.locator("body").inner_text().strip()
        browser.close()
        
        data = json.loads(content)
        if data.get("status") == "success" and data.get("shortenedUrl"):
            return data.get("shortenedUrl")
        else:
            raise RuntimeError(f"Link4M API Error: {data}")

if __name__ == "__main__":
    dest = sys.argv[1] if len(sys.argv) > 1 else "https://google.com/test"
    short_url = create_link4m_shortlink(dest)
    print(f"[+] Shortlink tạo thành công: {short_url}")
