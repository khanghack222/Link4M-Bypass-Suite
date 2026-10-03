/**
 * QCaptcha frame — code chạy trong iframe. plan/02 (collector), plan/08 (UX/a11y).
 *
 * Bí mật duy nhất ở đây là: không có bí mật nào ở đây. Mọi quyết định nằm ở server;
 * file này chỉ thu thập bằng chứng và vẽ giao diện (plan/00 §5).
 */

import { skeleton } from './skeleton.js';
import { setToolbarBusy } from './toolbar.js';

/**
 * Renderer nạp THEO NHU CẦU — PHASE-1 §10.5.
 *
 * Import tĩnh cả sáu loại nghĩa là mọi người dùng tải cả sáu, kể cả người chỉ gặp
 * một loại: 99KB thô cho một widget mà phần dùng tới chỉ là một phần sáu của nó.
 * Nạp động đưa con số đó về 78KB thô / 30KB sau nén, dưới ngân sách 60KB ở §9.9.
 *
 * Độ trễ thêm được giấu bằng cách bắt đầu nạp NGAY khi biết loại, tức là trước lúc
 * giải PoW — thứ vốn tốn vài trăm mili giây. Xem `preload` ở `start()`.
 */
const LOADERS = {
  grid3x3: () => import('./challenge-grid.js').then((m) => m.renderGrid),
  // C3 và C6 dùng lại đúng renderer lưới của C1 (§9.5) — chúng khác nhau ở CÂU HỎI,
  // không ở cách trình bày.
  relational: () => import('./challenge-grid.js').then((m) => m.renderGrid),
  oddoneout: () => import('./challenge-grid.js').then((m) => m.renderGrid),
  audio: () => import('./challenge-audio.js').then((m) => m.renderAudio),
  spatial: () => import('./challenge-spatial.js').then((m) => m.renderSpatial),
  order: () => import('./challenge-order.js').then((m) => m.renderOrder),
  pointclick: () => import('./challenge-pointclick.js').then((m) => m.renderPointclick),
  countshapes: () => import('./challenge-countshapes.js').then((m) => m.renderCountshapes),
};

const rendererCache = new Map();

/**
 * Nạp (và nhớ) renderer của một loại. Gọi nhiều lần chỉ tải một lần.
 *
 * Xoá khỏi cache khi Promise reject: nếu không, MỘT lần mất mạng thoáng qua lúc tải
 * chunk làm hỏng vĩnh viễn loại challenge này cho cả phiên trang — mọi lần gọi sau,
 * kể cả khi mạng đã khôi phục, đều trả lại đúng Promise đã hỏng đó (giữ nguyên khoá
 * cache = giữ nguyên lỗi). Xem docs/plans/03_frame_loading_ux.md §2.2/§4.3.
 */
function loadRenderer(type) {
  if (!LOADERS[type]) return Promise.resolve(null);
  if (!rendererCache.has(type)) {
    const p = LOADERS[type]().catch((err) => { rendererCache.delete(type); throw err; });
    rendererCache.set(type, p);
  }
  return rendererCache.get(type);
}
import { initLang, setLang, t } from './i18n.js';

const cfg = JSON.parse(decodeURIComponent(location.hash.slice(1) || '%7B%7D'));
const PARENT = cfg.host || '*';
const boxHost = document.getElementById('box-host');
const root = document.getElementById('modal-host');
const live = document.getElementById('live');

// Lựa chọn TƯỜNG MINH của trang luôn thắng cài đặt hệ điều hành — kể cả khi trang
// chọn 'light' còn máy đang ở chế độ tối. Không đặt thuộc tính nào khi theme là
// 'auto', để @media trong tokens.css/frame.html quyết định.
initLang(cfg.lang);

if (['dark', 'light', 'contrast'].includes(cfg.theme)) {
  document.documentElement.dataset.theme = cfg.theme;
}

/* ───────────────────────── postMessage ───────────────────────── */

function toParent(type, data = {}) {
  parent.postMessage({ src: 'qcaptcha', id: cfg.id, type, ...data }, PARENT);
}
function resize(w, h, overlay = false) {
  toParent('resize', { w, h, overlay });
}

