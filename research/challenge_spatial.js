/**
 * Renderer challenge suy luận không gian — PHASE-1 §9.3.
 *
 * Bố cục "tham chiếu + phương án": vật thể 3D ở trên, các hình nhìn từ trên xuống ở
 * dưới. Chọn một, không kéo thả — xem lý do ở đầu `src/challenge/spatial.js`.
 *
 * Toàn bộ thao tác được bằng bàn phím: mũi tên di chuyển, phím cách chọn, Enter gửi.
 */
import { toolbarHtml, wireToolbar } from './toolbar.js';
import { icon } from './icons.js';
import { t, pick } from './i18n.js';

/**
 * @param {object} ch    dữ liệu challenge từ server
 * @param {object} hooks {onSubmit(index), onRefresh(), onAccessible(), announce(msg), onPick(el, ev)}
 */
export function renderSpatial(root, ch, hooks) {
  const [ref, ...options] = ch.assets;

  root.innerHTML = `
   <div class="qc-modal">
    <div class="qc-card" role="group" aria-labelledby="qc-q" aria-describedby="qc-hint">
      <h1 class="qc-prompt" id="qc-q">${pick(ch.spec.question)}</h1>
      <p class="qc-hint" id="qc-hint">${pick(ch.spec.hint)}</p>

      <div class="qc-body">
        <div class="qc-sp__ref">
          <img src="${ref.url}" alt="${t('sp.refAlt')}" draggable="false">
        </div>

        <p class="qc-sp__divider" aria-hidden="true">${t('sp.topDown')}</p>

        <div class="qc-sp__options" role="radiogroup" aria-labelledby="qc-q" id="qc-options">
          ${options.map((o, i) => `
            <button class="qc-tile qc-sp__opt" role="radio" aria-checked="false"
                    tabindex="${i === 0 ? 0 : -1}" data-i="${i}"
                    aria-label="${t('sp.optAlt', i + 1, options.length)}">
              <img src="${o.url}" alt="" draggable="false">
              <span class="qc-tile__check" aria-hidden="true">${icon('check')}</span>
            </button>`).join('')}
        </div>
      </div>

      <div class="qc-error" id="qc-err" role="alert"></div>

      ${toolbarHtml({ step: ch.step, steps: ch.steps, audio: ch.accessibleAvailable })}
    </div>
   </div>`;

  const $ = (id) => root.querySelector(`#${id}`);
  const tiles = [...root.querySelectorAll('.qc-sp__opt')];
  let picked = -1;

  const select = (i, { focus = true } = {}) => {
    picked = i;
    tiles.forEach((el, k) => {
      el.setAttribute('aria-checked', String(k === i));
      el.tabIndex = k === i ? 0 : -1;
    });
    if (focus) tiles[i].focus({ preventScroll: true });
    hooks.announce?.(t('sp.picked', i + 1, tiles.length));
  };

  tiles.forEach((tile, i) => {
    tile.addEventListener('click', (e) => {
      // Chỉ click chuột thật mới ghi độ lệch tâm — click do bàn phím sinh ra có
      // detail = 0 và toạ độ 0,0, ghi vào sẽ thành "bấm trúng tâm tuyệt đối" và
      // rule SR042 phạt oan người dùng bàn phím.
      if (e.detail > 0) hooks.onPick?.(tile, e);
      select(i, { focus: false });
    });

    tile.addEventListener('keydown', (e) => {
      const cols = Math.min(tiles.length, 4);
      const map = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: cols, ArrowUp: -cols };
      if (map[e.key] !== undefined) {
        e.preventDefault();
        const n = (i + map[e.key] + tiles.length) % tiles.length;
        tiles[n].focus({ preventScroll: true });
        tiles.forEach((o, k) => { o.tabIndex = k === n ? 0 : -1; });
        return;
      }
      if (e.key === ' ') { e.preventDefault(); select(i); }
    });
  });

  const submit = () => {
    if (picked < 0) {
      $('qc-err').textContent = t('sp.pickOne');
      tiles[0].focus({ preventScroll: true });
      return;
    }
    hooks.onSubmit(picked);
  };

  wireToolbar(root, hooks, { onSubmit: submit });

  tiles[0]?.focus({ preventScroll: true });
  hooks.announce?.(t('sp.count', pick(ch.spec.question), tiles.length));

  return { destroy() {} };
}
