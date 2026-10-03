/**
 * Renderer challenge chọn đúng N hình — PHASE-1 §10.4.
 *
 * Cùng cơ chế toạ độ như C8 (`challenge-pointclick.js`) nhưng CHỌN NHIỀU ĐIỂM: mỗi
 * cú bấm đặt một dấu, bấm lại vào dấu cũ thì bỏ chọn.
 *
 * Bộ đếm "đã chọn 1/2" hiển thị thường trực và cũng được `aria-live` đọc lên. Đề bài
 * đã nói số lượng, nên giấu số đã chọn chỉ làm người dùng phải tự đếm dấu trên ảnh —
 * không làm bot khó thêm chút nào.
 */
import { toolbarHtml, wireToolbar } from './toolbar.js';
import { t, pick } from './i18n.js';

const STEP = 0.04;
const STEP_FINE = 0.01;

/** Khoảng cách coi là "bấm lại vào dấu cũ", theo tỉ lệ cạnh ảnh. */
const NEAR = 0.06;

export function renderCountshapes(root, ch, hooks) {
  const img = ch.assets[0];
  const need = ch.spec.pick;

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
        <p class="qc-hint" id="qc-count" style="text-align:center;margin:0">${t('pc.selected', 0, need)}</p>
      </div>

      <div class="qc-error" id="qc-err" role="alert"></div>

      ${toolbarHtml({ step: ch.step, steps: ch.steps, audio: ch.accessibleAvailable })}
    </div>
   </div>`;

  const $ = (id) => root.querySelector(`#${id}`);
  const stage = $('qc-stage');
  const cursor = $('qc-cursor');
  const picks = [];
  let caret = null; // vị trí con trỏ bàn phím

  const redraw = () => {
    [...stage.querySelectorAll('.qc-pc__mark')].forEach((el) => el.remove());
    picks.forEach((p, i) => {
      const el = document.createElement('span');
      el.className = 'qc-pc__mark';
      el.style.left = `${p.x * 100}%`;
      el.style.top = `${p.y * 100}%`;
      el.textContent = String(i + 1);
      el.setAttribute('aria-hidden', 'true');
      stage.appendChild(el);
    });
    $('qc-count').textContent = t('pc.selected', picks.length, need);
    hooks.announce?.(t('pc.selected', picks.length, need));
  };

  /** Bấm vào chỗ đã có dấu ⇒ bỏ dấu đó. Ngược lại thêm dấu mới. */
  const toggle = (x, y) => {
    const at = picks.findIndex((p) => Math.hypot(p.x - x, p.y - y) < NEAR);
    if (at >= 0) picks.splice(at, 1);
    else if (picks.length < need) picks.push({ x, y });
    else {
      // Đã đủ số: thay dấu cũ nhất thay vì im lặng bỏ qua cú bấm. Im lặng là chỗ
      // người dùng tưởng giao diện hỏng.
      picks.shift();
      picks.push({ x, y });
    }
    redraw();
  };

  const place = (x, y) => {
    caret = { x: Math.min(1, Math.max(0, x)), y: Math.min(1, Math.max(0, y)) };
    cursor.hidden = false;
    cursor.style.left = `${caret.x * 100}%`;
    cursor.style.top = `${caret.y * 100}%`;
    hooks.announce?.(t('pc.cursor', Math.round(caret.x * 100), Math.round(caret.y * 100)));
  };

  stage.addEventListener('click', (e) => {
    if (e.detail === 0) return; // click do bàn phím sinh ra: bỏ qua, Enter xử lý riêng
    const r = $('qc-pc-img').getBoundingClientRect();
    if (!r.width || !r.height) return;
    toggle((e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height);
    hooks.onPick?.(stage, e);
  });

  stage.addEventListener('keydown', (e) => {
    const d = e.shiftKey ? STEP_FINE : STEP;
    const map = { ArrowLeft: [-d, 0], ArrowRight: [d, 0], ArrowUp: [0, -d], ArrowDown: [0, d] };
    if (map[e.key]) {
      e.preventDefault();
      const [dx, dy] = map[e.key];
      const from = caret ?? { x: 0.5, y: 0.5 };
      place(from.x + dx, from.y + dy);
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      // Enter khi con trỏ đang ở đâu đó ⇒ chọn/bỏ chọn tại đó. Chỉ khi đã đủ số thì
      // Enter mới có nghĩa "gửi" — nếu không, người dùng bàn phím không có cách nào
      // đặt dấu cuối cùng.
      if (caret && picks.length < need) toggle(caret.x, caret.y);
      else submit();
    }
  });

  const submit = () => {
    if (picks.length !== need) {
      $('qc-err').textContent = t('pc.needExactly', need, picks.length);
      stage.focus({ preventScroll: true });
      return;
    }
    hooks.onSubmit(picks);
  };

  wireToolbar(root, hooks, { onSubmit: submit });

  stage.focus({ preventScroll: true });
  hooks.announce?.(pick(ch.spec.question));

  return { destroy() {} };
}
