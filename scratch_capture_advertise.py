import sys, os, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.expandvars(r'%LOCALAPPDATA%\Programs\Python\Python311\Lib\site-packages'))
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    captured = {}
    def on_res(res):
        if 'get-advertise' in res.url:
            try:
                captured['url'] = res.url
                captured['data'] = res.json()
            except Exception:
                pass
                
    page.on('response', on_res)
    page.goto('https://link4m.net/go/2kCcIqn', wait_until='networkidle')
    page.wait_for_timeout(2000)
    
    if captured:
        with open('scratch_link4m_advertise.json', 'w', encoding='utf-8') as f:
            json.dump(captured, f, indent=2, ensure_ascii=False)
        print("Captured get-advertise! Saved to scratch_link4m_advertise.json")
    else:
        print("Not captured!")
    browser.close()
