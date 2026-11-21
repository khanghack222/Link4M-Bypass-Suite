const { chromium } = require('playwright');
(async () => {
    const browser = await chromium.launch({
        headless: false,
        executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
    });
    const page = await browser.newPage();
    await page.goto('https://link4m.net/go/68pw167Y', { waitUntil: 'networkidle' });
    const info = await page.evaluate(() => {
        const r1 = document.querySelector('#recaptcha');
        const r2 = document.querySelector('#recaptcha-2');
        const f1 = document.querySelector('#main-form');
        const f2 = document.querySelector('#main-form-2');
        return {
            f1: f1 ? { display: window.getComputedStyle(f1).display, visibility: window.getComputedStyle(f1).visibility } : null,
            f2: f2 ? { display: window.getComputedStyle(f2).display, visibility: window.getComputedStyle(f2).visibility } : null,
            r1: r1 ? { display: window.getComputedStyle(r1).display, hasChild: r1.children.length } : null,
            r2: r2 ? { display: window.getComputedStyle(r2).display, hasChild: r2.children.length } : null,
        };
    });
    console.log(JSON.stringify(info, null, 2));
    await browser.close();
})();
