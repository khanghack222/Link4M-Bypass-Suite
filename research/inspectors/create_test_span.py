import sys
code = '''from playwright.sync_api import sync_playwright
import time, sys
sys.stdout.reconfigure(encoding='utf-8')

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    def route_traffic_js(route):
        res = route.fetch()
        text = res.text()
        text = text.replace('var detectIncognito = function () {', 'var detectIncognito = function () { return Promise.resolve({ isPrivate: false, browserName: \"Chrome\" }); }; var _old_detect = function() {')
        route.fulfill(response=res, body=text)

    page.route('**/Traffic/Index/*', route_traffic_js)
    
    print('[*] Navigating to https://onlinejob.com.co...')
    page.goto('https://onlinejob.com.co', wait_until='networkidle')
    
    btn_span = page.locator(\"[id='4JilBaPXK'] span\")
    if btn_span.count() > 0:
        print('[+] Found inner span button! Clicking...')
        btn_span.first.scroll_into_view_if_needed()
        btn_span.first.click(force=True)
        for sec in range(6):
            time.sleep(1)
            container = page.locator(\"[id='4JilBaPXK']\")
            print(f'  [T+{sec+1}s] Container text:', container.inner_text())
    browser.close()
'''
with open('test_onlinejob_span.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('Successfully written test_onlinejob_span.py!')
