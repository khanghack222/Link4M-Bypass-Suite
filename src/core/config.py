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

def _has_runtime_deps(py_bin: str) -> bool:
    """True nếu interpreter [PERSON_NAME]/patchright — tránh re-exec sang Python hệ thống."""
    for module in ("patchright", "playwright"):
        try:
            res = subprocess.run(
                [py_bin, "-c", f"import {module}"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20,
            )
            if res.returncode == 0:
                return True
        except (OSError, subprocess.SubprocessError):
            return False
    return False


def get_python_executable() -> str:
    """Finds best available Python runtime across Windows and Linux environments."""
    if os.environ.get("PYTHON_PATH") and os.path.exists(os.environ["PYTHON_PATH"]):
        return os.environ["PYTHON_PATH"]
    candidates = [
        sys.executable,
        os.path.join(BASE_DIR, ".venv", "bin", "python"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python311", "python.exe"),
        r"C:\Python311\python.exe",
        "/usr/bin/python3",
        "/usr/local/bin/python3",
    ]
    for c in candidates:
        if c and os.path.exists(c) and _has_runtime_deps(c):
            return c
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
            line = line.split("#")[0].strip()
            if not line:
                continue

            proto = "http"
            addr = line
            if "://" in line:
                proto, addr = line.split("://", 1)

            parts = addr.split(":")
            if len(parts) == 4:
                proxies.append({
                    "server": f"{proto}://{parts[0]}:{parts[1]}",
                    "username": parts[2],
                    "password": parts[3],
                    "raw": line
                })
            elif len(parts) == 2:
                proxies.append({
                    "server": f"{proto}://{parts[0]}:{parts[1]}",
                    "raw": line
                })
    return proxies

def get_chrome_path():
    env_bin = os.environ.get("CHROME_BIN")
    if env_bin and os.path.exists(env_bin):
        return env_bin
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        "/usr/bin/google-chrome",
        "/opt/google/chrome/chrome",
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

# Đường dẫn extension iNooJS (tuỳ chọn). Không đặt mặc định vì repo không
# chứa extension này nữa; chỉ dùng khi người dùng trỏ env vào bản có sẵn.
INOOJS_EXT_PATH = os.environ.get("INOOJS_EXT_PATH", "").strip()

def get_browser_launch_args(extra_args: list = None) -> list:
    args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-infobars",
        "--disable-dev-shm-usage",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1280,720",
        "--enable-features=DnsOverHttps",
        "--dns-over-https-templates=https://dns.google/dns-query"
    ]
    if os.path.exists(INOOJS_EXT_PATH):
        args.extend([
            f"--disable-extensions-except={INOOJS_EXT_PATH}",
            f"--load-extension={INOOJS_EXT_PATH}"
        ])
    if extra_args:
        args.extend(extra_args)
    return args

def get_clipboard_text() -> str:
    """Reads text directly from Windows Clipboard."""
    return get_clipboard()

STEALTH_INIT_SCRIPT = """
    // 1. Full Bypass Ẩn Danh (Anti-Incognito & Quota Hook by iNoo)
    try {
        const _IDBFactory = window.IDBFactory;
        if (_IDBFactory && _IDBFactory.prototype) {
            const _open = _IDBFactory.prototype.open;
            _IDBFactory.prototype.open = function (name, version) {
                const req = _open.apply(this, arguments);
                const _addEventListener = req.addEventListener.bind(req);
                Object.defineProperty(req, 'onupgradeneeded', {
                    set(handler) {
                        _addEventListener('upgradeneeded', function (event) {
                            const db = event.target.result;
                            const _createObjectStore = db.createObjectStore.bind(db);
                            db.createObjectStore = function (...args) {
                                const store = _createObjectStore(...args);
                                const _put = store.put.bind(store);
                                store.put = function (value, ...rest) {
                                    try { return _put(value, ...rest); } catch (_) {
                                        return _put(new Uint8Array([1]).buffer, ...rest);
                                    }
                                };
                                return store;
                            };
                            handler(event);
                        });
                    },
                    get() { return null; }
                });
                return req;
            };
        }
    } catch (_) {}

    try {
        if (navigator.webkitTemporaryStorage) {
            navigator.webkitTemporaryStorage.queryUsageAndQuota = function (success, error) {
                const fakeQuota = (performance?.memory?.jsHeapSizeLimit ?? 1073741824) * 4;
                const fakeUsage = 1024 * 1024;
                if (typeof success === 'function') success(fakeUsage, fakeQuota);
            };
        }
    } catch (_) {}

    try {
        if (window.webkitRequestFileSystem) {
            window.webkitRequestFileSystem = function (type, size, successCb, errorCb) {
                if (successCb) successCb({ root: {} });
            };
        }
    } catch (_) {}

    try {
        if (window.openDatabase) {
            const _origOpen = window.openDatabase.bind(window);
            window.openDatabase = function (name, ver, desc, size, cb) {
                try { return _origOpen(name, ver, desc, size, cb); }
                catch (_) {
                    return { transaction: () => {}, readTransaction: () => {} };
                }
            };
        }
    } catch (_) {}

    const _patchDetectIncognito = () => {
        if (typeof window.detectIncognito === 'function') {
            const _orig = window.detectIncognito;
            window.detectIncognito = function () {
                return Promise.resolve({ isPrivate: false, browserName: _orig.browserName ?? 'Chrome' });
            };
        }
    };
    _patchDetectIncognito();
    document.addEventListener('DOMContentLoaded', _patchDetectIncognito);
    window.addEventListener('load', _patchDetectIncognito);

    // 2. Bypass Check Bot PCS (CPU Fingerprint auto-resolver by iNoo)
    try {
        function fakeCPUData(count = 6) {
            const base = 140 + Math.random() * 20;
            return Array.from({ length: count }, () => +(base + (Math.random() * 4 - 2)).toFixed(2)).join(', ');
        }
        function runCpuBypass() {
            let token = null;
            for (const s of document.querySelectorAll("script")) {
                const m = s.src?.match(/token=([a-f0-9]+)/);
                if (m) { token = m[1]; break; }
            }
            if (!token) return;
            fetch(`/nv_vantay/cpu_save_md.php?token=${token}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ cpu: fakeCPUData() })
            }).catch(() => {});
        }
        if (document.getElementById("cpu_btn")) {
            runCpuBypass();
        } else {
            const obs = new MutationObserver(() => {
                if (!document.getElementById("cpu_btn")) return;
                obs.disconnect();
                runCpuBypass();
            });
            document.addEventListener('DOMContentLoaded', () => {
                if (document.body) obs.observe(document.body, { childList: true, subtree: true });
            });
        }
    } catch (_) {}

    // 3. AudioContext & MediaDevices Mock (Enables Google reCAPTCHA Audio challenge)
    try {
        if (!navigator.mediaDevices) navigator.mediaDevices = {};
        navigator.mediaDevices.enumerateDevices = async () => [
            { kind: 'audiooutput', deviceId: 'default', label: 'Speakers (Realtek High Definition Audio)', groupId: 'audio-group-1' },
            { kind: 'audioinput', deviceId: 'default', label: 'Microphone (Realtek High Definition Audio)', groupId: 'audio-group-1' }
        ];
    } catch (_) {}

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
        # Desktop copy is a Windows-only convenience; on POSIX the literal
        # "~\\Desktop\\..." path lands inside the repo instead.
        if os.name == "nt":
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


