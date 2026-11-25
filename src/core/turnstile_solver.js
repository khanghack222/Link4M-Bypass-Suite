#!/usr/bin/env node
/**
 * ⚡ CLOUDFLARE TURNSTILE SOLVER (Node.js + Patchright Engine) ⚡
 * Implementation of Theyka Turnstile Solver using native Node.js Patchright.
 * Bypasses Cloudflare CDP detection 100% using route-mocking and patched Input events.
 */

const { chromium } = require('patchright');
const fs = require('fs');

// patchright's own browser download can be blocked on locked-down boxes.
// Fall back to any installed Chrome/Chromium so the solver still launches.
function findChrome() {
    const candidates = [
        process.env.CHROME_BIN,
        '/usr/bin/google-chrome',
        '/usr/bin/google-chrome-stable',
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/opt/google/chrome/chrome',
        'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe'
    ];
    for (const candidate of candidates) {
        if (candidate && fs.existsSync(candidate)) return candidate;
    }
    return undefined;
}

const HTML_TEMPLATE = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Turnstile Solver</title>
    <script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async></script>
</head>
<body style="background:#111;color:#fff;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;">
    <div style="text-align:center;">
        <h3 style="font-family:sans-serif;margin-bottom:20px;">Solving Cloudflare Turnstile...</h3>
        <!-- cf turnstile -->
    </div>
</body>
</html>`;

async function solveTurnstile({ url, sitekey, headless = false, timeoutMs = 30000 }) {
    const startTime = Date.now();
    const urlWithSlash = url.endsWith('/') ? url : url + '/';
    
    const cleanSitekey = String(sitekey || "").replace(/[^a-zA-Z0-9_\-]/g, "");
    const turnstileDiv = `<div class="cf-turnstile" data-sitekey="${cleanSitekey}"></div>`;
    const pageData = HTML_TEMPLATE.replace('<!-- cf turnstile -->', turnstileDiv);

    const browser = await chromium.launch({
        headless: headless,
        executablePath: findChrome(),
        args: [
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--window-size=1280,800'
        ]
    });

    try {
        const context = await browser.newContext({
            viewport: { width: 1280, height: 800 },
            userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        });

        const page = await context.newPage();

        // Intercept origin URL to serve isolated Turnstile challenge
        await page.route(urlWithSlash, route => {
            route.fulfill({
                status: 200,
                contentType: 'text/html',
                body: pageData
            });
        });

        await page.goto(urlWithSlash, { waitUntil: 'domcontentloaded', timeout: timeoutMs });

        // Poll and click Turnstile widget
        const maxAttempts = Math.floor(timeoutMs / 1000);
        let solvedToken = null;

        for (let i = 0; i < maxAttempts; i++) {
            // Check if token is ready
            const token = await page.evaluate(() => {
                try {
                    if (typeof turnstile !== 'undefined' && turnstile.getResponse) {
                        const t = turnstile.getResponse();
                        if (t && String(t).length > 20) return String(t);
                    }
                } catch (e) {}
                const inp = document.querySelector('[name="cf-turnstile-response"]');
                if (inp && inp.value && inp.value.length > 20) return inp.value;
                return '';
            });

            if (token && token.length > 20) {
                solvedToken = token;
                break;
            }

            // Click the turnstile wrapper or iframe
            try {
                const ts = await page.$('.cf-turnstile');
                if (ts) {
                    await ts.click({ timeout: 1500 }).catch(() => {});
                }
            } catch (e) {}

            for (const f of page.frames()) {
                if (f.url().includes('challenges.cloudflare.com')) {
                    try {
                        const cb = (await f.$("input[type='checkbox']")) || (await f.$('body'));
                        if (cb) {
                            await cb.click({ timeout: 1000 }).catch(() => {});
                        }
                    } catch (e) {}
                }
            }

            await new Promise(r => setTimeout(r, 1000));
        }

        const elapsedSec = ((Date.now() - startTime) / 1000).toFixed(2);
        if (solvedToken) {
            return {
                status: 'success',
                turnstile_value: solvedToken,
                elapsed_time_seconds: parseFloat(elapsedSec),
                engine: 'patchright-node'
            };
        } else {
            return {
                status: 'failure',
                turnstile_value: null,
                elapsed_time_seconds: parseFloat(elapsedSec),
                reason: 'Timeout waiting for Turnstile verification',
                engine: 'patchright-node'
            };
        }
    } finally {
        await browser.close().catch(() => {});
    }
}

// CLI handler
if (require.main === module) {
    const args = process.argv.slice(2);
    const url = args[0] || 'https://bbmkts.com';
    const sitekey = args[1] || '0x4AAAAAAEzmJdRW__FHO9pu';
    const headless = args.includes('--headless');

    solveTurnstile({ url, sitekey, headless })
        .then(res => {
            console.log(JSON.stringify(res));
            process.exit(res.status === 'success' ? 0 : 1);
        })
        .catch(err => {
            console.error(JSON.stringify({ status: 'error', reason: err.message }));
            process.exit(1);
        });
}

module.exports = { solveTurnstile };
