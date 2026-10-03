import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'core'))
sys.path.insert(0, os.path.dirname(__file__))

from sponsor import detect_sponsor_domain

with open("scratch_link4m_advertise.json", "r", encoding="utf-8") as f:
    d = json.load(f)

cands = detect_sponsor_domain(None, campaign_payload=d['data'])
print("\n--- FINAL DETECTED SPONSOR CANDIDATES ---")
print(cands)
