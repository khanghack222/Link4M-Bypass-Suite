/**
 * Renderer challenge kéo sắp xếp — PHASE-1 §9.4.
 *
 * Dùng Pointer Events chứ không HTML5 drag-and-drop, vì ba lý do:
 *   1. HTML5 drag không chạy trên cảm ứng ở nhiều trình duyệt.
 *   2. Nó không cho toạ độ liên tục — mà quỹ đạo liên tục chính là thứ loại
 *      challenge này sinh ra để thu thập.
 *   3. Ảnh kéo mặc định của trình duyệt không tuỳ biến được, trông lệch hẳn.
 *
 * Đường bàn phím là ĐƯỜNG NGANG HÀNG, không phải phương án dự phòng: phím cách để
 * nhấc, mũi tên để dịch, phím cách để thả, Escape để huỷ.
 *
 * ── KIẾN TRÚC KÉO — docs/plans/02_order_drag_ux.md ──────────────────────────
 * Mảnh đang kéo được tách hẳn khỏi luồng flex (`position: fixed`, điều khiển bằng
 * `transform` theo con trỏ) và một PLACEHOLDER (`.qc-ord__slot`) đứng thế chỗ nó
 * trong danh sách — placeholder mới là thứ tham gia layout và bị đổi chỗ khi kéo
 * qua hàng-xóm. Nhờ vậy: (1) mảnh đang kéo không còn "kéo lê" khung flex của chính
 * nó — nguồn gây giật cũ, (2) placeholder chính là "mark" cho biết thả vào đâu,
 * (3) các mảnh bị đẩy dịch chỗ animate mượt bằng kỹ thuật FLIP thay vì nhảy tức thì.
 */
import { toolbarHtml, wireToolbar } from './toolbar.js';
import { t, pick } from './i18n.js';

/**
 * Có nên đổi chỗ mảnh đang kéo với mảnh hàng-xóm không?
 *
 * ── VÌ SAO CẦN VÙNG CHẾT ────────────────────────────────────────────────────
 *
 * Bản đầu đổi chỗ ngay khi con trỏ vượt qua TÂM mảnh bên cạnh. Sau khi đổi, mảnh
 * đang kéo chiếm đúng ô vừa rồi, nên con trỏ lập tức nằm ngay bên kia tâm của mảnh
 * vừa bị đẩy sang — và điều kiện đổi chỗ lại đúng, theo chiều ngược lại. Hai mảnh
 * nháy qua nháy lại liên tục chừng nào con trỏ còn đứng gần ranh giới.
 *
 * Vùng chết bắt con trỏ phải đi QUÁ tâm một quãng thì mới đổi, nên sau khi đổi xong
 * nó nằm trong vùng chết của chiều ngược lại và mọi thứ đứng yên.
 *
 * ── VÌ SAO PHẢI KIỂM TRA HÀNG (trục Y) ──────────────────────────────────────
 *
 * Danh sách xuống hàng ở độ khó 3 (5 mảnh 82px không vừa 368px nội dung một hàng —
 * xem docs/plans/02_order_drag_ux.md §2.3). So sánh chỉ theo trục X từng khiến một
 * mảnh ở HÀNG KHÁC nhưng trùng khoảng X bị coi là ứng viên đổi chỗ, gây nhảy cóc
 * không đoán trước được.
 *
 * @param {{x:number, y:number}} pointer toạ độ con trỏ
 * @param {{left:number, top:number, width:number, height:number}} neighbor hình chữ
 *   nhật (bounding rect) của mảnh hàng-xóm
 * @param {boolean} isAfter mảnh ĐANG KÉO hiện đứng TRƯỚC mảnh hàng-xóm trong danh
 *   sách (tức nếu đổi thì nó sẽ nhảy sang SAU mảnh đó)
 * @param {number} dead vùng chết, theo tỉ lệ bề rộng
 */
export function shouldSwap(pointer, neighbor, isAfter, dead = 0.25) {
  // Khác hàng thì không phải ứng viên, bất kể trục X trùng khoảng đến đâu.
  if (pointer.y < neighbor.top || pointer.y > neighbor.top + neighbor.height) return false;
  const mid = neighbor.left + neighbor.width / 2;
  const margin = neighbor.width * dead;
  return isAfter ? pointer.x > mid + margin : pointer.x < mid - margin;
}

