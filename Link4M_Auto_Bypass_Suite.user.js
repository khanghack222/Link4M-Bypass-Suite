// ==UserScript==
// @name         Link4M Smart Auto-Bypass & Sponsor Assistant
// @namespace    https://antigravity.weat/link4m
// @version      2.0
// @description  Tự động vượt chờ 60s trên trang tài trợ (tự cuộn, tự chạy ngầm không bị đóng băng tab, tự qua bước 2 lấy mã), tự động điền mã vào Link4M và tự động mở link đích ngay khi bạn tick reCAPTCHA!
// @author       [T]ris
// @match        https://*.link4m.org/*
// @match        https://*.link4m.net/*
// @match        https://*.link4m.co/*
// @match        https://*.link4m.com/*
// @match        https://*.link4m.app/*
// @match        *://*/*
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_addValueChangeListener
// @grant        GM_notification
// @grant        window.focus
// @run-at       document-start
// ==/UserScript==

(function() {
    'use strict';

    const currentUrl = window.location.href;
    const isLink4M = /link4m\.(org|net|co|com|app)/i.test(window.location.hostname);

    // =========================================================================
    // PHẦN 1: TỰ ĐỘNG XỬ LÝ TRÊN LINK4M
    // =========================================================================
    if (isLink4M) {
        console.log('[Link4M Suite] Activated on Link4M page.');

        // Banner thông báo trạng thái
        function createLink4MBanner() {
            if (document.getElementById('link4m-suite-banner')) return;
            const banner = document.createElement('div');
            banner.id = 'link4m-suite-banner';
            banner.style.cssText = `
                position: fixed;
                top: 20px;
                left: 50%;
                transform: translateX(-50%);
                background: linear-gradient(135deg, #0f172a, #1e293b);
                color: #38bdf8;
                border: 2px solid #38bdf8;
                box-shadow: 0 8px 25px rgba(0,0,0,0.6);
                padding: 12px 24px;
                border-radius: 12px;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                font-size: 14px;
                font-weight: 600;
                z-index: 2147483647;
                text-align: center;
                min-width: 340px;
                pointer-events: none;
                transition: all 0.3s ease;
            `;
            banner.innerHTML = `
                <div style="font-size: 16px; margin-bottom: 4px; color: #fff;">⚡ Link4M Auto-Bypass Suite</div>
                <div id="link4m-status-msg" style="color: #94a3b8; font-size: 13px;">Đang tìm mã tài trợ từ trang quảng cáo...</div>
            `;
            document.body.appendChild(banner);
        }

        function updateBanner(text, isSuccess = false) {
            const el = document.getElementById('link4m-status-msg');
            if (el) {
                el.innerText = text;
                el.style.color = isSuccess ? '#4ade80' : '#38bdf8';
            }
        }

        // Lắng nghe khi có mã mới được trang sponsor thu hoạch
        if (typeof GM_addValueChangeListener === 'function') {
            GM_addValueChangeListener('link4m_latest_code', function(name, old_val, new_val) {
                if (new_val && new_val.code) {
                    fillCodeIntoForm(new_val.code);
                }
            });
        }

        function fillCodeIntoForm(code) {
            const pwdInput = document.querySelector('input[name="password"]');
            if (pwdInput) {
                pwdInput.value = code;
                pwdInput.dispatchEvent(new Event('input', { bubbles: true }));
                pwdInput.dispatchEvent(new Event('change', { bubbles: true }));
                updateBanner(`🎉 Đã tự động điền Mã: ${code}! Vui lòng tick reCAPTCHA bên dưới.`, true);
                pwdInput.style.border = '2px solid #22c55e';
                pwdInput.style.backgroundColor = '#f0fdf4';
            }
        }

        // Theo dõi XHR để bắt link đích ngay khi reCAPTCHA được submit
        const origXhrOpen = XMLHttpRequest.prototype.open;
        XMLHttpRequest.prototype.open = function(method, url, ...args) {
            if (typeof url === 'string' && (url.includes('get-link-info') || url.includes('check-captcha'))) {
                this.addEventListener('load', function() {
                    try {
                        const res = JSON.parse(this.responseText);
                        if (res.success && res.url) {
                            updateBanner(`🚀 Thành công! Đang chuyển hướng đến: ${res.url}`, true);
                            setTimeout(() => {
                                window.location.href = res.url;
                            }, 500);
                        }
                    } catch (e) {}
                });
            }
            return origXhrOpen.apply(this, [method, url, ...args]);
        };

        // Khởi động giao diện Link4M
        window.addEventListener('DOMContentLoaded', () => {
            createLink4MBanner();

            // Kiểm tra mã đã có sẵn trong cache chưa
            const cached = GM_getValue('link4m_latest_code', null);
            if (cached && (Date.now() - cached.timestamp < 10 * 60 * 1000)) {
                fillCodeIntoForm(cached.code);
            }

            // Tự click nút Get Link khi active
            setInterval(() => {
                const getLinkBtn = document.querySelector('a.get-link:not(.disabled)');
                if (getLinkBtn) {
                    const href = getLinkBtn.getAttribute('href');
                    if (href && href.startsWith('http') && !href.includes('javascript') && !href.includes('link4m')) {
                        window.location.href = href;
                    } else {
                        getLinkBtn.click();
                    }
                }
            }, 800);
        });

        return;
    }

    // =========================================================================
    // PHẦN 2: TỰ ĐỘNG CHẠY & VƯỢT ĐẾM NGƯỢC TRÊN TRANG TÀI TRỢ / SPONSOR
    // (Bao gồm các trang dùng hệ thống widget của what-on.com như soikeobongda, tylenhacai...)
    // =========================================================================

    // 1. Chống đóng băng bộ đếm khi tab bị ẩn hoặc người dùng chuyển tab khác
    try {
        Object.defineProperty(document, 'hidden', { get: () => false });
        Object.defineProperty(document, 'visibilityState', { get: () => 'visible' });
        window.addEventListener('blur', (e) => e.stopImmediatePropagation(), true);
    } catch (e) {}

    // 2. Giả lập cuộn trang liên tục (Dynamic pageYOffset) để thỏa mãn điều kiện mouse_scroll
    let fakeScroll = 300;
    try {
        Object.defineProperty(window, 'pageYOffset', {
            get: () => {
                fakeScroll = (fakeScroll + 17) % 25000 + 100;
                return fakeScroll;
            }
        });
    } catch (e) {}

    setInterval(() => {
        window.dispatchEvent(new Event('scroll'));
    }, 250);

    // 3. Tự động tương tác với widget quảng cáo
    function initSponsorAutomation() {
        // Tìm nút lấy mã
        const btnSelector = 'button:has-text("LẤY MÃ"), div[id*="BUQeFzS"] button, div[class*="whaton"] button, button[onclick*="traffic"]';
        
        const checkWidgetInterval = setInterval(() => {
            // Kiểm tra xem trang có chứa widget lấy mã không
            let btn = null;
            const buttons = document.querySelectorAll('button');
            for (let b of buttons) {
                if (b.innerText && b.innerText.includes('LẤY MÃ')) {
                    btn = b;
                    break;
                }
            }

            if (btn && !btn.dataset.autoClicked) {
                btn.dataset.autoClicked = 'true';
                console.log('[Link4M Sponsor] Phát hiện nút LẤY MÃ, tự động kích hoạt...');
                btn.click();
            }

            // Kiểm tra trạng thái bộ đếm
            const statusBox = document.querySelector('.whatoncode');
            if (statusBox) {
                const text = statusBox.innerText || '';

                // BƯỚC 1 HOÀN TẤT: Yêu cầu click link bất kỳ để sang Bước 2
                if (text.includes('click vào link bất kỳ') && !statusBox.dataset.navigated) {
                    statusBox.dataset.navigated = 'true';
                    console.log('[Link4M Sponsor] Bước 1 xong, đang tìm link bài viết để chuyển Bước 2...');
                    
                    const internalLinks = Array.from(document.querySelectorAll('a[href]')).filter(a => {
                        const h = a.href;
                        return h.startsWith(window.location.origin) &&
                               h !== window.location.href &&
                               h !== window.location.origin + '/' &&
                               !h.includes('#') &&
                               !h.endsWith('.jpg') && !h.endsWith('.png');
                    });

                    if (internalLinks.length > 0) {
                        const targetLink = internalLinks[0];
                        console.log('[Link4M Sponsor] Chuyển tiếp tới:', targetLink.href);
                        setTimeout(() => {
                            targetLink.click();
                        }, 500);
                    }
                }

                // BƯỚC 2 HOÀN TẤT: Đã hiển thị Mã KM
                if (text.includes('Mã KM:')) {
                    const match = text.match(/Mã KM:\s*([A-Za-z0-9]+)/);
                    if (match && match[1]) {
                        const sponsorCode = match[1].trim();
                        clearInterval(checkWidgetInterval);
                        console.log('[Link4M Sponsor] 🎉 ĐÃ LẤY ĐƯỢC MÃ KM:', sponsorCode);

                        // Lưu mã vào storage Tampermonkey
                        GM_setValue('link4m_latest_code', {
                            code: sponsorCode,
                            domain: window.location.hostname,
                            timestamp: Date.now()
                        });

                        // Copy mã vào clipboard
                        try {
                            navigator.clipboard.writeText(sponsorCode);
                        } catch (e) {}

                        // Thông báo cho người dùng
                        if (typeof GM_notification === 'function') {
                            GM_notification({
                                title: '⚡ Link4M Auto-Bypass',
                                text: `Đã lấy thành công Mã KM: ${sponsorCode}! Mã đã được tự động đồng bộ sang Link4M.`,
                                timeout: 5000
                            });
                        }
                    }
                }
            }
        }, 1000);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initSponsorAutomation);
    } else {
        initSponsorAutomation();
    }

})();
