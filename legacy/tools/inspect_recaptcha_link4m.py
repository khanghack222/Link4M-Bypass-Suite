import time
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://link4m.net/go/68pw167Y')
    time.sleep(3)
    res = page.evaluate("""() => {
        const el = document.querySelector('.g-recaptcha');
        return {
            id: el ? el.id : null,
            data_recaptcha_id: (window.jQuery && el) ? jQuery(el).data('recaptcha-id') : null,
            dataset_recaptcha_id: el ? el.dataset.recaptchaId : null,
            api_domain: window.api_domain,
            grecaptcha_exists: typeof window.grecaptcha !== 'undefined',
            grecaptcha_getResponse: (window.grecaptcha && typeof window.grecaptcha.getResponse === 'function') ? window.grecaptcha.getResponse() : null
        };
    }""")
    print("Recaptcha info:", res)
    browser.close()