window.addEventListener('message', (ev) => {
  // Chỉ nhận lệnh từ đúng trang cha đã nhúng ta. `PARENT` lấy từ hash do loader
  // đặt, nhưng loader chạy trên trang cha nên giá trị đó do trang cha kiểm soát —
  // vì vậy phải đối chiếu với origin THẬT của message, không tin riêng hash.
  if (PARENT !== '*' && ev.origin !== PARENT) return;
  const m = ev.data;
  if (!m || m.src !== 'qcaptcha-parent') return;
  if (m.type === 'execute') start();
  // `reset()` chứ KHÔNG phải `renderIdle()`. Hai hàm này trông giống nhau trên màn
  // hình — cùng vẽ ra ô checkbox — nhưng `renderIdle` chỉ VẼ, còn `reset` mới xoá
  // phiên. Gọi nhầm thì widget trông như đã đặt lại nhưng vẫn giữ `sid` cũ, và cú
  // bấm tiếp theo gửi lại tín hiệu cho phiên đã dùng ⇒ server trả `replayed-payload`
  // (đúng như nó phải làm) ⇒ widget hiện "Có lỗi xảy ra".
  //
  // Trang demo gọi `qcaptcha.reset()` ngay sau khi gửi form, nên lỗi này xuất hiện
  // ở đúng lần xác minh thứ hai trở đi.
  if (m.type === 'reset') reset();
});

/* ─────────────────── Thu thập tín hiệu (plan/02) ─────────────────── */

const behavior = {
  mouseEvents: 0,
  untrustedEvents: 0,
  keyboardNav: false,
  timestamps: [],
  track: [],
  lastPoint: null,
  clickOffsetPx: null,
  pauseBeforeClickMs: null,
  lastMoveAt: null,
  readyAt: performance.now(),
  timeToClickMs: null,
  // Cảm ứng: KHÔNG bao giờ phát mousemove trước cú chạm đầu tiên — đây là hành vi
  // bình thường của người dùng thật trên di động, không phải dấu hiệu bot. SR040
  // (rules.js) và scoreMovement (behavior-model.js) đều cần tín hiệu này để không
  // phạt oan lượt chạm đầu tiên (spec/features.yaml nhóm `touch`).
  touchEvents: 0,
  touchRadii: [],
};

addEventListener(
  'mousemove',
  (e) => {
    behavior.mouseEvents++;
    if (!e.isTrusted) behavior.untrustedEvents++;
    const t = performance.now();
    if (behavior.timestamps.length < 400) behavior.timestamps.push(t);
    // Quỹ đạo là đầu vào của model hành vi và của phát hiện phát lại. Không gửi nó
    // thì cả hai lớp đó tự từ chối và ta mất tuyến duy nhất bắt được bot cấp 3+.
    if (behavior.track.length < 400) {
      behavior.track.push({ x: Math.round(e.clientX), y: Math.round(e.clientY), t: Math.round(t) });
    }
    behavior.lastPoint = { x: e.clientX, y: e.clientY };
  },
  { passive: true },
);
addEventListener(
  'touchstart',
  (e) => {
    behavior.touchEvents++;
    if (!e.isTrusted) behavior.untrustedEvents++;
    const touch = e.touches?.[0];
    // radiusX = 0/undefined trên phần lớn bot dispatch touch event; ngón tay thật
    // luôn có diện tích tiếp xúc (spec/features.yaml — touch_radius_mean/variance).
    if (touch && behavior.touchRadii.length < 400) {
      behavior.touchRadii.push(touch.radiusX ?? touch.radiusY ?? 0);
    }
  },
  { passive: true },
);
addEventListener('keydown', (e) => {
  if (e.key === 'Tab' || e.key.startsWith('Arrow') || e.key === ' ' || e.key === 'Enter') {
    behavior.keyboardNav = true;
  }
}, { passive: true });

function clickOffset(el, e) {
  const r = el.getBoundingClientRect();
  const dx = e.clientX - (r.left + r.width / 2);
  const dy = e.clientY - (r.top + r.height / 2);
  return Math.hypot(dx, dy);
}

function stddev(a) {
  if (a.length < 2) return null;
  const d = [];
  for (let i = 1; i < a.length; i++) d.push(a[i] - a[i - 1]);
  const m = d.reduce((s, v) => s + v, 0) / d.length;
  return Math.sqrt(d.reduce((s, v) => s + (v - m) ** 2, 0) / d.length);
}

async function canvasHash() {
  const draw = () => {
    const c = document.createElement('canvas');
    c.width = 200; c.height = 50;
    const x = c.getContext('2d');
    if (!x) return null;
    x.textBaseline = 'top';
    x.font = '14px "Arial"';
    x.fillStyle = '#f60';
    x.fillRect(0, 0, 100, 20);
    x.fillStyle = '#069';
    x.fillText('QCaptcha \u{1F512} 0123', 2, 15);
    return c.toDataURL();
  };
  try {
    // plan/02 §B4 — gọi 3 lần: trình duyệt thật luôn ra cùng một hash. Khác nhau
    // giữa các lần = có noise nhân tạo đang được chèn vào.
    const a = draw(), b = draw(), c = draw();
    if (a === null) return { stable: null, hash: null };
    return { stable: a === b && b === c, hash: a ? await digest(a) : null };
  } catch {
    return { stable: null, hash: null };
  }
}

