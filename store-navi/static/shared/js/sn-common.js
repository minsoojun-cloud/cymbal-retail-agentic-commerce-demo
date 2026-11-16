/* Cymbal Store Navi — shared helpers (customer & staff apps): window.SN */
(function () {
  'use strict';
  const CFG = window.SN_CONFIG || {};

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }
  function yen(n) { return Math.round(Number(n) || 0).toLocaleString('ja-JP') + '円'; }
  function km(m) {
    if (m == null) return '';
    return m < 1000 ? Math.round(m) + 'm' : (m / 1000).toFixed(m < 10000 ? 1 : 0) + 'km';
  }
  async function fetchJSON(url, opts) {
    const r = await fetch(url, Object.assign({ credentials: 'same-origin' }, opts || {}));
    if (!r.ok) {
      let detail = '';
      try { detail = (await r.json()).error || ''; } catch (e) { /* ignore */ }
      throw new Error('HTTP ' + r.status + (detail ? ' ' + detail : ''));
    }
    return r.json();
  }
  function postJSON(url, body) {
    return fetchJSON(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
  }

  const DRUG = {
    '第1類医薬品': { cls: '1', short: '第1類医薬品' },
    '指定第2類医薬品': { cls: 's2', short: '指定第2類' },
    '第2類医薬品': { cls: '2', short: '第2類医薬品' },
    '第3類医薬品': { cls: '3', short: '第3類医薬品' },
    '医薬部外品': { cls: 'q', short: '医薬部外品' },
  };
  // COMPLIANCE_ja.md §1 (exact wording)
  const DRUG_NOTE = {
    '第1類医薬品': '第1類医薬品：ご購入時に薬剤師からの説明が必要です。薬剤師不在時は購入できません。',
    '指定第2類医薬品': '指定第2類医薬品：使用上の注意（禁忌）を必ずご確認ください。ご不明点は薬剤師・登録販売者へ。',
    '第2類医薬品': '第2類医薬品：ご不明点は薬剤師・登録販売者にご相談ください。',
  };
  const ABUSE_NOTE = '指定濫用防止医薬品：お一人様1個まで。18歳未満の方は小容量1個のみ・年齢等の確認があります。この商品はレジ（医薬品カウンター）でお渡しします。';
  const DISCLAIMER = '※本サービスは一般的な情報提供であり、医師の診断に代わるものではありません。医薬品は添付文書をよく読み、用法・用量を守ってご使用ください。症状が続く・悪化する場合は医療機関を受診してください。ご不明点は店舗の薬剤師・登録販売者にご相談ください。';

  function drugBadges(p) {
    if (!p) return '';
    let h = '';
    const d = DRUG[p.drug_class];
    if (d) h += '<span class="sn-drug sn-drug--' + d.cls + '">' + esc(d.short) + '</span>';
    if (p.abuse_control) h += '<span class="sn-drug sn-drug--abuse" title="指定濫用防止医薬品">お一人様1個</span>';
    return h;
  }
  function isMedicine(p) { return !!(p && /医薬品$/.test(p.drug_class || '') && p.drug_class !== '医薬部外品'); }
  function complianceNotes(p) {
    const out = [];
    if (!p) return out;
    if (DRUG_NOTE[p.drug_class]) out.push({ level: p.drug_class === '第1類医薬品' ? 'warn' : 'info', text: DRUG_NOTE[p.drug_class] });
    if (p.drug_class === '第1類医薬品') out.push({ level: 'warn', text: '店頭購入は調剤カウンターで薬剤師にお声がけください。オンラインは薬剤師による確認後の発送です。' });
    if (p.abuse_control) out.push({ level: 'warn', text: ABUSE_NOTE });
    return out;
  }
  const ICON_INFO = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M11 7h2v2h-2zm0 4h2v6h-2zm1-9C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"/></svg>';
  function noticesHTML(p) {
    return complianceNotes(p).map((n) => '<div class="sn-notice' + (n.level === 'warn' ? ' sn-notice--warn' : '') + '">' + ICON_INFO + '<span>' + esc(n.text) + '</span></div>').join('');
  }
  const STATUS_JA = { in_stock: '在庫あり', low_stock: '残りわずか', out_of_stock: '在庫なし', not_carried: '取扱いなし' };
  function statusPill(status, qty) {
    const label = STATUS_JA[status] || status;
    const q = (status === 'low_stock' && qty) ? '（残り' + qty + '）' : '';
    return '<span class="sn-pill sn-pill--' + esc(status) + '">' + esc(label + q) + '</span>';
  }
  function img(src, alt, cls) {
    return '<div class="sn-img ' + (cls || '') + '"><img src="' + esc(src || '') + '" alt="' + esc(alt || '') + '" loading="lazy" onerror="this.parentNode.classList.add(\'is-broken\')"></div>';
  }

  // CONTRACT v7/v8 cross link (icon-only, hover tooltip)
  const ICONS = {
    staff: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 7h-4V5c0-1.1-.9-2-2-2h-4c-1.1 0-2 .9-2 2v2H4c-1.1 0-2 .9-2 2v11c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V9c0-1.1-.9-2-2-2zM10 5h4v2h-4V5zm2 5.5a2 2 0 1 1 0 4 2 2 0 0 1 0-4zM16 19H8v-.75c0-1.33 2.67-2 4-2s4 .67 4 2V19z"/></svg>',
    customer: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M17 1.01 7 1c-1.1 0-2 .9-2 2v18c0 1.1.9 2 2 2h10c1.1 0 2-.9 2-2V3c0-1.1-.9-1.99-2-1.99zM17 19H7V5h10v14zm-5-9.5a2 2 0 1 1 0 4 2 2 0 0 1 0-4zM15 17H9v-.6c0-1 2-1.6 3-1.6s3 .6 3 1.6v.6z"/></svg>',
    store: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19 6h-2c0-2.76-2.24-5-5-5S7 3.24 7 6H5c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm-7-3c1.66 0 3 1.34 3 3H9c0-1.66 1.34-3 3-3zm7 17H5V8h14v12zm-7-8c-1.66 0-3-1.34-3-3H7c0 2.76 2.24 5 5 5s5-2.24 5-5h-2c0 1.66-1.34 3-3 3z"/></svg>',
    enrich: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19 9l1.25-2.75L23 5l-2.75-1.25L19 1l-1.25 2.75L15 5l2.75 1.25L19 9zm-7.5.5L9 4 6.5 9.5 1 12l5.5 2.5L9 20l2.5-5.5L17 12l-5.5-2.5zM19 15l-1.25 2.75L15 19l2.75 1.25L19 23l1.25-2.75L23 19l-2.75-1.25L19 15z"/></svg>',
  };
  function crossLink(container, url, tooltip, icon, id) {
    if (!container || !/^https?:\/\//.test(String(url || ''))) return null;
    const a = document.createElement('a');
    a.className = 'sn-xlink';
    if (id) a.id = id;
    a.href = url;
    a.dataset.tooltip = tooltip;
    a.setAttribute('aria-label', tooltip);
    a.innerHTML = '<span class="sn-xlink__icon">' + (ICONS[icon] || icon || '') + '</span>';
    container.appendChild(a);
    return a;
  }

  // CONTRACT v9: cart buttons are a cart icon (Material add_shopping_cart) with aria-label / tooltip 「カートに追加」
  const ICON_ADD_CART = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M11 9h2V6h3V4h-3V1h-2v3H8v2h3v3zm-4 9c-1.1 0-1.99.9-1.99 2S5.9 22 7 22s2-.9 2-2-.9-2-2-2zm10 0c-1.1 0-1.99.9-1.99 2s.89 2 1.99 2 2-.9 2-2-.9-2-2-2zm-9.83-3.25.03-.12.9-1.63h7.45c.75 0 1.41-.41 1.75-1.03l3.86-7.01L19.42 4h-.01l-1.1 2-2.76 5H8.53l-.13-.27L6.16 6l-.95-2-.94-2H1v2h2l3.6 7.59-1.35 2.45c-.16.28-.25.61-.25.96 0 1.1.9 2 2 2h12v-2H7.42c-.13 0-.25-.11-.25-.25z"/></svg>';
  const ICON_IN_CART = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 18c-1.1 0-1.99.9-1.99 2S5.9 22 7 22s2-.9 2-2-.9-2-2-2zm10 0c-1.1 0-1.99.9-1.99 2s.89 2 1.99 2 2-.9 2-2-.9-2-2-2zM7.17 14.75l.03-.12.9-1.63h7.45c.75 0 1.41-.41 1.75-1.03l3.86-7.01L19.42 4h-.01l-1.1 2-2.76 5H8.53l-.13-.27L6.16 6l-.95-2-.94-2H1v2h2l3.6 7.59-1.35 2.45c-.16.28-.25.61-.25.96 0 1.1.9 2 2 2h12v-2H7.42c-.13 0-.25-.11-.25-.25zM10.5 9.5 8.4 7.4 7 8.8l3.5 3.5 6-6-1.4-1.4z"/></svg>';
  function cartBtn(pid, added) {
    const t = added ? 'カートに追加済み' : 'カートに追加';
    return '<button type="button" class="cart-ic' + (added ? ' is-added' : '') + '" data-cart="' + esc(pid) + '" aria-label="' + t + '" aria-pressed="' + (added ? 'true' : 'false') + '" data-tooltip="' + t + '">' +
      (added ? ICON_IN_CART : ICON_ADD_CART) + '</button>';
  }
  function setCartBtn(btn, added) {
    const t = added ? 'カートに追加済み' : 'カートに追加';
    btn.classList.toggle('is-added', added);
    btn.setAttribute('aria-label', t); btn.setAttribute('aria-pressed', added ? 'true' : 'false'); btn.dataset.tooltip = t;
    btn.innerHTML = added ? ICON_IN_CART : ICON_ADD_CART;
  }

  let toastTimer = null;
  function toast(msg) {
    let el = document.getElementById('sn-toast');
    if (!el) { el = document.createElement('div'); el.id = 'sn-toast'; el.className = 'sn-toast'; el.setAttribute('role', 'status'); document.body.appendChild(el); }
    el.textContent = msg;
    el.classList.add('is-on');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('is-on'), 2600);
  }

  window.SN = { CFG, esc, yen, km, fetchJSON, postJSON, DRUG, DRUG_NOTE, ABUSE_NOTE, DISCLAIMER, STATUS_JA,
    drugBadges, isMedicine, complianceNotes, noticesHTML, statusPill, img, crossLink, toast, ICON_INFO, cartBtn, setCartBtn, ICON_ADD_CART };
})();
