import sys
sys.path.insert(0, 'src/core')
import json
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    def on_resp(res):
        if "get-advertise" in res.url:
            try:
                data = res.json()
                with open("dumped_advertise.json", "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print("Successfully dumped advertise payload to dumped_advertise.json")
            except Exception as e:
                print("Error parsing get-advertise:", e)

    page.on("response", on_resp)
    page.goto("https://link4m.net/go/68pw167Y", wait_until="networkidle")
    import time
    time.sleep(3)
    browser.close()
