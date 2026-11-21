const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
    const browser = await chromium.launch({
        headless: false,
        executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
    });
    const page = await browser.newPage();

    let finalUnlockedUrl = null;
    page.on('response', async resp => {
        if (resp.url().includes('get-link-info')) {
            try {
                const j = await resp.json();
                console.log('API RESP:', JSON.stringify(j));
                if (j.url) {
                    finalUnlockedUrl = j.url;
                    console.log('🎉 UNLOCKED DESTINATION URL:', finalUnlockedUrl);
                    fs.writeFileSync('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/final_destination.txt', finalUnlockedUrl);
                }
            } catch (e) {}
        }
    });

    console.log('Navigating to Link4M...');
    await page.goto('https://link4m.net/go/68pw167Y', { waitUntil: 'networkidle' });

    // Fill password
    await page.fill('#main-form input[name="password"]', 'LbxReE');
    await page.dispatchEvent('#main-form input[name="password"]', 'input');

    // Click checkbox
    const iframeLoc = page.locator('#recaptcha iframe').first();
    await iframeLoc.scrollIntoViewIfNeeded();
    await iframeLoc.click({ position: { x: 28, y: 37 } });

    console.log('Waiting for reCAPTCHA challenge or checkmark...');
    await page.waitForTimeout(3000);

    // Keep page open for 60s so user can click or solve if prompted!
    console.log('>>> Chrome window is OPEN. If reCAPTCHA image puzzle appears, complete it in Chrome.');
    console.log('>>> Password is ALREADY FILLED: LbxReE');

    for (let i = 0; i < 20; i++) {
        await page.waitForTimeout(3000);
        if (finalUnlockedUrl) break;

        const btn = await page.$('#main-form a.get-link:not(.disabled)');
        if (btn) {
            console.log('Clicking get-link button...');
            await btn.click();
        }
    }

    if (finalUnlockedUrl) {
        console.log('🎉 SUCCESS! Final destination:', finalUnlockedUrl);
    } else {
        console.log('Timed out waiting for final URL.');
    }

    await page.waitForTimeout(5000);
    await browser.close();
})();
