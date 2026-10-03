import urllib.request
import re

url = "https://bbmkts.com/go/PGzlY"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
try:
    html = urllib.request.urlopen(req, timeout=15).read().decode('utf-8', errors='ignore')
    print('HTML len:', len(html))
    canvas = [s for s in re.findall(r'<script[^>]*>(.*?)</script>', html, re.S) if 'imgCanvas' in s]
    print('Canvas found:', len(canvas))
    if canvas:
        print('Canvas content:', canvas[0][:200])
    imgs = re.findall(r'https?://bbmkts\.com/uploads/[^\s\'"]+', html)
    print('Upload imgs:', imgs)
except Exception as e:
    print('Error:', e)