async function digest(s) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return btoa(String.fromCharCode(...new Uint8Array(buf).slice(0, 12)));
}

function webglInfo() {
  try {
    const c = document.createElement('canvas');
    const gl = c.getContext('webgl') || c.getContext('experimental-webgl');
    if (!gl) return { renderer: null, vendor: null };
    const ext = gl.getExtension('WEBGL_debug_renderer_info');
    return {
      renderer: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
      vendor: ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR),
    };
  } catch {
    return { renderer: null, vendor: null };
  }
}

const PROBE_FONTS = ['Arial','Verdana','Georgia','Courier New','Times New Roman','Trebuchet MS',
  'Comic Sans MS','Impact','Tahoma','Palatino','Garamond','Bookman'];

function fontCount() {
  try {
    const base = ['monospace', 'sans-serif', 'serif'];
    const span = document.createElement('span');
    span.style.cssText = 'position:absolute;left:-9999px;font-size:72px';
    span.textContent = 'mmmmmmmmmmlli';
    document.body.appendChild(span);
    const ref = {};
    for (const b of base) { span.style.fontFamily = b; ref[b] = span.offsetWidth; }
    let n = 0;
    for (const f of PROBE_FONTS) {
      if (base.some((b) => { span.style.fontFamily = `"${f}",${b}`; return span.offsetWidth !== ref[b]; })) n++;
    }
    span.remove();
    return n;
  } catch {
    // Firefox-RFP / Tor chặn dò font ⇒ null. Server KHÔNG phạt vì null (plan/03 SR015).
    return null;
  }
}

function automationProbe() {
  const artifacts = [];
  for (const k of Object.keys(window)) {
    if (/^(cdc_|\$cdc_|_selenium|__webdriver|__playwright|__puppeteer|__nightmare|_phantom)/.test(k)) {
      artifacts.push(k.slice(0, 24));
    }
  }
  if (window.callPhantom || window._phantom || window.__nightmare) artifacts.push('phantom');
  if (navigator.webdriver === true) artifacts.push('webdriver');

  // plan/02 §B3 — hàm native bị patch sẽ mất chuỗi "[native code]".
  try {
    const s = Function.prototype.toString.call(navigator.permissions.query);
    if (!s.includes('[native code]')) artifacts.push('patched-native');
  } catch { /* API không tồn tại là chuyện bình thường */ }

  const missingApis = [];
  for (const [name, ok] of [
    ['Intl', typeof Intl !== 'undefined'],
    ['Notification', 'Notification' in window],
    ['localStorage', (() => { try { return Boolean(window.localStorage); } catch { return true; } })()],
    ['requestAnimationFrame', typeof requestAnimationFrame === 'function'],
    ['MutationObserver', typeof MutationObserver === 'function'],
  ]) if (!ok) missingApis.push(name);

  return { artifacts, missingApis };
}

async function collect(collectList) {
  const want = new Set(collectList || []);
  const out = {
    ts: Date.now(),
    nav: {
      ua: navigator.userAgent,
      platform: navigator.platform,
      languages: navigator.languages ? navigator.languages.slice(0, 4) : [],
      hardwareConcurrency: navigator.hardwareConcurrency ?? null,
      deviceMemory: navigator.deviceMemory ?? null,
      maxTouchPoints: navigator.maxTouchPoints ?? 0,
      webdriver: navigator.webdriver === true,
      tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
    },
    screen: { w: screen.width, h: screen.height, dpr: devicePixelRatio, depth: screen.colorDepth },
    behavior: {
      mouseEvents: behavior.mouseEvents,
      untrustedEvents: behavior.untrustedEvents,
      keyboardNav: behavior.keyboardNav,
      timeToClickMs: behavior.timeToClickMs,
      clickOffsetPx: behavior.clickOffsetPx,
      pauseBeforeClickMs: behavior.pauseBeforeClickMs,
      interEventStddev: stddev(behavior.timestamps),
      track: behavior.track,
      touchEvents: behavior.touchEvents,
      touchRadii: behavior.touchRadii,
    },
    // Thời gian PoW thật, để server đối chiếu với thời gian lý thuyết. Nộp nhanh
    // bất khả thi nghĩa là đã port sang GPU/native (plan/05 §9.1).
    telemetry: { powMs: state.powMs ?? null },
  };
  if (want.has('automation')) out.automation = automationProbe();
  if (want.has('webgl')) out.webgl = webglInfo();
  if (want.has('canvas')) out.canvas = await canvasHash();
  if (want.has('fonts')) out.fonts = { count: fontCount() };
  out.fp = { ua: out.nav.ua, tz: out.nav.tz, s: `${screen.width}x${screen.height}`, hc: out.nav.hardwareConcurrency };
  return out;
}