/**
 * Chỉ số ứng viên đổi chỗ: hàng-xóm liền kề của placeholder trong danh sách hiện
 * tại (`±1`), không phải toàn bộ danh sách.
 *
 * Bản đầu duyệt TẤT CẢ mảnh khác và dừng ở khớp đầu tiên theo thứ tự DOM — khi kéo
 * nhanh (đặc biệt trên cảm ứng, sự kiện thưa hơn chuột), con trỏ có thể đã vượt qua
 * nhiều mảnh trong một sự kiện, và logic đó có thể đổi chỗ với một mảnh không liền
 * kề, gây nhảy cóc không theo trực giác kéo-tới-đâu-đổi-tới-đó. Giới hạn ứng viên ở
 * đúng hai hàng-xóm liền kề loại bỏ khả năng đó.
 */
export function swapCandidates(slotIndex, length) {
  return [slotIndex - 1, slotIndex + 1].filter((i) => i >= 0 && i < length);
}

/**
 * Nhóm chỉ số theo HÀNG dựa vào `top` đo được — cùng hàng thì cùng `top` (làm tròn
 * để tránh sai số subpixel). Trả về mảng hàng theo thứ tự trên→dưới, mỗi hàng là
 * mảng chỉ số (giữ nguyên thứ tự trái→phải).
 *
 * ── VÌ SAO CẦN HÀM NÀY ──────────────────────────────────────────────────────
 *
 * `swapCandidates` mã hoá "hàng-xóm" thuần theo KHOẢNG CÁCH CHỈ SỐ trong mảng
 * phẳng — đúng khi cả danh sách nằm một hàng, nhưng sai khi xuống nhiều hàng: một
 * mảnh lẻ ở hàng cuối (vd. mảnh 5 khi 5 mảnh không vừa một hàng — xem
 * docs/plans/02_order_drag_ux.md §2.3/§7) chỉ vào tầm ngắm SAU KHI đã đổi chỗ tuần
 * tự đủ số bước để chỉ số phẳng của placeholder áp sát nó — một chuỗi thao tác
 * không ai làm được trong một cử chỉ kéo thật, nên nó có cảm giác "bất động".
 * `groupRows` + `nearestInRow` bên dưới thay bằng một quy tắc hình học: mảnh nào
 * GẦN CON TRỎ NHẤT trong đúng hàng con trỏ đang ở, bất kể xa bao nhiêu bước theo
 * chỉ số phẳng.
 */
export function groupRows(tops) {
  const rows = [];
  tops.forEach((top, i) => {
    const rounded = Math.round(top);
    let row = rows.find((r) => r.top === rounded);
    if (!row) { row = { top: rounded, indices: [] }; rows.push(row); }
    row.indices.push(i);
  });
  return rows.sort((a, b) => a.top - b.top).map((r) => r.indices);
}

/**
 * Chỉ số (trong `rowIndices`) của mảnh GẦN toạ độ X `x` nhất — "điểm đột phá" khi
 * con trỏ băng sang hàng khác (xem `groupRows`): không cần liền kề theo chỉ số
 * phẳng, chỉ cần gần theo hình học. `rects` là bounding rect của TOÀN BỘ danh sách,
 * cùng thứ tự chỉ số với `rowIndices`.
 */
export function nearestInRow(x, rowIndices, rects) {
  let best = rowIndices[0];
  let bestDist = Infinity;
  for (const i of rowIndices) {
    const mid = rects[i].left + rects[i].width / 2;
    const dist = Math.abs(x - mid);
    if (dist < bestDist) { bestDist = dist; best = i; }
  }
  return best;
}

/**
 * Ứng viên đổi chỗ tiếp theo cho placeholder — hàm THUẦN, không đụng DOM, dễ test
 * độc lập với `renderOrder`.
 *
 * Cùng hàng với placeholder: hàng-xóm liền kề + vùng chết theo tâm, KHÔNG đổi so
 * với thiết kế ban đầu (§3.3/§3.4). Khác hàng: mảnh gần con trỏ nhất theo X trong
 * hàng đó — "điểm đột phá" §7.3, để một mảnh lẻ ở hàng cuối luôn vào tầm ngắm ngay
 * khi con trỏ băng tới, không cần đi qua chuỗi đổi chỗ trung gian nào trước.
 *
 * @param {{x:number, y:number}} pointer
 * @param {number} slotIndex chỉ số placeholder trong danh sách hiện tại
 * @param {{left:number, top:number, width:number, height:number}[]} rects bounding
 *   rect của TOÀN BỘ danh sách, cùng thứ tự chỉ số với `slotIndex`
 * @returns {{index: number, isAfter: boolean} | null}
 */
