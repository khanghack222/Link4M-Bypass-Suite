import asyncio
import os
import shutil
from playwright.async_api import async_playwright

async def test_real_profile():
    # Make a lightweight profile copy or test launch
    user_data = os.path.join(os.getcwd(), "test_user_profile")
    os.makedirs(user_data, exist_ok=True)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=user_data,
            headless=False,
            channel="chrome", # Use real Google Chrome installation!
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
            ]
        )
        page = await browser.new_page()
        print("[*] Navigating to Google reCAPTCHA demo...")
        await page.goto("https://www.google.com/recaptcha/api2/demo")
        await asyncio.sleep(2)
        
        anchor = None
        for f in page.frames:
            if "recaptcha/api2/anchor" in f.url:
                anchor = f
                break
                
        if anchor:
            print("[*] Clicking anchor...")
            await anchor.click("#recaptcha-anchor")
            await asyncio.sleep(2)
            
            ticked = await anchor.evaluate("() => document.getElementById('recaptcha-anchor').getAttribute('aria-checked')")
            print(f"[*] Instant tick result: {ticked}")
            
            token = await page.evaluate("() => document.getElementById('g-recaptcha-response') ? document.getElementById('g-recaptcha-response').value : ''")
            print(f"[*] Token obtained: {token[:40]}... (length={len(token)})")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_real_profile())
