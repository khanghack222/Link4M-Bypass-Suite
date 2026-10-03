from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    # Give it fake storage quota or override detectIncognito
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    page = context.new_page()

    page.on("request", lambda r: print(f"--> {r.method} {r.url[:100]}"))
    page.on("response", lambda r: print(f"<-- {r.status} {r.url[:100]}"))
    page.on("console", lambda m: print(f"[CONSOLE] {m.text}"))

    # Goto secgroup.vn with Google referrer
    page.goto("https://secgroup.vn", referer="https://www.google.com/")
    time.sleep(3)

    # Check widget element
    res = page.evaluate('''() => {
        const scripts = Array.from(document.querySelectorAll('script')).map(s => s.src).filter(s => s.includes('what-on'));
        const btns = Array.from(document.querySelectorAll('button, div')).filter(e => e.innerText && e.innerText.includes('LẤY MÃ')).map(e => ({
            tag: e.tagName,
            id: e.id,
            className: e.className,
            text: e.innerText,
            parent: e.parentElement ? e.parentElement.tagName + '#' + e.parentElement.id : null
        }));
        const allDivsWithKey = Array.from(document.querySelectorAll('div[id]')).filter(d => d.id.length >= 5 && d.id.length <= 8).map(d => d.id);
        return { scripts, btns, allDivsWithKey };
    }''')
    print("PAGE INFO:", res)

    # Click the button
    print("\n--- ATTEMPTING CLICK ---")
    click_res = page.evaluate('''() => {
        const btn = document.querySelector('button');
        const btns = Array.from(document.querySelectorAll('button')).filter(b => b.innerText.includes('LẤY MÃ'));
        if (btns.length > 0) {
            btns[0].click();
            return { clicked: true, tag: btns[0].tagName, id: btns[0].id };
        }
        return { clicked: false };
    }''')
    print("CLICK RESULT:", click_res)

    # Wait 5s and check what happens
    time.sleep(5)
    body_text = page.evaluate('''() => {
        const whaton = document.querySelector('.whatoncode') || document.querySelector('.whatoncode-wrapper');
        return {
            whaton_html: whaton ? whaton.outerHTML : null,
            wrapper_text: whaton ? whaton.innerText : null
        };
    }''')
    print("AFTER CLICK WIDGET:", body_text)

    browser.close()