export function pickTarget(pointer, slotIndex, rects) {
  const rows = groupRows(rects.map((r) => r.top));
  const slotRow = rows.findIndex((row) => row.includes(slotIndex));
  const cur = rects[rows[slotRow][0]];
  // Vùng chết theo trục Y giữa hai hàng — cùng tinh thần vùng chết trong-hàng của
  // shouldSwap, để chuyển hàng không phập phù khi con trỏ đứng sát ranh giới (§7.5).
  const margin = cur.height * 0.25;
  const below = rows[slotRow + 1];
  const above = rows[slotRow - 1];

  if (below && pointer.y > cur.top + cur.height + margin) {
    const i = nearestInRow(pointer.x, below, rects);
    return { index: i, isAfter: pointer.x >= rects[i].left + rects[i].width / 2 };
  }
  if (above && pointer.y < cur.top - margin) {
    const i = nearestInRow(pointer.x, above, rects);
    return { index: i, isAfter: pointer.x >= rects[i].left + rects[i].width / 2 };
  }
  for (const j of swapCandidates(slotIndex, rects.length)) {
    const r = rects[j];
    const isAfter = j > slotIndex;
    const neighbor = { left: r.left, top: r.top, width: r.width, height: r.height };
    if (shouldSwap(pointer, neighbor, isAfter)) return { index: j, isAfter };
  }
  return null;
}

/**
 * Độ dịch của mảnh đang kéo, tính từ vị trí GỐC đã đo lúc bấm xuống (dùng chung cho
 * cả hai trục — client/grabD/origin cùng đơn vị, cùng trục).
 *
 * ── ĐÂY LÀ NGUYÊN NHÂN CỦA HIỆN TƯỢNG NHÁY (LỊCH SỬ) ────────────────────────
 *
 * Bản đầu lấy mốc bằng `drag.el.getBoundingClientRect().left` ngay trong lúc kéo —
 * nhưng rect đó ĐÃ bao gồm phép dịch đang áp dụng. Gọi L là vị trí layout, T là độ
 * dịch hiện tại, D là độ dịch đúng cần có:
 *
 *     T' = clientX - dx - (L + T) = D - T
 *
 * Con trỏ đứng yên thì T nhảy 0 → D → 0 → D … mỗi sự kiện pointermove một lần. Ở
 * tần số 60–120Hz thì mắt thấy đúng là mảnh rung. Lấy mốc từ vị trí GỐC (chốt lúc
 * bấm xuống) thì T' = D, đứng yên.
 *
 * Từ khi mảnh đang kéo ra khỏi luồng flex hẳn (`position: fixed` — xem đầu file),
 * vị trí gốc không còn bị đổi bởi việc mảnh khác bị đẩy dịch chỗ nữa, nên hàm này
 * giờ chỉ còn là phép trừ toạ độ ổn định — nhưng vẫn là điểm neo DUY NHẤT, không
 * đo lại `getBoundingClientRect()` giữa lúc kéo.
 */
export function dragOffset(clientX, grabDx, originLeft) {
  return clientX - grabDx - originLeft;
}

