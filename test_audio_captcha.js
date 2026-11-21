const { chromium } = require('playwright');

(async () => {
    const browser = await chromium.launch({
        headless: false,
        executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
    });
    const page = await browser.newPage();
    await page.goto('https://link4m.net/go/68pw167Y', { waitUntil: 'networkidle' });

    await page.fill('#main-form input[name="password"]', 'LbxReE');
    await page.dispatchEvent('#main-form input[name="password"]', 'input');

    const iframeLoc = page.locator('#recaptcha iframe').first();
    await iframeLoc.scrollIntoViewIfNeeded();
    await iframeLoc.click({ position: { x: 28, y: 37 } });

    await page.waitForTimeout(3000);

    // Find bframe
    const bframe = page.frames().find(f => f.url().includes('recaptcha/api2/bframe'));
    if (bframe) {
        console.log('Found bframe! Checking for audio button...');
        const audioBtn = await bframe.$('#recaptcha-audio-button');
        if (audioBtn) {
            console.log('Audio button found! Clicking audio button...');
            await audioBtn.click();
            await page.waitForTimeout(3000);
            const audioSrc = await bframe.$eval('#audio-source', el => el.src).catch(() => null);
            console.log('Audio source URL:', audioSrc);
        } else {
            console.log('Audio button not found.');
        }
    } else {
        console.log('No bframe popped up (checkbox might be checked directly!)');
    }

    await page.screenshot({ path: 'C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/recaptcha_state.png' });
    console.log('Saved recaptcha_state.png');

    await page.waitForTimeout(5000);
    await browser.close();
})();
