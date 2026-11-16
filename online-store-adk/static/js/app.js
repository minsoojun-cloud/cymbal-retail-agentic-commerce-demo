/* Shared helpers, product card + detail modal, view host. window.CR */
(function () {
  'use strict';
  const CFG = window.CR_CONFIG || {};

  const PLACEHOLDER_IMG = 'data:image/svg+xml;utf8,' + encodeURIComponent(
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' fill='#f1f3f4'/>" +
    "<circle cx='50' cy='46' r='14' fill='none' stroke='#bdc1c6' stroke-width='3'/></svg>");
  const SPARK = '<svg viewBox="0 0 24 24" aria-hidden="true"><defs><linearGradient id="crsg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#4285f4"/><stop offset=".6" stop-color="#9b72cb"/><stop offset="1" stop-color="#d96570"/></linearGradient></defs><path fill="url(#crsg)" d="M12 2c.4 4.9 2.9 8.5 9 10-6.1 1.5-8.6 5.1-9 10-.4-4.9-2.9-8.5-9-10 6.1-1.5 8.6-5.1 9-10z"/></svg>';

  const yen = (n) => '¥' + Math.round(Number(n) || 0).toLocaleString('ja-JP');
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  function getCookie(name) {
    const m = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
    return m ? decodeURIComponent(m[1]) : null;
  }
  function getCustomer() {
    const id = getCookie('cr_customer') || 'CR-0001';
    const c = (CFG.customers || {})[id] || { customer_id: id, name: 'さくら' };
    return { customer_id: id, name: c.name };
  }
  function getVisitorId() {
    let v = getCookie('cr_visitor');
    if (!v) {
      try { v = localStorage.getItem('cr_visitor_id'); } catch (e) { /* ignore */ }
      if (!v) { v = 'v-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8); }
      try { localStorage.setItem('cr_visitor_id', v); } catch (e) { /* ignore */ }
    }
    return v;
  }

  let toastTimer = null;
  function toast(msg, opts) {
    opts = opts || {};
    const el = document.getElementById('cr-toast');
    if (!el) return;
    el.textContent = msg;
    el.classList.toggle('is-success', !!opts.success);
    el.classList.add('is-show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('is-show'), opts.ms || 3200);
  }

  async function fetchJSON(url, init) {
    const r = await fetch(url, Object.assign({ headers: { Accept: 'application/json', 'Content-Type': 'application/json' } }, init || {}));
    if (!r.ok) throw new Error('HTTP ' + r.status + ' ' + url);
    return r.json();
  }

  // ---- product cache ----
  const productCache = new Map();
  /** CONTRACT v6: each site serves its own product images → absolute catalog URIs (…/img/products/<file>) become relative */
  function localImg(u) {
    if (!u || typeof u !== 'string') return u || '';
    const m = u.split(/[?#]/)[0].match(/\/img\/products\/([^/]+)$/);
    return m ? '/img/products/' + m[1] : u;
  }
  function remember(list) { (list || []).forEach((p) => { if (p && p.id) { if (p.image) p.image = localImg(p.image); productCache.set(p.id, p); } }); return list; }
  async function fetchProducts(ids) {
    ids = (ids || []).map(String).filter(Boolean);
    const missing = ids.filter((i) => !productCache.has(i));
    if (missing.length) {
      const res = await fetchJSON('/api/products?ids=' + encodeURIComponent(missing.join(',')));
      remember(res.products || []);
    }
    return ids.map((i) => productCache.get(i)).filter(Boolean);
  }
  async function getProduct(id) { return (await fetchProducts([id]))[0] || null; }

  // ---- feature status (✨ labels) ----
  let featureStatus = {};
  function featureLabel(name, key) {
    const st = featureStatus[key] || '';
    const tip = { live: 'Vertex AI Search for Commerce（ライブ）', fallback: 'フォールバック表示', mock: 'ローカルモード（モック）' }[st] || '';
    return '<span class="cr-feature" data-feature="' + esc(key) + '" data-status="' + esc(st) + '" title="' + esc(tip) + '">' + esc(name) + '</span>';
  }
  function setFeatureStatus(map) {
    featureStatus = Object.assign({}, featureStatus, map || {});
    $$('.cr-feature[data-feature]').forEach((el) => { const s = featureStatus[el.dataset.feature]; if (s) el.dataset.status = s; });
  }

  // ---- rendering ----
  function stars(r) {
    const n = Math.round(Number(r) || 0);
    return '<i>' + '★'.repeat(n) + '<span style="color:#dadce0">' + '★'.repeat(Math.max(0, 5 - n)) + '</span></i>';
  }
  function priceHtml(p) {
    const sale = p.on_sale && p.original_price > p.price;
    return '<div class="cr-price"><span class="cr-price__now' + (sale ? ' is-sale' : '') + '">' + yen(p.price) + '</span>' +
      (sale ? '<span class="cr-price__was">' + yen(p.original_price) + '</span>' : '') +
      '<span class="cr-price__tax">税込</span></div>';
  }
  function discountBadge(p) {
    if (!p.on_sale) return '';
    const pct = Math.round((p.discount_rate || 0) * 100);
    return '<span class="cr-card__badge">' + (pct > 0 ? pct + '%OFF' : 'セール') + '</span>';
  }
  // dinner-set tag chips (show_products_on_page sections[].tags) → colour class
  const TAG_CLASS = { 'よく購入': 'freq', '家族の好み': 'family', '特価': 'sale', '旬': 'season', '時短': 'quick' };
  function cardHtml(p, opts) {
    opts = opts || {};
    remember([p]);
    return '<article class="cr-card' + (opts.highlight ? ' is-highlight' : '') + (opts.compact ? ' cr-card--h' : '') + '" data-pid="' + esc(p.id) + '" style="animation-delay:' + ((opts.i || 0) * 25) + 'ms">' +
      '<button type="button" class="cr-card__media" data-open="' + esc(p.id) + '" aria-label="' + esc(p.title) + ' の詳細">' +
        '<img loading="lazy" src="' + esc(p.image || PLACEHOLDER_IMG) + '" alt="" onerror="this.onerror=null;this.src=CR.PLACEHOLDER_IMG">' +
        discountBadge(p) +
        (opts.rank ? '<span class="cr-card__rank' + (opts.rank <= 3 ? ' is-top' : '') + '" data-rank="' + opts.rank + '">' + opts.rank + '</span>' : '') +
        (opts.highlight ? '<span class="cr-card__ai">✨ AIおすすめ</span>' : '') +
      '</button>' +
      '<div class="cr-card__body">' +
        '<button type="button" class="cr-card__title" data-open="' + esc(p.id) + '">' + esc(p.title) + '</button>' +
        (opts.qty > 1 ? priceHtml(p).replace(/<\/div>$/, '<span class="cr-price__qty" data-qty="' + opts.qty + '">×' + opts.qty + '</span></div>') : priceHtml(p)) +
        '<div class="cr-card__meta"><span class="cr-stars">' + stars(p.rating) + ' ' + (p.rating || '') + ' <small>(' + (p.rating_count || 0) + ')</small></span></div>' +
        (opts.tags && opts.tags.length ? '<div class="cr-tags">' + opts.tags.map((t) => '<span class="cr-tag cr-tag--' + (TAG_CLASS[t] || 'other') + '">' + esc(t) + '</span>').join('') + '</div>' : '') +
        (opts.reason ? '<div class="cr-card__reason">' + esc(opts.reason) + '</div>' : '') +
      '</div>' +
      '<button type="button" class="cr-btn cr-btn--tonal cr-card__add" data-add="' + esc(p.id) + '" id="add-' + esc(p.id) + '">カートに追加</button>' +
    '</article>';
  }
  function skeletonGrid(n) {
    let h = '';
    for (let i = 0; i < (n || 8); i++) h += '<div class="cr-skel-card"><div class="m"></div><div class="l"></div><div class="l s"></div></div>';
    return h;
  }

  // ---- product modal ----
  const modal = () => document.getElementById('cr-product-modal');
  let modalQty = 1;
  async function openProduct(id, opts) {
    const p = await getProduct(id);
    if (!p) { toast('商品が見つかりませんでした'); return; }
    modalQty = 1;
    const body = document.getElementById('cr-pm-body');
    body.innerHTML =
      '<div class="cr-pd">' +
        '<div class="cr-pd__media"><img src="' + esc(p.image || PLACEHOLDER_IMG) + '" alt="' + esc(p.title) + '">' + discountBadge(p) + '</div>' +
        '<div>' +
          '<div class="cr-pd__brand">' + esc(p.brand || p.category) + '</div>' +
          '<h2 id="cr-pm-title">' + esc(p.title) + '</h2>' +
          '<div class="cr-stars">' + stars(p.rating) + ' ' + esc(p.rating) + ' <small>(' + esc(p.rating_count) + '件のレビュー)</small></div>' +
          '<div style="margin-top:14px">' + priceHtml(p) + '</div>' +
          (p.promo_text ? '<div class="cr-pd__promo">' + esc(p.promo_text) + '</div>' : '') +
          '<div class="cr-pd__labels">' + [p.category, p.size].concat(p.labels || []).filter(Boolean).map((l) => '<span>' + esc(l) + '</span>').join('') + '</div>' +
          '<div class="cr-pd__desc">' + esc(p.description) + '</div>' +
          '<div class="cr-pd__buy">' +
            '<div class="cr-qty"><button type="button" data-qstep="-1" aria-label="数量を減らす">−</button><span id="cr-pm-qty">1</span><button type="button" data-qstep="1" aria-label="数量を増やす">＋</button></div>' +
            '<button type="button" class="cr-btn cr-btn--primary" id="cr-pm-add" style="flex:1;height:44px;border-radius:22px">カートに追加</button>' +
          '</div>' +
          '<button type="button" class="cr-btn cr-pd__ask" id="cr-pm-ask">' + SPARK + 'AIコンシェルジュに相談する</button>' +
        '</div>' +
      '</div>' +
      '<button type="button" class="cr-icon-btn cr-pd__close" data-close aria-label="閉じる"><svg viewBox="0 0 24 24"><path d="M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg></button>';
    body.querySelector('#cr-pm-add').onclick = () => { window.Cart.add(p, modalQty); closeProduct(); };
    body.querySelector('#cr-pm-ask').onclick = () => { closeProduct(); window.CRChat && window.CRChat.ask('「' + p.title + '」について教えてください。'); };
    body.querySelectorAll('[data-qstep]').forEach((b) => b.onclick = () => {
      modalQty = Math.max(1, Math.min(99, modalQty + Number(b.dataset.qstep)));
      body.querySelector('#cr-pm-qty').textContent = modalQty;
    });
    modal().hidden = false;
    document.body.style.overflow = 'hidden';
    CR.pageContext.product_id = p.id; CR.pageContext.product_title = p.title;
    CR.emit('context');
    if (!(opts && opts.noHistory)) {
      const u = new URL(location.href); u.searchParams.set('product', p.id);
      history.replaceState(history.state, '', u);
    }
  }
  function closeProduct() {
    if (modal().hidden) return;
    modal().hidden = true;
    document.body.style.overflow = '';
    CR.pageContext.product_id = ''; CR.pageContext.product_title = '';
    CR.emit('context');
    const u = new URL(location.href);
    if (u.searchParams.has('product')) { u.searchParams.delete('product'); history.replaceState(history.state, '', u); }
  }

  // ---- tiny event bus ----
  const bus = {};
  const on = (ev, fn) => { (bus[ev] = bus[ev] || []).push(fn); };
  const emit = (ev, data) => (bus[ev] || []).forEach((fn) => { try { fn(data); } catch (e) { console.error(e); } });

  const CR = window.CR = {
    CFG, PLACEHOLDER_IMG, SPARK, yen, esc, localImg, $, $$, getCookie, getCustomer, getVisitorId, toast, fetchJSON,
    fetchProducts, getProduct, remember, cardHtml, priceHtml, stars, skeletonGrid, openProduct, closeProduct, TAG_CLASS,
    featureLabel, setFeatureStatus, on, emit,
    pageContext: { view: 'home', query: '', product_id: '', product_title: '' },
    view: () => document.getElementById('cr-view'),
  };

  // global delegation: open product / add to cart from any card
  document.addEventListener('click', (e) => {
    const add = e.target.closest('[data-add]');
    if (add) {
      e.preventDefault();
      const p = productCache.get(add.dataset.add);
      if (p) {
        window.Cart.add(p, 1);
        add.classList.add('is-added'); add.textContent = '✓ 追加しました';
        setTimeout(() => { add.classList.remove('is-added'); add.textContent = 'カートに追加'; }, 1600);
      }
      return;
    }
    const op = e.target.closest('[data-open]');
    if (op) { e.preventDefault(); openProduct(op.dataset.open); return; }
    if (e.target.closest('#cr-product-modal [data-close]')) closeProduct();
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeProduct(); });

  // Header icon-only cross-links (with hover tooltip) to Data Enrichment Studio, Store Navi, etc.
  const ICON_ENRICH = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19 9l1.25-2.75L23 5l-2.75-1.25L19 1l-1.25 2.75L15 5l2.75 1.25L19 9zm-7.5.5L9 4 6.5 9.5 1 12l5.5 2.5L9 20l2.5-5.5L17 12l-5.5-2.5zM19 15l-1.25 2.75L15 19l2.75 1.25L19 23l1.25-2.75L23 19l-2.75-1.25L19 15z"/></svg>';
  const ICON_STORE = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 4H4v2h16V4zm1 10v-2l-1-5H4l-1 5v2h1v6h10v-6h4v6h2v-6h1zm-9 4H6v-4h6v4z"/></svg>';
  const ICON_FLYER = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-5 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z"/></svg>';
  function applyBrandName() {
    const brand = String(CFG.brandName || '').trim();
    if (!brand || brand === 'Cymbal Retail') return;
    document.title = brand + ' オンラインストア | AI Commerce Search デモ';
    const logo = document.getElementById('cr-logo');
    if (logo) {
      logo.setAttribute('aria-label', brand + ' ホーム');
      const parts = brand.split(/\s+/);
      const a = logo.querySelector('.cr-logo__a');
      const b = logo.querySelector('.cr-logo__b');
      if (a) a.textContent = parts[0] || brand;
      if (b) b.textContent = parts.slice(1).join(' ');
    }
    const copy = document.querySelector('.cr-footer__inner > span:first-child');
    if (copy) copy.textContent = '© 2026 ' + brand + '（デモサイト）';
    const sub = document.getElementById('cr-chat-sub');
    if (sub && sub.textContent === 'Cymbal Retail') sub.textContent = brand;
  }
  function mountCrossLinks() {
    const nav = document.querySelector('.cr-header__actions');
    if (!nav) return;
    const flyerUrl = String(CFG.flyerUrl || '');
    if (/^https?:\/\//.test(flyerUrl) && !document.getElementById('cr-flyer-link')) {
      const a = document.createElement('a');
      a.id = 'cr-flyer-link';
      a.className = 'cr-xlink';
      a.href = flyerUrl;
      a.dataset.tooltip = 'チラシ作成スタジオ';
      a.title = 'チラシ作成スタジオ';
      a.setAttribute('aria-label', 'チラシ作成スタジオへ');
      a.innerHTML = '<span class="cr-xlink__icon">' + ICON_FLYER + '</span><span class="cr-xlink__label" hidden>チラシ作成スタジオ</span>';
      nav.insertBefore(a, nav.firstChild);
    }
    const storeAppUrl = String(CFG.storeAppUrl || '');
    if (/^https?:\/\//.test(storeAppUrl) && !document.getElementById('cr-store-app-link')) {
      const a = document.createElement('a');
      a.id = 'cr-store-app-link';
      a.className = 'cr-xlink';
      a.href = storeAppUrl;
      a.dataset.tooltip = '店舗ナビ';
      a.title = '店舗ナビ（お客様アプリ）へ';
      a.setAttribute('aria-label', '店舗ナビ（お客様アプリ）へ');
      a.innerHTML = '<span class="cr-xlink__icon">' + ICON_STORE + '</span><span class="cr-xlink__label" hidden>店舗ナビ</span>';
      nav.insertBefore(a, nav.firstChild);
    }
    const url = String(CFG.enrichUrl || '');
    if (/^https?:\/\//.test(url) && !document.getElementById('cr-enrich-link')) {
      const a = document.createElement('a');
      a.id = 'cr-enrich-link';
      a.className = 'cr-xlink';
      a.href = url;
      a.dataset.tooltip = 'データエンリッチメント';
      a.title = '商品データエンリッチメント・スタジオへ';
      a.setAttribute('aria-label', '商品データエンリッチメント・スタジオへ');
      a.innerHTML = '<span class="cr-xlink__icon">' + ICON_ENRICH + '</span>';
      nav.insertBefore(a, nav.firstChild);
    }
    if (document.getElementById('cr-enrich-link') || document.getElementById('cr-store-app-link') || document.getElementById('cr-flyer-link')) {
      const header = document.getElementById('cr-header');
      if (header) header.classList.add('cr-header--xlink');
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    applyBrandName();
    mountCrossLinks();
    const c = getCustomer();
    const g = document.getElementById('cr-greeting'); if (g) g.textContent = c.name + 'さん';
    const a = document.getElementById('cr-avatar'); if (a) a.textContent = (c.name || 'ゲ').slice(0, 1);
    const header = document.getElementById('cr-header');
    window.addEventListener('scroll', () => header.classList.toggle('is-scrolled', window.scrollY > 4), { passive: true });
    fetchJSON('/api/features').then((f) => setFeatureStatus(f.features)).catch(() => {});
  });
})();
