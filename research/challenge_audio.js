/**
 * Renderer challenge âm thanh — PHASE-1 §9.2.
 *
 * Toàn bộ màn hình này thao tác được chỉ bằng bàn phím và đọc được bằng screen
 * reader. Đó không phải tính năng phụ mà là toàn bộ lý do nó tồn tại: nếu người
 * khiếm thị không dùng được thì challenge này vô nghĩa.
 *
 * Khác các loại khác: KHÔNG có đếm ngược và KHÔNG phạt vì chậm. Nghe lại ba lần rồi
 * gõ đáp án thì đương nhiên lâu hơn nhìn ảnh.
 */
import { toolbarHtml, wireToolbar } from './toolbar.js';
import { t, pick } from './i18n.js';

const MAX_REPLAYS = 3;

/**
 * @param {object} ch    dữ liệu challenge từ server
 * @param {object} hooks {onSubmit(value), onRefresh(), onBack(), announce(msg)}
 * @returns {{destroy:Function}}
 */
export function renderAudio(root, ch, hooks) {
  const [minA, maxA] = ch.spec.answerRange ?? [1, 12];
  let played = 0;

  root.innerHTML = `
   <div class="qc-modal">
    <div class="qc-card" role="group" aria-labelledby="qc-q" aria-describedby="qc-hint">
      <h1 class="qc-prompt" id="qc-q">${pick(ch.spec.question)}</h1>
      <p class="qc-hint" id="qc-hint">${pick(ch.spec.hint)}</p>

      <div class="qc-body qc-audio">
        <button class="qc-btn qc-btn--primary qc-audio__play" id="qc-play" type="button">
          ${icon('play')} <span id="qc-play-label">${t('au.play')}</span>
        </button>

        <p class="qc-hint qc-audio__count" id="qc-plays" aria-live="polite">
          Còn ${MAX_REPLAYS} lần nghe
        </p>

        <label class="qc-audio__label" for="qc-answer">
          Số tiếng bíp cao bạn nghe được
        </label>
        <input class="qc-audio__input" id="qc-answer" type="number" inputmode="numeric"
               min="${minA}" max="${maxA}" step="1" autocomplete="off"
               aria-describedby="qc-hint" placeholder="—">

        <div class="qc-audio__speed" role="group" aria-label="${t('au.speed')}">
          <span class="qc-hint">${t('au.speed')}</span>
          <button class="qc-btn qc-btn--icon" data-rate="0.75" type="button" aria-pressed="false">0,75×</button>
          <button class="qc-btn qc-btn--icon" data-rate="1" type="button" aria-pressed="true">1×</button>
          <button class="qc-btn qc-btn--icon" data-rate="1.25" type="button" aria-pressed="false">1,25×</button>
        </div>

        <a class="qc-audio__dl qc-btn" id="qc-dl" download="qcaptcha-audio.wav" href="${ch.audioUrl}">
          ${icon('download')} ${t('au.download')}
        </a>
      </div>

      <div class="qc-error" id="qc-err" role="alert"></div>

      ${toolbarHtml({ step: ch.step, steps: ch.steps, audio: false, skip: false, back: true })}
    </div>
   </div>`;

  const $ = (id) => root.querySelector(`#${id}`);
  const audio = new Audio(ch.audioUrl);
  audio.preload = 'auto';

  const play = () => {
    if (played >= MAX_REPLAYS) return;
    played++;
    audio.currentTime = 0;
    audio.play().catch(() => {
      // Trình duyệt chặn autoplay khi chưa có tương tác. Nút này luôn do người dùng
      // bấm nên hiếm khi xảy ra, nhưng nếu có thì phải nói rõ chứ không im lặng.
      $('qc-err').textContent = t('au.blocked');
    });
    const left = MAX_REPLAYS - played;
    $('qc-plays').textContent = left > 0 ? t('au.left', left) : t('au.none');
    if (left === 0) $('qc-play').disabled = true;
    hooks.announce?.(t('au.playingLeft', left));
  };

  audio.addEventListener('playing', () => { $('qc-play-label').textContent = t('au.playing'); });
  audio.addEventListener('ended', () => {
    $('qc-play-label').textContent = t('au.replay');
    hooks.announce?.(t('au.ended'));
    $('qc-answer').focus();
  });

  $('qc-play').addEventListener('click', play);

  root.querySelectorAll('[data-rate]').forEach((b) => {
    b.addEventListener('click', () => {
      audio.playbackRate = Number(b.dataset.rate);
      root.querySelectorAll('[data-rate]').forEach((o) => o.setAttribute('aria-pressed', String(o === b)));
      hooks.announce?.(t('au.rate', b.textContent.trim()));
    });
  });

  const submit = () => {
    const v = $('qc-answer').value.trim();
    if (v === '') {
      $('qc-err').textContent = t('au.needAnswer');
      $('qc-answer').focus();
      return;
    }
    hooks.onSubmit(Number(v));
  };

  wireToolbar(root, hooks, { onSubmit: submit });
  $('qc-answer').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); submit(); }
  });

  // Tiêu điểm vào nút Phát ngay: người dùng screen reader nghe được ngay việc cần
  // làm đầu tiên mà không phải Tab đi tìm.
  $('qc-play').focus({ preventScroll: true });
  hooks.announce?.(`${pick(ch.spec.question)}. ${pick(ch.spec.hint)}`);

  return {
    destroy() {
      audio.pause();
      audio.src = '';
    },
  };
}
