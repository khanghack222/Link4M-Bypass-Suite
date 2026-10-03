from playwright.sync_api import sync_playwright
import json

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    
    def on_resp(res):
        if '/campaign/get-advertise' in res.url:
            print("STATUS:", res.status)
            txt = res.text()
            print("GET-ADVERTISE LENGTH:", len(txt))
            data = json.loads(txt)
            html = data.get('html', '')
            print("HTML SNIPPET (first 1000):", html[:1000])
            with open('advertise_payload.json', 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    pg.on('response', on_resp)
    
    pg.goto('https://link4m.net/go/2kCcIqn')
    pg.wait_for_timeout(5000)
    b.close()
