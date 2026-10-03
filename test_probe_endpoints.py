import urllib.request, ssl, json

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

campaign_id = '68e9d2c359129e58d7045122'
display_id = '6ac05f5ca64e3dfeb10f7077'
code = '082f65583db349bc22c422b01730e52e'

endpoints = [
    f'/api/campaign/get?campaign_id={campaign_id}',
    f'/api/campaign/info?campaign_id={campaign_id}',
    f'/api/campaign/detail?campaign_id={campaign_id}',
    f'/api/campaign/details?id={campaign_id}',
    f'/api/campaign/get-campaign?id={campaign_id}',
    f'/api/campaign/show?id={campaign_id}',
    f'/api/campaign/view?id={campaign_id}',
    f'/api/campaign/get-advertise-info?campaign_id={campaign_id}',
    f'/api/campaign/check?campaign_id={campaign_id}',
    f'/widget/click.html?campaign_id={campaign_id}&display_id={display_id}&code={code}',
    f'/widget/info.html?campaign_id={campaign_id}',
    f'/widget/get-code.html?campaign_id={campaign_id}',
]

for ep in endpoints:
    url = 'https://s1.link4m.app' + ep
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://link4m.net/'
        }
    )
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=3) as r:
            body = r.read().decode('utf-8', errors='ignore')
            print(f"200 OK: {ep} -> {body[:150]}")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            print(f"HTTP {e.code}: {ep}")
    except Exception:
        pass
