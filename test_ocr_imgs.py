import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'core'))
sys.path.insert(0, os.path.dirname(__file__))

from sponsor import get_ocr, extract_quest_instructions

ocr = get_ocr()
for i in range(4):
    fpath = f"scratch_img_{i}.png"
    if os.path.exists(fpath):
        with open(fpath, "rb") as f:
            b = f.read()
        res, _ = ocr(b)
        texts = [r[1] for r in res] if res else []
        print(f"Img {i} OCR: {texts}")

all_lines = []
for i in range(4):
    with open(f"scratch_img_{i}.png", "rb") as f:
        res, _ = ocr(f.read())
        if res:
            all_lines.extend([r[1] for r in res])

print("\n--- ALL LINES ---")
print(all_lines)
quest = extract_quest_instructions(all_lines)
print("\n--- EXTRACTED QUEST ---")
print(quest)
