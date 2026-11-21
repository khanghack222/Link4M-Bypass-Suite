import os
import sys
import ssl
import json
import time
import urllib.request
import paramiko

sys.path.append(r'C:\Users\XUAN\.gemini\antigravity\scratch')
sys.path.append(r'C:\Users\XUAN\.gemini\antigravity\scratch\kho-anime-bi-mat')
from build_perfect_stealth_jar import build_perfect_stealth_jar

API_KEY = 'gz_live_ec3b4e4368ec39ede78f26cbdefc9a2f4b73dd5aa618bcef'
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def set_power(signal):
    data = json.dumps({'signal': signal}).encode('utf-8')
    req = urllib.request.Request(
        'https://api.gimzonodes.space/api/client/servers/de133d57/power',
        data=data,
        headers={'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'}
    )
    urllib.request.urlopen(req, context=ctx)
    print(f"[Power] Signal '{signal}' sent")

set_power('kill')
time.sleep(2)

cmd = "/bin/sh -c 'while true; do echo ALIVE $(date) > alive.txt; sleep 5; done'"
local_jar = r'C:\Users\XUAN\.gemini\antigravity\scratch\kho-anime-bi-mat\test_loop.jar'
build_perfect_stealth_jar(cmd, local_jar)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('gimzonodes.space', port=2022, username='kieuxuan257@gmail.com.de133d57', password='1234khang1234', timeout=15, look_for_keys=False, allow_agent=False)
sftp = ssh.open_sftp()
sftp.put(local_jar, 'server.jar', confirm=False)
sftp.close()
ssh.close()
print("Uploaded server.jar")

set_power('start')
time.sleep(5)

# Check resources
req = urllib.request.Request(
    'https://api.gimzonodes.space/api/client/servers/de133d57/resources',
    headers={'Authorization': f'Bearer {API_KEY}'}
)
with urllib.request.urlopen(req, context=ctx) as resp:
    print("Resources after start:", resp.read().decode())
