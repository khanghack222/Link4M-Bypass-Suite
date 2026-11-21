const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
    const browser = await chromium.launch({
        headless: false,
        executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
    });
    const page = await browser.newPage();

    let unlockedUrl = null;
    page.on('response', async resp => {
        if (resp.url().includes('get-link-info')) {
            try {
                const j = await resp.json();
                console.log('>>> API RESPONSE:', JSON.stringify(j));
                if (j.url) {
                    unlockedUrl = j.url;
                    console.log('🎉 UNLOCKED DESTINATION URL:', unlockedUrl);
                    fs.writeFileSync('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/final_destination.txt', unlockedUrl);
                }
            } catch (e) {}
        }
    });

    console.log('[+] Navigating to Link4M...');
    await page.goto('https://link4m.net/go/68pw167Y', { waitUntil: 'networkidle' });

    console.log('[+] Typing password in #main-form input.password ...');
    await page.fill('#main-form input[name="password"]', 'LbxReE');
    await page.dispatchEvent('#main-form input[name="password"]', 'input');

    await page.waitForTimeout(1000);

    console.log('[+] Scrolling #recaptcha iframe into view...');
    const iframeLoc = page.locator('#recaptcha iframe').first();
    await iframeLoc.scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);

    console.log('[+] Clicking reCAPTCHA checkbox at x=28, y=37...');
    await iframeLoc.click({ position: { x: 28, y: 37 } });

    console.log('[+] Checkbox clicked! Monitoring for completion (up to 40s)...');
    for (let i = 0; i < 15; i++) {
        await page.waitForTimeout(3000);
        if (unlockedUrl) break;

        const btn = await page.$('#main-form a.get-link:not(.disabled)');
        if (btn) {
            console.log('Clicking get-link button...');
            await btn.click();
        }
    }

    if (unlockedUrl) {
        console.log('FINAL DESTINATION:', unlockedUrl);
    } else {
        console.log('Waiting ended. Check if reCAPTCHA challenge needs solving in browser.');
    }

    await page.waitForTimeout(4000);
    await browser.close();
})();
