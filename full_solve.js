const { chromium } = require('playwright');
const fs = require('fs');

(async () => {
    console.log('[+] Starting full quest solver...');
    const browser = await chromium.launch({
        headless: false,
        executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
    });

    const context = await browser.newContext({
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        viewport: { width: 1280, height: 800 }
    });

    const page = await context.newPage();

    let capturedCode = null;

    page.on('response', async resp => {
        if (resp.url().includes('get_quest_code.html')) {
            try {
                const json = await resp.json();
                console.log('<< QUEST CODE API RESP:', JSON.stringify(json));
                if (json.html && /^\d{4,8}$/.test(json.html.trim())) {
                    capturedCode = json.html.trim();
                    console.log('>>> FOUND FINAL 6-DIGIT CODE:', capturedCode);
                    fs.writeFileSync('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/solved_code.txt', capturedCode);
                }
            } catch (e) {}
        }
    });

    console.log('[1/2] Navigating to target sponsor article...');
    await page.goto('https://khovatlieunoithatdanang.com/van-ep-phu-phim-da-nang', {
        referer: 'https://www.google.com/',
        waitUntil: 'domcontentloaded'
    });

    await page.waitForTimeout(3000);
    const btn1 = await page.$('#VkanofiI button');
    if (btn1) {
        console.log('[1/2] Clicking initial LẤY MÃ button...');
        await btn1.scrollIntoViewIfNeeded();
        await page.waitForTimeout(500);
        await btn1.click();
    }

    // Step 1: Wait for 60s countdown
    console.log('[1/2] Waiting for Step 1 countdown...');
    for (let i = 0; i < 20; i++) {
        await page.waitForTimeout(4000);
        await page.mouse.wheel(0, 100);
        await page.waitForTimeout(400);
        await page.mouse.wheel(0, -100);

        const text = await page.evaluate(() => {
            const el = document.querySelector('.whatoncode') || document.querySelector('#VkanofiI');
            return el ? el.innerText : '';
        });
        if (text.includes('click vào link') || text.includes('bất kỳ')) {
            console.log('[1/2] Step 1 finished! Instruction:', text.replace(/\n/g, ' '));
            break;
        }
    }

    // Step 2: Click another link on the website!
    console.log('[2/2] Navigating to second article to trigger Step 2...');
    await page.goto('https://khovatlieunoithatdanang.com/van-phu-phim-gia-re', {
        waitUntil: 'domcontentloaded'
    });

    await page.waitForTimeout(3000);
    const btn2 = await page.$('#VkanofiI button');
    if (btn2) {
        console.log('[2/2] Found Step 2 button, clicking...');
        await btn2.scrollIntoViewIfNeeded();
        await page.waitForTimeout(500);
        await btn2.click();
    } else {
        console.log('[2/2] Checking if Step 2 auto-started...');
    }

    // Monitor Step 2 countdown (15 seconds)
    for (let i = 0; i < 10; i++) {
        await page.waitForTimeout(3000);
        await page.mouse.wheel(0, 100);
        await page.waitForTimeout(400);
        await page.mouse.wheel(0, -100);

        const text = await page.evaluate(() => {
            const el = document.querySelector('.whatoncode') || document.querySelector('#VkanofiI');
            return el ? el.innerText : '';
        });
        console.log(`[2/2] [${(i+1)*3}s] Text:`, text.replace(/\n/g, ' '));

        const match = text.match(/\b\d{4,8}\b/);
        if (match && !text.includes('s (')) {
            capturedCode = match[0];
            console.log('>>> EXTRACTED CODE FROM TEXT:', capturedCode);
            fs.writeFileSync('C:/Users/XUAN/.gemini/antigravity/scratch/Link4M_Bypass_Suite/solved_code.txt', capturedCode);
            break;
        }
    }

    await page.waitForTimeout(3000);
    await browser.close();
    console.log('[+] Quest automation finished. Code:', capturedCode);
})();
