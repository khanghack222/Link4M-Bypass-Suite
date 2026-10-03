import sys
sys.stdout.reconfigure(encoding='utf-8')
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    js_content = None
    def handle_resp(r):
        global js_content
        if 'ZNYetjdv.js' in r.url:
            js_content = r.text()
    page.on('response', handle_resp)
    page.goto('https://direct.gtraffic.io/ufib3Q_', timeout=30000, wait_until='networkidle')
    b.close()

if js_content:
    target = 'var nt="api/url/tracking-url"'
    p = js_content.find(target)
    print("Code before tracking-url:")
    print(js_content[max(0, p-1200):p])
