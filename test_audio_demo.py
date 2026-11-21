import asyncio
from playwright.async_api import async_playwright

async def test_audio():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.navigator.chrome = { runtime: {} };
        """)
        page = await context.new_page()
        print("[*] Navigating to google demo...")
        await page.goto("https://www.google.com/recaptcha/api2/demo")
        await asyncio.sleep(2)
        
        anchor = None
        for f in page.frames:
            if "recaptcha/api2/anchor" in f.url:
                anchor = f
                break
        if anchor:
            await anchor.click("#recaptcha-anchor")
            await asyncio.sleep(2)
            
            ticked = await anchor.evaluate("() => document.getElementById('recaptcha-anchor').getAttribute('aria-checked')")
            print("[*] Demo ticked:", ticked)
            
            bframe = None
            for f in page.frames:
                if "recaptcha/api2/bframe" in f.url:
                    bframe = f
                    break
            if bframe:
                btn = await bframe.query_selector("#recaptcha-audio-button")
                if btn:
                    print("[*] Clicking audio button...")
                    await btn.click()
                    await asyncio.sleep(2)
                    txt = await bframe.evaluate("() => document.body.innerText")
                    print("[*] Bframe text after audio click:\n", txt[:300].strip())
                    
                    audio_link = await bframe.evaluate("""() => {
                        const a = document.querySelector('.rc-audiochallenge-tdownload-link, a.rc-audiochallenge-download-link, a[href*="audio.mp3"]');
                        return a ? a.href : null;
                    }""")
                    print("[*] Audio link:", audio_link)
                else:
                    print("[!] No audio button found")
                    
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_audio())
