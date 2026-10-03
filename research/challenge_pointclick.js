/**
 * Renderer challenge click toạ độ — PHASE-1 §10.3.
 *
 * Khác mọi renderer trước: không có danh sách phương án. Người dùng bấm thẳng lên
 * ảnh, và thứ gửi đi là một cặp `{x, y}` chuẩn hoá 0–1 — không phải chỉ số ô.
 *
 * ── VÌ SAO CHUẨN HOÁ 0–1 ────────────────────────────────────────────────────
 * Ảnh hiển thị co giãn theo bề rộng khung, mà khung thì đổi theo màn hình người
 * dùng. Gửi pixel màn hình lên thì server phải đoán tỉ lệ hiển thị — đoán sai một
 * chút là chấm sai. Chuẩn hoá theo `getBoundingClientRect()` của chính thẻ ảnh làm
 * chuyện đó biến mất.
 *
 * ── BÀN PHÍM ────────────────────────────────────────────────────────────────
 * Con trỏ chữ thập di bằng phím mũi tên (Shift = bước nhỏ), Enter để chọn. Cố tình
 * KHÔNG có danh sách vùng focus cho từng nhân vật: đó sẽ là phép phân vùng miễn phí
 * cho bot — lý do đầy đủ ở đầu `src/challenge/pointclick.js`.
 *
 * Người dùng screen reader không dùng được loại này. Nút âm thanh (phím A) luôn có
 * mặt trên thanh công cụ và đó là đường ra của họ.
 */
import { toolbarHtml, wireToolbar } from './toolbar.js';
import { t, pick } from './i18n.js';

const STEP = 0.04;      // bước di chuyển của con trỏ, theo tỉ lệ ảnh
const STEP_FINE = 0.01; // giữ Shift

export function renderPointclick(root, ch, hooks) {
  const img = ch.assets[0];

  root.innerHTML = `
   <div class="qc-modal">
    <div class="qc-card" role="group" aria-labelledby="qc-q" aria-describedby="qc-hint">
      <h1 class="qc-prompt" id="qc-q">${pick(ch.spec.question)}</h1>
      <p class="qc-hint" id="qc-hint">${pick(ch.spec.hint)}</p>

      <div class="qc-body">
        <div class="qc-pc__stage" id="qc-stage" tabindex="0" role="application"
             aria-label="${pick(ch.spec.question)}. ${pick(ch.spec.hint)}">
          <img src="${img.url}" alt="" draggable="false" id="qc-pc-img">
          <span class="qc-pc__cursor" id="qc-cursor" hidden aria-hidden="true"></span>
        </div>
      </div>

      <div class="qc-error" id="qc-err" role="alert"></div>

      ${toolbarHtml({ step: ch.step, steps: ch.steps, audio: ch.accessibleAvailable })}
    </div>
   </div>`;

  const $ = (id) => root.querySelector(`#${id}`);
  const stage = $('qc-stage');
  const cursor = $('qc-cursor');
  let point = null; // {x, y} chuẩn hoá

  const place = (x, y, { announce = true } = {}) => {
    point = { x: Math.min(1, Math.max(0, x)), y: Math.min(1, Math.max(0, y)) };
    cursor.hidden = false;
    cursor.style.left = `${point.x * 100}%`;
    cursor.style.top = `${point.y * 100}%`;
    if (announce) {
      hooks.announce?.(t('pc.cursor', Math.round(point.x * 100), Math.round(point.y * 100)));
    }
  };

  stage.addEventListener('click', (e) => {
    const r = $('qc-pc-img').getBoundingClientRect();
    if (!r.width || !r.height) return;
    // Click do bàn phím sinh ra có detail = 0 và toạ độ 0,0 — bỏ qua, nếu không con
    // trỏ nhảy về góc trên bên trái ngay khi người dùng bấm Enter.
    if (e.detail === 0) return;
    place((e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height, { announce: false });
    hooks.onPick?.(stage, e);
  });

  stage.addEventListener('keydown', (e) => {
    const d = e.shiftKey ? STEP_FINE : STEP;
    const map = { ArrowLeft: [-d, 0], ArrowRight: [d, 0], ArrowUp: [0, -d], ArrowDown: [0, d] };
    if (map[e.key]) {
      e.preventDefault();
      const [dx, dy] = map[e.key];
      const from = point ?? { x: 0.5, y: 0.5 };
      place(from.x + dx, from.y + dy);
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      submit();
    }
  });

  const submit = () => {
    if (!point) {
      $('qc-err').textContent = t('pc.needPoint');
      stage.focus({ preventScroll: true });
      return;
    }
    hooks.onSubmit(point);
  };

  wireToolbar(root, hooks, { onSubmit: submit });

  stage.focus({ preventScroll: true });
  hooks.announce?.(pick(ch.spec.question));

  return { destroy() {} };
}