/* ───────────── Crypto phiên: ECDH P-256 → HKDF → AES-GCM ───────────── */

const b64u = {
  enc: (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''),
  dec: (s) => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/')), (c) => c.charCodeAt(0)),
};

async function sealPayload(serverPubB64, sid, obj) {
  const serverKey = await crypto.subtle.importKey(
    'raw', b64u.dec(serverPubB64), { name: 'ECDH', namedCurve: 'P-256' }, false, [],
  );
  const mine = await crypto.subtle.generateKey({ name: 'ECDH', namedCurve: 'P-256' }, true, ['deriveBits']);
  const shared = await crypto.subtle.deriveBits({ name: 'ECDH', public: serverKey }, mine.privateKey, 256);

  const ikm = await crypto.subtle.importKey('raw', shared, 'HKDF', false, ['deriveBits']);
  const bits = await crypto.subtle.deriveBits(
    { name: 'HKDF', hash: 'SHA-256', salt: new TextEncoder().encode(sid), info: new TextEncoder().encode('qcaptcha/v1/signals') },
    ikm, 256,
  );
  const key = await crypto.subtle.importKey('raw', bits, 'AES-GCM', false, ['encrypt']);

  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, new TextEncoder().encode(JSON.stringify(obj)));
  return {
    clientPub: b64u.enc(await crypto.subtle.exportKey('raw', mine.publicKey)),
    iv: b64u.enc(iv),
    ct: b64u.enc(ct),
  };
}

/* ─────────────────────── PoW worker (plan/05 §1) ─────────────────────── */

// Lõi thuật toán nằm ở web/pow-worker.js + web/scrypt.js, không nhúng chuỗi ở đây:
// một bản cài đặt duy nhất là một chỗ duy nhất để sai.


let worker = null;
function solvePow(pow, onProgress) {
  return new Promise((resolve) => {
    if (!pow || !pow.bits) return resolve('0');
    // Module worker phục vụ từ file thật thay vì blob: nhờ vậy lõi scrypt dùng
    // chung một bản với server, và bảo chứng "khớp native" ở test/scrypt.test.js
    // áp dụng luôn cho phía trình duyệt.
    if (!worker) worker = new Worker('/pow-worker.js', { type: 'module' });
    const handler = (e) => {
      if (e.data.progress !== undefined) return onProgress?.(e.data.progress);
      worker.removeEventListener('message', handler);
      // Báo thời gian thật để server đối chiếu với thời gian lý thuyết — nộp nhanh
      // bất khả thi nghĩa là đã port sang GPU/native (plan/05 §9.1).
      state.powMs = e.data.ms ?? null;
      resolve(e.data.nonce ?? '0');
    };
    worker.addEventListener('message', handler);
    worker.postMessage({ algo: pow.algo, salt: pow.salt, bits: pow.bits, N: pow.N, r: pow.r });
  });
}

/* ───────────────────────── Giao diện ───────────────────────── */

const state = { sid: null, pubkey: null, pow: null, collect: [], challenge: null, token: '', busy: false };
let overlayActive = false;

function announce(msg) { live.textContent = msg; }

function prepareModal() {
  root.hidden = true;
  root.setAttribute('aria-hidden', 'true');
  root.inert = true;
}

function closeModal() {
  prepareModal();
  boxHost.hidden = false;
  if (overlayActive) {
    resize(cfg.size === 'compact' ? 164 : 302, 76, false);
    overlayActive = false;
  }
}

function openModal() {
  // Box vẫn tồn tại trong DOM và giữ state riêng, nhưng không được lọt lên đầu
  // viewport khi iframe đã chuyển thành fullscreen overlay.
  boxHost.hidden = true;
  overlayActive = true;
  resize(innerWidth, innerHeight, true);
  root.hidden = false;
  root.removeAttribute('aria-hidden');
  root.inert = false;
  toParent('open');
}

