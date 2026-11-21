import requests
import re
import json

with open("link4m_page.html", "r", encoding="utf-8") as f:
    text = f.read()

m_alias = re.search(r"data-alias\s*=\s*['\"]([^'\"]+)['\"]", text)
m_code = re.search(r"data-code\s*=\s*['\"]([^'\"]+)['\"]", text)

alias = m_alias.group(1) if m_alias else ""
code = m_code.group(1) if m_code else ""
print("alias:", alias)
print("code:", code[:40] + "...")

resp = requests.post(
    "https://s1.link4m.app/api/campaign/get-advertise",
    data={"alias": alias, "codes": code},
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Origin": "https://link4m.net",
        "Referer": "https://link4m.net/go/68pw167Y"
    }
)
print("get-advertise status:", resp.status_code)
data = resp.json()
print("get-advertise success:", data.get("success"))
if "form" in data:
    print("=== FORM HTML ===")
    print(data["form"])
if "run" in data:
    print("=== RUN SCRIPT ===")
    print(data["run"])
