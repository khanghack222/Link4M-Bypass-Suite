import time
import os
import sys
import json
import requests
import re
from patchright.sync_api import sync_playwright

# Ponytail approach: Minimal, functional, no BS.
# If you want 0$ cost, no Vision AI, and server-side: We use a Warmed Profile.
# Run with --setup once to log into Google. Then run normally (headless).

def setup_profile():
    print("[*] Opening browser for setup. Please log into your Google Account.")
    print("[*] A logged-in Google account gives you INSTANT GREEN TICKS (0s, 0 CPU, 0$).")
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=os.path.abspath('google_profile'),
            headless=False,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto("https://accounts.google.com")
        print("[*] Close the browser window when you are done logging in.")
        try:
            page.wait_for_event("close", timeout=0)
        except:
            pass

def bypass_link(url):
    print(f"[*] Bypassing: {url}")
    if not os.path.exists('google_profile'):
        print("[!] Profile not found. Run 'python bypass_ponytail.py --setup' first!")
        return

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=os.path.abspath('google_profile'),
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto(url)
        
        # Click the captcha
        print("[*] Waiting for captcha...")
        try:
            frame = page.wait_for_selector("iframe[title*='reCAPTCHA']", timeout=10000).content_frame()
            frame.locator(".recaptcha-checkbox-border").click()
            print("[*] Clicked captcha. Waiting for green tick...")
            # Wait for green tick (aria-checked=true)
            frame.locator("span[aria-checked='true']").wait_for(timeout=10000)
            print("[+] Captcha bypassed!")
        except Exception as e:
            print("[-] Captcha failed. Ensure your Google account is trusted or you might need a proxy.")
            return
            
        time.sleep(2)
        print("[*] Extracting destination...")
        # Click continue/get link
        try:
            page.evaluate("document.querySelector('.get-link')?.click()")
            time.sleep(3)
            print("[+] Result URL:", page.url)
        except:
            print("[-] Could not click get link.")

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--setup':
        setup_profile()
    elif len(sys.argv) > 1:
        bypass_link(sys.argv[1])
    else:
        print("Usage: python bypass_ponytail.py <url> | --setup")
