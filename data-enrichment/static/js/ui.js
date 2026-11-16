// Shared UI helpers (escaping, formatting, chips, toasts, stepper, evidence highlighting).
import { api, modelPref, isMock } from './api.js?v=20261111q';

export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

export const fmtInt = (n) => (n === null || n === undefined || isNaN(n) ? '—' : Math.round(Number(n)).toLocaleString('ja-JP'));
export const fmtPct = (r, d = 0) => (r === null || r === undefined || isNaN(r) ? '—' : (Number(r) * 100).toFixed(d) + '%');
export const fmtScore = (s) => (s === null || s === undefined || isNaN(s) ? '—' : Number(s).toFixed(2));
export function fmtJpy(v, digits) {
  if (v === null || v === undefined || isNaN(v)) return '—';
  const n = Number(v);
  if (digits !== undefined) return n.toLocaleString('ja-JP', { minimumFractionDigits: digits, maximumFractionDigits: digits }) + '円';
  if (n >= 10000) {
    const man = n / 10000;
    return (man >= 100 ? Math.round(man).toLocaleString('ja-JP') : man.toFixed(man >= 10 ? 1 : 2).replace(/\.?0+$/, '')) + '万円';
  }
  if (n >= 100) return Math.round(n).toLocaleString('ja-JP') + '円';
  return n.toLocaleString('ja-JP', { maximumFractionDigits: n < 1 ? 3 : 1 }) + '円';
}
export function fmtDate(s) {
  if (!s) return '—';
  const d = new Date(s);
  if (isNaN(d)) return esc(s);
  const p = (x) => String(x).padStart(2, '0');
  return `${d.getFullYear()}/${p(d.getMonth() + 1)}/${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
export function fmtValue(v, type) {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'boolean' || type === 'bool') return v === true || v === 'true' ? 'あり' : 'なし';
  if (typeof v === 'number') return Number.isInteger(v) ? v.toLocaleString('ja-JP') : v.toLocaleString('ja-JP', { maximumFractionDigits: 3 });
  return String(v);
}

export const STATUS = {
  auto_approved: { label: '自動承認', cls: 'ok', dot: '🟢' },
  approved: { label: '承認済(人手)', cls: 'ok', dot: '🟢' },
  edited: { label: '修正済', cls: 'info', dot: '🔵' },
  needs_review: { label: '要レビュー', cls: 'warn', dot: '🟡' },
  rejected: { label: '棄却(ルール)', cls: 'bad', dot: '🔴' },
  human_rejected: { label: '却下(人手)', cls: 'dark', dot: '⚫' },
  // product-level
  completed: { label: '完了', cls: 'ok' },
  not_processed: { label: '未処理', cls: 'mute' },
  missing: { label: '未抽出', cls: 'mute' },
};
export function chip(status, extra = '') {
  const s = STATUS[status] || { label: status || '—', cls: 'mute' };
  return `<span class="chip chip-${s.cls} ${extra}">${esc(s.label)}</span>`;
}
export const scoreCls = (s) => (s === null || s === undefined ? 'mute' : s >= 0.9 ? 'ok' : s >= 0.7 ? 'warn' : 'bad');
export function confBar(score, { showNum = true } = {}) {
  const w = Math.max(0, Math.min(1, Number(score) || 0)) * 100;
  return `<div class="conf"><div class="conf-track"><div class="conf-fill conf-${scoreCls(score)}" style="width:${w}%"></div></div>${showNum ? `<span class="conf-num">${fmtScore(score)}</span>` : ''}</div>`;
}
export function fillBars(before, after) {
  return `<div class="fillbars">
    <div class="fb-row"><span class="fb-lab">Before</span><div class="fb-track"><div class="fb-fill fb-before" style="width:${(before || 0) * 100}%"></div></div><span class="fb-num">${fmtPct(before)}</span></div>
    <div class="fb-row"><span class="fb-lab">After</span><div class="fb-track"><div class="fb-fill fb-after" style="width:${(after || 0) * 100}%"></div></div><span class="fb-num fb-num-after">${fmtPct(after)}</span></div>
  </div>`;
}
export const tip = (label, text) => (label === '?'
  ? `<span class="tip icon-only" tabindex="0" data-tip="${esc(text)}"><span class="tip-i">?</span></span>`
  : `<span class="tip" tabindex="0" data-tip="${esc(text)}">${esc(label)}<span class="tip-i">?</span></span>`);

export const skeleton = (n = 3, cls = '') => Array.from({ length: n }, () => `<div class="skel ${cls}"></div>`).join('');
export const emptyState = (icon, title, sub = '') => `<div class="empty"><div class="empty-icon">${icon}</div><div class="empty-title">${esc(title)}</div><div class="empty-sub">${esc(sub)}</div></div>`;
export const errorState = (err, retryId = '') => `<div class="empty err"><div class="empty-icon">⚠️</div><div class="empty-title">データを取得できませんでした</div><div class="empty-sub">${esc(err && err.message ? err.message : err)}</div>${retryId ? `<button class="btn btn-outline" id="${retryId}">再読み込み</button>` : ''}</div>`;

// ── Toast ────────────────────────────────────────────────────────────────
export function toast(msg, type = 'info', ms = 3200) {
  const box = document.getElementById('toasts');
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  const icon = { info: 'ℹ️', ok: '✅', warn: '⚠️', err: '⛔' }[type] || 'ℹ️';
  el.innerHTML = `<span class="toast-icon">${icon}</span><span>${esc(msg)}</span>`;
  box.appendChild(el);
  requestAnimationFrame(() => el.classList.add('show'));
  setTimeout(() => { el.classList.remove('show'); setTimeout(() => el.remove(), 300); }, ms);
}

// ── Modal ────────────────────────────────────────────────────────────────
export function openModal(title, bodyHtml, { okLabel = 'OK', cancelLabel = 'キャンセル', onOk } = {}) {
  const wrap = document.createElement('div');
  wrap.className = 'modal-back';
  wrap.innerHTML = `<div class="modal" role="dialog" aria-modal="true"><div class="modal-head"><h3>${esc(title)}</h3><button class="icon-btn modal-x" aria-label="閉じる">✕</button></div>
    <div class="modal-body">${bodyHtml}</div>
    <div class="modal-foot"><button class="btn btn-ghost modal-cancel">${esc(cancelLabel)}</button><button class="btn btn-primary modal-ok">${esc(okLabel)}</button></div></div>`;
  document.body.appendChild(wrap);
  requestAnimationFrame(() => wrap.classList.add('show'));
  const close = () => { wrap.classList.remove('show'); setTimeout(() => wrap.remove(), 200); document.removeEventListener('keydown', onKey); };
  const onKey = (e) => { if (e.key === 'Escape') close(); };
  document.addEventListener('keydown', onKey);
  wrap.addEventListener('click', (e) => { if (e.target === wrap) close(); });
  $('.modal-x', wrap).onclick = close;
  $('.modal-cancel', wrap).onclick = close;
  $('.modal-ok', wrap).onclick = async () => {
    const btn = $('.modal-ok', wrap);
    btn.disabled = true; btn.classList.add('loading');
    try { if (onOk) { const r = await onOk(wrap); if (r === false) { btn.disabled = false; btn.classList.remove('loading'); return; } } close(); } catch (e) {
      btn.disabled = false; btn.classList.remove('loading'); toast(e.message || String(e), 'err');
    }
  };
  return { el: wrap, close };
}

// ── Global app state ───────────────────────────────────────────────────────
export const state = { config: null, dashboard: null, reviewCount: null, products: null, models: [] };

export async function loadConfig() {
  try {
    state.config = await api.config();
  } catch (e) {
    state.config = { threshold: 0.9, model: '', groups: {}, weights: { evidence: 0.5, self: 0.3, token: 0.2 } };
  }
  if (!state.config.models && isMock) {
    try { const d = await api.models(); state.config.models = d.models; state.config.model = d.default; } catch (_) { /* ignore */ }
  }
  state.models = state.config.models || [];
  return state.config;
}

// ── LLM model selection (header picker + per-run override) ────────────────
const TIER_LABEL = { flash: 'Flash', 'flash-lite': 'Flash-Lite', pro: 'Pro', frontier: 'Gemini 4' };
export const modelInfo = (id) => (state.models || []).find((m) => m.id === id) || null;
export const modelLabel = (id) => { const m = modelInfo(id); return m ? m.label : String(id || '').replace(/^gemini-/i, 'Gemini ').replace(/-/g, ' '); };
export const availableModels = () => (state.models || []).filter((m) => m.status === 'available');
/** The model chosen in the header (falls back to the server default when the stored one is unavailable). */
export function selectedModel() {
  const pref = modelPref.get();
  const ok = availableModels();
  if (pref && ok.some((m) => m.id === pref)) return pref;
  return (state.config && state.config.model) || (ok[0] && ok[0].id) || 'gemini-3.8-flash';
}
/** Per-run override <select>: '' = follow the header. */
export function modelOverrideHtml(id, { compact = false, value = '' } = {}) {
  const cur = selectedModel();
  return `<label class="run-model${compact ? ' compact' : ''}" title="この実行だけ別のモデルを使う（既定はヘッダーで選択中のモデル）"><span class="rm-cap">モデル</span>
    <select class="select rm-sel" id="${esc(id)}" data-run-model>
      <option value="">ヘッダー: ${esc(modelLabel(cur))}</option>
      ${availableModels().map((m) => `<option value="${esc(m.id)}" ${m.id === value ? 'selected' : ''}>${esc(m.label)}</option>`).join('')}
    </select></label>`;
}
/** Effective model for a run: per-run override if chosen, otherwise the header selection. */
export function runModel(root, id) {
  const el = root && root.querySelector(`#${id}`);
  return (el && el.value) || selectedModel();
}
function refreshOverrides() {
  const cur = selectedModel();
  document.querySelectorAll('select[data-run-model]').forEach((sel) => { if (sel.options[0]) sel.options[0].textContent = `ヘッダー: ${modelLabel(cur)}`; });
}
const statusBadge = (m) => (m.status === 'available'
  ? (m.reason ? `<span class="mb mb-warn">${esc(m.reason)}</span>` : '<span class="mb mb-ok">利用可</span>')
  : m.status === 'probing' ? '<span class="mb mb-mute">確認中…</span>' : `<span class="mb mb-bad" title="${esc(m.reason || '')}">利用不可</span>`);