function renderIdle(label = t('cb.label')) {
  closeModal();
  boxHost.innerHTML = `
    <div class="box" id="box" role="checkbox" aria-checked="false" tabindex="0">
      <span class="cb" id="cb" aria-hidden="true"></span>
      <span class="label">${label}</span>
      <span class="brand">${t('cb.brand')}<br>${t('cb.privacy')}</span>
    </div>`;
  const box = boxHost.querySelector('#box');
  box.addEventListener('click', (e) => {
    behavior.timeToClickMs = performance.now() - behavior.readyAt;
    behavior.clickOffsetPx = clickOffset(box, e);
    // Khoảng dừng trước khi bấm: người thật dừng 40–150ms để nhắm, bot bấm ngay.
    const lastMove = behavior.track.at(-1);
    if (lastMove) behavior.pauseBeforeClickMs = Math.round(performance.now() - lastMove.t);
    start();
  });
  box.addEventListener('keydown', (e) => {
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault();
      behavior.keyboardNav = true;
      behavior.timeToClickMs = performance.now() - behavior.readyAt;
      start();
    }
  });
}

function renderBusy(text = t('cb.verifying')) {
  const keepOverlay = overlayActive;
  prepareModal();
  if (!keepOverlay) {
    boxHost.hidden = false;
    resize(cfg.size === 'compact' ? 164 : 302, 76, false);
  } else {
    boxHost.hidden = true;
  }
  boxHost.innerHTML = `<div class="box"><span class="spin" aria-hidden="true"></span><span class="label">${text}</span>
    <span class="brand">QCaptcha</span></div>`;
  announce(text);
}

function renderSuccess() {
  closeModal();
  boxHost.innerHTML = `<div class="box"><span class="cb on" aria-hidden="true">✓</span>
    <span class="label">${t('cb.verified')}</span><span class="brand">${t('cb.brand')}</span></div>`;
  announce(t('cb.verified'));
}

function renderError(msg) {
  closeModal();
  boxHost.innerHTML = `<div class="box" id="box" role="button" tabindex="0">
    <span class="cb" aria-hidden="true">!</span><span class="label">${msg}</span><span class="brand">${t('cb.retry')}</span></div>`;
  boxHost.querySelector('#box').addEventListener('click', () => { reset(); start(); });
  announce(msg);
}

async function renderChallenge(ch) {
  state.challenge = ch;
  state.startedAt = performance.now();

  // Giữ box nguyên trạng trong lúc tải renderer/PoW. Modal chỉ được mở sau khi
  // nội dung đã dựng xong, tránh nhấp nháy một iframe fullscreen rỗng.
  prepareModal();

  // Dọn renderer cũ trước khi vẽ cái mới — nếu không, thẻ <audio> của màn hình
  // trước vẫn phát tiếp trong nền.
  state.renderer?.destroy?.();
  state.renderer = null;

  const shared = {
    onSubmit: (value, extra) => submit(value, extra),
    // `reason` chỉ để ghi nhận (menu "Ảnh khó nhìn"), không đổi hành vi: thứ người
    // dùng cần lúc đó là một câu khác, ngay lập tức.
    onRefresh: () => { announce(t('st.loading')); start(true); },
    onAccessible: switchToAccessible,
    onBack: () => start(true),
    // §10.5 — Bỏ qua: đổi sang LOẠI câu hỏi khác mà KHÔNG huỷ phiên và không mất
    // tiến độ. Khác `onRefresh` ở chỗ đó: refresh làm lại từ đầu.
    onSkip: skipType,
    onLang: (lang) => {
      setLang(lang);
      // Vẽ lại đúng câu hỏi hiện tại bằng ngôn ngữ mới. Không gọi server: câu hỏi
      // đã có sẵn cả hai bản, và cấp câu mới chỉ vì đổi ngôn ngữ là phạt người dùng
      // vì một thao tác giao diện.
      renderChallenge(state.challenge);
    },
    onKeyboard: () => { behavior.keyboardNav = true; },
    onPick: (el, e) => { behavior.clickOffsetPx = clickOffset(el, e); },
    // Cảm ứng không phát mousemove, nên renderer kéo-thả đẩy điểm lên tường minh.
    // Không có đường này thì model hành vi mất trắng dữ liệu của người dùng di động.
    onDragMove: (x, y) => {
      if (behavior.track.length < 400) {
        behavior.track.push({ x: Math.round(x), y: Math.round(y), t: Math.round(performance.now()) });
      }
      behavior.mouseEvents++;
    },
    announce,
  };

  const render = await loadRenderer(ch.type);
  if (!render) {
    // Server cấp một loại mà bundle này không biết vẽ — thường là widget cũ gặp
    // server mới. Nói thẳng còn hơn để màn hình trắng.
    renderError(t('cb.error'));
    return;
  }
  // Người dùng có thể đã bấm Bỏ qua trong lúc chờ nạp module; nếu vậy thì câu hỏi
  // này không còn là câu đang hiển thị nữa và vẽ nó ra là ghi đè lên câu mới.
  if (state.challenge !== ch) return;
  state.renderer = render(root, ch, shared);
  skeleton(root);
  // Gỡ trước khi gắn: `renderChallenge` chạy lại cho mỗi bước, không gỡ thì mỗi lần
  // nhấn Enter sẽ submit nhiều lần chồng lên nhau.
  removeEventListener('keydown', escOnce);
  addEventListener('keydown', escOnce);
  root.removeEventListener('click', closeOnOutsideClick);
  root.addEventListener('click', closeOnOutsideClick);

  // Chỉ lúc này iframe mới chuyển sang overlay fullscreen. Box vẫn tồn tại ở
  // boxHost, nhưng được ẩn riêng trong lớp overlay và không bị renderer thay thế.
  openModal();
}

