import os
import sys

_py311_site = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python311", "Lib", "site-packages")
if os.path.exists(_py311_site) and _py311_site not in sys.path:
    sys.path.insert(0, _py311_site)

import time
import subprocess

CORE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(CORE_DIR, "..", ".."))
ROOT_DIR = BASE_DIR
LOG_FILE = os.path.join(BASE_DIR, "e2e_bypass.log")
DEST_FILE = os.path.join(BASE_DIR, "destination_url.txt")
CODE_FILE = os.path.join(BASE_DIR, "extracted_code.txt")
PROXIES_FILE = os.path.join(BASE_DIR, "proxies.txt")

def get_python_executable() -> str:
    """Finds best available Python runtime across Windows and Linux environments."""
    if os.environ.get("PYTHON_PATH") and os.path.exists(os.environ["PYTHON_PATH"]):
        return os.environ["PYTHON_PATH"]
    candidates = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python311", "python.exe"),
        r"C:\Python311\python.exe",
        "/usr/bin/python3",
        "/usr/local/bin/python3",
        sys.executable
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return sys.executable

def ensure_python_runtime():
    """Auto-reruns script under Python 3.11/Playwright interpreter if needed."""
    py_bin = get_python_executable()
    if os.path.exists(py_bin) and os.path.abspath(sys.executable).lower() != os.path.abspath(py_bin).lower():
        cmd = [py_bin] + sys.argv
        res = subprocess.run(cmd)
        sys.exit(res.returncode)

