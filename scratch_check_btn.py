import re

html = open('page2_dump.html', encoding='utf-8').read()
for s in re.findall(r'<script[^>]*src=[\'"][^\'"]*btd\.js[^\'"]*[\'"][^>]*>', html):
    print("BTD SCRIPT:", s)
for s in re.findall(r'<script[^>]*src=[\'"][^\'"]*andanh\.js[^\'"]*[\'"][^>]*>', html):
    print("ANDANH SCRIPT:", s)
