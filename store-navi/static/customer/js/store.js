/* Store screen: personalized coupons (「〇〇さん限定」), 特価, search form with autocomplete, AI concierge entry. */
(function () {
  'use strict';
  const { esc, fetchJSON } = window.SN;
  const QUICK = ['かぜ薬', '解熱鎮痛薬', '冷却シート', '経口補水液', '目薬', '湿布', '敏感肌 化粧水', 'マスク'];

  function searchboxHTML(value) {
    return '<div class="searchbox"><form class="searchbox__form" id="sb-form" role="search" autocomplete="off">' +
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>' +
      '<input id="sb-input" type="search" name="q" value="' + esc(value || '') + '" placeholder="商品名・症状で探す（例: かぜ薬）" aria-label="商品を検索" aria-autocomplete="list" aria-controls="sb-ac" enterkeyhint="search">' +
      '<button type="button" class="searchbox__clear" id="sb-clear" aria-label="クリア"' + (value ? '' : ' hidden') + '><svg viewBox="0 0 24 24"><path d="M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg></button>' +
      '<ul class="ac" id="sb-ac" role="listbox" hidden></ul></form></div>';
  }
  function bindSearchbox(root, storeId) {
    window.Autocomplete.attach(root.querySelector('#sb-form'), root.querySelector('#sb-input'), root.querySelector('#sb-ac'),
      root.querySelector('#sb-clear'), (q) => window.SNC.go('#/store/' + storeId + '/search?q=' + encodeURIComponent(q)));
  }

  async function render(view) {
    const S = window.SNC.state;
    const s = window.SNC.storeById(S.storeId);
    if (!s) { window.SNC.go('#/'); return; }
    const name = (S.customer && S.customer.name) || '';
    view.innerHTML =
      '<section class="store-top"><div class="store-top__row"><h1 class="store-top__name">' + esc(s.name) + '</h1></div>' +
      '<div class="store-top__row" style="margin-top:6px">' + window.Home.openPill(s) + (s.in_store ? '<span class="sn-pill sn-pill--online">店内モード</span>' : '') +
      '<span class="store-top__hours">' + esc(window.Home.hoursLine(s)) + ' ・ ' + window.Home.pharmacyLine(s) + '</span></div>' +
      searchboxHTML('') +
      '<div class="quick">' + QUICK.map((q) => '<button type="button" class="sn-chip" data-q="' + esc(q) + '">' + esc(q) + '</button>').join('') + '</div></section>' +
      '<button type="button" class="ai-card" id="ai-card"><span class="ai-card__icon"><svg viewBox="0 0 24 24"><path d="M12 2l1.9 5.6L19.5 9.5 13.9 11.4 12 17l-1.9-5.6L4.5 9.5l5.6-1.9L12 2zm7 11 1 2.8 2.8 1-2.8 1-1 2.8-1-2.8-2.8-1 2.8-1 1-2.8z"/></svg></span>' +
      '<span><span class="ai-card__title">症状やお悩みをAIに相談</span><br><span class="ai-card__sub">「昨日から熱っぽい」など。合う商品の候補と、店内の回る順番をご案内します。</span></span></button>' +
      '<section class="sec"><div class="sec__head"><h2 class="sec__title" id="personal-title">' + esc(name ? name + 'さん限定クーポン' : 'あなたへのクーポン') + '</h2></div>' +
      '<div class="hscroll" id="st-coupons"><div class="coupon sn-skel"></div><div class="coupon sn-skel"></div></div></section>' +
      '<section class="sec"><div class="sec__head"><h2 class="sec__title">本日の特価<small>' + esc(name ? name + 'さんへのおすすめ順' : '') + '</small></h2></div>' +
      '<div class="hscroll" id="st-offers"><div class="offer sn-skel" style="height:220px"></div><div class="offer sn-skel" style="height:220px"></div></div></section>';
    bindSearchbox(view, s.store_id);
    view.querySelectorAll('.quick [data-q]').forEach((b) => b.addEventListener('click', () => {
      window.Autocomplete.pushRecent(b.dataset.q);
      window.SNC.go('#/store/' + s.store_id + '/search?q=' + encodeURIComponent(b.dataset.q));
    }));
    view.querySelector('#ai-card').addEventListener('click', () => window.Chat.open());
    try {
      const home = await fetchJSON('/api/stores/' + encodeURIComponent(s.store_id) + '/home');
      const personal = (home.coupons || []).filter((c) => c.personal);
      const others = (home.coupons || []).filter((c) => !c.personal);
      view.querySelector('#st-coupons').innerHTML = personal.concat(others).map(window.Home.couponHTML).join('') || '<p class="res-empty">クーポンはありません</p>';
      if (!personal.length) view.querySelector('#personal-title').textContent = 'クーポン';
      const of = view.querySelector('#st-offers');
      of.innerHTML = (home.offers || []).map(window.Home.offerHTML).join('');
      window.Home.bindOffers(of, home.offers || [], s.store_id);
    } catch (e) { view.querySelector('#st-coupons').innerHTML = ''; }
  }

  window.Store = { render, searchboxHTML, bindSearchbox };
})();
