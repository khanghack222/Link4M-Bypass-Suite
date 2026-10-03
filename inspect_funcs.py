from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page()
    pg.goto('https://link4m.net/go/2kCcIqn')
    pg.wait_for_timeout(3000)
    js = pg.evaluate('''() => {
        let res = {};
        if (typeof checkPassword !== 'undefined') res.checkPassword = checkPassword.toString();
        if (typeof checkCaptcha !== 'undefined') res.checkCaptcha = checkCaptcha.toString();
        return res;
    }''')
    for k, v in js.items():
        print(f"=== {k} ===")
        print(v)
    b.close()
