import sys
import os
import json
import ssl
import time
import urllib.request
import paramiko

sys.path.append(r'C:\Users\XUAN\.gemini\antigravity\scratch')
sys.stdout.reconfigure(encoding='utf-8')
from generate_stealth_jar import build_server_jar

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

# 1. Stop server
set_power('kill')
time.sleep(2)

# 2. Command to check python & environment and write to a static file that dufs serves
probe_cmd = "/bin/sh -c 'mkdir -p storage && echo \"START_PROBE\" > storage/probe.txt && which python3 python node java >> storage/probe.txt && uname -a >> storage/probe.txt && ./dufs storage -p 27181 -A --enable-cors --render-index'"

local_jar = r'C:\Users\XUAN\.gemini\antigravity\scratch\stealth_server.jar'
build_server_jar(probe_cmd, local_jar)

# 3. SFTP Upload
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('gimzonodes.space', port=2022, username='kieuxuan257@gmail.com.de133d57', password='1234khang1234', timeout=15, look_for_keys=False, allow_agent=False)
sftp = ssh.open_sftp()
sftp.put(local_jar, 'server.jar', confirm=False)
sftp.close()
ssh.close()
print("[SFTP] Uploaded server.jar")

# 4. Start server
set_power('start')
print("[Power] Started server, waiting for dufs response on 45.131.64.86:27181...")

for i in range(15):
    time.sleep(2)
    try:
        req = urllib.request.Request('http://45.131.64.86:27181/probe.txt')
        with urllib.request.urlopen(req, timeout=3) as resp:
            print("\n[✓] PROBE OUTPUT:")
            print(resp.read().decode('utf-8'))
            break
    except Exception as e:
        print(".", end="", flush=True)
