/**
 * Renderer challenge lưới ảnh C1 — PHASE-1 §10.5.
 *
 * ── VÌ SAO TÁCH RA KHỎI `frame.js` ──────────────────────────────────────────
 *
 * C1 là loại đầu tiên nên nó được viết thẳng vào `frame.js`, kèm luôn một bộ CSS
 * riêng (`.card`, `.tile`, `.row`, `.act`) từ trước khi có hệ token ở §9.1. Hậu quả
 * là widget mang HAI hệ giao diện song song, và chúng lệch nhau thật: theme tối của
 * hệ này không đổi theo cài đặt hệ điều hành trong khi hệ kia có, nên tiêu đề từng
 * hiện chữ đen trên nền đen (§9.1).
 *
 * Chuyển C1 sang đúng khung `qc-*` như bốn loại còn lại thì bộ CSS thứ hai không còn
 * lý do tồn tại, và C1 được thanh công cụ dùng chung: chấm tiến trình, nút Bỏ qua,
 * menu phụ, nút đổi ngôn ngữ — những thứ trước đây nó không có.
 */
import { toolbarHtml, wireToolbar } from './toolbar.js';
import { icon } from './icons.js';
import { skeleton } from './skeleton.js';
import { t, pick } from './i18n.js';

export function renderGrid(root, ch, hooks) {
  const cols = ch.spec.cols ?? 3;
  // C6 chỉ có MỘT đáp án (§9.5). Vai trò ARIA phải nói đúng điều đó: `checkbox` báo
  // cho screen reader rằng chọn nhiều được, và người dùng làm theo rồi trượt.
  const single = Boolean(ch.spec.single);
  const role = single ? 'radio' : 'checkbox';

  root.innerHTML = `
   <div class="qc-modal">
    <div class="qc-card" role="group" aria-labelledby="qc-q" aria-describedby="qc-hint">
      <h1 class="qc-prompt" id="qc-q">${pick(ch.spec.question)}</h1>
      <p class="qc-hint" id="qc-hint">${t('gr.hint')}</p>

      <div class="qc-body">
        <div class="qc-grid" id="qc-grid" role="${single ? 'radiogroup' : 'grid'}"
             aria-labelledby="qc-q" style="--qc-cols:${cols}">
          ${ch.assets.map((a, i) => `
            <button class="qc-tile qc-skel" role="${role}" aria-checked="false"
                    tabindex="${i === 0 ? 0 : -1}" data-i="${i}"
                    aria-label="${t('gr.cell', i + 1, Math.floor(i / cols) + 1, (i % cols) + 1)}">
              <img src="${a.url}" alt="" draggable="false">
              <span class="qc-tile__check" aria-hidden="true">${icon('check')}</span>
            </button>`).join('')}
        </div>
      </div>

      <div class="qc-error" id="qc-err" role="alert"></div>

      ${toolbarHtml({ step: ch.step, steps: ch.steps, audio: ch.accessibleAvailable })}
    </div>
   </div>`;

  const $ = (id) => root.querySelector(`#${id}`);
  const tiles = [...root.querySelectorAll('.qc-tile')];
  const selected = new Set();

  skeleton(root);

  const toggle = (btn) => {
    const i = Number(btn.dataset.i);
    const on = selected.has(i);
    if (single) {
      // Chọn một: ô mới thay ô cũ. Bấm lại chính nó thì bỏ chọn — người dùng phải
      // có đường lùi mà không cần đoán.
      selected.clear();
      tiles.forEach((el) => el.setAttribute('aria-checked', 'false'));
      if (!on) selected.add(i);
    } else if (on) selected.delete(i);
    else selected.add(i);

    btn.setAttribute('aria-checked', String(!on));
    hooks.announce?.(single
      ? t('gr.pickedOne', i + 1, tiles.length)
      : t('gr.selected', selected.size, tiles.length));
  };

  tiles.forEach((btn, i) => {
    btn.addEventListener('click', (e) => {
      // Chỉ click chuột thật mới ghi độ lệch tâm: click do bàn phím sinh ra có
      // detail = 0, ghi vào thành "bấm trúng tâm tuyệt đối" và rule SR042 phạt oan.
      if (e.detail > 0) hooks.onPick?.(btn, e);
      toggle(btn);
    });

    // plan/08 §10.2 — roving tabindex + phím mũi tên trong lưới.
    btn.addEventListener('keydown', (e) => {
      const map = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: cols, ArrowUp: -cols };
      if (map[e.key] !== undefined) {
        e.preventDefault();
        hooks.onKeyboard?.();
        const n = (i + map[e.key] + tiles.length) % tiles.length;
        tiles.forEach((el) => { el.tabIndex = -1; });
        tiles[n].tabIndex = 0;
        tiles[n].focus();
        return;
      }
      if (e.key === ' ') { e.preventDefault(); hooks.onKeyboard?.(); toggle(btn); }
    });
  });

  wireToolbar(root, hooks, { onSubmit: () => hooks.onSubmit([...selected]) });

  tiles[0]?.focus({ preventScroll: true });
  hooks.announce?.(pick(ch.spec.question));

  return { destroy() {}, errorEl: () => $('qc-err') };
}
