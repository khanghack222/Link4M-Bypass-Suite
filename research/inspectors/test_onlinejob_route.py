from playwright.sync_api import sync_playwright
import time, sys
sys.stdout.reconfigure(encoding='utf-8')

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    def route_traffic_js(route):
        res = route.fetch()
        text = res.text()
        text = text.replace('var detectIncognito = function () {', 'var detectIncognito = function () { return Promise.resolve({ isPrivate: false, browserName: "Chrome" }); }; var _old_detect = function() {')
        route.fulfill(response=res, body=text)

    page.route('**/Traffic/Index/*', route_traffic_js)
    
    print('[*] Navigating to https://onlinejob.com.co with neutralized incognito check...')
    page.goto('https://onlinejob.com.co', wait_until='networkidle')
    
    btn = page.locator("[id='4JilBaPXK']")
    if btn.count() > 0:
        print('[+] Found button 4JilBaPXK! Text:', btn.inner_text())
        btn.scroll_into_view_if_needed()
        btn.click()
        print('[+', 'Clicked button! Monitoring next 10 seconds...')
        for sec in range(10):
            time.sleep(1)
            t = btn.inner_text()
            print(f'  [T+${sec+1}s] Button text:', t)
    browser.close()