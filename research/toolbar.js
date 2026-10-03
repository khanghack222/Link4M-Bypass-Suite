/**
 * Thanh công cụ dùng chung của overlay — PHASE-1 §10.5.
 *
 * Trước đây năm renderer tự viết năm bản HTML gần giống nhau. Thêm một nút — nút
 * "Bỏ qua" của §10.5 chẳng hạn — là sửa năm chỗ, và chỉ cần quên một chỗ là loại
 * challenge đó thiếu nút mà không test nào biết.
 *
 * Bố cục theo quy ước chung của captcha ảnh (§9.0: lấy quy ước, không lấy biểu đạt):
 *
 *     [⋮] [↻] [🔊] [Bỏ qua]        ● ● ●        [VI]  [ Xác nhận ]
 *
 * Chấm tiến trình ở giữa, hành động chính bên phải, các nút phụ bên trái.
 */
import { icon } from './icons.js';
import { t, getLang, nextLang, LANGS } from './i18n.js';

/**
 * @param {object}  o
 * @param {number}  o.step      bước hiện tại (1-based)
 * @param {number?} o.steps     tổng số bước; null khi cố tình không lộ (tarpit)
 * @param {boolean} o.audio     có luồng âm thanh để chuyển sang không
 * @param {boolean} o.skip      có cho đổi loại câu hỏi không
 * @param {boolean} o.submit    có nút xác nhận không (loại tự gửi thì tắt)
 * @param {boolean} o.back      có nút quay lại câu hỏi hình ảnh không (chỉ luồng âm thanh)
 */
export function toolbarHtml({ step = 1, steps = null, audio = true, skip = true, submit = true, back = false } = {}) {
  // Không hiện gì khi server giấu tổng số bước: `steps === null` là dấu hiệu tarpit
  // (plan/05 §5) và vẽ chấm ra là nói cho bot biết nó đang bị giữ chân.
  const finiteSteps = Number.isFinite(steps) && steps >= 1;
  const dots = finiteSteps
    ? `<span class="qc-dots" aria-hidden="true">${
      Array.from({ length: steps }, (_, i) => `<span class="qc-dot${i < step ? ' qc-dot--on' : ''}"></span>`).join('')
    }</span>`
    : '';
  // Người dùng screen reader vẫn cần biết tiến độ kể cả khi không vẽ chấm.
  const progress = steps ? `<span class="qc-sr">${t('tb.progress', step, steps)}</span>` : '';
  // Không có chấm (tarpit ẩn steps) thì hàng --main chỉ còn spacer + nút Xác nhận,
  // trống hẳn bên trái. Placeholder THUẦN TRANG TRÍ, loại trừ lẫn nhau với dots —
  // không bao giờ render cùng lúc nên không giẫm lên ý nghĩa của chấm tiến trình.
  const brandPlaceholder = finiteSteps ? '' : `<span class="qc-toolbar__brand" aria-hidden="true">${t('cb.brand')}</span>`;

  const btn = (id, name, label) =>
    `<button class="qc-btn qc-btn--icon" id="${id}" type="button" title="${label}" aria-label="${label}">${icon(name)}</button>`;

  /*
   * HAI HÀNG, chia theo vai trò — không phải một hàng rồi để nó tự tràn.
   *
   *   [⋮] [↻] [🔊] [Bỏ qua]                    [VI]
   *   ● ●                                 [ Xác nhận ]
   *
   * Sáu nút không vừa một hàng trong thẻ rộng 400px: đo ra ~418px nội dung trên
   * 368px chỗ trống. `flex-wrap` khi đó đẩy nút Xác nhận xuống dòng dưới và dán nó
   * vào mép trái — hành động chính của màn hình lại nằm ở chỗ khó đoán nhất. Chia
   * hàng tường minh thì vị trí các nút cố định ở mọi bề rộng.
   */
  return `
    <div class="qc-toolbar">
      <div class="qc-toolbar__row">
        <div class="qc-menu" id="qc-menu-wrap">
          ${btn('qc-menu', 'more', t('tb.menu'))}
          <div class="qc-menu__pop" id="qc-menu-pop" role="menu" hidden>
            <button class="qc-menu__item" id="qc-mi-help" role="menuitem" type="button">${t('menu.help')}</button>
            <button class="qc-menu__item" id="qc-mi-hard" role="menuitem" type="button">${t('menu.hard')}</button>
            <button class="qc-menu__item" id="qc-mi-privacy" role="menuitem" type="button">${t('menu.privacy')}</button>
          </div>
        </div>
        ${btn('qc-refresh', 'refresh', t('tb.refresh'))}
        ${audio ? btn('qc-a11y', 'audio', t('tb.audio')) : ''}
        ${back ? btn('qc-back', 'close', t('tb.back')) : ''}
        ${skip ? `<button class="qc-btn" id="qc-skip" type="button" title="${t('tb.skipTitle')}">${t('tb.skip')}</button>` : ''}
        <span class="qc-spacer"></span>
        <button class="qc-btn qc-btn--lang" id="qc-lang" type="button"
                title="${t('tb.lang')}" aria-label="${t('tb.lang')}: ${getLang().toUpperCase()}">${getLang().toUpperCase()}</button>
      </div>
      <div class="qc-toolbar__row qc-toolbar__row--main">
        ${dots}${progress}${brandPlaceholder}
        <span class="qc-spacer"></span>
        ${submit ? `<button class="qc-btn qc-btn--primary" id="qc-submit" type="button">${t('tb.submit')}</button>` : ''}
      </div>
    </div>`;
}

