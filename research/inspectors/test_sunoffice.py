from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    
    scripts = []
    page.on('request', lambda req: scripts.append(req.url) if req.resource_type == 'script' else None)
    
    try:
        page.goto('https://sunoffice.vn/cho-thue-van-phong-quan-hai-ba-trung/', referer='https://www.google.com/', wait_until='networkidle', timeout=30000)
        print('Loaded sunoffice.vn!')
        for s in scripts:
            if any(k in s for k in ['gtraffic', 'pages.dev', 'ontops', 'traffic', 'bt', 'btd', 'btf']):
                print('FOUND SCRIPT:', s)
        btn1 = page.locator('#trade-btn-clf').count()
        btn2 = page.locator('#trade-btn').count()
        print(f'Button count on sunoffice: #trade-btn-clf={btn1}, #trade-btn={btn2}')
    except Exception as e:
        print('Error on sunoffice:', e)
    finally:
        browser.close()
