// ==UserScript==
// @name         BBMKTS Auto Bypass & Instant Decoder
// @namespace    https://bbmkts.com/
// @version      2.0
// @description  Tự động điền mã, bypass captcha/quảng cáo và giải mã link gốc tức thì trên BBMKTS
// @author       Lazy Senior Dev
// @match        https://bbmkts.com/go/*
// @run-at       document-start
// @grant        none
// ==/UserScript==

(function () {
    'use strict';

    const currentUrl = window.location.href;

    // 1. TẦNG 1: GIẢI MÃ TỨC THÌ TRANG TRUNG GIAN /go/file/
    if (currentUrl.includes('/go/file/')) {
        const parts = currentUrl.split('/go/file/');
        if (parts.length > 1) {
            const rawPart = parts[1].split('?')[0].split('#')[0];
            let targetUrl = null;

            // Thu thuat giai ma Base64
            try {
                const dec = atob(rawPart);
                if (/^(https?:\/\/)/.test(dec)) targetUrl = dec;
            } catch (e) {}

            // Thu thuat URL Decode
            if (!targetUrl) {
                try {
                    const dec = decodeURIComponent(rawPart);
                    if (/^(https?:\/\/)/.test(dec)) targetUrl = dec;
                } catch (e) {}
            }

            if (targetUrl) {
                console.log('[BBMKTS BYPASS] Da giai ma link goc:', targetUrl);
                window.location.replace(targetUrl);
                return;
            }
        }
    }

    // 2. TẦNG 2: AUTO BYPASS TRANG NHIỆM VỤ /go/{code}
    if (currentUrl.includes('/go/') && !currentUrl.includes('/go/file/')) {
        // Chan cac tracker chan click va popup
        const blockedPatterns = ['apiip.js', 'api.js', 'sweetalert2', 'firebase'];
        const origAppendChild = Node.prototype.appendChild;
        Node.prototype.appendChild = function (child) {
            if (child && child.src) {
                for (const pat of blockedPatterns) {
                    if (child.src.includes(pat)) {
                        console.log('[BBMKTS BYPASS] Blocked tracker script:', child.src);
                        return child;
                    }
                }
            }
            return origAppendChild.apply(this, arguments);
        };

        window.addEventListener('DOMContentLoaded', async () => {
            console.log('[BBMKTS BYPASS] Trang da tai. Bat dau quy trinh bypass...');

            // Fake focus va visibility de khong bi pause timer neu co
            Object.defineProperty(document, 'hidden', { value: false, writable: true });
            Object.defineProperty(document, 'visibilityState', { value: 'visible', writable: true });

            // Ham submit ma
            async function submitCode(code) {
                const token = document.querySelector('input[name="token"]')?.value || '';
                const pageId = document.querySelector('input[name="page_id"]')?.value || '';
                const linkId = document.querySelector('input[name="link_id"]')?.value || '';

                const formData = new URLSearchParams();
                formData.append('token', token);
                formData.append('code', code);
                formData.append('page_id', pageId);
                formData.append('link_id', linkId);

                // Kich hoat /update/link-ads
                const linkBtn = document.getElementById('link');
                if (linkBtn && linkBtn.href) {
                    fetch(linkBtn.href).catch(() => {});
                }

                const res = await fetch('https://bbmkts.com/link/submit', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: formData.toString()
                });
                return await res.json();
            }

            // Giai ma ket qua tra ve tu submit
            function handleDestination(fileUrl) {
                if (!fileUrl) return;
                if (fileUrl.includes('/go/file/')) {
                    const enc = fileUrl.split('/go/file/')[1];
                    let decoded = null;
                    try { decoded = atob(enc); } catch (e) {}
                    if (!decoded || !decoded.startsWith('http')) {
                        try { decoded = decodeURIComponent(enc); } catch (e) {}
                    }
                    if (decoded && decoded.startsWith('http')) {
                        console.log('[BBMKTS BYPASS] Da giai ma thanh cong link ngoai:', decoded);
                        window.location.replace(decoded);
                        return;
                    }
                }
                window.location.replace(fileUrl);
            }

            // Cho 1.5s de DOM on dinh
            setTimeout(async () => {
                // Kiem tra loai chien dich
                const hasCanvas = document.querySelector('canvas') || document.body.innerHTML.includes('imgCanvas');
                let codeToTry = 'trafficseo2025';

                console.log(`[BBMKTS BYPASS] Chuan bi submit ma: ${codeToTry}`);
                try {
                    const result = await submitCode(codeToTry);
                    console.log('[BBMKTS BYPASS] Ket qua:', result);
                    if (result && result.url) {
                        handleDestination(result.url);
                    } else if (result && result.message) {
                        console.warn('[BBMKTS BYPASS] Server phan hoi:', result.message);
                    }
                } catch (err) {
                    console.error('[BBMKTS BYPASS] Loi submit:', err);
                }
            }, 1500);
        });
    }
})();