// Đóng challenge như người dùng bỏ dở: ESC hoặc bấm ra ngoài .qc-card đều đi qua
// đây, gỡ cả hai listener rồi báo cho trang chủ + vẽ lại checkbox rỗng.
function closeChallenge() {
  removeEventListener('keydown', escOnce);
  root.removeEventListener('click', closeOnOutsideClick);
  toParent('close');
  reset();
}

function escOnce(e) {
  if (e.key === 'Escape') { closeChallenge(); }

  // plan/08 §4.1 — phím A chuyển sang luồng tiếp cận được, từ BẤT KỲ loại challenge
  // nào. Bỏ qua khi đang gõ vào ô nhập, nếu không người dùng gõ chữ "a" sẽ bị nhảy
  // màn hình.
  const typing = e.target?.tagName === 'INPUT' || e.target?.tagName === 'TEXTAREA';
  if (!typing && (e.key === 'a' || e.key === 'A') && state.challenge && state.challenge.type !== 'audio') {
    e.preventDefault();
    switchToAccessible();
    return;
  }
  // Enter chỉ submit khi tiêu điểm KHÔNG nằm trên một ô — nếu không, phím Enter để
  // chọn ô sẽ vô tình gửi luôn cả bài.
  if (e.key === 'Enter' && state.challenge && !e.target?.classList?.contains('tile')) {
    e.preventDefault();
    submit();
  }
}

// Bấm ra ngoài .qc-card cũng đóng, giống ESC — trước đây chỉ có ESC, không có nút
// tắt nào khác trên overlay. `root` (#modal-host) chính là lớp nền `.qc-modal`
// (position:fixed;inset:0;display:grid;place-items:center) — bấm trúng .qc-modal
// nghĩa là bấm vào phần đệm QUANH thẻ, không phải bấm vào bất kỳ đâu bên trong nó.
function closeOnOutsideClick(e) {
  if (e.target.classList?.contains('qc-modal')) closeChallenge();
}

/* ───────────────────────── Luồng chính ───────────────────────── */

async function api(path, body, signal) {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });
  return r.json();
}

function reset() {
  state.sid = null; state.challenge = null; state.token = '';
  behavior.readyAt = performance.now();
  closeModal();
  renderIdle();
}

/**
 * Bọc chung mọi thao tác async có thể lỗi — timeout thật (`fetch` trần trước đây có
 * thể treo vô thời hạn), cờ `busy`, trạng thái nút, và MỘT nơi duy nhất quyết định
 * hiển thị gì khi lỗi.
 *
 * Trước đây bốn hàm (start/skipType/switchToAccessible/submit) tự chép lại đúng mẫu
 * try/busy/catch/finally, không hàm nào có timeout, và quan trọng nhất: không hàm
 * nào `await` đúng lời gọi `renderChallenge()` lồng bên trong nó — một `return
 * renderChallenge(...)` trần hoặc gọi trần không `await` khiến lỗi tải renderer
 * (mất mạng giữa chừng) trở thành unhandled rejection, kẹt màn hình ở `renderBusy()`
 * vĩnh viễn. Xem docs/plans/03_frame_loading_ux.md §2.1/§3/§4.1.
 */
async function runAction(fn, { timeoutMs = 15_000, onError } = {}) {
  if (state.busy) return;
  state.busy = true;
  setToolbarBusy(root, true);
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), timeoutMs);
  try {
    await fn(ac.signal);
  } catch (err) {
    console.warn('[qcaptcha]', err);
    onError(err);
  } finally {
    clearTimeout(timer);
    state.busy = false;
    setToolbarBusy(root, false);
  }
}

/** Timeout do chính `runAction` chủ động huỷ khác bản chất với lỗi mạng/server thật. */
function errorMessage(err) {
  return err?.name === 'AbortError' ? t('st.timeout') : t('st.netError');
}

