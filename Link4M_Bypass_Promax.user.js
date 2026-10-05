// ==UserScript==
// @name         Link4M Auto Bypass Suite - Promax
// @namespace    https://github.com/
// @version      3.2.0
// @description  Auto Link4M & Sponsor Tasks (What-on/Gtraffic/Layma). Auto fill code, waits for user to solve captcha then auto submits.
// @author       Promax
// @match        *://*.link4m.net/*
// @match        *://*.link4m.co/*
// @match        *://*.link4m.app/*
// @match        *://*/*
// @exclude      *://*.google.com/*
// @exclude      *://*.youtube.com/*
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_openInTab
// @grant        GM_setClipboard
// @grant        GM_addStyle
// @grant        GM_xmlhttpRequest
// @connect      2captcha.com
// @connect      *
// @run-at       document_start
// ==/UserScript==

(function () {
    'use strict';

    const IS_L4M = /(?:link4m\.(?:net|co|app))/i.test(window.location.hostname);

    /* ══════════════════════════════════════════════════════════
       SPONSOR DOMAIN AUTOMATION (What-on / Gtraffic / Layma)
       ══════════════════════════════════════════════════════════ */
    if (!IS_L4M) {
        try {
            if (window.navigator?.webkitTemporaryStorage) {
                window.navigator.webkitTemporaryStorage.queryUsageAndQuota = (cb) => cb && cb(0, 107374182400);
            }
            Object.defineProperty(document, 'hidden', { get: () => false, configurable: true });
            Object.defineProperty(document, 'visibilityState', { get: () => 'visible', configurable: true });

            let y = 600;
            Object.defineProperty(window, 'pageYOffset', {
                get: () => { y += (Math.random() > 0.5 ? 6 : -4); return y; },
                configurable: true
            });

            setInterval(() => {
                window.dispatchEvent(new Event('scroll'));
                window.dispatchEvent(new Event('mousemove'));
            }, 350);
        } catch (e) {}

        const origOpen = XMLHttpRequest.prototype.open;
        XMLHttpRequest.prototype.open = function (m, url) {
            this._u = url;
            return origOpen.apply(this, arguments);
        };
        const origSend = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.send = function () {
            this.addEventListener('load', function () {
                try {
                    if (this._u && this._u.includes('get_quest_code')) {
                        const d = JSON.parse(this.responseText);
                        handleQuest(d);
                    }
                } catch (e) {}
            });
            return origSend.apply(this, arguments);
        };

        let codeDone = false, s1Done = false;

        function handleQuest(d) {
            if (!d?.success) return;
            if (d.id && !s1Done) {
                s1Done = true;
                setPill('Step 1 complete! Navigating article...');
                setTimeout(navArticle, 1500);
            } else if (d.html) {
                const s = String(d.html).trim();
                if (!s.includes('Vui lòng') && !s.includes('click') && s.length > 0) {
                    onCode(s);
                }
            }
        }

        function onCode(c) {
            if (codeDone) return;
            codeDone = true;
            GM_setValue('L4M_CODE', c);
            GM_setValue('L4M_STATE', 'DONE');
            setPill('Code found: ' + c);
            try { GM_setClipboard(c); } catch (e) {}
            setTimeout(() => window.close(), 3000);
        }

        function navArticle() {
            const h = window.location.hostname;
            const p = window.location.pathname;
            const links = Array.from(document.querySelectorAll('a[href]'));
            let target = null;
            for (const a of links) {
                const href = a.getAttribute('href');
                if (!href || href.startsWith('#') || href.startsWith('javascript:')) continue;
                try {
                    const u = new URL(href, window.location.origin);
                    if (u.hostname === h && u.pathname !== p && u.pathname.length > 3) {
                        if (!/lien-he|contact|privacy|terms|gioi-thieu/i.test(u.pathname)) {
                            target = u.href;
                            break;
                        }
                    }
                } catch (e) {}
            }
            if (target) window.location.href = target;
            else { window.location.hash = '#step2-' + Date.now(); window.location.reload(); }
        }

        function findBtn() {
            const exp = document.querySelector('#traffic-button, .whatoncode, button.whatoncode, #fC6by7 button, [id*="traffic_"] button');
            if (exp) return exp;
            for (const el of Array.from(document.querySelectorAll('button, a, div[role="button"]'))) {
                const t = (el.innerText || el.textContent || '').trim().toUpperCase();
                if (t.includes('LẤY MÃ') || t.includes('LAY MA') || t.includes('GET CODE') || t.includes('LẤY CODE')) return el;
            }
            return null;
        }

        function setPill(msg) {
            let p = document.getElementById('l4m-pill');
            if (!p && document.body) {
                p = document.createElement('div');
                p.id = 'l4m-pill';
                p.style.cssText = 'position:fixed!important;bottom:20px!important;left:20px!important;z-index:2147483647!important;' +
                    'background:rgba(15,23,42,0.95)!important;color:#00f0ff!important;padding:8px 16px!important;border-radius:9999px!important;' +
                    'font-family:sans-serif!important;font-size:12px!important;border:1px solid #00f0ff!important;box-shadow:0 0 15px rgba(0,240,255,0.4)!important;';
                document.body.appendChild(p);
            }
            if (p) p.innerText = '⚡ [BYPASS]: ' + msg;
        }

        window.addEventListener('DOMContentLoaded', () => {
            if (GM_getValue('L4M_STATE', 'IDLE') === 'IDLE') return;
            let count = 0;
            const t = setInterval(() => {
                count++;
                const whaton = document.querySelector('.whatoncode, .whatoncode-wrapper');
                if (whaton) {
                    const txt = whaton.innerText || '';
                    const m = txt.match(/Mã\s*(?:KM)?:?\s*([A-Za-z0-9_\-]+)/i);
                    if (m && m[1] && m[1].length >= 4) {
                        onCode(m[1].trim());
                        clearInterval(t);
                        return;
                    }
                    if ((txt.includes('click') || txt.includes('bài viết')) && !s1Done) {
                        s1Done = true;
                        setPill('Step 1 finished! Next...');
                        setTimeout(navArticle, 1500);
                        return;
                    }
                    const tm = txt.match(/(\d+)\s*s/i);
                    if (tm) setPill('Countdown: ' + tm[1] + 's...');
                }

                const b = findBtn();
                if (b && !b.dataset.l4m) {
                    b.dataset.l4m = '1';
                    setPill('Clicking button...');
                    b.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    setTimeout(() => b.click(), 600);
                }
                if (count > 400) clearInterval(t);
            }, 600);
        });
        return;
    }

    /* ══════════════════════════════════════════════════════════
       LINK4M PAGE AUTOMATION & HUD MENU
       ══════════════════════════════════════════════════════════ */

    GM_addStyle(`
        #l4m-hud { position:fixed!important; top:20px!important; right:20px!important; width:340px!important; z-index:2147483647!important;
            background:rgba(13,17,23,0.96)!important; backdrop-filter:blur(16px)!important; border:1px solid rgba(0,240,255,0.4)!important;
            border-radius:12px!important; box-shadow:0 20px 45px rgba(0,0,0,0.8), 0 0 20px rgba(0,240,255,0.2)!important;
            font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif!important; color:#f0f6fc!important; overflow:hidden!important; }
        #l4m-hud * { box-sizing:border-box!important; }
        .l4m-head { display:flex!important; justify-content:space-between!important; align-items:center!important; padding:10px 14px!important;
            background:linear-gradient(90deg,#1e293b,#0f172a)!important; border-bottom:1px solid rgba(255,255,255,0.1)!important; cursor:grab!important; }
        .l4m-title { font-size:13px!important; font-weight:800!important; background:linear-gradient(135deg,#00f0ff,#ff0080)!important;
            -webkit-background-clip:text!important; -webkit-text-fill-color:transparent!important; }
        .l4m-body { padding:12px!important; display:flex!important; flex-direction:column!important; gap:10px!important; }
        .l4m-card { background:#161b22!important; border:1px solid rgba(255,255,255,0.08)!important; border-radius:8px!important; padding:10px!important; font-size:12px!important; }
        .l4m-row { display:flex!important; justify-content:space-between!important; margin-bottom:4px!important; }
        .l4m-lbl { color:#8b949e!important; }
        .l4m-val { font-weight:600!important; color:#58a6ff!important; }
        .l4m-alert { display:none; background:rgba(234,88,12,0.25)!important; border:1px solid #f97316!important; border-radius:8px!important;
            padding:10px!important; text-align:center!important; animation:l4m-pulse 1.5s infinite!important; }
        .l4m-alert.show { display:block!important; }
        .l4m-alert-title { font-weight:800!important; font-size:12px!important; color:#fb923c!important; }
        .l4m-alert-desc { font-size:11px!important; color:#fdba74!important; margin-top:3px!important; }
        .l4m-btn { background:linear-gradient(135deg,#00f0ff,#0284c7)!important; color:#030712!important; border:none!important;
            border-radius:6px!important; padding:8px!important; font-weight:700!important; font-size:12px!important; cursor:pointer!important; text-align:center!important; }
        .l4m-btn:hover { filter:brightness(1.15)!important; }
        .l4m-log { background:#090d16!important; border:1px solid rgba(255,255,255,0.08)!important; border-radius:6px!important;
            height:85px!important; overflow-y:auto!important; padding:6px!important; font-family:monospace!important; font-size:11px!important; color:#94a3b8!important; }
        @keyframes l4m-pulse { 0%,100% { box-shadow:0 0 10px rgba(249,115,22,0.4); } 50% { box-shadow:0 0 20px rgba(249,115,22,0.8); } }
    `);

    function unmask(raw) {
        if (!raw) return [];
        const res = [];
        const clean = raw.replace(/★/g, '*').replace(/x/g, 'x');
        const p1 = /([a-zA-Z0-9\-]{2,})\.(?:co|c)\*+\.([a-zA-Z]{2,4})/gi;
        let m;
        while ((m = p1.exec(clean)) !== null) res.push(`${m[1].toLowerCase()}.com.${m[2].toLowerCase()}`, `${m[1].toLowerCase()}.${m[2].toLowerCase()}`);
        const p2 = /([a-zA-Z0-9\-]{2,})\.(?:co|c)\*+(?![a-zA-Z0-9])/gi;
        while ((m = p2.exec(clean)) !== null) res.push(`${m[1].toLowerCase()}.com`);
        const p3 = /(?:https?:\/\/)?([a-zA-Z0-9\-]{2,}\.[a-zA-Z]{2,}(?:\.[a-zA-Z]{2,})?)/gi;
        while ((m = p3.exec(clean)) !== null) {
            const d = m[1].toLowerCase();
            if (!d.includes('link4m') && !d.includes('google') && !d.includes('youtube')) res.push(d);
        }
        return Array.from(new Set(res));
    }

    let targetDomain = null, submitted = false;

    function buildHUD() {
        if (document.getElementById('l4m-hud')) return;
        const hud = document.createElement('div');
        hud.id = 'l4m-hud';
        hud.innerHTML = `
            <div class="l4m-head" id="l4m-drag">
                <span class="l4m-title">⚡ LINK4M PROMAX</span>
                <span id="l4m-min" style="cursor:pointer;color:#94a3b8;">_</span>
            </div>
            <div class="l4m-body" id="l4m-cnt">
                <div class="l4m-card">
                    <div class="l4m-row"><span class="l4m-lbl">Trạng thái:</span><span class="l4m-val" id="l4m-st">Đang quét...</span></div>
                    <div class="l4m-row"><span class="l4m-lbl">Tài trợ:</span><span class="l4m-val" id="l4m-dom">--</span></div>
                    <div class="l4m-row"><span class="l4m-lbl">Mã:</span><span class="l4m-val" id="l4m-code" style="color:#4ade80;">--</span></div>
                </div>
                <div class="l4m-alert" id="l4m-alert">
                    <div class="l4m-alert-title">⚠️ VUI LÒNG GIẢI CAPTCHA</div>
                    <div class="l4m-alert-desc">Tích Captcha bên dưới. Tool sẽ TỰ ĐỘNG nhấn Tiếp Tục ngay khi giải xong!</div>
                </div>
                <button class="l4m-btn" id="l4m-btn">🚀 CHẠY LẠI FLOW</button>
                <div class="l4m-log" id="l4m-logs"></div>
            </div>
        `;
        document.body.appendChild(hud);

        const h = document.getElementById('l4m-drag');
        let drag = false, sx, sy, il, it;
        h.addEventListener('mousedown', (e) => {
            drag = true; sx = e.clientX; sy = e.clientY;
            const r = hud.getBoundingClientRect();
            il = r.left; it = r.top;
            const onM = (ev) => {
                if (!drag) return;
                hud.style.right = 'auto';
                hud.style.left = (il + ev.clientX - sx) + 'px';
                hud.style.top = (it + ev.clientY - sy) + 'px';
            };
            const onU = () => { drag = false; window.removeEventListener('mousemove', onM); window.removeEventListener('mouseup', onU); };
            window.addEventListener('mousemove', onM);
            window.addEventListener('mouseup', onU);
        });

        document.getElementById('l4m-min').addEventListener('click', () => {
            const c = document.getElementById('l4m-cnt');
            c.style.display = c.style.display === 'none' ? 'flex' : 'none';
        });

        document.getElementById('l4m-btn').addEventListener('click', runFlow);
    }

    function log(msg, clr) {
        const l = document.getElementById('l4m-logs');
        if (!l) return;
        const div = document.createElement('div');
        div.style.color = clr || '#94a3b8';
        div.innerText = `[${new Date().toLocaleTimeString()}] ${msg}`;
        l.appendChild(div);
        l.scrollTop = l.scrollHeight;
    }

    function runFlow() {
        log('Bắt đầu phân tích trang...', '#00f0ff');
        const text = document.body.innerText || '';
        const list = unmask(text);
        if (list.length > 0) {
            targetDomain = list[0];
            document.getElementById('l4m-dom').innerText = targetDomain;
            log('Tìm thấy domain: ' + targetDomain, '#4ade80');
            openSponsor(targetDomain);
        } else {
            log('Chưa thấy domain, đợi API...', '#fb923c');
        }
    }

    function openSponsor(dom) {
        GM_setValue('L4M_STATE', 'RUNNING');
        GM_setValue('L4M_CODE', '');
        document.getElementById('l4m-st').innerText = 'Đang vượt tài trợ...';
        log('Mở tab tài trợ ngầm...', '#00f0ff');
        GM_openInTab('https://' + dom, { active: false, insert: true });
        watchCode();
    }

    function watchCode() {
        const t = setInterval(() => {
            const c = GM_getValue('L4M_CODE', '');
            if (c) {
                clearInterval(t);
                document.getElementById('l4m-code').innerText = c;
                log('Đã có mã: ' + c, '#4ade80');
                fillAndSubmit(c);
            }
        }, 800);
    }

    function fillAndSubmit(c) {
        document.querySelectorAll("input[name='password'], #password-2, #password, .password").forEach(inp => {
            inp.value = c;
            inp.dispatchEvent(new Event('input', { bubbles: true }));
            inp.dispatchEvent(new Event('change', { bubbles: true }));
        });
        document.querySelectorAll('#ad_banner, .modal-backdrop, [class*="overlay"]').forEach(el => el.remove());

        let token = '';
        document.querySelectorAll('[name="g-recaptcha-response"], [name="cf-turnstile-response"]').forEach(el => {
            if (el.value && el.value.length > 20) token = el.value;
        });

        const capBox = document.querySelector('.g-recaptcha, #recaptcha-2, #recaptcha, .cf-turnstile');
        if (capBox && !token) {
            solveCaptchaAuto(() => {
                doSubmit();
            });
        } else {
            doSubmit();
        }
    }

    function solveCaptchaAuto(onSolved) {
        const key = GM_getValue('L4M_2CAPTCHA_KEY', 'c77b0e8cbdf802ecf529296bf5bef91c');
        let sitekey = '6LcQsTQgAAAAADNQ_pCfukfvS0i9lk4oJTVSs5bZ';
        const el = document.querySelector('.g-recaptcha[data-sitekey], [data-sitekey]');
        if (el && el.getAttribute('data-sitekey')) sitekey = el.getAttribute('data-sitekey');

        log('Đang gửi 2Captcha Cloud giải reCAPTCHA v2...', '#00f0ff');
        document.getElementById('l4m-st').innerText = 'Đang giải Captcha tự động...';

        const inUrl = `https://2captcha.com/in.php?key=${key}&method=userrecaptcha&googlekey=${sitekey}&pageurl=${encodeURIComponent(window.location.href)}&json=1`;

        GM_xmlhttpRequest({
            method: 'GET',
            url: inUrl,
            timeout: 15000,
            onload: function(res) {
                try {
                    const data = JSON.parse(res.responseText);
                    if (data.status === 1) {
                        const taskId = data.request;
                        log(`2Captcha Task #${taskId} tạo thành công. Đang chờ giải...`, '#00f0ff');
                        let attempts = 0;
                        const pollInterval = setInterval(() => {
                            attempts++;
                            if (attempts > 30) {
                                clearInterval(pollInterval);
                                log('2Captcha hết thời gian chờ, chuyển sang thủ công.', '#fb923c');
                                fallbackManualCaptcha();
                                return;
                            }
                            GM_xmlhttpRequest({
                                method: 'GET',
                                url: `https://2captcha.com/res.php?key=${key}&action=get&id=${taskId}&json=1`,
                                timeout: 10000,
                                onload: function(pollRes) {
                                    try {
                                        const pData = JSON.parse(pollRes.responseText);
                                        if (pData.status === 1) {
                                            clearInterval(pollInterval);
                                            const token = pData.request;
                                            log('2Captcha giải thành công! Đang inject token...', '#4ade80');
                                            document.querySelectorAll('[name="g-recaptcha-response"], #g-recaptcha-response').forEach(e => {
                                                e.value = token;
                                            });
                                            try {
                                                if (window.___grecaptcha_cfg && window.___grecaptcha_cfg.clients) {
                                                    for (const cid in window.___grecaptcha_cfg.clients) {
                                                        const cl = window.___grecaptcha_cfg.clients[cid];
                                                        for (const k in cl) {
                                                            if (cl[k] && typeof cl[k].callback === 'function') {
                                                                cl[k].callback(token);
                                                            }
                                                        }
                                                    }
                                                }
                                            } catch (e) {}
                                            onSolved(token);
                                        } else if (pData.request !== 'CAPCHA_NOT_READY') {
                                            clearInterval(pollInterval);
                                            log(`2Captcha phản hồi lỗi: ${pData.request}`, '#ef4444');
                                            fallbackManualCaptcha();
                                        }
                                    } catch (e) {}
                                }
                            });
                        }, 4000);
                    } else {
                        log(`2Captcha từ chối tạo task: ${data.request}`, '#fb923c');
                        fallbackManualCaptcha();
                    }
                } catch (e) {
                    fallbackManualCaptcha();
                }
            },
            onerror: function() {
                log('Lỗi kết nối 2Captcha API, chuyển sang thủ công.', '#fb923c');
                fallbackManualCaptcha();
            }
        });
    }

    function fallbackManualCaptcha() {
        const capBox = document.querySelector('.g-recaptcha, #recaptcha-2, #recaptcha, .cf-turnstile');
        document.getElementById('l4m-alert').classList.add('show');
        document.getElementById('l4m-st').innerText = 'Chờ bạn giải Captcha';
        log('Vui lòng tích giải Captcha!', '#fb923c');
        if (capBox) capBox.scrollIntoView({ behavior: 'smooth', block: 'center' });

        const pollCap = setInterval(() => {
            let tk = '';
            document.querySelectorAll('[name="g-recaptcha-response"], [name="cf-turnstile-response"]').forEach(el => {
                if (el.value && el.value.length > 20) tk = el.value;
            });
            if (tk && tk.length > 20) {
                clearInterval(pollCap);
                document.getElementById('l4m-alert').classList.remove('show');
                log('Đã giải Captcha xong! Đang submit...', '#4ade80');
                doSubmit();
            }
        }, 500);
    }

    function doSubmit() {
        if (submitted) return;
        submitted = true;
        document.getElementById('l4m-st').innerText = 'Đang mở link đích...';

        const codeVal = GM_getValue('L4M_CODE', '');
        let validToken = '';
        document.querySelectorAll('[name="g-recaptcha-response"]').forEach(el => {
            if (el.value && el.value.length > 20) validToken = el.value;
        });

        const f2 = document.querySelector('#main-form-2');
        if (f2) {
            if (window.jQuery && typeof checkPassword === 'function') {
                window.check_form = jQuery(f2);
                try { checkPassword(); } catch (e) {}
            }
            const b = f2.querySelector('button[type="submit"], input[type="submit"], #btn-main-2, .btn, .get-link');
            if (b) b.click();
        }
        const f1 = document.querySelector('#main-form');
        if (f1) {
            const b = f1.querySelector('button[type="submit"], input[type="submit"], #btn-main, .btn, .get-link');
            if (b) b.click();
        }

        // Direct API dispatch fallback
        try {
            const forms = [f2, f1].filter(Boolean);
            forms.forEach(f => {
                const formData = new FormData(f);
                if (codeVal) formData.set('password', codeVal);
                if (validToken) formData.set('g-recaptcha-response', validToken);
                const params = new URLSearchParams(formData).toString();
                const endpoint = (window.api_domain || 'https://s1.link4m.app') + '/links/get-link-info';
                fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'X-Requested-With': 'XMLHttpRequest' },
                    body: params
                }).then(r => r.json()).then(res => {
                    if (res && res.url && !res.url.includes('link4m')) {
                        window.destination_url = res.url;
                        window.location.href = res.url;
                    }
                }).catch(() => {});
            });
        } catch (e) {}

        let c = 0;
        const destT = setInterval(() => {
            c++;
            if (window.destination_url && window.destination_url.startsWith('http') && !window.destination_url.includes('link4m')) {
                clearInterval(destT);
                window.location.href = window.destination_url;
                return;
            }
            const gl = document.querySelector('.get-link, a#get-link, a[href*="download"], #btn-get-link, .btn-success');
            if (gl) {
                const h = gl.getAttribute('href') || '';
                if (h.startsWith('http') && !h.includes('link4m') && !h.includes('about:blank')) {
                    clearInterval(destT);
                    window.location.href = h;
                    return;
                }
                if (!gl.classList.contains('disabled')) gl.click();
            }
            if (c > 30) clearInterval(destT);
        }, 500);
    }

    window.addEventListener('DOMContentLoaded', () => {
        buildHUD();
        setTimeout(runFlow, 1200);
    });
})();
