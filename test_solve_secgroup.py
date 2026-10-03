import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'core'))
sys.path.insert(0, os.path.dirname(__file__))

from playwright.sync_api import sync_playwright
from sponsor import solve_sponsor_quest

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    code = solve_sponsor_quest(context, ["https://secgroup.vn"])
    print(f"\n[+] RESULT CODE FROM SECGROUP: {code}")
    browser.close()