/**
 * Nối sự kiện cho thanh công cụ.
 *
 * `hooks` là bộ hook chung mà `frame.js` truyền cho mọi renderer, cộng thêm
 * `onSubmit` của riêng renderer.
 */
export function wireToolbar(root, hooks, { onSubmit } = {}) {
  const $ = (id) => root.querySelector(`#${id}`);

  $('qc-refresh')?.addEventListener('click', () => hooks.onRefresh());
  $('qc-a11y')?.addEventListener('click', () => hooks.onAccessible());
  $('qc-back')?.addEventListener('click', () => hooks.onBack?.());
  $('qc-skip')?.addEventListener('click', () => hooks.onSkip?.());
  $('qc-submit')?.addEventListener('click', () => onSubmit?.());

  // Đổi ngôn ngữ: chỉ có hai thứ tiếng nên một nút bấm-là-đổi rẻ hơn và nhanh hơn
  // một danh sách thả xuống. Thêm ngôn ngữ thứ ba thì đổi chỗ này, không phải đổi
  // renderer nào.
  $('qc-lang')?.addEventListener('click', () => hooks.onLang?.(nextLang()));

  /* ─────────── Menu phụ ─────────── */

  const pop = $('qc-menu-pop');
  const menuBtn = $('qc-menu');

  const closeMenu = () => {
    if (!pop || pop.hidden) return;
    pop.hidden = true;
    menuBtn?.setAttribute('aria-expanded', 'false');
  };
  const openMenu = () => {
    if (!pop) return;
    pop.hidden = false;
    menuBtn?.setAttribute('aria-expanded', 'true');
    pop.querySelector('.qc-menu__item')?.focus();
  };

  menuBtn?.setAttribute('aria-expanded', 'false');
  menuBtn?.addEventListener('click', (e) => {
    e.stopPropagation();
    if (pop?.hidden) openMenu(); else closeMenu();
  });

  // Bấm ra ngoài hoặc Esc thì đóng. Esc ở đây phải CHẶN không cho nổi lên trên, nếu
  // không nó đóng luôn cả overlay — người dùng mở nhầm menu rồi bấm Esc sẽ mất cả
  // câu hỏi đang giải.
  root.addEventListener('click', closeMenu);
  pop?.addEventListener('click', (e) => e.stopPropagation());
  pop?.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { e.stopPropagation(); closeMenu(); menuBtn?.focus(); }
  });

  $('qc-mi-help')?.addEventListener('click', () => { closeMenu(); hooks.announce?.(t('menu.helpText'), { sticky: true }); });
  $('qc-mi-privacy')?.addEventListener('click', () => { closeMenu(); hooks.announce?.(t('menu.privacyText'), { sticky: true }); });
  // "Ảnh khó nhìn" đổi sang LOẠI khác chứ không chỉ đổi câu cùng loại: người không
  // đọc nổi ảnh này thì thường cũng không đọc nổi ảnh sau của cùng loại đó. Lý do
  // được gửi kèm và đếm lại — đó là số duy nhất cho biết loại nào đang làm khó
  // người thật, thứ mà gate "người ≥ 95%" ở §10.3/§10.4 cần.
  $('qc-mi-hard')?.addEventListener('click', () => { closeMenu(); hooks.onSkip?.('hard-to-read'); });

  return { closeMenu };
}

/**
 * Bật/tắt trạng thái "đang xử lý" cho thanh công cụ — docs/plans/03_frame_loading_ux.md
 * §2.4/§4.4.
 *
 * `state.busy` ở `frame.js` đã chặn xử lý-hai-lần ở tầng logic, nhưng về mặt hình
 * ảnh các nút vẫn trông "sống" — người dùng trên mạng chậm rất dễ bấm lại nhiều lần
 * mà không có phản hồi gì. Vô hiệu hoá nút (đã có sẵn kiểu `:disabled` mờ đi ở
 * `tokens.css`) + đổi nhãn nút Xác nhận là tín hiệu tối thiểu, không cần animation
 * mới. An toàn gọi cả khi `root` chưa vẽ toolbar nào (mọi truy vấn đều optional).
 */
export function setToolbarBusy(root, on) {
  for (const id of ['qc-menu', 'qc-refresh', 'qc-a11y', 'qc-back', 'qc-skip', 'qc-lang', 'qc-submit']) {
    const el = root.querySelector(`#${id}`);
    if (el) el.disabled = on;
  }
  const submit = root.querySelector('#qc-submit');
  if (submit) submit.textContent = on ? t('tb.submitBusy') : t('tb.submit');
}

export const _internal = { LANGS };
