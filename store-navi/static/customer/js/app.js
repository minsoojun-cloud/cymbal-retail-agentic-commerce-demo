/* Store Navi customer app shell: state, hash router, header (store chip, demo login, staff cross link), sheets. */
(function () {
  'use strict';
  const { CFG, esc, fetchJSON, postJSON, crossLink, toast } = window.SN;
  const SS = window.sessionStorage;

  const state = {
    customer: null,           // {customer_id, name, avatar}
    stores: [], nearestId: null, coords: null, geoSource: 'none', simKey: '',
    storeId: SS.getItem('sn_store') || '', inStore: false,
    view: 'home', homeCache: {},
  };

  function save() {
    SS.setItem('sn_store', state.storeId || '');
    SS.setItem('sn_geo', JSON.stringify({ coords: state.coords, src: state.geoSource, sim: state.simKey }));
  }
  try {
    const g = JSON.parse(SS.getItem('sn_geo') || 'null');
    if (g && g.coords) { state.coords = g.coords; state.geoSource = g.src; state.simKey = g.sim || ''; }
  } catch (e) { /* ignore */ }

  function storeById(id) { return state.stores.find((s) => s.store_id === id) || null; }

  async function loadStores() {
    const c = state.coords;
    const q = c ? ('?lat=' + c.lat + '&lng=' + c.lng) : '';
    const r = await fetchJSON('/api/stores' + q);
    state.stores = r.stores || [];
    state.nearestId = r.nearest_id;
    const cur = storeById(state.storeId);
    state.inStore = !!(cur && cur.in_store);
    return r;
  }

  // ---------------------------------------------------------------- header
  function renderHeader() {
    const s = storeById(state.storeId);
    const chip = document.getElementById('hdr-store');
    const back = document.getElementById('hdr-back');
    const inStoreView = state.view !== 'home' && !!s;
    chip.hidden = !inStoreView;
    back.hidden = state.view === 'home';
    document.getElementById('hdr-logo').hidden = false;
    if (s) {
      document.getElementById('hdr-store-name').textContent = s.short_name || s.name;
      document.getElementById('hdr-store-dot').classList.toggle('is-closed', !s.open_now);
      chip.title = s.name + (s.open_now ? '（営業中）' : '（営業時間外）');
    }
    const av = document.getElementById('hdr-avatar');
    if (state.customer) {
      av.textContent = state.customer.avatar || '🙂';
      document.getElementById('hdr-login').title = state.customer.name + 'さん（デモユーザーを切り替え）';
    }
    document.getElementById('fab-ai').hidden = !inStoreView;
  }

  function initHeader() {
    const actions = document.getElementById('hdr-actions');
    const loginBtn = document.getElementById('hdr-login');
    const storeLink = crossLink(actions, CFG.onlineStoreLink, 'オンラインストア', 'store', 'sn-online-store-link');
    if (storeLink && loginBtn) actions.insertBefore(storeLink, loginBtn);
    const enrichLink = crossLink(actions, CFG.enrichUrl, 'データエンリッチメント', 'enrich', 'sn-enrich-link');
    if (enrichLink && loginBtn) actions.insertBefore(enrichLink, loginBtn);
    const link = crossLink(actions, CFG.staffUrl, 'スタッフアプリ', 'staff', 'sn-staff-link');
    if (link && loginBtn) actions.insertBefore(link, loginBtn);
    document.getElementById('hdr-back').addEventListener('click', () => {
      if (state.view === 'results') go('#/store/' + state.storeId);
      else go('#/');
    });
    document.getElementById('hdr-store').addEventListener('click', () => go('#/store/' + state.storeId));
    document.getElementById('hdr-login').addEventListener('click', openLogin);
    document.getElementById('fab-ai').addEventListener('click', () => window.Chat.open());
    document.getElementById('scrim').addEventListener('click', closeSheets);
  }

  // ---------------------------------------------------------------- sheets
  function openSheet(id) {
    closeSheets(true);
    document.getElementById('scrim').hidden = false;
    document.getElementById(id).hidden = false;
  }
  function closeSheets(keepScrim) {
    ['sheet-login', 'sheet-geo', 'sheet-cart', 'chat'].forEach((id) => { const el = document.getElementById(id); if (el) el.hidden = true; });
    if (!keepScrim) document.getElementById('scrim').hidden = true;
  }

  function openLogin() {
    const list = document.getElementById('login-list');
    list.innerHTML = (CFG.customers || []).map((c) => {
      const on = state.customer && state.customer.customer_id === c.customer_id;
      return '<button type="button" class="login-opt' + (on ? ' is-on' : '') + '" data-cid="' + esc(c.customer_id) + '">' +
        '<span class="login-opt__av">' + esc(c.avatar || '🙂') + '</span>' +
        '<span><span class="login-opt__name">' + esc(c.name) + 'さん</span>' +
        '<span class="login-opt__meta">' + esc([c.age ? c.age + '歳' : '', (c.concerns || []).join('・')].filter(Boolean).join(' ・ ')) + '</span></span>' +
        (on ? '<svg class="login-opt__check" viewBox="0 0 24 24"><path d="M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg>' : '<span></span>') + '</button>';
    }).join('');
    list.querySelectorAll('[data-cid]').forEach((b) => b.addEventListener('click', async () => {
      const r = await postJSON('/api/login', { customer_id: b.dataset.cid });
      state.customer = r.customer;
      state.homeCache = {};
      closeSheets();
      toast(r.customer.name + 'さんとしてログインしました');
      window.Chat && window.Chat.reset();
      route();
    }));
    openSheet('sheet-login');
  }

  // ---------------------------------------------------------------- router
  function go(hash) { if (location.hash === hash) route(); else location.hash = hash; }

  async function route() {
    const h = location.hash || '#/';
    const view = document.getElementById('view');
    let m;
    if ((m = h.match(/^#\/store\/([A-Za-z0-9_-]+)\/search\?(.*)$/))) {
      state.storeId = m[1]; state.view = 'results'; save();
      const p = new URLSearchParams(m[2]);
      renderHeader();
      await window.Search.render(view, p.get('q') || '', p.get('only') === '1');
    } else if ((m = h.match(/^#\/store\/([A-Za-z0-9_-]+)/))) {
      state.storeId = m[1]; state.view = 'store'; save();
      renderHeader();
      await window.Store.render(view);
    } else {
      state.view = 'home';
      renderHeader();
      await window.Home.render(view);
    }
    renderHeader();
    window.scrollTo({ top: 0 });
  }

  async function boot() {
    initHeader();
    try {
      const me = await fetchJSON('/api/me');
      state.customer = me.customer;
    } catch (e) { /* ignore */ }
    try { await loadStores(); } catch (e) { toast('店舗情報を取得できませんでした'); }
    window.Cart && window.Cart.init();
    window.Chat && window.Chat.init();
    window.FloorMap && window.FloorMap.init();
    window.addEventListener('hashchange', route);
    await route();
    if (!state.coords) window.Geo.auto();
  }

  window.SNC = { state, boot, go, route, save, loadStores, storeById, renderHeader, openSheet, closeSheets };
})();
