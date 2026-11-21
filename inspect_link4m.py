import requests
import re
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

r = requests.get('https://link4m.net/go/68pw167Y', headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
print('Page status:', r.status_code)

forms = re.findall(r'<form[^>]*>.*?</form>', r.text, re.S)
print(f'Total forms: {len(forms)}')
for idx, f in enumerate(forms):
    print(f'=== FORM {idx} ===\n{f}\n')

scripts = re.findall(r'<script[^>]*>(.*?)</script>', r.text, re.S)
for s in scripts:
    if 'recaptcha' in s.lower() or 'token' in s.lower() or 'submit' in s.lower():
        print(f'=== SCRIPT ===\n{s}\n')