def load_proxies():
    if not os.path.exists(PROXIES_FILE):
        return []
    proxies = []
    with open(PROXIES_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip().lstrip('\ufeff')
            if not line or line.startswith("#"):
                continue
            parts = line.split(":")
            if len(parts) == 4:
                proxies.append({
                    "server": f"http://{parts[0]}:{parts[1]}",
                    "username": parts[2],
                    "password": parts[3],
                    "raw": line
                })
            elif len(parts) == 2:
                proxies.append({
                    "server": f"http://{parts[0]}:{parts[1]}",
                    "raw": line
                })
    return proxies

def get_chrome_path():
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser"
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    # Return None so Playwright uses its built-in installed Chromium on Linux/Cloud
    return None

CHROME_PATH = get_chrome_path()

def log(msg: str):
    print(f"[{time.strftime('%X')}] {msg}", flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%X')}] {msg}\n")
    except Exception:
        pass

def copy_to_clipboard(text: str) -> bool:
    # Disabled by user request
    return True

def get_clipboard() -> str:
    """Reads URL directly from Windows Clipboard with 0.001ms ctypes latency."""
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.GetClipboardData.argtypes = [wintypes.UINT]
        user32.GetClipboardData.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_wchar_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.restype = wintypes.BOOL

        if user32.OpenClipboard(None):
            try:
                CF_UNICODETEXT = 13
                h_clip = user32.GetClipboardData(CF_UNICODETEXT)
                if h_clip:
                    text = kernel32.GlobalLock(h_clip)
                    kernel32.GlobalUnlock(h_clip)
                    if text:
                        return text.strip()
            finally:
                user32.CloseClipboard()
    except Exception:
        pass
    return ""

def get_clipboard_text() -> str:
    """Reads text directly from Windows Clipboard."""
    return get_clipboard()
STEALTH_INIT_SCRIPT = """
    // 1. Quota & Webdriver & Incognito bypass
    window.detectIncognito = async function() {
        return { isPrivate: false, browserName: 'Chrome' };
    };
    if (window.navigator && window.navigator.webkitTemporaryStorage) {
        window.navigator.webkitTemporaryStorage.queryUsageAndQuota = function(success, error) {
            if (typeof success === 'function') success(0, 100 * 1024 * 1024 * 1024);
        };
    }
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    window.mouse_scroll = true;
    window.traffic_click = true;

    // 2. Fake Google Referrer
    try {
        Object.defineProperty(document, 'referrer', {
            get: () => 'https://www.google.com/',
            configurable: true
        });
    } catch (e) {}

    // 3. Always Active (Anti-Blur / Anti-Tab Switch / Fake Visibility)
    try {
        Object.defineProperty(document, 'hidden', {
            get: () => false,
            configurable: true
        });

        Object.defineProperty(document, 'visibilityState', {
            get: () => 'visible',
            configurable: true
        });

        Object.defineProperty(document, 'webkitVisibilityState', {
            get: () => 'visible',
            configurable: true
        });

        window.hasFocus = () => true;

        const blockedEvents = [
            'visibilitychange',
            'webkitvisibilitychange',
            'blur',
            'mouseleave'
        ];

        blockedEvents.forEach(eventType => {
            window.addEventListener(eventType, (e) => {
                e.stopImmediatePropagation();
            }, true);

            document.addEventListener(eventType, (e) => {
                e.stopImmediatePropagation();
            }, true);
        });
    } catch (e) {}

    // 4. Anti-Headless Stealth Fingerprint
    try {
        Object.defineProperty(window, 'outerWidth', { get: () => window.innerWidth || 1280 });
        Object.defineProperty(window, 'outerHeight', { get: () => window.innerHeight || 720 });
        Object.defineProperty(screen, 'availWidth', { get: () => 1280 });
        Object.defineProperty(screen, 'availHeight', { get: () => 720 });
        Object.defineProperty(navigator, 'languages', { get: () => ['vi-VN', 'vi', 'en-US', 'en'] });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        if (!window.chrome) window.chrome = {};
        if (!window.chrome.runtime) window.chrome.runtime = {};
    } catch (e) {}
    window.__NUXT__ = window.__NUXT__ || {};
    window.__NUXT__.config = window.__NUXT__.config || {
            public: {
                baseUrl: (window.location && window.location.origin) || "https://direct.gtraffic.io",
                api_public: (window.location && window.location.origin && window.location.origin.includes('direct')) ? "https://dr-client.gtraffic.io/" : "https://client.gtraffic.io/",
                api_private: (window.location && window.location.origin && window.location.origin.includes('direct')) ? "https://dr-manager.gtraffic.io/" : "https://manager.gtraffic.io/",
                api_login: "https://drsso.gtraffic.io/",
                webName: "Gtraffic",
                webDescription: ""
            },
            app: { baseURL: "/", buildAssetsDir: "/_nuxt/", cdnURL: "" }
        };
"""

def save_destination(url: str, run_id: str = None):
    if not url or not isinstance(url, str) or not url.startswith("http"):
        return
    url = url.strip()
    active_run_id = run_id or os.environ.get("BYPASS_RUN_ID")
    try:
        if active_run_id:
            with open(os.path.join(ROOT_DIR, f"destination_url-{active_run_id}.txt"), "w", encoding="utf-8") as f_run:
                f_run.write(url)
        with open(DEST_FILE, "w", encoding="utf-8") as f:
            f.write(url)
        with open(os.path.join(ROOT_DIR, "DESTINATION_FINAL_URL.txt"), "w", encoding="utf-8") as f:
            f.write(url)
        desk = os.path.expanduser(r"~\Desktop\destination_url.txt")
        with open(desk, "w", encoding="utf-8") as fd:
            fd.write(url)
    except Exception:
        pass

def log_result_card(url: str, engine_name: str, duration: int = None):
    dur_str = f" | Thời gian: {duration}s" if duration is not None else ""
    log("==========================================")
    log(f"🎉 FINAL DESTINATION URL [{engine_name}]: {url}{dur_str}")
    log("==========================================")

def read_destination(run_id: str = None) -> str:
    active_run_id = run_id or os.environ.get("BYPASS_RUN_ID")
    paths = []
    if active_run_id:
        paths.append(os.path.join(ROOT_DIR, f"destination_url-{active_run_id}.txt"))
    paths.extend([os.path.join(ROOT_DIR, "DESTINATION_FINAL_URL.txt"), DEST_FILE])
    for path in paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    u = f.read().strip()
                    if u.startswith("http"):
                        return u
            except Exception:
                pass
    return ""


