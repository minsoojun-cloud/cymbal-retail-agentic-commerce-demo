/* AI concierge chat (bottom sheet): SSE v3 events (status/text/action/chips/done/error) from /api/agent/stream,
   recommendation card for action show_store_items (numbered items, 「まとめて棚を探す」, 「まとめて購入」), fixed disclaimer. */
(function () {
  'use strict';
  const { esc, yen, km, drugBadges, img, CFG, DISCLAIMER, ICON_INFO, statusPill } = window.SN;
  const IN = ['in_stock', 'low_stock'];
  const WARN = '<svg viewBox="0 0 24 24"><path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z"/></svg>';
  const ROUTE = '<svg viewBox="0 0 24 24"><path d="M13.5 5.5c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zM9.8 8.9 7 23h2.1l1.8-8 2.1 2v6h2v-7.5l-2.1-2 .6-3C14.8 12 16.8 13 19 13v-2c-1.9 0-3.5-1-4.3-2.4l-1-1.6c-.4-.6-1-1-1.7-1-.3 0-.5.1-.8.1L6 8.3V13h2V9.6l1.8-.7"/></svg>';
  let busy = false;
  let started = false;
  const recs = [];

  const $ = (id) => document.getElementById(id);
  function sessionId() {
    const S = window.SNC.state;
    const k = 'sn_chat_' + (S.customer ? S.customer.customer_id : '') + '_' + S.storeId;
    let v = sessionStorage.getItem(k);
    if (!v) { v = 'sn-' + Math.random().toString(36).slice(2) + Date.now().toString(36); sessionStorage.setItem(k, v); }
    return v;
  }
  function md(s) {
    return esc(s).replace(/^\s*[-*_]{3,}\s*$/gm, '').replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1$2').replace(/\n{3,}/g, '\n\n').replace(/^\*+|\*+$/g, '');
  }
  function scroll() { const log = $('chat-log'); log.scrollTop = log.scrollHeight; }
  function add(el) { $('chat-log').appendChild(el); scroll(); return el; }
  function bubble(cls, html) { const d = document.createElement('div'); d.className = 'msg ' + cls; d.innerHTML = html; return add(d); }

  function welcome() {
    const S = window.SNC.state;
    const s = window.SNC.storeById(S.storeId) || {};
    const name = S.customer ? S.customer.name + 'さん' : '';
    $('chat-log').innerHTML = '<div class="chat__welcome"><h3><span>' + esc(name) + '</span>、どうされましたか？</h3>' +
      '<p>' + esc(s.short_name || '') + 'の在庫と売場から、症状やお悩みに合う商品の候補をご案内します。</p></div>';
    chips(['昨日から熱があって、かぜっぽいです', '子どもが38度の熱', '目が疲れる', '膝が痛い', '経口補水液はどこ？']);
    started = true;
  }
  function chips(items) {
    const box = $('chat-chips');
    box.innerHTML = (items || []).map((t) => '<button type="button" class="sn-chip" data-chip="' + esc(t) + '">' + esc(t) + '</button>').join('');
    box.querySelectorAll('[data-chip]').forEach((b) => b.addEventListener('click', () => {
      const t = b.dataset.chip;
      if (t === 'まとめて棚を探す' && recs.length) { findAll(recs[recs.length - 1]); return; }
      send(t);
    }));
  }

  function whereHTML(it) {
    const av = it.availability || {};
    const c = av.current || {};
    if (IN.indexOf(c.status) >= 0) {
      return statusPill(c.status, c.quantity) + '<span>' + esc(window.Search.shelfText(c.shelf)) + '</span>';
    }
    const near = (av.nearby || []).find((n) => IN.indexOf(n.status) >= 0);
    let h = statusPill(c.status === 'not_carried' ? 'not_carried' : 'out_of_stock') + '<span>この店舗</span>';
    if (near) h += '<span>→ ' + esc(near.short_name) + '（約' + esc(km(near.distance_m)) + '）に在庫</span>';
    if ((av.online || {}).available) h += '<a href="' + esc(av.online.url) + '" target="_blank" rel="noopener">オンラインで購入</a>';
    return h;
  }

  function recCard(args) {
    recs.push(args);
    const items = args.items || [];
    const inStore = items.filter((it) => it.in_store);
    const el = document.createElement('article');
    el.className = 'rec';
    el.innerHTML = '<div class="rec__head"><div class="rec__theme">' + esc(args.theme || 'おすすめの商品') + '</div>' +
      '<div class="rec__store">' + esc(args.store_name || '') + (args.customer_name ? ' ・ ' + esc(args.customer_name) + 'さん向け' : '') + '</div>' +
      (args.advice ? '<div class="rec__advice">' + md(args.advice) + '</div>' : '') + '</div>' +
      (args.red_flag ? '<div class="rec__flag">' + WARN + '<span>医療機関の受診をおすすめします。医薬品は表示していません（受診までの補助用品のみ）。急な病気やけがで迷ったら救急安心センター #7119、緊急時は 119番へ。</span></div>' : '') +
      '<ol class="rec__items">' + items.map((it) => {
        const p = it.product || {};
        const notes = (it.notes || []).filter((n) => n.length > 8);
        return '<li class="rec-item"><span class="rec-item__no' + (it.no ? '' : ' is-off') + '">' + (it.no || '他店') + '</span>' + img(p.image, p.title) +
          '<div><div class="rec-item__role">' + esc(it.role || '') + '</div><div class="rec-item__title">' + esc(p.title || '') + '</div>' +
          '<div class="rec-item__meta"><b>' + yen(p.price) + '</b>' + drugBadges(p) + '<span class="rec-item__cart">' + window.SN.cartBtn(p.id, window.Cart.has(p.id)) + '</span></div>' +
          (it.reason ? '<div class="rec-item__reason">' + esc(it.reason) + '</div>' : '') +
          '<div class="rec-item__where">' + whereHTML(it) + '</div>' +
          (notes.length ? '<div class="rec-item__notes">' + notes.map((n) => '<div class="sn-notice' + (/第1類|濫用/.test(n) ? ' sn-notice--warn' : '') + '">' + ICON_INFO + '<span>' + esc(n) + '</span></div>').join('') + '</div>' : '') +
          '</div></li>';
      }).join('') + '</ol>' +
      (args.route && args.route.length_m ? '<div class="rec__route">' + ROUTE + '入口から番号順に回ってレジまで 約' + Math.round(args.route.length_m) + 'm</div>' : '') +
      (items.length ? '<div class="rec__actions"><button type="button" class="sn-btn sn-btn--primary" data-act="find"' + (inStore.length ? '' : ' disabled') + '>まとめて棚を探す</button>' +
        '<button type="button" class="sn-btn sn-btn--tonal" data-act="buy">まとめて購入</button></div>' : '');
    el.querySelectorAll('[data-cart]').forEach((btn) => btn.addEventListener('click', () => {
      const it = items.find((x) => x.product && x.product.id === btn.dataset.cart);
      if (it) window.SN.setCartBtn(btn, window.Cart.toggle({ product: it.product, availability: it.availability, role: it.role }));
    }));
    el.querySelector('[data-act=find]') && el.querySelector('[data-act=find]').addEventListener('click', () => findAll(args));
    el.querySelector('[data-act=buy]') && el.querySelector('[data-act=buy]').addEventListener('click', () => {
      window.Cart.open(items.map((it) => ({ product: it.product, availability: it.availability, role: it.role })), 'store');
    });
    add(el);
  }
  function findAll(args) {
    const items = (args.items || []).filter((it) => it.in_store);
    if (!items.length) { window.SN.toast('この店舗に在庫のある商品がありません'); return; }
    close();
    window.FloorMap.open({ storeId: args.store_id || window.SNC.state.storeId, items, route: args.route });
  }
  function disclaimer() {
    const d = document.createElement('div');
    d.className = 'disclaimer';
    d.textContent = DISCLAIMER;
    add(d);
  }

  async function send(text) {
    text = (text || '').trim();
    if (!text || busy) return;
    busy = true;
    $('chat-send').disabled = true;
    $('chat-chips').innerHTML = '';
    if (!started) welcome();
    const w = $('chat-log').querySelector('.chat__welcome');
    if (w) w.remove();
    bubble('msg--user', esc(text));
    const typing = bubble('msg--bot is-typing', '<span class="dots"><i></i><i></i><i></i></span><span class="lbl">考えています…</span>');
    let cur = null, buf = '', health = false, gotChips = false;
    const S = window.SNC.state;
    try {
      const resp = await fetch(CFG.agentEndpoint || '/api/agent/stream', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
        body: JSON.stringify({ session_id: sessionId(), message: text, store_id: S.storeId,
          page_state: { page_context: { view: S.view, query: (location.hash.match(/q=([^&]+)/) || [])[1] ? decodeURIComponent(location.hash.match(/q=([^&]+)/)[1]) : '' } } }),
      });
      if (!resp.ok || !resp.body) throw new Error('HTTP ' + resp.status);
      const reader = resp.body.getReader();
      const dec = new TextDecoder();
      let pending = '';
      const handle = (ev) => {
        if (ev.type === 'status') { const l = typing.querySelector('.lbl'); if (l) l.textContent = ev.text; }
        else if (ev.type === 'text') {
          if (!cur) { typing.remove(); cur = bubble('msg--bot', ''); }
          buf += ev.text;
          cur.innerHTML = md(buf);
          if (/受診|薬剤師|医薬品|#7119|119/.test(ev.text)) health = true;
          scroll();
        } else if (ev.type === 'action' && ev.name === 'show_store_items') {
          if (ev.result && ev.result.ok === false) return;
          typing.remove();
          recCard(ev.args || {});
          health = true;
          cur = null; buf = '';
        } else if (ev.type === 'chips') { chips(ev.items || []); gotChips = true; }
        else if (ev.type === 'error') { typing.remove(); bubble('msg--bot msg--error', esc(ev.message || 'エラーが発生しました')); }
        else if (ev.type === 'done') { if ((ev.red_flags || []).length) health = true; }
      };
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        pending += dec.decode(value, { stream: true });
        let i;
        while ((i = pending.indexOf('\n\n')) >= 0) {
          const chunk = pending.slice(0, i); pending = pending.slice(i + 2);
          chunk.split('\n').forEach((line) => {
            if (!line.startsWith('data:')) return;
            try { handle(JSON.parse(line.slice(5).trim())); } catch (e) { /* ignore */ }
          });
        }
      }
      typing.remove();
      if (health) disclaimer();
      if (!gotChips) chips(['熱っぽい', '目が疲れる']);
    } catch (e) {
      typing.remove();
      bubble('msg--bot msg--error', '申し訳ございません、接続できませんでした。もう一度お試しください。');
    } finally {
      busy = false;
      $('chat-send').disabled = false;
      scroll();
    }
  }

  function open(prefill) {
    window.SNC.openSheet('chat');
    if (!started) welcome();
    $('chat-sub').textContent = 'Gemini ・ Agent Development Kit' + (CFG.agentMode === 'mock' ? '（デモモード）' : '');
    if (prefill) send(prefill);
    else setTimeout(() => $('chat-input').focus({ preventScroll: true }), 250);
  }
  function close() { window.SNC.closeSheets(); }
  function reset() { started = false; recs.length = 0; $('chat-log').innerHTML = ''; $('chat-chips').innerHTML = ''; }

  function init() {
    $('chat-close').addEventListener('click', close);
    $('chat-form').addEventListener('submit', (e) => { e.preventDefault(); const v = $('chat-input').value; $('chat-input').value = ''; send(v); });
    window.addEventListener('hashchange', () => { /* store switch → new conversation */
      const m = location.hash.match(/^#\/store\/([^/?]+)/);
      if (m && Chat._store && Chat._store !== m[1]) reset();
      if (m) Chat._store = m[1];
    });
  }

  const Chat = { init, open, close, send, reset, _store: null };
  window.Chat = Chat;
})();
