// ==UserScript==
// @name         Link4M Auto Bypass Suite - Loader
// @namespace    https://github.com/khanghack222/Link4M-Bypass-Suite
// @version      3.6.0
// @description  Tự động vượt toàn bộ flow Link4M & Nhà tài trợ (chỉ cần người dùng tích Captcha).
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
// @connect      raw.githubusercontent.com
// @connect      cdn.jsdelivr.net
// @connect      termbin.com
// @run-at       document_start
// ==/UserScript==

(function() {
    'use strict';
    // Đa nguồn dự phòng: CDN vĩnh viễn (fast, no rate-limit), GitHub Raw, và Termbin
    const SOURCES = [
        'https://cdn.jsdelivr.net/gh/khanghack222/Link4M-Bypass-Suite@main/dist/core.bundle.js',
        'https://raw.githubusercontent.com/khanghack222/Link4M-Bypass-Suite/main/dist/core.bundle.js',
        'https://termbin.com/lkmp'
    ];

    function executeScript(code) {
        try {
            const run = new Function(code);
            run();
        } catch (e) {
            console.error('[L4M Loader] Runtime error:', e);
        }
    }

    function fetchSource(index) {
        if (index >= SOURCES.length) {
            console.error('[L4M Loader] Tất cả các nguồn tải đều thất bại.');
            return;
        }

        const url = SOURCES[index];
        if (typeof GM_xmlhttpRequest !== 'undefined') {
            GM_xmlhttpRequest({
                method: 'GET',
                url: url,
                timeout: 8000,
                onload: function(res) {
                    if (res.status === 200 && res.responseText && res.responseText.length > 500) {
                        executeScript(res.responseText);
                    } else {
                        fetchSource(index + 1);
                    }
                },
                onerror: function() {
                    fetchSource(index + 1);
                },
                ontimeout: function() {
                    fetchSource(index + 1);
                }
            });
        } else {
            fetch(url)
                .then(r => {
                    if (!r.ok) throw new Error('Network response not ok');
                    return r.text();
                })
                .then(code => executeScript(code))
                .catch(() => fetchSource(index + 1));
        }
    }

    fetchSource(0);
})();