export function paintModelPicker() {
  const cur = selectedModel();
  const info = modelInfo(cur);
  const name = document.getElementById('model-name');
  if (name) { name.textContent = info ? info.label : cur; name.dataset.model = cur; }
  const btn = document.getElementById('model-btn');
  if (btn) btn.dataset.model = cur;
  const dot = document.getElementById('model-dot');
  if (dot) dot.className = 'mp-dot ' + (!info ? 'probing' : info.status === 'available' ? (info.reason ? 'busy' : 'ok') : info.status);
  const pop = document.getElementById('model-pop');
  if (!pop) return;
  const list = state.models || [];
  const probing = list.some((m) => m.status === 'probing');
  pop.innerHTML = `<div class="mp-head"><b>LLM モデルを選択</b><span class="muted small">Gemini 3.x 以降・このプロジェクトで疎通確認${probing ? '中…' : '済み'}</span></div>
    ${list.filter((m) => m.status !== 'unavailable').map((m) => `<button type="button" role="option" class="mp-opt${m.id === cur ? ' on' : ''}" data-model="${esc(m.id)}" aria-selected="${m.id === cur}" ${m.status !== 'available' ? 'disabled' : ''}>
        <span class="mp-check">${m.id === cur ? '✓' : ''}</span>
        <span class="mp-o-main"><span class="mp-o-label">${esc(m.label)}${m.default ? '<span class="mb mb-blue">既定</span>' : ''}</span><span class="mp-o-id mono">${esc(m.id)}</span></span>
        <span class="mp-o-badges">${statusBadge(m)}${m.batch ? '<span class="mb mb-info" title="Vertex AI Batch Prediction に対応">Batch</span>' : ''}<span class="mb mb-tier">${esc(TIER_LABEL[m.tier] || m.tier || '')}</span></span>
      </button>`).join('')}
    ${list.some((m) => m.status === 'unavailable') ? `<div class="mp-foot muted small">利用不可（一覧から除外）: ${list.filter((m) => m.status === 'unavailable').map((m) => esc(m.id)).join(', ')}</div>` : ''}
    <div class="mp-foot muted small">選択はこのブラウザに保存され、すべての実行に使われます。各画面の「モデル」で 1 回だけ変更することもできます。</div>`;
}

