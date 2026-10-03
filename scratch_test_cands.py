import sys, os
sys.path.insert(0, os.path.expandvars(r'%LOCALAPPDATA%\Programs\Python\Python311\Lib\site-packages'))
sys.path.insert(0, r'src/core')

from sponsor import extract_domain_candidates

lines = ['betlive', 'https://betlive', 'Vi-Vn', 'MU88BETLIVE4D-Va0Day', 'MU88.JP', 'VoiEm2026']
cands = extract_domain_candidates(lines)
print("Candidates count:", len(cands))
print("betlive4d.net in candidates?", 'betlive4d.net' in cands)

import urllib.request, ssl
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

for c in cands:
    if 'betlive4d' in c:
        url = f"https://{c}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=4) as resp:
                html = resp.read(524288).decode("utf-8", errors="ignore")
                is_btn = any(w in html for w in ['trade-btn', 'trade-btn-clf', 'traffic-button', 'trade-d-btn', 'pages.dev', 'btd.js'])
                print(f"Verified {c}: code={resp.status}, is_btn={is_btn}")
        except Exception as e:
            print(f"Error {c}: {e}")
