import sys, os, json, re, base64
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'core'))
sys.path.insert(0, os.path.dirname(__file__))

from sponsor import extract_quest_instructions, extract_domain_candidates, fallback_ai_search, probe_domain_live
from domain_utils import unmask_domain_candidates

with open("scratch_link4m_advertise.json", "r", encoding="utf-8") as f:
    d = json.load(f)

html = d['data']['html']
b64_matches = re.findall(r'src=["\'](data:image/[^"\']+)["\']', html)
print(f"Total b64 images: {len(b64_matches)}")

from sponsor import get_ocr
ocr = get_ocr()
all_texts = []
for idx, b64_str in enumerate(b64_matches[:4]):
    raw_b64 = b64_str.split(",", 1)[1] if "," in b64_str else b64_str
    b = base64.b64decode(raw_b64)
    res, _ = ocr(b)
    if res:
        texts = [r[1].strip() for r in res if len(r) > 1 and r[1].strip()]
        all_texts.extend(texts)
        print(f"Img {idx}: {texts}")

print("All texts:", all_texts)
quest_info = extract_quest_instructions(all_texts)
print("Quest info:", quest_info)

# Now test fallback_ai_search
keyword = quest_info.get("keyword", "")
domain_hint = quest_info.get("domain_hint", "")
clean_stem = domain_hint.replace('www.', '').split('.')[0].replace('*', '').strip()

search_query = f"{keyword} {clean_stem}"
print("Search query:", search_query)
ai_results = fallback_ai_search(search_query, domain_hint)
print("AI search results:", ai_results)

# Check candidates
candidates = extract_domain_candidates(all_texts, quest_info=quest_info)
for ar in ai_results:
    if ar not in candidates:
        candidates.insert(0, ar)
print("Candidates before probe:", candidates[:10])

# Probe each
for c in candidates[:5]:
    p = probe_domain_live(c)
    print(f"Candidate {c} -> probe: {p}")
