const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
    const browser = await chromium.launch({
        headless: false,
        executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
    });
    const page = await browser.newPage();
    await page.goto('https://link4m.net/go/68pw167Y', { waitUntil: 'networkidle' });

    let finalUnlockedUrl = null;
    page.on('response', async resp => {
        if (resp.url().includes('get-link-info')) {
            try {
                const j = await resp.json();
                console.log('API RESP:', JSON.stringify(j));
                if (j.url) {
                    finalUnlockedUrl = j.url;
                    fs.writeFileSync('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/final_destination.txt', finalUnlockedUrl);
                }
            } catch (e) {}
        }
    });

    await page.fill('#main-form input[name="password"]', 'LbxReE');
    await page.dispatchEvent('#main-form input[name="password"]', 'input');

    const iframeLoc = page.locator('#recaptcha iframe').first();
    await iframeLoc.scrollIntoViewIfNeeded();
    await iframeLoc.click({ position: { x: 28, y: 37 } });

    await page.waitForTimeout(3000);

    // Find the visible bframe
    console.log('Searching for visible bframe...');
    for (const frame of page.frames()) {
        if (frame.url().includes('recaptcha/api2/bframe')) {
            const audioBtn = await frame.$('#recaptcha-audio-button');
            if (audioBtn) {
                console.log('Found audio button in frame:', frame.url().slice(0, 80));
                console.log('Clicking audio challenge button...');
                await audioBtn.click();
                await page.waitForTimeout(3000);

                // Check for audio source
                const src = await frame.$eval('#audio-source', el => el.src).catch(() => null);
                console.log('Audio source URL:', src);

                if (src) {
                    // Download audio
                    const axios = require('http');
                    console.log('Audio challenge ready to transcribe!');
                }
                break;
            }
        }
    }

    await page.screenshot({ path: 'C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/audio_state.png' });
    console.log('Saved audio_state.png');

    // Keep open 40 seconds so user can complete or we solve
    for (let i = 0; i < 15; i++) {
        await page.waitForTimeout(3000);
        if (finalUnlockedUrl) {
            console.log('🎉 UNLOCKED URL:', finalUnlockedUrl);
            break;
        }
        const btn = await page.$('#main-form a.get-link:not(.disabled)');
        if (btn) {
            console.log('Clicking get-link button...');
            await btn.click();
        }
    }

    await page.waitForTimeout(3000);
    await browser.close();
})();