/**
 * `invalid-session` không phải lỗi mạng: server đã quên hẳn `sid` (TTL 120s hết hạn
 * giữa chừng challenge, hoặc store mất session — xem app.js `SESSION_TTL`). Tiếp tục
 * gọi `/v1/solve`/`skip`/`accessible` với `state.sid` cũ chỉ nhận lại đúng lỗi này mãi
 * mãi — không có gì để "thử lại" ở phía server, phải cấp phiên mới.
 */
function isSessionLost(err) {
  return err?.message === 'invalid-session';
}

/**
 * Cấp lại phiên từ đầu sau khi phát hiện mất phiên giữa chừng challenge.
 *
 * Phải hoãn qua `setTimeout` chứ không gọi `start()` ngay: hàm này chạy bên trong
 * `onError` của `runAction`, tức là TRƯỚC khối `finally` hạ `state.busy = false` của
 * chính lần gọi đang lỗi — gọi `start()` (tự bọc `runAction`) ngay lúc đó bị chặn im
 * lặng bởi guard `if (state.busy) return`.
 */
function recoverSession() {
  announce(t('st.sessionExpired'));
  setTimeout(() => { reset(); start(); }, 0);
}

async function start(forceNew = false) {
  return runAction(async (signal) => {
    // WebCrypto chỉ tồn tại trong secure context. Mở qua http:// trên IP hoặc tên
    // miền (không phải localhost) thì `crypto.subtle` là undefined, và lỗi thật —
    // "Cannot read properties of undefined (reading 'importKey')" — không hề gợi ra
    // nguyên nhân. Chặn sớm với thông báo nói đúng việc phải làm.
    // Thông báo để tiếng Anh: nó đi ra console và postMessage cho người tích hợp,
    // không phải văn bản hiển thị cho người dùng cuối (kiểm bởi test/shell.test.js).
    if (!globalThis.crypto?.subtle) {
      throw new Error(
        'WebCrypto unavailable: this page must run in a secure context. ' +
        `Use https://, or open it via localhost (e.g. ssh -L). Current origin: ${location.origin}`,
      );
    }
    renderBusy();
    if (!state.sid || forceNew) {
      // `forceType` chỉ có tác dụng ở server dev có nạp key demo — xem `allowForcedType`
      // trong app.js. Gửi kèm ở production cũng vô hại vì server bỏ qua.
      // `host` = origin trang cha (api.js đặt vào hash từ `location.origin` của
      // chính trang nhúng). BẮT BUỘC gửi: request này đi từ trong iframe nên Origin
      // của nó là frame.<domain>, server không có cách nào khác để biết widget đang
      // chạy ở đâu mà đối chiếu allowlist domain của sitekey.
      const init = await api('/v1/init', { sitekey: cfg.sitekey, host: cfg.host, forceType: cfg.forceType || undefined }, signal);
      if (init.error) throw new Error(init.error);
      state.sid = init.sid; state.pubkey = init.pubkey; state.pow = init.pow; state.collect = init.collect;
    }

    const nonce = await solvePow(state.pow);
    const signals = await collect(state.collect);
    const sealed = await sealPayload(state.pubkey, state.sid, signals);

    const res = await api('/v1/verify_passive', { sid: state.sid, ...sealed, powNonce: nonce }, signal);
    if (res.error) throw new Error(res.error);

    if (res.action === 'pass') { finish(res.token); return; }
    if (res.action === 'challenge') {
      state.pow = res.pow;
      // Bắt đầu tải renderer NGAY, song song với việc giải PoW. PoW tốn vài trăm ms
      // nên module về trước khi cần dùng, và người dùng không thấy độ trễ nào.
      loadRenderer(res.type);
      state.challengePow = await solvePow(res.pow);
      // PHẢI await: lỗi tải renderer (mất mạng giữa chừng) phải quay lại đúng catch
      // của runAction, không phải rơi thành unhandled rejection — xem
      // docs/plans/03_frame_loading_ux.md §2.1/§4.2.
      await renderChallenge(res);
      return;
    }
    throw new Error('unexpected-action');
  }, {
    onError: (err) => {
      toParent('error', { err: String(err.message ?? err) });
      renderError(t('cb.error'));
    },
  });
}

/** @param {*} override Đáp án do renderer riêng cung cấp (ví dụ số của bài nghe). */
/** Đổi sang loại challenge dùng được với screen reader. */
/**
 * Đổi sang loại câu hỏi khác — nút "Bỏ qua" (§10.5).
 *
 * Khác `start(true)` ở chỗ KHÔNG tạo phiên mới: người dùng gặp loại họ không làm
 * được thì đổi loại, chứ không phải bắt đầu lại từ đầu.
 */
