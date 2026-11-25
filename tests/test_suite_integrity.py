import sys
import os

SUITE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, SUITE_DIR)
sys.path.insert(0, os.path.join(SUITE_DIR, "src", "core"))

from auto_bypass import classify_url

def test_classifiers():
    test_cases = {
        "https://gtraffic.io/X3BR2OQ?ref=test": "GTRAFFIC",
        "https://direct.gtraffic.io/dr-client/ABC123": "GTRAFFIC",
        "https://bbmkts.com/go/3p82s": "BBMKTS",
        "https://yeumoney.com/go/file/aHR0cHM6Ly9leGFtcGxlLmNvbQ==": "BBMKTS",
        "https://layma.net/pohWNZgba": "LAYMA",
        "https://trafficvn.net/get/MFGm2tAlcSn": "TRAFFICVN",
        "https://trafficvn.com/get/123": "TRAFFICVN",
        "https://octolink.vip/abc": "OCTOLINK",
        "https://link4m.co/go/abc": "LINK4M",
        "https://link4m.net/go/2kCcIqn": "LINK4M"
    }

    for url, expected in test_cases.items():
        res = classify_url(url)
        assert res == expected, f"FAILED for {url}: expected {expected}, got {res}"
        print(f"[PASS] {url} -> {res}")

def test_gtraffic_slug_extraction():
    urls = [
        ("https://gtraffic.io/X3BR2OQ", "X3BR2OQ"),
        ("https://gtraffic.io/X3BR2OQ/", "X3BR2OQ"),
        ("https://gtraffic.io/X3BR2OQ?ref=facebook&tag=123", "X3BR2OQ"),
        ("https://direct.gtraffic.io/dr-client/ABC123#anchor", "ABC123")
    ]
    for url, expected in urls:
        slug = url.split("?")[0].split("#")[0].strip().rstrip("/").split("/")[-1]
        assert slug == expected, f"Slug extraction failed for {url}: expected {expected}, got {slug}"
        print(f"[PASS] Slug from {url} -> {slug}")

def test_imports():
    import gtraffic_runner
    import layma_runner
    import trafficvn_runner
    import bbmkts_runner
    import bypass
    print("[PASS] All runner modules imported cleanly without missing dependencies!")

if __name__ == "__main__":
    print("=== RUNNING SUITE INTEGRITY TESTS ===")
    test_classifiers()
    test_gtraffic_slug_extraction()
    test_imports()
    print("=== ALL INTEGRITY CHECKS PASSED SUCCESSFULLY ===")
