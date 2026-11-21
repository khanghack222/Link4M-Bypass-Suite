import asyncio
from playwright.async_api import async_playwright

async def get_instant_token():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        print("[1] Navigating to https://link4m.net/go/68pw167Y ...")
        await page.goto("https://link4m.net/go/68pw167Y", wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        
        anchor_frame = None
        for f in page.frames:
            if "recaptcha/api2/anchor" in f.url:
                anchor_frame = f
                break

        if anchor_frame:
            print("[2] Clicking recaptcha anchor...")
            await anchor_frame.evaluate('() => { const b = document.getElementById("recaptcha-anchor"); if(b) b.click(); }')
            await asyncio.sleep(2)
            
            checked = await anchor_frame.evaluate('() => { const el = document.getElementById("recaptcha-anchor"); return el ? el.getAttribute("aria-checked") : null; }')
            print(f"[3] Checkbox aria-checked: {checked}")
            
            bframe = None
            for f in page.frames:
                if "recaptcha/api2/bframe" in f.url:
                    bframe = f
                    break
            if bframe:
                txt = await bframe.evaluate('() => document.body.innerText')
                print(f"[Challenge Popup Triggered]: {txt[:120].strip()}")
            
            token = await page.evaluate('''() => {
                const el = document.getElementById("g-recaptcha-response") || document.querySelector("[name='g-recaptcha-response']");
                return el ? el.value : "";
            }''')
            
            g_resp = await page.evaluate('''() => {
                try { return window.grecaptcha ? grecaptcha.getResponse() : ""; } catch(e) { return ""; }
            }''')
            
            final_token = token or g_resp
            print(f"[4] Token extracted: {final_token}")
            print(f"[5] Token length: {len(final_token)}")
        else:
            print("Anchor frame not found")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(get_instant_token())
