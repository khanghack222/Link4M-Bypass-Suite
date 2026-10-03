/**
 * QCaptcha loader — plan/06 §1, plan/11 §9.1.
 *
 * Zero dependency. Bundle này chạy trên trang của khách hàng nên mỗi dependency là
 * một rủi ro bảo mật cho họ (plan/11 §9.8).
 *
 * Registry theo widgetID chứ không dùng biến global ⇒ nhiều widget trên một trang
 * hoạt động đúng, và React 18 StrictMode render hai lần không tạo widget trùng
 * (plan/11 §9.5).
 */
(function () {
  'use strict';

  var script = document.currentScript;
  var params = new URLSearchParams((script && script.src.split('?')[1]) || '');
  var SCRIPT_ORIGIN = script ? new URL(script.src).origin : location.origin;

  /**
   * Origin phục vụ iframe. Server thay chuỗi này lúc trả api.js.
   *
   * Ranh giới bảo mật ở plan/01 §5 chỉ tồn tại thật khi iframe khác origin với
   * trang khách hàng — cùng origin thì trang khách đọc được nội bộ widget và mọi
   * lớp cô lập chỉ còn trên giấy. Khi chưa cấu hình, rơi về origin của script:
   * chạy được cho dev, nhưng KHÔNG có cô lập.
   */
  var FRAME_ORIGIN = 'https://frame.103-141-140-153.sslip.io';
  if (FRAME_ORIGIN.indexOf('__QC_') === 0) FRAME_ORIGIN = SCRIPT_ORIGIN;
  var COMPAT = params.get('compat') || (params.get('recaptchacompat') === 'off' ? '' : '');

  var widgets = Object.create(null);
  var seq = 0;

  function readParams(el) {
    var d = el.dataset;
    return {
      sitekey: d.sitekey || '',
      // 'auto' = theo cài đặt hệ điều hành. KHÔNG mặc định 'light': mặc định sáng
      // nghĩa là mọi trang không khai báo gì đều ép sáng, kể cả khi máy đang ở chế
      // độ tối — mà `tokens.css` thì vẫn theo hệ điều hành, nên hai bên lệch nhau.
      theme: d.theme || 'auto',
      // Không khai gì ⇒ ngôn ngữ mặc định (tiếng Việt). Khai 'auto' để theo cài đặt
      // trình duyệt. Xem `initLang` trong i18n.js.
      lang: d.lang || '',
      // Chỉ dùng cho trang demo. Server ở production bỏ qua trường này.
      forceType: d.forceType || '',
      size: d.size || 'normal',
      tabindex: d.tabindex || '0',
      callback: d.callback || '',
      'expired-callback': d.expiredCallback || '',
      'chalexpired-callback': d.chalexpiredCallback || '',
      'error-callback': d.errorCallback || '',
      'open-callback': d.openCallback || '',
      'close-callback': d.closeCallback || '',
    };
  }

  function callHook(name, arg) {
    if (!name) return;
    var fn = window[name];
    if (typeof fn === 'function') fn(arg);
  }

  function fieldNames() {
    var names = ['q-captcha-response'];
    if (COMPAT === 'hcaptcha') names.push('h-captcha-response');
    if (COMPAT === 'recaptcha') names.push('g-recaptcha-response');
    return names;
  }

  function setResponse(w, token) {
    var form = w.el.closest('form');
    fieldNames().forEach(function (name) {
      var input = w.inputs[name];
      if (!input) {
        input = document.createElement('textarea');
        input.name = name;
        input.style.cssText = 'display:none';
        input.readOnly = true;
        (form || w.el).appendChild(input);
        w.inputs[name] = input;
      }
      input.value = token || '';
    });
  }

  function render(container, opts) {
    var el = typeof container === 'string' ? document.querySelector(container) : container;
    if (!el) throw new Error('qcaptcha: container not found');
    if (el.dataset.qcaptchaId) return el.dataset.qcaptchaId; // idempotent

    var id = 'qc-' + ++seq;
    var cfg = Object.assign(readParams(el), opts || {});
    if (!cfg.sitekey) throw new Error('qcaptcha: missing sitekey');

    var frame = document.createElement('iframe');
    frame.title = 'QCaptcha';
    frame.setAttribute('scrolling', 'no');
    // Reserve space cố định ⇒ CLS = 0 (plan/08 §10.8).
    var compact = cfg.size === 'compact';
    frame.style.cssText =
      'border:0;width:' + (compact ? '164px' : '302px') + ';height:' + (compact ? '144px' : '76px') +
      ';display:block;overflow:hidden;color-scheme:normal';
    frame.src =
      FRAME_ORIGIN + '/frame.html#' +
      encodeURIComponent(JSON.stringify({ id: id, sitekey: cfg.sitekey, theme: cfg.theme, lang: cfg.lang, size: cfg.size, forceType: cfg.forceType, host: location.origin }));

    el.appendChild(frame);
    el.dataset.qcaptchaId = id;

    var w = { id: id, el: el, frame: frame, cfg: cfg, token: '', key: '', inputs: {} };
    widgets[id] = w;
    setResponse(w, '');
    return id;
  }

  window.addEventListener('message', function (ev) {
    // plan/01 §5 — origin check nghiêm ngặt. Không có dòng này thì bất kỳ trang nào
    // cũng postMessage giả token vào được.
    if (ev.origin !== FRAME_ORIGIN) return;
    var msg = ev.data;
    if (!msg || msg.src !== 'qcaptcha' || !widgets[msg.id]) return;
    var w = widgets[msg.id];

    switch (msg.type) {
      case 'resize':
        // Đặt từng thuộc tính thay vì nối vào cssText: nối chuỗi làm style phình
        // thêm mỗi lần mở/đóng overlay, và sau vài lượt thì không gỡ sạch được nữa.
        if (msg.overlay) {
          w.frame.style.position = 'fixed';
          w.frame.style.inset = '0';
          w.frame.style.width = '100vw';
          w.frame.style.height = '100vh';
          w.frame.style.zIndex = '2147483647';
          w.frame.style.background = 'rgba(0,0,0,.45)';
        } else {
          w.frame.style.position = '';
          w.frame.style.inset = '';
          w.frame.style.zIndex = '';
          w.frame.style.background = '';
          w.frame.style.width = msg.w + 'px';
          w.frame.style.height = msg.h + 'px';
        }
        break;
      case 'ready':
        w.ready = true;
        // Lệnh execute() gọi trước khi iframe kịp gắn listener sẽ mất hút. Xếp hàng
        // rồi phát lại khi frame báo sẵn sàng.
        if (w.queued) { post(w, w.queued); w.queued = null; }
        callHook(w.cfg['ready-callback']);
        break;
      case 'verified':
        w.token = msg.token;
        w.key = msg.key || '';
        setResponse(w, msg.token);
        callHook(w.cfg.callback, msg.token);
        if (w.pending) { w.pending.resolve({ response: msg.token, key: w.key }); w.pending = null; }
        break;
      case 'expired':
        w.token = '';
        setResponse(w, '');
        callHook(w.cfg['expired-callback']);
        break;
      case 'chalexpired':
        callHook(w.cfg['chalexpired-callback']);
        break;
      case 'open':
        callHook(w.cfg['open-callback']);
        break;
      case 'close':
        callHook(w.cfg['close-callback']);
        break;
      case 'error':
        callHook(w.cfg['error-callback'], msg.err);
        if (w.pending) { w.pending.reject(new Error(msg.err)); w.pending = null; }
        break;
    }
  });

  function post(w, type, data) {
    w.frame.contentWindow.postMessage(Object.assign({ src: 'qcaptcha-parent', type: type }, data || {}), FRAME_ORIGIN);
  }

  function firstId() {
    var k = Object.keys(widgets);
    return k.length ? k[0] : null;
  }

  var api = {
    render: render,
    execute: function (id, opts) {
      if (id && typeof id === 'object') { opts = id; id = null; }
      var w = widgets[id || firstId()];
      if (!w) throw new Error('qcaptcha: no widget');
      if (w.ready) post(w, 'execute');
      else w.queued = 'execute';
      if (opts && opts.async) {
        return new Promise(function (resolve, reject) { w.pending = { resolve: resolve, reject: reject }; });
      }
      return undefined;
    },
    reset: function (id) {
      var w = widgets[id || firstId()];
      if (!w) return;
      w.token = '';
      setResponse(w, '');
      post(w, 'reset');
    },
    remove: function (id) {
      var w = widgets[id || firstId()];
      if (!w) return;
      w.frame.remove();
      delete w.el.dataset.qcaptchaId;
      delete widgets[w.id];
    },
    getResponse: function (id) {
      var w = widgets[id || firstId()];
      return w ? w.token : '';
    },
    getRespKey: function (id) {
      var w = widgets[id || firstId()];
      return w ? w.key : '';
    },
    setData: function () { /* enterprise: rqdata — chưa triển khai */ },
  };

  window.qcaptcha = api;
  // plan/11 §6 — compat shim để site đang dùng hCaptcha/reCAPTCHA migrate bằng
  // cách đổi đúng thẻ script.
  if (COMPAT === 'hcaptcha') window.hcaptcha = api;
  if (COMPAT === 'recaptcha') window.grecaptcha = api;

  function autoRender() {
    var sel = '.q-captcha' + (COMPAT === 'hcaptcha' ? ',.h-captcha' : '') + (COMPAT === 'recaptcha' ? ',.g-recaptcha' : '');
    document.querySelectorAll(sel).forEach(function (el) {
      if (!el.dataset.qcaptchaId) { try { render(el); } catch (e) { console.error(e); } }
    });
    callHook(params.get('onload'));
  }

  if (params.get('render') === 'explicit') {
    callHook(params.get('onload'));
  } else if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoRender);
  } else {
    autoRender();
  }
})();
