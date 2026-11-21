const { chromium } = require('playwright');

(async () => {
    console.log('Launching browser...');
    const browser = await chromium.launch({
        headless: false, // visible so we see everything
        executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
    });

    const context = await browser.newContext({
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        viewport: { width: 1280, height: 800 }
    });

    const page = await context.newPage();

    // Log all requests & responses to what-on
    page.on('request', req => {
        if (req.url().includes('what-on') || req.url().includes('link4m')) {
            console.log('>> REQ:', req.method(), req.url());
            const postData = req.postData();
            if (postData) {
                console.log('   POST DATA:', postData.slice(0, 200));
            }
        }
    });

    page.on('response', async resp => {
        if (resp.url().includes('what-on') || resp.url().includes('link4m')) {
            console.log('<< RESP:', resp.status(), resp.url());
            try {
                const text = await resp.text();
                console.log('   BODY:', text.slice(0, 150));
            } catch (e) {}
        }
    });

    console.log('Navigating to sponsor page with Google referrer...');
    await page.goto('https://khovatlieunoithatdanang.com/van-ep-phu-phim-da-nang', {
        referer: 'https://www.google.com/',
        waitUntil: 'domcontentloaded'
    });

    console.log('Waiting for #VkanofiI button...');
    await page.waitForTimeout(3000);

    const btn = await page.$('#VkanofiI button');
    if (btn) {
        console.log('Found button! Scrolling to it...');
        await btn.scrollIntoViewIfNeeded();
        await page.waitForTimeout(1000);
        console.log('Clicking button...');
        await btn.click();
    } else {
        console.log('Button not found directly in #VkanofiI, checking page content...');
    }

    console.log('Monitoring for 90 seconds...');
    for (let i = 0; i < 18; i++) {
        await page.waitForTimeout(5000);
        // Slowly scroll up and down as required by the script
        await page.mouse.wheel(0, 100);
        await page.waitForTimeout(500);
        await page.mouse.wheel(0, -100);

        const btnText = await page.evaluate(() => {
            const el = document.querySelector('.whatoncode') || document.querySelector('#VkanofiI');
            return el ? el.innerText : '';
        });
        console.log(`[${(i+1)*5}s] Button text:`, btnText.replace(/\n/g, ' '));
        if (btnText.includes('Mã KM') || btnText.match(/\d{6}/)) {
            console.log('SUCCESS! Extracted code from UI:', btnText);
            break;
        }
    }

    await page.waitForTimeout(5000);
    await browser.close();
})();
