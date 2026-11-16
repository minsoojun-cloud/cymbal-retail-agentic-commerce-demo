/* Checkout state machine: idle → delivery (slot select) → payment (Cymbal Pay) → confirm → placed.
 * UI buttons and agent actions (start_checkout / select_delivery_slot / place_order) call the
 * same methods, so chat and clicks always stay in sync. */
(function () {
  'use strict';
  const { yen, esc, toast, PLACEHOLDER_IMG } = window.CR;
  const PAYMENT = 'Cymbal Pay（VISA **** 4242）';
  const KEY = 'cr_checkout_v1';
  const STEPS = [
    { id: 'delivery', label: 'お届け日時' },
    { id: 'payment', label: 'お支払い' },
    { id: 'confirm', label: 'ご注文内容の確認' },
    { id: 'placed', label: '注文完了' },
  ];
  const WD = ['日', '月', '火', '水', '木', '金', '土'];

  function slotDefs() {
    const base = new Date();
    const day = (n) => { const d = new Date(base); d.setDate(d.getDate() + n); return d; };
    const dl = (d) => (d.getMonth() + 1) + '月' + d.getDate() + '日(' + WD[d.getDay()] + ')';
    const d1 = day(1), d2 = day(2);
    const mk = (id, rel, d, time) => ({ slot_id: id, label: rel + ' ' + time, day: rel, time, date_label: dl(d), date: d.toISOString().slice(0, 10) });
    return [
      mk('d1_am', '明日', d1, '9:00-12:00'),
      mk('d1_pm', '明日', d1, '14:00-17:00'),
      mk('d1_eve', '明日', d1, '18:00-21:00'),
      mk('d2_am', '明後日', d2, '9:00-12:00'),
      mk('d2_pm', '明後日', d2, '14:00-17:00'),
    ];
  }

  const saved = (() => { try { return JSON.parse(sessionStorage.getItem(KEY) || '{}'); } catch (e) { return {}; } })();

  const Checkout = {
    PAYMENT,
    state: saved.state || 'idle',
    slot: saved.slot_id ? slotDefs().find((s) => s.slot_id === saved.slot_id) || null : null,
    lastOrderId: saved.lastOrderId || '',
    slots: slotDefs,
    persist() { try { sessionStorage.setItem(KEY, JSON.stringify({ state: this.state, slot_id: this.slot && this.slot.slot_id, lastOrderId: this.lastOrderId })); } catch (e) { /* ignore */ } },
    go(state, opts) {
      this.state = state;
      this.persist();
      window.CR.emit('checkout', { state });
      if (state === 'placed') { window.Orders.track(this.lastOrderId); return; }
      if (state === 'idle') return;
      if (!(opts && opts.noNav)) window.Router.go({ view: 'checkout' }, { replace: window.Router.current().view === 'checkout' });
      else this.render();
    },
    totals() {
      const sub = window.Cart.subtotal();
      const ship = window.Cart.shippingFor(sub);
      return { subtotal: sub, shipping: ship, total: sub + ship };
    },
    /** レジに進む / start_checkout */
    open() {
      if (!window.Cart.count()) return { ok: false, error: 'EMPTY_CART' };
      if (this.state === 'placed' || this.state === 'idle') this.slot = null;
      this.go('delivery');
      return { ok: true, slots: slotDefs().map((s) => ({ slot_id: s.slot_id, label: s.label })), cart_total_tax_included: window.Cart.subtotal() };
    },
    /** 配送スロット選択 / select_delivery_slot */
    selectSlot(id) {
      const s = slotDefs().find((x) => x.slot_id === id);
      if (!s) return { ok: false, error: 'INVALID_SLOT', slots: slotDefs().map((x) => x.slot_id) };
      if (!window.Cart.count()) return { ok: false, error: 'EMPTY_CART' };
      this.slot = s;
      this.go('payment');
      return { ok: true, slot_label: s.label };
    },
    /** 支払い方法確認 (Cymbal Pay fixed) */
    confirmPayment() {
      if (!this.slot) return { ok: false, error: 'NO_SLOT' };
      this.go('confirm');
      return { ok: true, payment_method: PAYMENT };
    },
    /** 注文を確定する / place_order — CONTRACT v3: use the agent-generated order id (args.order_id) when given */
    placeOrder(orderId) {
      orderId = typeof orderId === 'string' && /^CR-\d{8}-\d{4}$/.test(orderId) ? orderId : '';
      const dup = orderId && window.Orders.get(orderId);
      if (dup) return { ok: true, order_id: dup.id, total_tax_included: dup.total, slot_label: dup.slot ? dup.slot.label : '', duplicate: true };
      if (!window.Cart.count()) return { ok: false, error: 'EMPTY_CART' };
      if (!this.slot) return { ok: false, error: 'NO_SLOT', message: '先にお届け日時を選択してください' };
      const t = this.totals();
      const order = {
        id: orderId || window.Orders.newOrderId(),
        lines: window.Cart.lines(),
        subtotal: t.subtotal, shipping: t.shipping, total: t.total,
        slot: this.slot, payment: PAYMENT,
        placedAt: Date.now(), speedSec: Number((window.CR_CONFIG || {}).deliverySpeedSec) || 8,
        status: 'placed', customer_id: window.CR.getCustomer().customer_id,
      };
      window.Orders.save(order);
      this.lastOrderId = order.id;
      this.state = 'placed';
      window.Cart.clear();
      const slotLabel = this.slot.label;
      this.slot = null;
      this.go('placed');
      toast('ご注文を確定しました（' + order.id + '）', { success: true });
      return { ok: true, order_id: order.id, total_tax_included: order.total, slot_label: slotLabel };
    },
    cancel() { this.state = 'idle'; this.slot = null; this.persist(); window.Router.go({ view: 'home' }); },

    // ---------- view ----------
    render() {
      const v = window.CR.view();
      if (!window.Cart.count() && this.state !== 'placed') {
        v.innerHTML = '<div class="cr-container"><div class="cr-empty"><h2>カートに商品はありません</h2><p>商品をカートに追加してからレジにお進みください。</p><button class="cr-btn cr-btn--primary" data-nav="home">お買い物を続ける</button></div></div>';
        return;
      }
      if (this.state === 'idle' || this.state === 'placed') { this.state = 'delivery'; this.persist(); }
      const idx = STEPS.findIndex((s) => s.id === this.state);
      const t = this.totals();
      const lines = window.Cart.lines();
      const stepper = '<ol class="cr-steps" id="cr-steps">' + STEPS.map((s, i) =>
        '<li class="' + (i < idx ? 'is-done' : i === idx ? 'is-active' : '') + '" data-step="' + s.id + '"><b>' + (i < idx ? '✓' : i + 1) + '</b>' + s.label + '</li>').join('') + '</ol>';

      const slotPanel = '<section class="cr-panel" id="cr-step-delivery"><h2>お届け日時を選択</h2><p class="cr-panel__sub">ご都合のよい時間帯をお選びください。' + (t.shipping ? '¥3,000以上で送料無料。' : '送料無料でお届けします。') + '</p>' +
        '<div class="cr-slots">' + slotDefs().map((s) =>
          '<button type="button" class="cr-slot' + (this.slot && this.slot.slot_id === s.slot_id ? ' is-selected' : '') + '" data-slot="' + s.slot_id + '" id="slot-' + s.slot_id + '">' +
            '<span class="cr-slot__day">' + s.day + ' ・ ' + s.date_label + '</span><span class="cr-slot__time">' + s.time + '</span>' +
            '<span class="cr-slot__fee">' + (t.shipping ? '送料 ' + yen(t.shipping) : '送料無料') + '</span></button>').join('') +
        '</div></section>';
      const slotDone = this.slot ? '<section class="cr-panel"><h2>お届け日時 <button type="button" class="cr-link-btn" data-step-go="delivery">変更</button></h2><p class="cr-panel__sub" style="margin:0">' + esc(this.slot.date_label + ' ' + this.slot.time) + '（' + esc(this.slot.label) + '）</p></section>' : '';
      const payPanel = '<section class="cr-panel" id="cr-step-payment"><h2>お支払い方法</h2><p class="cr-panel__sub">登録済みのお支払い方法を使用します。</p>' +
        '<div class="cr-pay"><span class="cr-pay__card">VISA</span><div><b>' + PAYMENT + '</b><span>有効期限 12/29 ・ Cymbalポイントが貯まります</span></div></div>' +
        '<div class="cr-co__actions"><button type="button" class="cr-btn" data-step-go="delivery">戻る</button><button type="button" class="cr-btn cr-btn--primary" id="cr-pay-next">確認画面へ進む</button></div></section>';
      const confirmPanel = '<section class="cr-panel" id="cr-step-confirm"><h2>ご注文内容の確認</h2><p class="cr-panel__sub">内容をご確認のうえ「注文を確定する」を押してください。</p>' +
        '<dl class="cr-confirm-list">' +
          '<div><dt>お届け日時</dt><dd>' + esc(this.slot ? this.slot.date_label + ' ' + this.slot.time : '-') + '</dd><button type="button" class="cr-link-btn" data-step-go="delivery">変更</button></div>' +
          '<div><dt>お支払い方法</dt><dd>' + PAYMENT + '</dd><span></span></div>' +
          '<div><dt>お届け先</dt><dd>' + esc(window.CR.getCustomer().name) + ' 様（ご登録住所）</dd><span></span></div>' +
          '<div><dt>合計（税込）</dt><dd><strong style="font:700 20px var(--cr-font)">' + yen(t.total) + '</strong></dd><span></span></div>' +
        '</dl>' +
        '<div class="cr-co__actions"><button type="button" class="cr-btn" data-step-go="payment">戻る</button><button type="button" class="cr-btn cr-btn--primary" id="cr-place-order" style="min-width:220px;height:48px;border-radius:24px;font-size:15px">注文を確定する</button></div>' +
        '<div class="cr-agent-note">✨ AIコンシェルジュに「注文を確定して」と伝えても注文できます</div></section>';

      let main = '';
      if (this.state === 'delivery') main = slotPanel;
      else if (this.state === 'payment') main = slotDone + payPanel;
      else main = confirmPanel;

      v.innerHTML = '<div class="cr-container"><div class="cr-co" id="cr-checkout" data-state="' + this.state + '">' +
        '<div><h1>レジ</h1>' + stepper + main + '</div>' +
        '<aside class="cr-summary" id="cr-co-summary"><h2>注文の概要（' + window.Cart.count() + '点）</h2>' +
          '<ul class="cr-summary__lines">' + lines.map((l) => '<li><img src="' + esc(l.image || PLACEHOLDER_IMG) + '" alt=""><span class="t">' + esc(l.title) + ' × ' + l.qty + '</span><span>' + yen(l.price * l.qty) + '</span></li>').join('') + '</ul>' +
          '<div class="cr-summary__row"><span>小計</span><span>' + yen(t.subtotal) + '</span></div>' +
          '<div class="cr-summary__row"><span>送料</span><span id="cr-co-shipping">' + (t.shipping ? yen(t.shipping) : '無料') + '</span></div>' +
          '<div class="cr-summary__row total"><span>合計（税込）</span><strong id="cr-co-total">' + yen(t.total) + '</strong></div>' +
        '</aside></div></div>';
    },
  };
  window.Checkout = Checkout;

  document.addEventListener('click', (e) => {
    const s = e.target.closest('[data-slot]');
    if (s) { Checkout.selectSlot(s.dataset.slot); return; }
    if (e.target.closest('#cr-pay-next')) { Checkout.confirmPayment(); return; }
    if (e.target.closest('#cr-place-order')) { Checkout.placeOrder(); return; }
    const g = e.target.closest('[data-step-go]');
    if (g) { Checkout.go(g.dataset.stepGo); }
  });
  window.CR.on('cart', () => { if (window.Router && window.Router.current().view === 'checkout' && Checkout.state !== 'placed') Checkout.render(); });
})();
