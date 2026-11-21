const { chromium } = require('playwright');

(async () => {
    const browser = await chromium.launch({
        headless: false,
        executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
    });
    const page = await browser.newPage();
    await page.goto('https://link4m.net/go/68pw167Y', { waitUntil: 'networkidle' });

    console.log('Frames on page:');
    for (const f of page.frames()) {
        console.log('-', f.url());
    }

    console.log('Forms on page:');
    const forms = await page.evaluate(() => {
        return Array.from(document.querySelectorAll('form')).map(f => ({
            id: f.id,
            visible: f.offsetParent !== null,
            inputs: Array.from(f.querySelectorAll('input')).map(i => ({ name: i.name, type: i.type, value: i.value }))
        }));
    });
    console.log(JSON.stringify(forms, null, 2));

    await browser.close();
})();
