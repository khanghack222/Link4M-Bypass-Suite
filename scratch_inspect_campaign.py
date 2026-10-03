import sys, os, time, json, re
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page()
    
    def on_resp(res):
        if 'campaign/get-advertise' in res.url:
            try:
                data = res.json()
                print('GET-ADVERTISE SUCCESS:', data.get('success'))
                html = data.get('html', '')
                print('Html length:', len(html))
                imgs = re.findall(r'src=["\']([^"\']+\.(?:png|jpg|jpeg|webp))["\']', html)
                print('Images in campaign:', imgs)
                anchors = re.findall(r'href=["\']([^"\']+)["\']', html)
                print('Links in campaign:', anchors[:5])
                with open('current_campaign.html', 'w', encoding='utf-8') as f:
                    f.write(html)
            except Exception as e:
                print('Resp error:', e)
                
    pg.on('response', on_resp)
    pg.goto('https://link4m.net/go/2kCcIqn')
    pg.wait_for_timeout(4000)
    b.close()
