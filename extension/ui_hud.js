/**
 * ⚡ LINK4M PROMAX HUD CONTROLLER ⚡
 * In-page Floating HUD component for Link4M tabs.
 */

window.Link4MHUD = (function() {
  let container = null;
  let logEl = null;
  let statusEl = null;
  let domainEl = null;
  let codeEl = null;
  let alertBanner = null;

  function initHUD() {
    if (document.getElementById('link4m-pro-hud')) return;

    container = document.createElement('div');
    container.id = 'link4m-pro-hud';
    container.innerHTML = `
      <div class="hud-header" id="l4m-drag-handle">
        <div class="hud-brand">
          <span class="hud-logo">⚡ LINK4M PROMAX</span>
          <span class="hud-badge">v2.1</span>
        </div>
        <div class="hud-controls">
          <button class="hud-btn-icon" id="l4m-btn-min" title="Thu nhỏ">_</button>
          <button class="hud-btn-icon" id="l4m-btn-close" title="Đóng">×</button>
        </div>
      </div>

      <div class="hud-body">
        <div class="status-card">
          <div class="status-row">
            <span class="status-label">Trạng thái:</span>
            <span class="status-value" id="l4m-val-status">Khởi tạo...</span>
          </div>
          <div class="status-row">
            <span class="status-label">Nhà tài trợ:</span>
            <span class="status-value" id="l4m-val-domain">Đang quét...</span>
          </div>
          <div class="status-row">
            <span class="status-label">Mã xác nhận:</span>
            <span class="status-value" id="l4m-val-code" style="color: #4ade80;">Chưa có</span>
          </div>
        </div>

        <div class="captcha-alert-banner" id="l4m-captcha-banner">
          <div class="captcha-alert-title">⚠️ YÊU CẦU GIẢI CAPTCHA</div>
          <div class="captcha-alert-desc">
            Vui lòng giải captcha hiển thị bên dưới.<br>
            Hệ thống sẽ <b>TỰ ĐỘNG</b> gửi mã ngay sau khi bạn tích xong!
          </div>
        </div>

        <div class="hud-actions">
          <button class="hud-btn-main" id="l4m-act-run">
            <span>⚡ TỰ ĐỘNG CHẠY FLOW</span>
          </button>
          <button class="hud-btn-sub" id="l4m-act-open">
            <span>🌐 Mở Tài Trợ</span>
          </button>
          <button class="hud-btn-sub" id="l4m-act-submit">
            <span>🚀 Tiếp Tục</span>
          </button>
          <button class="hud-btn-sub" id="l4m-act-reset" style="grid-column: span 2;">
            <span>🔄 Khởi động lại</span>
          </button>
        </div>

        <div class="hud-console" id="l4m-console"></div>
      </div>
    `;

    document.body.appendChild(container);

    // Elements
    logEl = document.getElementById('l4m-console');
    statusEl = document.getElementById('l4m-val-status');
    domainEl = document.getElementById('l4m-val-domain');
    codeEl = document.getElementById('l4m-val-code');
    alertBanner = document.getElementById('l4m-captcha-banner');

    setupDraggable();
    setupControls();

    log('Khởi chạy giao diện HUD thành công', 'cyan');
  }

  function setupDraggable() {
    const handle = document.getElementById('l4m-drag-handle');
    let isDragging = false;
    let startX, startY, initLeft, initTop;

    handle.addEventListener('mousedown', (e) => {
      isDragging = true;
      startX = e.clientX;
      startY = e.clientY;
      const rect = container.getBoundingClientRect();
      initLeft = rect.left;
      initTop = rect.top;

      const onMouseMove = (ev) => {
        if (!isDragging) return;
        const dx = ev.clientX - startX;
        const dy = ev.clientY - startY;
        container.style.right = 'auto';
        container.style.left = `${Math.max(10, initLeft + dx)}px`;
        container.style.top = `${Math.max(10, initTop + dy)}px`;
      };

      const onMouseUp = () => {
        isDragging = false;
        window.removeEventListener('mousemove', onMouseMove);
        window.removeEventListener('mouseup', onMouseUp);
      };

      window.addEventListener('mousemove', onMouseMove);
      window.addEventListener('mouseup', onMouseUp);
    });
  }

  function setupControls() {
    const minBtn = document.getElementById('l4m-btn-min');
    minBtn.addEventListener('click', () => {
      container.classList.toggle('minimized');
      minBtn.innerText = container.classList.contains('minimized') ? '+' : '_';
    });

    const closeBtn = document.getElementById('l4m-btn-close');
    closeBtn.addEventListener('click', () => {
      container.style.display = 'none';
    });

    document.getElementById('l4m-act-reset').addEventListener('click', () => {
      chrome.runtime.sendMessage({ type: 'RESET_QUEST' }, () => {
        window.location.reload();
      });
    });

    document.getElementById('l4m-act-submit').addEventListener('click', () => {
      if (window.onManualSubmitRequested) {
        window.onManualSubmitRequested();
      }
    });

    document.getElementById('l4m-act-open').addEventListener('click', () => {
      if (window.onManualOpenSponsorRequested) {
        window.onManualOpenSponsorRequested();
      }
    });

    document.getElementById('l4m-act-run').addEventListener('click', () => {
      if (window.onStartFlowRequested) {
        window.onStartFlowRequested();
      }
    });
  }

  function log(msg, colorClass = '') {
    if (!logEl) return;
    const timeStr = new Date().toLocaleTimeString([], { hour12: false });
    const item = document.createElement('div');
    item.className = 'hud-log-item';
    item.innerHTML = `<span class="log-time">[${timeStr}]</span> <span class="log-${colorClass}">${msg}</span>`;
    logEl.appendChild(item);
    logEl.scrollTop = logEl.scrollHeight;
  }

  function setStatus(text) {
    if (statusEl) statusEl.innerText = text;
  }

  function setDomain(text) {
    if (domainEl) domainEl.innerText = text;
  }

  function setCode(text) {
    if (codeEl) codeEl.innerText = text;
  }

  function showCaptchaAlert(show = true) {
    if (alertBanner) {
      if (show) alertBanner.classList.add('active');
      else alertBanner.classList.remove('active');
    }
  }

  return {
    init: initHUD,
    log: log,
    setStatus: setStatus,
    setDomain: setDomain,
    setCode: setCode,
    showCaptchaAlert: showCaptchaAlert
  };
})();
