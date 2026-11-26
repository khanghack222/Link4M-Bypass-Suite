import sys
sys.path.insert(0, 'src/core')
import time
from patchright.sync_api import sync_playwright
from recaptcha_solver import get_solver

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://link4m.net/go/68pw167Y', wait_until='networkidle')
    solver = get_solver(headless=True)
    res = solver.solve_on_page(page, container_selector='#main-form')
    print('FULL SOLVE RESULT WITH PATCHRIGHT:', res)
    browser.close()
