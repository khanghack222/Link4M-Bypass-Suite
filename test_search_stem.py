import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'core'))
sys.path.insert(0, os.path.dirname(__file__))

from sponsor import fallback_ai_search

q = "chuyen nha tron goi secgr"
print(f"Testing search: {q}")
results = fallback_ai_search(q, "secgr.vn")
print("Results:", results)
