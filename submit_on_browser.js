const { chromium } = require('playwright');

(async () => {
    console.log('[+] Opening Link4M page in Chrome...');
    const browser = await chromium.launch({
        headless: false,
        executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
    });

    const context = await browser.newContext({
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        viewport: { width: 1280, height: 800 }
    });

    const page = await context.newPage();

    let finalUnlockedUrl = null;

    page.on('response', async resp => {
        if (resp.url().includes('get-link-info')) {
            try {
                const json = await resp.json();
                console.log('>>> GET-LINK-INFO RESPONSE:', JSON.stringify(json));
                if (json.url) {
                    finalUnlockedUrl = json.url;
                    console.log('🎉 UNLOCKED DESTINATION URL:', finalUnlockedUrl);
                }
            } catch (e) {}
        }
    });

    console.log('Navigating to https://link4m.net/go/68pw167Y ...');
    await page.goto('https://link4m.net/go/68pw167Y', { waitUntil: 'domcontentloaded' });

    console.log('Waiting for password input...');
    await page.waitForSelector('input.password', { timeout: 15000 });

    console.log('Typing password code: LbxReE ...');
    await page.fill('input.password', 'LbxReE');

    console.log('Waiting 2 seconds...');
    await page.waitForTimeout(2000);

    // Look for recaptcha iframe
    const recaptchaFrame = page.frames().find(f => f.url().includes('recaptcha/api2/anchor'));
    if (recaptchaFrame) {
        console.log('Found reCAPTCHA frame! Clicking checkbox...');
        const checkbox = await recaptchaFrame.$('#recaptcha-anchor');
        if (checkbox) {
            await checkbox.click();
            console.log('Clicked reCAPTCHA checkbox!');
        }
    } else {
        console.log('reCAPTCHA frame not found directly, checking frames:', page.frames().map(f => f.url()));
    }

    // Monitor for 45 seconds for user or auto solve
    console.log('Monitoring for final unlocked URL...');
    for (let i = 0; i < 15; i++) {
        await page.waitForTimeout(3000);
        if (finalUnlockedUrl) break;

        // Check if get-link button is enabled
        const btn = await page.$('a.get-link:not(.disabled)');
        if (btn) {
            console.log('Get-link button enabled! Clicking...');
            await btn.click();
        }
    }

    console.log('Done! Result:', finalUnlockedUrl);
    await page.waitForTimeout(5000);
    await browser.close();
})();
