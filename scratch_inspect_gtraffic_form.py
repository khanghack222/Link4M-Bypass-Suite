import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.expandvars(r'%LOCALAPPDATA%\Programs\Python\Python311\Lib\site-packages'))
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://gtraffic.io/X3BR2OQ', wait_until='networkidle')
    html = page.content()
    import re
    form_tags = re.findall(r'<form[^>]*>.*?</form>', html, re.DOTALL | re.I)
    print("Forms found:", len(form_tags))
    for f in form_tags:
        print(f[:500])
    
    # Also find all buttons and inputs
    btns = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('button, input[type="submit"], [role="button"], a.btn, .btn')).map(b => ({
            tag: b.tagName,
            id: b.id,
            className: b.className,
            text: b.innerText,
            onclick: b.getAttribute('onclick')
        }));
    }""")
    print("Buttons found:", btns)
    browser.close()
