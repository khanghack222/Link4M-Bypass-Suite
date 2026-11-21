// ==UserScript==
// @name         Link4M Auto-Bypass & Direct Link Extractor
// @namespace    https://github.com/
// @version      1.0
// @description  Tự động bỏ qua 60s tìm kiếm Google / nhiệm vụ quảng cáo trên Link4M, tự mở sẵn reCAPTCHA để người dùng chỉ cần tick/giải một lần, sau đó tự động chuyển hướng thẳng tới link đích!
// @author       Weat
// @match        https://*.link4m.org/go/*
// @match        https://*.link4m.net/go/*
// @match        https://*.link4m.co/go/*
// @match        https://*.link4m.com/go/*
// @run-at       document-start
// @grant        none
// ==/UserScript==

(function() {
    'use strict';

    console.log('[Link4M Bypass] UserScript loaded. Activating Zero-Pass exploit...');

    // 1. CHẶN REQUEST QUẢNG CÁO ĐỂ KÍCH HOẠT FALLBACK RECAPTCHA KHÔNG CẦN PASSWORD
    const originalFetch = window.fetch;
    window.fetch = function(...args) {
        const url = args[0] ? (typeof args[0] === 'string' ? args[0] : args[0].url) : '';
        if (url && url.includes('/api/campaign/get-advertise')) {
            console.log('[Link4M Bypass] Blocked get-advertise via fetch');
            return Promise.reject(new Error('Campaign blocked by user bypass'));
        }
        return originalFetch.apply(this, args);
    };

    const originalOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url, ...rest) {
        if (typeof url === 'string' && url.includes('/api/campaign/get-advertise')) {
            console.log('[Link4M Bypass] Blocked get-advertise via XHR');
            // Ghi đè URL thành endpoint không tồn tại để Link4M kích hoạt nhánh fallback (createDefaultRecaptcha)
            url = 'https://s1.link4m.app/api/campaign/bypass_blocked';
        }
        return originalOpen.apply(this, [method, url, ...rest]);
    };

    // 2. TỰ ĐỘNG BẮT LINK ĐÍCH KHI USER GIẢI XONG CAPTCHA
    const originalSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function(...args) {
        this.addEventListener('load', function() {
            try {
                if (this.responseURL && (this.responseURL.includes('check-captcha') || this.responseURL.includes('get-link-info'))) {
                    const data = JSON.parse(this.responseText);
                    if (data && data.success && data.url) {
                        console.log('[Link4M Bypass] 🎉 PHÁT HIỆN LINK ĐÍCH:', data.url);
                        showNotification('Đã lấy link đích thành công! Đang chuyển hướng...', data.url);
                        setTimeout(() => {
                            window.location.href = data.url;
                        }, 800);
                    }
                }
            } catch (e) {}
        });
        return originalSend.apply(this, args);
    };

    // 3. UI HELPER & AUTO CLICK "GET LINK" KHI ĐƯỢC KÍCH HOẠT
    function initUI() {
        const checkInterval = setInterval(() => {
            // Tự click nút Get Link nếu nó hết bị disabled
            const getLinkBtn = document.querySelector('a.get-link:not(.disabled)');
            if (getLinkBtn) {
                const targetHref = getLinkBtn.getAttribute('href');
                if (targetHref && targetHref.startsWith('http') && !targetHref.includes('javascript')) {
                    clearInterval(checkInterval);
                    console.log('[Link4M Bypass] Redirecting to:', targetHref);
                    window.location.href = targetHref;
                    return;
                }
                getLinkBtn.click();
            }

            // Xóa bỏ các thông báo đếm ngược hay hướng dẫn nhiệm vụ thừa thãi
            const advBox = document.getElementById('advertise-html-wrapper');
            if (advBox && advBox.children.length > 0) {
                advBox.innerHTML = '';
            }

            // Tạo banner trạng thái tiện ích
            if (!document.getElementById('bypass-status-banner')) {
                const banner = document.createElement('div');
                banner.id = 'bypass-status-banner';
                banner.style.cssText = `
                    position: fixed;
                    top: 15px;
                    left: 50%;
                    transform: translateX(-50%);
                    background: #0f172a;
                    color: #38bdf8;
                    border: 1px solid #38bdf8;
                    padding: 10px 20px;
                    border-radius: 8px;
                    font-size: 15px;
                    font-family: sans-serif;
                    z-index: 999999;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.5);
                    text-align: center;
                `;
                banner.innerHTML = `🛡️ <b>Link4M Bypass:</b> Đã tắt 60s chờ & lấy mã. Bạn chỉ cần <b>tick vào reCAPTCHA</b> bên dưới, hệ thống sẽ tự nhảy thẳng tới link đích!`;
                document.body.appendChild(banner);
            }
        }, 500);
    }

    function showNotification(msg, url) {
        const banner = document.getElementById('bypass-status-banner');
        if (banner) {
            banner.style.background = '#065f46';
            banner.style.color = '#34d399';
            banner.style.borderColor = '#34d399';
            banner.innerHTML = `🎉 <b>${msg}</b><br><a href="${url}" style="color:#fff;text-decoration:underline;">Nhấn vào đây nếu không tự chuyển</a>`;
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initUI);
    } else {
        initUI();
    }
})();
