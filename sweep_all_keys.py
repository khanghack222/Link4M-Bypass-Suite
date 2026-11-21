import glob
import re
import urllib.request
import json
from concurrent.futures import ThreadPoolExecutor

files = glob.glob(r'C:\Users\XUAN\Downloads\captcha\*.txt')
all_text = ""
for f in files:
    try:
        with open(f, 'r', encoding='utf-8', errors='ignore') as fp:
            all_text += "\n" + fp.read()
    except Exception:
        pass

# Find all 32 hex character tokens
raw_tokens = re.findall(r'\b[a-f0-9]{32}\b', all_text, re.I)
unique_tokens = list(set([t.lower() for t in raw_tokens]))
print(f"Total unique 32-char hex candidates: {len(unique_tokens)}")

positive_keys = []

def check_key(k):
    try:
        url = f"http://2captcha.com/res.php?key={k}&action=getbalance&json=1"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3.0) as r:
            res = json.loads(r.read().decode())
            if res.get("status") == 1:
                bal = float(res.get("request", 0))
                print(f"[FOUND] {k} -> {bal} USD", flush=True)
                if bal > 0:
                    return (k, bal)
    except Exception:
        pass
    return None

with ThreadPoolExecutor(max_workers=25) as executor:
    results = executor.map(check_key, unique_tokens)
    for res in results:
        if res:
            positive_keys.append(res)

print("="*50)
print(f"Total positive keys found: {len(positive_keys)}")
for k, b in positive_keys:
    print(f"KEY: {k} | Balance: {b}")

with open("found_positive_keys.txt", "w") as out:
    for k, b in positive_keys:
        out.write(f"{k}:{b}\n")