export function renderOrder(root, ch, hooks) {
  const n = ch.assets.length;

  root.innerHTML = `
   <div class="qc-modal">
    <div class="qc-card" role="group" aria-labelledby="qc-q" aria-describedby="qc-hint">
      <h1 class="qc-prompt" id="qc-q">${pick(ch.spec.question)}</h1>
      <p class="qc-hint" id="qc-hint">${pick(ch.spec.hint)}</p>

      <div class="qc-body">
        <ol class="qc-ord__list" id="qc-list" role="listbox" aria-labelledby="qc-q">
          ${ch.assets.map((a, i) => `
            <li class="qc-ord__item" role="option" aria-selected="false"
                tabindex="${i === 0 ? 0 : -1}" data-id="${i}"
                aria-label="${t('or.item', i + 1, i + 1, n)}">
              <img src="${a.url}" alt="" draggable="false">
              <span class="qc-ord__pos" aria-hidden="true">${i + 1}</span>
            </li>`).join('')}
        </ol>
      </div>

      <div class="qc-error" id="qc-err" role="alert"></div>

      ${toolbarHtml({ step: ch.step, steps: ch.steps, audio: ch.accessibleAvailable })}
    </div>
   </div>`;

  const $ = (id) => root.querySelector(`#${id}`);
  const list = $('qc-list');
  let moveCount = 0;
  let lifted = null; // phần tử đang được nhấc bằng bàn phím

  /**
   * Thứ tự logic hiện tại: mảnh không đang bị kéo, hoặc placeholder đứng thế chỗ
   * mảnh ĐANG kéo (nó đã ra khỏi luồng, không còn là ứng viên vị trí thật).
   */
  const items = () => [...list.children].filter((el) =>
    (el.classList.contains('qc-ord__item') && !el.classList.contains('qc-ord__item--dragging'))
    || el.classList.contains('qc-ord__slot'));

  /** Cập nhật số thứ tự và nhãn cho screen reader sau mỗi lần đổi chỗ. */
  const relabel = () => {
    items().forEach((el, i) => {
      const posEl = el.querySelector('.qc-ord__pos');
      if (posEl) posEl.textContent = String(i + 1);
      if (el.classList.contains('qc-ord__item')) {
        el.setAttribute('aria-label', t('or.item', Number(el.dataset.id) + 1, i + 1, n));
      }
    });
  };

  const currentOrder = () => items().map((el) => Number(el.dataset.id));

  /**
   * Đo vị trí MỌI phần tử trừ `excludeEl`, chạy `mutate` (đổi DOM), rồi animate
   * phần chênh lệch bằng transform — kỹ thuật FLIP (First-Last-Invert-Play), không
   * cần thư viện. `excludeEl` là phần tử người dùng đang trực tiếp điều khiển (đang
   * kéo, hoặc đang nhấc bằng bàn phím) — nó tự có cách di chuyển riêng, FLIP đè
   * `transform` lên nó sẽ xung đột với cách di chuyển đó.
   */
  const flip = (mutate, excludeEl) => {
    const before = new Map();
    for (const el of list.children) {
      if (el !== excludeEl) before.set(el, el.getBoundingClientRect());
    }
    mutate();
    for (const [el, from] of before) {
      const to = el.getBoundingClientRect();
      const dx = from.left - to.left;
      const dy = from.top - to.top;
      if (!dx && !dy) continue;
      el.style.transition = 'none';
      el.style.transform = `translate(${dx}px, ${dy}px)`;
      requestAnimationFrame(() => {
        el.style.transition = '';
        el.style.transform = '';
      });
    }
  };

  /* ─────────────── Kéo bằng con trỏ ─────────────── */

  let drag = null;

  const onPointerDown = (e) => {
    const el = e.target.closest('.qc-ord__item');
    if (!el || e.button > 0 || drag) return;
    e.preventDefault();
    el.setPointerCapture?.(e.pointerId);

    // Đo TRƯỚC khi đổi bất cứ gì — đây là vị trí layout gốc, điểm neo duy nhất.
    const r = el.getBoundingClientRect();

    const slot = document.createElement('li');
    slot.className = 'qc-ord__slot';
    slot.dataset.id = el.dataset.id;
    slot.setAttribute('aria-hidden', 'true');
    el.before(slot);

    drag = {
      el, slot,
      id: e.pointerId,
      dx: e.clientX - r.left,
      dy: e.clientY - r.top,
      originLeft: r.left,
      originTop: r.top,
      moved: false,
    };
    el.classList.add('qc-ord__item--dragging');
    el.style.left = `${r.left}px`;
    el.style.top = `${r.top}px`;
    hooks.announce?.(t('or.drag'));
  };

  /**
   * Dán mảnh đang kéo vào đúng dưới con trỏ. `originLeft/originTop` không bao giờ
   * đổi trong lúc kéo — mảnh đã ra khỏi luồng flex hẳn (xem đầu file), nên vị trí
   * gốc không còn có thể bị các mảnh khác đẩy lệch.
   */
  const follow = (clientX, clientY) => {
    drag.el.style.transform =
      `translate(${dragOffset(clientX, drag.dx, drag.originLeft)}px, ${dragOffset(clientY, drag.dy, drag.originTop)}px)`;
  };

  const onPointerMove = (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    drag.moved = true;

    // Quỹ đạo trong lúc kéo là lý do tồn tại của loại challenge này. Trình duyệt
    // không phát mousemove khi kéo bằng cảm ứng, nên đẩy điểm lên tường minh.
    hooks.onDragMove?.(e.clientX, e.clientY);

    follow(e.clientX, e.clientY);

    const all = items();
    const rects = all.map((el) => el.getBoundingClientRect());
    const slotIndex = all.indexOf(drag.slot);
    const target = pickTarget({ x: e.clientX, y: e.clientY }, slotIndex, rects);

    if (target) {
      const el = all[target.index];
      flip(() => (target.isAfter ? el.after(drag.slot) : el.before(drag.slot)), drag.el);
      moveCount++;
      relabel();
    }
  };

  const onPointerUp = (e) => {
    if (!drag || e.pointerId !== drag.id) return;

    drag.slot.replaceWith(drag.el);
    drag.el.classList.remove('qc-ord__item--dragging');
    // Tắt transition trong lúc trả style về bình thường, rồi buộc trình duyệt áp
    // dụng NGAY (đọc offsetWidth ép reflow) trước khi bật lại transition — nếu
    // không, transform từ toạ độ fixed cũ sẽ animate về 0 trong hệ toạ độ MỚI
    // (relative, vị trí flex khác hẳn), tạo một cú nhảy/giật ngay lúc thả.
    drag.el.style.transition = 'none';
    drag.el.style.left = '';
    drag.el.style.top = '';
    drag.el.style.transform = '';
    void drag.el.offsetWidth;
    drag.el.style.transition = '';

    if (drag.moved) hooks.announce?.(t('or.dropped', items().indexOf(drag.el) + 1, n));
    drag = null;
    relabel();
  };

  list.addEventListener('pointerdown', onPointerDown);
  list.addEventListener('pointermove', onPointerMove);
  list.addEventListener('pointerup', onPointerUp);
  list.addEventListener('pointercancel', onPointerUp);

  /* ─────────────── Bàn phím ─────────────── */

  list.addEventListener('keydown', (e) => {
    const el = e.target.closest('.qc-ord__item');
    if (!el) return;
    const all = items();
    const i = all.indexOf(el);

    if (e.key === ' ') {
      e.preventDefault();
      if (lifted === el) {
        lifted = null;
        el.setAttribute('aria-selected', 'false');
        el.classList.remove('qc-ord__item--lifted');
        hooks.announce?.(`Đã đặt vào vị trí ${i + 1} trên ${n}.`);
      } else {
        lifted = el;
        el.setAttribute('aria-selected', 'true');
        el.classList.add('qc-ord__item--lifted');
        hooks.announce?.(t('or.lift'));
      }
      return;
    }

    if (e.key === 'Escape' && lifted) {
      e.preventDefault();
      lifted.setAttribute('aria-selected', 'false');
      lifted.classList.remove('qc-ord__item--lifted');
      lifted = null;
      hooks.announce?.(t('st.cancelled'));
      return;
    }

    const dir = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
    if (!dir) return;
    e.preventDefault();

    if (lifted === el) {
      // Đang nhấc: mũi tên DI CHUYỂN phần tử. Bọc trong flip() để nhất quán hình
      // ảnh với đường con trỏ — mảnh bị đẩy dịch chỗ cũng animate mượt.
      const target = all[i + dir];
      if (!target) return;
      flip(() => (dir > 0 ? target.after(el) : target.before(el)), el);
      moveCount++;
      relabel();
      el.focus({ preventScroll: true });
      hooks.announce?.(`Chuyển tới vị trí ${items().indexOf(el) + 1} trên ${n}.`);
    } else {
      // Không nhấc: mũi tên DI CHUYỂN TIÊU ĐIỂM.
      const next = all[(i + dir + all.length) % all.length];
      all.forEach((o) => { o.tabIndex = -1; });
      next.tabIndex = 0;
      next.focus({ preventScroll: true });
    }
  });

  /* ─────────────── Gửi ─────────────── */

  wireToolbar(root, hooks, { onSubmit: () => hooks.onSubmit(currentOrder(), { moveCount }) });

  items()[0]?.focus({ preventScroll: true });
  hooks.announce?.(`${pick(ch.spec.question)}. Có ${n} hình.`);

  return {
    destroy() {
      list.removeEventListener('pointerdown', onPointerDown);
      list.removeEventListener('pointermove', onPointerMove);
      list.removeEventListener('pointerup', onPointerUp);
      list.removeEventListener('pointercancel', onPointerUp);
    },
  };
}
