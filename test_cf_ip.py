import socket
import requests
import urllib3
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
urllib3.disable_warnings()

# Monkey patch getaddrinfo for 789-club.cc -> 104.21.17.228
orig_getaddrinfo = socket.getaddrinfo

def patched_getaddrinfo(host, port, *args, **kwargs):
    if host == '789-club.cc':
        host = '104.21.17.228'
    return orig_getaddrinfo(host, port, *args, **kwargs)

socket.getaddrinfo = patched_getaddrinfo

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Referer': 'https://www.google.com/',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7'
}

url = 'https://789-club.cc/'
try:
    r = requests.get(url, headers=headers, verify=False, timeout=10)
    print("Status:", r.status_code, "Length:", len(r.text))
    if 'Just a moment' in r.text:
        print("[!] Cloudflare Challenge triggered")
    else:
        print("[+] SUCCESS! Web content fetched without Cloudflare challenge!")
        # Search for widget scripts
        scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', r.text)
        print("\nScripts found:")
        for s in scripts:
            if any(k in s for k in ['traffic', 'what-on', 'yoads', 'widget', 'service', 'key', 'analytics']):
                print(' -', s)
        for s in re.findall(r'<script[^>]*>(.*?)</script>', r.text, re.DOTALL):
            if any(k in s for k in ['traffic_key', 'traffic_domain', 'traffic_session', 'what-on']):
                print('\nFound inline config:\n', s.strip()[:600])
except Exception as e:
    print("Error:", e)
