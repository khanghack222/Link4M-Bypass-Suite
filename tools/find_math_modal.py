import re
from bs4 import BeautifulSoup

with open("data/temp/123bloom_after_click.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")
tb = soup.find(id="traffic-button-no")
if tb:
    print("traffic-button-no found:")
    print(tb.prettify()[:1000])

# Look for all elements with class containing 'answer' or 'captcha' or 'math'
for el in soup.find_all(lambda tag: any(k in str(tag.get("class", "")) or k in str(tag.get("id", "")) for k in ["captcha", "math", "answer", "ontop"])):
    print("MATCH:", el.name, el.get("id"), el.get("class"))
    print(el.prettify()[:300])

# Also look for images with data:image/png
for img in soup.find_all("img"):
    src = img.get("src", "")
    if src.startswith("data:image"):
        print("Found base64 img:", src[:50], "parent:", img.parent.name if img.parent else None)
