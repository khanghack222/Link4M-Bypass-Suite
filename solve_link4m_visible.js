const { chromium } = require('playwright');

(async () => {
    console.log('[+] Opening Link4M page in visible Chrome...');
    const browser = await chromium.launch({
        headless: false,
        executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
    });

    const context = await browser.newContext({
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        viewport: { width: 1280, height: 850 }
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
                    console.log('==============================================');
                    console.log('🎉 UNLOCKED DESTINATION URL:', finalUnlockedUrl);
                    console.log('==============================================');
                    const fs = require('fs');
                    fs.writeFileSync('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/final_destination.txt', finalUnlockedUrl);
                }
            } catch (e) {}
        }
    });

    console.log('Navigating to https://link4m.net/go/68pw167Y ...');
    await page.goto('https://link4m.net/go/68pw167Y', { waitUntil: 'networkidle' });

    console.log('Waiting for password input...');
    await page.waitForSelector('input.password', { timeout: 30000 });

    console.log('Typing password code: LbxReE ...');
    await page.fill('input.password', 'LbxReE');
    await page.dispatchEvent('input.password', 'input');

    console.log('Waiting for reCAPTCHA iframe...');
    await page.waitForTimeout(3000);

    // Find recaptcha iframe
    const recaptchaFrame = page.frames().find(f => f.url().includes('recaptcha/api2/anchor'));
    if (recaptchaFrame) {
        console.log('Found reCAPTCHA frame! Clicking checkbox with force: true...');
        await recaptchaFrame.click('#recaptcha-anchor', { force: true });
        console.log('Clicked reCAPTCHA checkbox!');
    } else {
        console.log('reCAPTCHA anchor frame not found directly.');
    }

    // Keep page open for 60 seconds so user or auto-solve completes
    console.log('Waiting for completion (up to 60s)...');
    for (let i = 0; i < 20; i++) {
        await page.waitForTimeout(3000);
        if (finalUnlockedUrl) break;

        const btn = await page.$('a.get-link:not(.disabled)');
        if (btn) {
            console.log('Get-link button enabled! Clicking...');
            await btn.click();
        }
    }

    if (finalUnlockedUrl) {
        console.log('SUCCESS! Final destination:', finalUnlockedUrl);
    } else {
        console.log('Did not capture URL automatically within timeout.');
    }

    await page.waitForTimeout(5000);
    await browser.close();
})();
