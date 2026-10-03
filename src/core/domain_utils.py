# -*- coding: utf-8 -*-
"""
⚡ DOMAIN UTILITIES MODULE ⚡
Zero-dependency domain unmasking, TLD recognition, and normalization.
"""

import re
from typing import List

VALID_TLDS = [
    'com.vn', 'com.tw', 'co.uk', 'co.jp', 'za.com', 'de.com', 'uk.com', 'jpn.com', 'gb.net', 'jp.net', 'cn.com',
    'in.net', 'com.co', 'co.in', 'net.in', 'stridewalk.in', 'org.vn', 'edu.vn', 'pro', 'fun', 'bet', 'asia',
    'com', 'net', 'org', 'io', 'cc', 'me', 'vn', 'tw', 'vip', 'tv', 'co', 'site', 'top', 'online', 'xyz',
    'info', 'biz', 'club', 'games', 'app', 'live', 'ai', 'in', 'us', 'uk'
]
TLD_REGEX = '|'.join([re.escape(t) for t in sorted(VALID_TLDS, key=len, reverse=True)])

def unmask_domain_candidates(raw_text: str) -> List[str]:
    """Auto unmask domains with asterisks like shin-shih.co***.tw or site.c***"""
    results = []
    clean = raw_text.replace('★', '*').replace('x', 'x')

    # Pattern 1: domain.c***.tw / domain.co***.vn / domain.co***.tw
    for m in re.finditer(r'([a-zA-Z0-9\-]{2,})\.(?:co|c)\*+\.([a-zA-Z]{2,4})', clean, re.IGNORECASE):
        p, cc = m.group(1).lower(), m.group(2).lower()
        results.extend([f"{p}.com.{cc}", f"{p}.co.{cc}", f"{p}.{cc}"])

    # Pattern 2: domain.c*** or domain.co***
    for m in re.finditer(r'([a-zA-Z0-9\-]{2,})\.(?:co|c)\*+(?![a-zA-Z0-9])', clean, re.IGNORECASE):
        results.append(f"{m.group(1).lower()}.com")

    # Pattern 3: domain.n***
    for m in re.finditer(r'([a-zA-Z0-9\-]{2,})\.n\*+(?![a-zA-Z0-9])', clean, re.IGNORECASE):
        results.append(f"{m.group(1).lower()}.net")

    # Pattern 4: domain.o***
    for m in re.finditer(r'([a-zA-Z0-9\-]{2,})\.o\*+(?![a-zA-Z0-9])', clean, re.IGNORECASE):
        results.append(f"{m.group(1).lower()}.org")

    # Pattern 5: domain.v***
    for m in re.finditer(r'([a-zA-Z0-9\-]{2,})\.v\*+(?![a-zA-Z0-9])', clean, re.IGNORECASE):
        results.append(f"{m.group(1).lower()}.vn")

    # Pattern 6: split/masked domains like dawnseeker. .com or site.***.com
    for m in re.finditer(r'([a-zA-Z0-9\-]{3,})\.(?:[\s\*\.\-\_]+)(com|net|org|vn|tw|za\.com|co|site|vip)', clean, re.IGNORECASE):
        p, suf = m.group(1).lower(), m.group(2).lower()
        results.extend([f"{p}.za.{suf}", f"{p}.{suf}", f"{p}.com.{suf}", f"{p}.com", f"{p}.net", f"{p}.org"])

    # Pattern 7: Masked stem with asterisks like secgr***.vn, vinah***.com, f8b***.com
    COMMON_STEM_SUFFIXES = [
        'group', 'corp', 'land', 'bet', 'club', 'vn', 'tech', 'media', 'express',
        'taxi', 'moving', 'logistics', 'auto', 'pro', 'asia', 'invest', 'holding',
        'service', 'solution', 'security', 'soft', 'home', 'house', 'clean', 'real'
    ]
    for m in re.finditer(r'([a-zA-Z0-9\-]{3,})\*+\.([a-zA-Z0-9\.\-]+)', clean, re.IGNORECASE):
        prefix, ext = m.group(1).lower(), m.group(2).lower()
        results.append(f"{prefix}.{ext}")
        # Try blending prefix with common suffixes
        for suf in COMMON_STEM_SUFFIXES:
            for overlap in range(min(len(prefix), len(suf)), 0, -1):
                if prefix.endswith(suf[:overlap]):
                    candidate_stem = prefix + suf[overlap:]
                    results.append(f"{candidate_stem}.{ext}")
                    break
            results.append(f"{prefix}{suf}.{ext}")

    def _sanitize(dom_str: str) -> str:
        s = re.sub(r'^(?:b[uư][oơ]c|buroc)\s*\d*\s*', '', dom_str, flags=re.IGNORECASE)
        s = re.sub(r'^(?:bam|click|vao|tim|website|websiter|trangweb|web|site)+', '', s, flags=re.IGNORECASE)
        return s.strip('./- ')

    out = []
    for r in results:
        cleaned = _sanitize(r)
        if '.' in cleaned and len(cleaned.split('.')[0]) >= 2:
            out.append(cleaned)

    return list(dict.fromkeys(out))