let pollT = null;
export function initModelPicker() {
  const btn = document.getElementById('model-btn');
  const pop = document.getElementById('model-pop');
  if (!btn || !pop) return;
  const close = () => { pop.hidden = true; btn.setAttribute('aria-expanded', 'false'); };
  btn.addEventListener('click', (e) => { e.stopPropagation(); pop.hidden = !pop.hidden; btn.setAttribute('aria-expanded', String(!pop.hidden)); if (!pop.hidden) paintModelPicker(); });
  document.addEventListener('click', (e) => { if (!pop.hidden && !pop.contains(e.target)) close(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });
  pop.addEventListener('click', (e) => {
    const o = e.target.closest('.mp-opt');
    if (!o || o.disabled) return;
    const id = o.dataset.model;
    const prev = selectedModel();
    modelPref.set(id);
    close();
    if (id !== prev) toast(`モデルを ${modelLabel(id)} に切り替えました`, 'ok');
  });
  window.addEventListener('enrich:model', () => { paintModelPicker(); refreshOverrides(); });
  paintModelPicker();
  // the server probes models at startup; poll until every candidate has a result
  const poll = async () => {
    if (!(state.models || []).some((m) => m.status === 'probing')) return;
    try { const d = await api.models(); state.models = d.models; if (state.config) state.config.models = d.models; paintModelPicker(); refreshOverrides(); } catch (_) { /* ignore */ }
    pollT = setTimeout(poll, 2500);
  };
  clearTimeout(pollT);
  pollT = setTimeout(poll, 1500);
}
export async function productList() {
  if (!state.products) {
    const d = await api.products({});
    state.products = d.items || [];
  }
  return state.products;
}

export function setReviewBadge(n) {
  state.reviewCount = n;
  const b = document.getElementById('review-badge');
  if (!b) return;
  b.textContent = n > 999 ? '999+' : String(n ?? '');
  b.hidden = !n;
}

export async function refreshShell() {
  try {
    const d = await api.dashboard();
    state.dashboard = d;
    setReviewBadge(d.totals ? d.totals.needs_review : 0);
    if (!stepper.live) stepper.setGlobal(d.funnel);
    return d;
  } catch (e) {
    return null;
  }
}

// ── Pipeline stepper ─────────────────────────────────────────────────────
export const STEPS = [
  { key: 'source', label: '原本データ', tipText: 'ECの商品マスタ(タイトル・説明文・属性)をそのまま読み込みます' },
  { key: 'extract', label: 'Gemini抽出', tipText: 'Gemini が responseSchema(出力の型定義)に沿って属性と根拠テキストを JSON で抽出します' },
  { key: 'normalize', label: '単位正規化', tipText: '「約W70cm」「110kg」などの表記ゆれを mm / kg / L などの標準単位にそろえます' },
  { key: 'gate', label: 'ルール/確信度判定', tipText: '第1関門: 物理ルール検査、第2関門: AI スコア ≥ 0.90 で自動承認、それ以外は人手レビューへ' },
  { key: 'golden', label: 'ゴールデンレコード', tipText: '承認済みの正しい属性だけを集めた「信頼できる商品マスタ」' },
];
export const stepper = {
  live: false,
  el: () => document.getElementById('stepper'),
  render() {
    const el = this.el();
    el.innerHTML = `<div class="stepper-mode" id="stepper-mode">全体</div>` + STEPS.map((s, i) => `
      ${i ? '<div class="step-arrow" aria-hidden="true"></div>' : ''}
      <div class="step" data-step="${i}" title="${esc(s.tipText)}">
        <div class="step-num"><span class="n">${i + 1}</span><span class="check">✓</span></div>
        <div class="step-body"><div class="step-label">${esc(s.label)}</div><div class="step-count" id="step-count-${i}">—</div></div>
      </div>`).join('');
  },
  setCount(i, html) { const c = document.getElementById(`step-count-${i}`); if (c) c.innerHTML = html; },
  setState(i, st) {
    const s = this.el().querySelector(`.step[data-step="${i}"]`);
    if (!s) return;
    s.classList.remove('running', 'done', 'error');
    if (st) s.classList.add(st);
  },
  setMode(html, live) {
    const m = document.getElementById('stepper-mode');
    if (m) { m.innerHTML = html; m.classList.toggle('live', !!live); }
  },
  setGlobal(f) {
    if (!f) return;
    this.live = false;
    this.setMode('全体', false);
    STEPS.forEach((_, i) => this.setState(i, null));
    this.setCount(0, `<b>${fmtInt(f.source_skus)}</b> SKU`);
    this.setCount(1, `<b>${fmtInt(f.extracted)}</b> 属性`);
    this.setCount(2, `<b>${fmtInt(f.normalized)}</b> OK`);
    this.setCount(3, `<span class="sc-ok">自動 <b>${fmtInt(f.auto_approved)}</b></span> <span class="sc-warn">要確認 <b>${fmtInt(f.needs_review)}</b></span>`);
    this.setCount(4, `<b>${fmtInt(f.golden_skus)}</b> SKU`);
  },
  startLive(sku) {
    this.live = true;
    this.setMode(`<span class="live-dot"></span>LIVE`, true);
    const m = document.getElementById('stepper-mode'); if (m) m.title = `ライブ実行中: SKU ${sku}`;
    STEPS.forEach((_, i) => { this.setState(i, null); this.setCount(i, '待機中'); });
  },
  endLive(keepMs = 0) {
    const restore = () => { this.live = false; if (state.dashboard) this.setGlobal(state.dashboard.funnel); };
    if (keepMs) setTimeout(() => { if (this.live === 'ended') restore(); }, keepMs);
    else restore();
    if (keepMs) this.live = 'ended';
  },
};

// ── Evidence matching / highlighting ──────────────────────────────────────
// Build a normalized (NFKC, lowercase, whitespace-stripped) view of `text` with index map.
function normMap(text) {
  const chars = [];
  const map = [];
  for (let i = 0; i < text.length; i++) {
    const n = text[i].normalize('NFKC').toLowerCase();
    for (const c of n) {
      if (/\s/.test(c)) continue;
      chars.push(c);
      map.push(i);
    }
  }
  return { s: chars.join(''), map };
}
const normStr = (s) => normMap(s).s;

/** Returns [start, end) in `text` for `evidence`, or null. mode: 'exact' | 'fuzzy'. */
export function findEvidence(text, evidence) {
  if (!text || !evidence) return null;
  const ev = String(evidence).trim();
  if (!ev) return null;
  let i = text.indexOf(ev);
  if (i >= 0) return { start: i, end: i + ev.length, mode: 'exact' };
  const T = normMap(text);
  const E = normStr(ev);
  if (!E) return null;
  i = T.s.indexOf(E);
  if (i >= 0) return { start: T.map[i], end: T.map[i + E.length - 1] + 1, mode: 'fuzzy' };
  return null;
}
/** Render text with an optional highlight range (escaped). */
export function markText(text, range, cls = 'ev-mark') {
  if (!range) return esc(text);
  return esc(text.slice(0, range.start)) + `<mark class="${cls}">` + esc(text.slice(range.start, range.end)) + '</mark>' + esc(text.slice(range.end));
}

// ── Icons ───────────────────────────────────────────────────────────────
export const ICON = {
  csv: '<svg viewBox="0 0 24 24"><path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm4 18H6V4h7v5h5v11zM8 15.01l1.41 1.41L11 14.84V19h2v-4.16l1.59 1.59L16 15.01 12.01 11 8 15.01z"/></svg>',
  gmc: '<svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.17L4 17.17V4h16v12z"/><path d="M12 5.5l1.1 2.4 2.4 1.1-2.4 1.1L12 12.5l-1.1-2.4L8.5 9l2.4-1.1z"/><path d="M16.5 11l.6 1.4 1.4.6-1.4.6-.6 1.4-.6-1.4-1.4-.6 1.4-.6z"/></svg>',
  dash: '<svg viewBox="0 0 24 24"><path d="M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z"/></svg>',
  list: '<svg viewBox="0 0 24 24"><path d="M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z"/></svg>',
  studio: '<svg viewBox="0 0 24 24"><path d="M19 9l1.25-2.75L23 5l-2.75-1.25L19 1l-1.25 2.75L15 5l2.75 1.25L19 9zm-7.5.5L9 4 6.5 9.5 1 12l5.5 2.5L9 20l2.5-5.5L17 12l-5.5-2.5zM19 15l-1.25 2.75L15 19l2.75 1.25L19 23l1.25-2.75L23 19l-2.75-1.25L19 15z"/></svg>',
  review: '<svg viewBox="0 0 24 24"><path d="M9 16.2L4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4L9 16.2z"/></svg>',
  batch: '<svg viewBox="0 0 24 24"><path d="M11.8 10.9c-2.27-.59-3-1.2-3-2.15 0-1.09 1.01-1.85 2.7-1.85 1.78 0 2.44.85 2.5 2.1h2.21c-.07-1.72-1.12-3.3-3.21-3.81V3h-3v2.16c-1.94.42-3.5 1.68-3.5 3.61 0 2.31 1.91 3.46 4.7 4.13 2.5.6 3 1.48 3 2.41 0 .69-.49 1.79-2.7 1.79-2.06 0-2.87-.92-2.98-2.1h-2.2c.12 2.19 1.76 3.42 3.68 3.83V21h3v-2.15c1.95-.37 3.5-1.5 3.5-3.55 0-2.84-2.43-3.81-4.7-4.4z"/></svg>',
  images: '<svg viewBox="0 0 24 24"><path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V5h14v14z"/><path d="M14.14 11.86l-3 3.87L9 13.14 6 17h12l-3.86-5.14z"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M17 4.6l.6 1.3 1.3.6-1.3.6-.6 1.3-.6-1.3-1.3-.6 1.3-.6z"/></svg>',
  docs: '<svg viewBox="0 0 24 24"><path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h5.5a6.5 6.5 0 0 1-1.3-2H6V4h7v5h5v1.3a6.4 6.4 0 0 1 2 .9V8l-6-6z"/><path d="M16.5 11a4.5 4.5 0 1 0 2.5 8.24l2.3 2.3 1.4-1.42-2.3-2.3A4.5 4.5 0 0 0 16.5 11zm0 7a2.5 2.5 0 1 1 0-5 2.5 2.5 0 0 1 0 5z"/></svg>',
};
