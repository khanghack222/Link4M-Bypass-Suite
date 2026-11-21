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
                console.log('GET-LINK-INFO:', JSON.stringify(j));
                if (j.url) {
                    unlockedUrl = j.url;
                    fs.writeFileSync('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/final_destination.txt', unlockedUrl);
                }
            } catch (e) {}
        }
    });

    console.log('Opening page...');
    await page.goto('https://link4m.net/go/68pw167Y', { waitUntil: 'networkidle' });

    console.log('Typing password in #main-form input[name=password]...');
    const input = await page.$('#main-form input[name=password]');
    await input.fill('LbxReE');
    await input.dispatchEvent('input');

    await page.waitForTimeout(2000);

    // Target the exact frame matching key 6LcQsTQgAAAAADNQ_pCfukfvS0i9lk4oJTVSs5bZ
    const frame = page.frames().find(f => f.url().includes('6LcQsTQgAAAAADNQ_pCfukfvS0i9lk4oJTVSs5bZ') && f.url().includes('/anchor'));
    if (frame) {
        console.log('Found exact #recaptcha frame!');
        const anchor = await frame.$('#recaptcha-anchor');
        if (anchor) {
            console.log('Clicking #recaptcha-anchor...');
            await anchor.click({ force: true });
        }
    } else {
        console.log('Frame not found!');
    }

    // Wait 30 seconds for user or captcha solve
    console.log('Monitoring for 30s...');
    for (let i = 0; i < 10; i++) {
        await page.waitForTimeout(3000);
        if (unlockedUrl) {
            console.log('🎉 UNLOCKED URL:', unlockedUrl);
            break;
        }
        // Try clicking get-link button
        const btn = await page.$('#main-form a.get-link:not(.disabled)');
        if (btn) {
            console.log('Clicking get-link...');
            await btn.click();
        }
    }

    await page.waitForTimeout(5000);
    await browser.close();
})();
