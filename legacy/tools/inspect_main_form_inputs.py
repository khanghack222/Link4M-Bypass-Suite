import time
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://link4m.net/go/68pw167Y')
    time.sleep(3)
    inputs = page.evaluate('() => Array.from(document.querySelectorAll("#main-form input")).map(i => ({ name: i.name, value: i.value, type: i.type }))')
    print('Inputs in #main-form after 3s:', inputs)
    browser.close()
