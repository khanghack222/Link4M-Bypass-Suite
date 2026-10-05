/**
 * ⚡ LINK4M CONTENT AUTOMATION ⚡
 * Runs on Link4M pages (link4m.net, link4m.co, s1.link4m.app).
 * Orchestrates advertise parsing, sponsor launch, code entry, and user captcha handling.
 */

(function() {
  console.log('[Link4M Content] Initiating on:', window.location.href);

  let currentSponsorDomain = null;
  let receivedCode = null;
  let isSubmitted = false;

  // Initialize UI HUD
  window.Link4MHUD.init();
  window.Link4MHUD.setStatus('Đang quét nhiệm vụ...');

  // 1. Intercept advertise API request
  const originalXhrOpen = XMLHttpRequest.prototype.open;
  const originalXhrSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method, url) {
    this._l4m_url = url;
    return originalXhrOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function() {
    this.addEventListener('load', function() {
      try {
        if (this._l4m_url && this._l4m_url.includes('get-advertise')) {
          const res = JSON.parse(this.responseText);
          if (res && res.data && res.data.html) {
            parseAdvertiseHtml(res.data.html);
          }
        }
      } catch (e) {}
    });
    return originalXhrSend.apply(this, arguments);
  };

  // 2. Parse Advertise DOM / HTML
  function parseAdvertiseHtml(htmlContent) {
    window.Link4MHUD.log('Đã phát hiện chiến dịch quảng cáo', 'cyan');

    // Use unmaskDomainCandidates on HTML content
    const candidates = unmaskDomainCandidates(htmlContent);
    if (candidates && candidates.length > 0) {
      currentSponsorDomain = candidates[0];
      window.Link4MHUD.setDomain(currentSponsorDomain);
      window.Link4MHUD.log(`Tìm thấy domain tài trợ: ${currentSponsorDomain}`, 'green');
      window.Link4MHUD.setStatus('Đã có nhà tài trợ');
      autoOpenSponsor();
    } else {
      // Fallback: check google search keyword in html
      const mKw = htmlContent.match(/từ kho[áa]\s*[:\-]?\s*<strong[^>]*>([^<]+)<\/strong>/i);
      if (mKw && mKw[1]) {
        window.Link4MHUD.log(`Từ khoá nhiệm vụ: "${mKw[1].trim()}"`, 'purple');
      }
    }
  }

  // Scan existing page DOM if advertise is already rendered
  function scanExistingDOM() {
    const pageText = document.body.innerText || '';
    const candidates = unmaskDomainCandidates(pageText);

    if (candidates.length > 0) {
      currentSponsorDomain = candidates[0];
      window.Link4MHUD.setDomain(currentSponsorDomain);
      window.Link4MHUD.log(`Phát hiện domain từ trang: ${currentSponsorDomain}`, 'green');
      window.Link4MHUD.setStatus('Sẵn sàng');
      autoOpenSponsor();
      return true;
    }
    return false;
  }

  // Auto trigger opening sponsor tab
  function autoOpenSponsor() {
    if (!currentSponsorDomain) return;

    window.Link4MHUD.setStatus('Mở trang tài trợ...');
    window.Link4MHUD.log(`Gửi yêu cầu mở: ${currentSponsorDomain}`, 'cyan');

    chrome.runtime.sendMessage({
      type: 'OPEN_SPONSOR_TAB',
      domain: currentSponsorDomain
    }, (resp) => {
      if (resp && resp.success) {
        window.Link4MHUD.setStatus('Chờ lấy mã từ tài trợ...');
        window.Link4MHUD.log('Tab tài trợ đang chạy ngầm tự động đếm ngược', 'cyan');
      }
    });
  }

  // Fill extracted code into Link4M form
  function fillCode(code) {
    receivedCode = code;
    window.Link4MHUD.setCode(code);
    window.Link4MHUD.log(`Nhận mã từ tài trợ: ${code}`, 'green');

    // Fill inputs
    const inputs = document.querySelectorAll("input[name='password'], #password-2, #password, .password");
    inputs.forEach(inp => {
      inp.value = code;
      inp.dispatchEvent(new Event('input', { bubbles: true }));
      inp.dispatchEvent(new Event('change', { bubbles: true }));
    });

    // Remove any ad popups/modals
    document.querySelectorAll('#ad_banner, .modal-backdrop, [class*="overlay"]').forEach(el => el.remove());

    // Check Captcha status
    verifyCaptchaAndSubmit();
  }

  // Check if captcha is required / solved
  function verifyCaptchaAndSubmit() {
    if (isSubmitted) return;

    let recaptchaToken = '';
    document.querySelectorAll('[name="g-recaptcha-response"]').forEach(el => {
      if (el.value && el.value.length > 20) recaptchaToken = el.value;
    });

    let turnstileToken = '';
    document.querySelectorAll('[name="cf-turnstile-response"]').forEach(el => {
      if (el.value && el.value.length > 20) turnstileToken = el.value;
    });

    // Also check window.grecaptcha
    try {
      if (window.grecaptcha && typeof window.grecaptcha.getResponse === 'function') {
        const t = window.grecaptcha.getResponse();
        if (t && t.length > 20) recaptchaToken = t;
      }
    } catch (e) {}

    // Check if captcha container exists on page
    const captchaContainer = document.querySelector('.g-recaptcha, #recaptcha-2, #recaptcha, .cf-turnstile');

    if (captchaContainer && !recaptchaToken && !turnstileToken) {
      // Captcha present but not solved yet
      window.Link4MHUD.showCaptchaAlert(true);
      window.Link4MHUD.setStatus('⚠️ Vui lòng giải Captcha');
      window.Link4MHUD.log('Chờ bạn giải Captcha trên màn hình...', 'orange');

      // Scroll captcha into view so user can easily solve it
      captchaContainer.scrollIntoView({ behavior: 'smooth', block: 'center' });

      // Start watcher interval until user completes captcha
      startCaptchaWatcher();
    } else {
      // No captcha or already solved!
      window.Link4MHUD.showCaptchaAlert(false);
      window.Link4MHUD.log('Captcha đã sẵn sàng! Đang gửi mã...', 'green');
      submitForm();
    }
  }

  // Poll for user solving captcha
  let watcherInterval = null;
  function startCaptchaWatcher() {
    if (watcherInterval) return;

    watcherInterval = setInterval(() => {
      let token = '';
      document.querySelectorAll('[name="g-recaptcha-response"], [name="cf-turnstile-response"]').forEach(el => {
        if (el.value && el.value.length > 20) token = el.value;
      });

      try {
        if (window.grecaptcha && typeof window.grecaptcha.getResponse === 'function') {
          const t = window.grecaptcha.getResponse();
          if (t && t.length > 20) token = t;
        }
      } catch (e) {}

      if (token && token.length > 20) {
        clearInterval(watcherInterval);
        watcherInterval = null;
        window.Link4MHUD.showCaptchaAlert(false);
        window.Link4MHUD.log('✅ Đã nhận giải Captcha thành công!', 'green');
        submitForm();
      }
    }, 500);
  }

  // Submit the form and trigger unlock
  function submitForm() {
    if (isSubmitted) return;
    isSubmitted = true;
    window.Link4MHUD.setStatus('Đang gửi...');

    const f2 = document.querySelector('#main-form-2');
    if (f2) {
      if (window.jQuery && typeof checkPassword === 'function') {
        window.check_form = jQuery(f2);
        try { checkPassword(); } catch (e) {}
      }
      const btn = f2.querySelector('button[type="submit"], input[type="submit"], #btn-main-2, .btn, .get-link');
      if (btn) btn.click();
    }

    const f1 = document.querySelector('#main-form');
    if (f1) {
      const btn = f1.querySelector('button[type="submit"], input[type="submit"], #btn-main, .btn, .get-link');
      if (btn) btn.click();
    }

    window.Link4MHUD.log('Đã gửi form xác thực!', 'cyan');
    monitorDestinationRedirect();
  }

  // Watch for destination button unlock
  function monitorDestinationRedirect() {
    let checkCount = 0;
    const destInterval = setInterval(() => {
      checkCount++;

      // Check window.destination_url
      if (window.destination_url && window.destination_url.startsWith('http') && !window.destination_url.includes('link4m')) {
        onDestinationFound(window.destination_url);
        clearInterval(destInterval);
        return;
      }

      // Check .get-link button
      const getLinkBtn = document.querySelector('.get-link, a#get-link, a[href*="download"], #btn-get-link, .btn-success');
      if (getLinkBtn) {
        const href = getLinkBtn.getAttribute('href') || '';
        if (href.startsWith('http') && !href.includes('link4m') && !href.includes('about:blank')) {
          onDestinationFound(href);
          clearInterval(destInterval);
          return;
        }
        if (!getLinkBtn.classList.contains('disabled')) {
          getLinkBtn.click();
        }
      }

      if (checkCount > 40) {
        clearInterval(destInterval);
      }
    }, 500);
  }

  function onDestinationFound(destUrl) {
    window.Link4MHUD.setStatus('🎉 THÀNH CÔNG');
    window.Link4MHUD.log(`Link đích: ${destUrl}`, 'green');
    chrome.runtime.sendMessage({
      type: 'LINK4M_COMPLETED',
      destinationUrl: destUrl
    });

    setTimeout(() => {
      window.location.href = destUrl;
    }, 1200);
  }

  // Hook manual UI button requests
  window.onStartFlowRequested = () => {
    window.Link4MHUD.log('Bắt đầu thủ công toàn bộ flow...', 'cyan');
    if (!scanExistingDOM()) {
      autoOpenSponsor();
    }
  };

  window.onManualOpenSponsorRequested = () => {
    if (currentSponsorDomain) {
      autoOpenSponsor();
    } else {
      window.Link4MHUD.log('Chưa nhận diện được domain tài trợ', 'orange');
    }
  };

  window.onManualSubmitRequested = () => {
    verifyCaptchaAndSubmit();
  };

  // Listen to messages from background worker
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === 'STATUS_UPDATE') {
      window.Link4MHUD.log(msg.detail, 'cyan');
    } else if (msg.type === 'FILL_CODE_AND_SUBMIT') {
      fillCode(msg.code);
    }
  });

  // Run DOM scan on load
  setTimeout(() => {
    scanExistingDOM();
  }, 1000);

})();
