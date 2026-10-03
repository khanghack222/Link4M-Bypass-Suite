import sys
import base64
import urllib.parse
import requests

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def decode_file_url(url):
    """Giai ma URL tu duong dan trang trung gian /go/file/<encoded> hoac query redirect"""
    if not url:
        return None

    # 0. Check query string params (dest, target, url, redirect, file, link)
    try:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        for k in ["dest", "target", "url", "redirect", "file", "link", "go"]:
            if k in qs and qs[k]:
                val = qs[k][0].strip()
                if val.startswith("http"):
                    return val
                try:
                    pad = (-len(val)) % 4
                    dec = base64.b64decode(val + ("=" * pad)).decode("utf-8", errors="ignore")
                    if dec.startswith("http"):
                        return dec
                except Exception:
                    pass
    except Exception:
        pass

    if '/go/file/' in url:
        part = url.split('/go/file/')[-1].split('?')[0].split('#')[0].strip('/')
        # 1. Base64 với dynamic padding
        try:
            pad = (-len(part)) % 4
            dec = base64.b64decode(part + ("=" * pad)).decode('utf-8', errors='ignore')
            if dec.startswith('http'):
                return dec
        except Exception:
            pass
        # 2. URL Decode
        try:
            dec = urllib.parse.unquote(part)
            if dec.startswith('http'):
                return dec
        except Exception:
            pass
    return None


def follow_destination(url):
    """Kiem tra chuyen huong link dich neu can"""
    try:
        r = requests.get(url, allow_redirects=False, timeout=5, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code in (301, 302, 303, 307, 308):
            return r.headers.get('Location')
    except Exception:
        pass
    return None

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Cú pháp: python decode_link.py <url>")
        sys.exit(1)

    input_url = sys.argv[1].strip()
    print(f"[*] Input: {input_url}")

    # Neu la link /go/file/
    if '/go/file/' in input_url:
        real_url = decode_file_url(input_url)
        if real_url:
            print(f"[+] Link gốc giải mã: {real_url}")
            next_hop = follow_destination(real_url)
            if next_hop:
                print(f"[+] Chuyển hướng tiếp theo: {next_hop}")
        else:
            print("[-] Không thể giải mã chuỗi.")
    elif '/go/' in input_url:
        print("[*] Link shortlink nhiệm vụ. Đang gọi engine bypass...")
        import subprocess
        auto_bypass_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "auto_bypass.py")
        subprocess.run([sys.executable, auto_bypass_path, input_url])
    else:
        # Thu decode truc tiep neu la chuoi ma hoa
        try:
            dec = base64.b64decode(input_url + '===').decode('utf-8')
            if dec.startswith('http'):
                print(f"[+] Base64 decoded: {dec}")
        except Exception:
            pass
