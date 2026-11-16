/* Search results: AICS search + 3-tier availability (current store fixed first row → nearby stores → online),
   drug_class badges + compliance notices, 「この店舗の在庫のみ」 toggle, 「棚を探す」 → floor map. */
(function () {
  'use strict';
  const { esc, yen, km, fetchJSON, drugBadges, noticesHTML, statusPill, img, CFG } = window.SN;
  const IN = ['in_stock', 'low_stock'];
  const I = {
    shelf: '<svg viewBox="0 0 24 24"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5a2.5 2.5 0 0 1 0-5 2.5 2.5 0 0 1 0 5z"/></svg>',
    map: '<svg viewBox="0 0 24 24"><path d="m20.5 3-.16.03L15 5.1 9 3 3.36 4.9c-.21.07-.36.25-.36.48V20.5c0 .28.22.5.5.5l.16-.03L9 18.9l6 2.1 5.64-1.9c.21-.07.36-.25.36-.48V3.5c0-.28-.22-.5-.5-.5zM15 19l-6-2.11V5l6 2.11V19z"/></svg>',
    plus: '<svg viewBox="0 0 24 24"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>',
    check: '<svg viewBox="0 0 24 24"><path d="M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>',
    cart: '<svg viewBox="0 0 24 24"><path d="M7 18c-1.1 0-1.99.9-1.99 2S5.9 22 7 22s2-.9 2-2-.9-2-2-2zM1 2v2h2l3.6 7.59-1.35 2.45c-.16.28-.25.61-.25.96 0 1.1.9 2 2 2h12v-2H7.42a.25.25 0 0 1-.25-.25l.03-.12.9-1.63h7.45c.75 0 1.41-.41 1.75-1.03l3.58-6.49A1 1 0 0 0 20 4H5.21l-.94-2H1zm16 16c-1.1 0-1.99.9-1.99 2s.89 2 1.99 2 2-.9 2-2-.9-2-2-2z"/></svg>',
  };

  function shelfText(sh) {
    if (!sh) return '';
    if (sh.unassigned) return '売場を確認中です（スタッフにお尋ねください）';
    if (sh.counter || (sh.fixture_id || sh.gondola_id) === 'RX') return 'レジ（医薬品カウンター）でお渡し';
    const fid = sh.fixture_id || sh.gondola_id;
    if (sh.slot_label) return (sh.fixture_label ? fid + ' ' + sh.fixture_label + ' ・ ' : '') + sh.slot_label;
    return sh.label || fid;
  }

  function availHTML(av, p) {
    if (!av || !av.current) return '';
    const c = av.current;
    const isIn = IN.indexOf(c.status) >= 0;
    const isUnassigned = !!(c.shelf && c.shelf.unassigned);
    let shelfLine = '';
    if (c.status === 'not_carried') shelfLine = '<span class="avail__shelf is-muted">この店舗では取扱いがありません</span>';
    else if (isUnassigned) shelfLine = '<span class="avail__shelf is-warning">' + I.shelf + '売場を確認中です（スタッフにお尋ねください）</span>';
    else if (!isIn) shelfLine = '<span class="avail__shelf is-muted">在庫なし' + (c.shelf ? '（通常の売場: ' + esc(shelfText(c.shelf)) + '）' : '') + '</span>';
    else if (c.shelf) shelfLine = '<span class="avail__shelf">' + I.shelf + esc(shelfText(c.shelf)) + '</span>';
    let h = '<div class="avail">' +
      '<div class="avail__row avail__row--current' + (isIn ? '' : ' is-out') + '"><span class="avail__who"><span class="avail__store"><span class="avail__tag">この店舗</span>' +
      esc(c.short_name) + ' ' + statusPill(c.status, c.quantity) + '</span>' + shelfLine + '</span>' +
      (isIn && c.shelf && !isUnassigned ? '<button type="button" class="sn-btn sn-btn--tonal sn-btn--sm" data-find="' + esc(p.id) + '">' + I.map + '棚を探す</button>' : '<span></span>') + '</div>';
    let other = '';
    (av.nearby || []).slice(0, 2).forEach((n) => {
      other += '<div class="avail__row avail__row--other"><span class="avail__who"><span class="avail__store">' + esc(n.short_name) + ' ' + statusPill(n.status, n.quantity) + '</span>' +
        '<span class="avail__shelf is-muted">約' + esc(km(n.distance_m)) + (n.open_now ? '' : ' ・ 営業時間外') + (IN.indexOf(n.status) >= 0 && n.shelf ? ' ・ ' + esc(shelfText(n.shelf)) : '') + '</span></span><span></span></div>';
    });
    const on = av.online || {};
    other += '<div class="avail__row avail__row--other"><span class="avail__who"><span class="avail__store">オンライン ' +
      (on.available ? '<span class="sn-pill sn-pill--online">配送できます</span>' : statusPill('out_of_stock')) + '</span>' +
      '<span class="avail__shelf is-muted">' + yen(on.price) + '（税込）' + (p.drug_class === '第1類医薬品' ? ' ・ 薬剤師による確認後の発送' : '') + '</span></span>' +
      (on.available ? '<a class="sn-btn sn-btn--outline sn-btn--sm" href="' + esc(on.url || ((CFG.onlineStoreUrl || '') + '/?product=' + p.id)) + '" target="_blank" rel="noopener" data-online="' + esc(p.id) + '">オンラインで購入</a>' : '<span></span>') + '</div>';
    if (isIn) {
      h += '<button type="button" class="avail__toggle" data-more-avail="' + esc(p.id) + '" aria-expanded="false">' +
        '<span class="avail__toggle-lbl">他店舗・オンラインの在庫を見る</span>' +
        '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z"/></svg></button>' +
        '<div class="avail__other" hidden>' + other + '</div>';
    } else {
      h += '<div class="avail__other is-open">' + other + '</div>';
    }
    return h + '</div>';
  }

  function cardHTML(p) {
    const added = window.Cart && window.Cart.has(p.id);
    const sale = p.original_price > p.price;
    return '<article class="pcard" data-pid="' + esc(p.id) + '">' +
      '<div class="pcard__main">' + img(p.image, p.title) + '<div>' +
      '<div class="pcard__badges">' + drugBadges(p) + '</div>' +
      '<div class="pcard__title">' + esc(p.title) + '</div>' +
      '<div class="pcard__price" style="justify-content:space-between"><span><b class="' + (sale ? 'sale' : '') + '">' + yen(p.price) + '</b>' + (sale ? ' <s>' + yen(p.original_price) + '</s>' : '') + '</span>' +
      window.SN.cartBtn(p.id, added) + '</div>' +
      '</div></div>' + (noticesHTML(p) ? '<div class="pcard__notes">' + noticesHTML(p) + '</div>' : '') + availHTML(p.availability, p) + '</article>';
  }

  let last = { q: '', only: false, results: [] };

  async function render(view, q, only) {
    const S = window.SNC.state;
    const s = window.SNC.storeById(S.storeId);
    if (!s) { window.SNC.go('#/'); return; }
    view.innerHTML = '<section class="store-top" style="padding-top:8px">' + window.Store.searchboxHTML(q) + '</section>' +
      '<div class="res-head"><span class="res-head__q" id="res-q">「' + esc(q) + '」<small id="res-count">検索中…</small></span>' +
      '<label class="switch"><input type="checkbox" id="only-store"' + (only ? ' checked' : '') + '>この店舗の在庫のみ</label></div>' +
      '<div class="res-list" id="res-list">' + [1, 2, 3].map(() => '<div class="pcard sn-skel" style="height:220px"></div>').join('') + '</div>';
    window.Store.bindSearchbox(view, s.store_id);
    view.querySelector('#only-store').addEventListener('change', (e) => {
      window.SNC.go('#/store/' + s.store_id + '/search?q=' + encodeURIComponent(q) + (e.target.checked ? '&only=1' : ''));
    });
    let r;
    try {
      r = await fetchJSON('/api/search?q=' + encodeURIComponent(q) + '&store_id=' + encodeURIComponent(s.store_id) + '&in_store_only=' + (only ? 1 : 0) + '&page_size=20');
    } catch (e) {
      view.querySelector('#res-list').innerHTML = '<p class="res-empty">検索できませんでした。時間をおいてお試しください。</p>';
      return;
    }
    last = { q, only, results: r.results || [] };
    view.querySelector('#res-count').textContent = (r.total || 0).toLocaleString('ja-JP') + '件' + (only ? '（' + (s.short_name || '') + 'に在庫あり）' : '');
    const list = view.querySelector('#res-list');
    if (!last.results.length) {
      list.innerHTML = '<p class="res-empty">' + (only ? 'この店舗に在庫のある商品が見つかりませんでした。<br>トグルをオフにすると近隣店舗・オンラインの在庫も表示します。' : '該当する商品が見つかりませんでした。') + '</p>';
      return;
    }
    list.innerHTML = last.results.map(cardHTML).join('');
    list.querySelectorAll('[data-find]').forEach((b) => b.addEventListener('click', () => {
      const p = last.results.find((x) => x.id === b.dataset.find);
      window.FloorMap.open({ storeId: s.store_id, items: [{ product: p, availability: p.availability }] });
    }));
    list.querySelectorAll('[data-cart]').forEach((b) => b.addEventListener('click', () => {
      const p = last.results.find((x) => x.id === b.dataset.cart);
      window.SN.setCartBtn(b, window.Cart.toggle({ product: p, availability: p.availability }));
    }));
    list.querySelectorAll('[data-more-avail]').forEach((b) => b.addEventListener('click', () => {
      const box = b.nextElementSibling;
      if (!box) return;
      const open = box.hidden;
      box.hidden = !open;
      b.setAttribute('aria-expanded', open ? 'true' : 'false');
      b.classList.toggle('is-open', open);
      const lbl = b.querySelector('.avail__toggle-lbl');
      if (lbl) lbl.textContent = open ? '他店舗・オンラインの在庫を閉じる' : '他店舗・オンラインの在庫を見る';
    }));
  }

  window.Search = { render, availHTML, shelfText, IN };
})();
