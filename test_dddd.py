import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'core'))
sys.path.insert(0, os.path.dirname(__file__))

from sponsor import get_dddd

dddd = get_dddd()
if dddd:
    with open("scratch_img_3.png", "rb") as f:
        res = dddd.classification(f.read())
    print("DDDD OCR on img 3:", res)
else:
    print("DDDD not available")