async function skipType(reason) {
  if (!state.sid) return;
  const errEl = document.getElementById('qc-err');
  return runAction(async (signal) => {
    const res = await api('/v1/skip', { sid: state.sid, reason }, signal);
    if (res.error) throw new Error(res.error);
    loadRenderer(res.type);
    state.pow = res.pow;
    state.challengePow = await solvePow(res.pow);
    await renderChallenge(res);
  }, {
    onError: (err) => {
      if (isSessionLost(err)) { recoverSession(); return; }
      // announce() cho screen reader; errEl cho người dùng sáng mắt — trước đây chỉ
      // có announce(), nút "Bỏ qua" trông như không phản ứng gì khi lỗi (§2.3).
      announce(t('st.skipFail'));
      if (errEl) errEl.textContent = errorMessage(err);
    },
  });
}

async function switchToAccessible() {
  const errEl = document.getElementById('qc-err');
  return runAction(async (signal) => {
    announce(t('st.toAudio'));
    const next = await api('/v1/accessible', { sid: state.sid }, signal);
    if (next.error) throw new Error(next.error);
    loadRenderer(next.type);
    state.pow = next.pow;
    state.challengePow = await solvePow(next.pow);
    await renderChallenge(next);
  }, {
    onError: (err) => {
      if (isSessionLost(err)) { recoverSession(); return; }
      announce(t('st.audioFail'));
      if (errEl) errEl.textContent = errorMessage(err);
    },
  });
}

/**
 * @param {*} override Đáp án do renderer riêng cung cấp (số của bài nghe, mảng thứ
 *                     tự của bài kéo sắp xếp).
 * @param {object} extra Số liệu thao tác riêng của renderer, ví dụ số lần đổi chỗ.
 */
async function submit(override, extra = {}) {
  if (!state.challenge) return;
  // Mọi renderer đều dùng cùng một id lỗi kể từ §10.5. Trước đây có hai id vì lưới
  // ảnh C1 sống trong `frame.js` với bộ CSS riêng của nó.
  const errEl = document.getElementById('qc-err');
  return runAction(async (signal) => {
    const res = await api('/v1/solve', {
      sid: state.sid,
      cid: state.challenge.cid,
      // Mảng giữ nguyên (bài kéo sắp xếp gửi cả thứ tự); giá trị đơn thì bọc lại.
      // Mảng giữ nguyên (lưới ảnh và bài sắp xếp gửi cả danh sách); giá trị đơn thì
      // bọc lại cho đồng nhất.
      answer: Array.isArray(override) ? override : [override],
      powNonce: state.challengePow,
      telemetry: {
        solveMs: Math.round(performance.now() - state.startedAt),
        mouseEvents: behavior.mouseEvents,
        keyboardNav: behavior.keyboardNav,
        ...extra,
      },
    }, signal);

    if (res.error) throw new Error(res.error);
    if (res.ok) { removeEventListener('keydown', escOnce); root.removeEventListener('click', closeOnOutsideClick); finish(res.token); return; }

    if (res.next) {
      loadRenderer(res.next.type);
      state.pow = res.next.pow;
      state.challengePow = await solvePow(res.next.pow);
      if (errEl) errEl.textContent = t(res.reason === 'expired' ? 'st.expired' : 'st.wrong');
      // PHẢI await — khác `start()`, đây KHÔNG phải statement cuối được `return`, mà
      // nằm giữa thân hàm; không await thì lỗi tải renderer của câu TIẾP THEO hoàn
      // toàn tách khỏi promise của `submit()`, không cách nào bắt được. Xem
      // docs/plans/03_frame_loading_ux.md §2.1/§4.2.
      await renderChallenge(res.next);
    }
  }, {
    onError: (err) => {
      if (isSessionLost(err)) { recoverSession(); return; }
      // Lỗi giữa chừng một challenge ĐANG hiển thị: không renderError() (sẽ xoá
      // luôn câu hỏi + tiến độ đã làm) — chỉ báo lỗi tại chỗ, giữ nguyên state.
      if (errEl) errEl.textContent = errorMessage(err);
    },
  });
}

function finish(token) {
  state.token = token;
  renderSuccess();
  toParent('verified', { token });
  // plan/06 §4 — token TTL 120s; báo cho trang cha khi hết hạn.
  setTimeout(() => {
    if (state.token === token) { toParent('expired'); reset(); }
  }, 115_000);
}

renderIdle();
toParent('ready');
