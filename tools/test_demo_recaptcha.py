import sys
sys.path.insert(0, 'src/core')
from patchright.sync_api import sync_playwright
from recaptcha_solver import get_solver

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://google.com/recaptcha/api2/demo', wait_until='networkidle')
    solver = get_solver(headless=True)
    res = solver.solve_on_page(page)
    print('DEMO RECAPTCHA RESULT:', res)
    browser.close()
