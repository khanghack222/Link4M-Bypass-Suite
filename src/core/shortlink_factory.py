import requests
import urllib.parse
import sys

TOKEN = "d0b3f4767f11054fcfc21ead"

def create_shortlink(target_url: str, token: str = TOKEN) -> str:
    api_url = f"https://bbmkts.com/ql?token={token}&longurl={urllib.parse.quote(target_url)}"
    r = requests.get(api_url, allow_redirects=False, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code == 302 and "Location" in r.headers:
        return r.headers["Location"]
    raise RuntimeError(f"Failed to create shortlink: HTTP {r.status_code} - {r.text}")

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com/test-debug"
    short = create_shortlink(url)
    print(f"[+] Tao link thanh cong: {short}")
