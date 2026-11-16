// ⑤ バッチ & コスト — Vertex AI Batch ジョブ + モデル別「定価（標準オンライン）」コスト試算
import { api, goldenCsvUrl, isMock, PRICING_URL } from '../api.js?v=20261111q';
import {
  esc, $, $$, fmtInt, fmtPct, fmtJpy, fmtDate, fmtValue, skeleton, emptyState, errorState, toast, openModal, state, tip,
  refreshShell, selectedModel, modelLabel, modelInfo,
} from '../ui.js?v=20261111q';

const JOB_STATE = {
  JOB_STATE_SUCCEEDED: ['SUCCEEDED', 'ok', '完了'],
  JOB_STATE_RUNNING: ['RUNNING', 'run', '実行中'],
  JOB_STATE_PENDING: ['PENDING', 'pend', '待機中'],
  JOB_STATE_QUEUED: ['QUEUED', 'pend', '待機中'],
  JOB_STATE_FAILED: ['FAILED', 'bad', '失敗'],
  JOB_STATE_CANCELLED: ['CANCELLED', 'mute', '取消'],
  JOB_STATE_EXPIRED: ['EXPIRED', 'mute', '期限切れ'],
};
const MIN = 100, MAX = 1000000;
const toSkus = (pos) => { const v = Math.pow(10, Math.log10(MIN) + (Math.log10(MAX) - Math.log10(MIN)) * pos / 1000); return roundNice(v); };
const toPos = (n) => Math.max(0, Math.min(1000, Math.round((Math.log10(Math.max(n, 1)) - Math.log10(MIN)) / (Math.log10(MAX) - Math.log10(MIN)) * 1000)));
function roundNice(v) { const p = Math.pow(10, Math.max(0, Math.floor(Math.log10(v)) - 1)); return Math.round(v / p) * p; }
const FX_KEY = 'cymbal.enrich.usdjpy';
const BASIS_KEY = 'cymbal.enrich.pricebasis.v2';   // 'list' (default) | 'promo' (reference only)
let simSkus = 8807;
const autoTried = new Set();         // models auto-measured in this session (auto on first view)
const measuring = {};                // model -> { stages: {stage1,stage3,gmc}, sku, title, error }
const STAGE_LABEL = { stage1: '属性', stage3: 'タグ', gmc: 'GMC' };

export function fmtUsd(v) {
  if (v === null || v === undefined || isNaN(v)) return '—';
  const n = Number(v);
  if (n === 0) return '$0';
  if (n < 0.01) return '$' + n.toPrecision(2);
  if (n < 100) return '$' + n.toFixed(2);
  return '$' + Math.round(n).toLocaleString('en-US');
}
const fxRate = () => { const v = parseFloat(localStorage.getItem(FX_KEY) || ''); return v > 0 ? v : ((state.config && state.config.usd_jpy) || 150); };
const basisPref = () => (localStorage.getItem(BASIS_KEY) === 'promo' ? 'promo' : 'list');
const priceUrl = () => (state.config && state.config.pricing_url) || PRICING_URL;

export async function render(root, _params, stale) {
  const retrieved = (state.config && state.config.price_retrieved_at) || '';
  root.innerHTML = `
    <div class="page-head"><div><h1>バッチ &amp; コスト</h1><p class="sub">Batch Prediction の状況と、モデル別の<b>定価（標準・オンライン）</b>コスト試算 — 実測トークン × Vertex AI 公式価格</p></div>
      <div class="head-actions"><button class="btn btn-outline" id="b-refresh">↻ 状態を更新</button><button class="btn btn-primary" id="b-new">＋ 新規バッチ投入</button></div></div>

    <div class="panel cost" id="cost-panel">
      <div class="panel-head cost-head">
        <h2>モデル別コスト試算（定価） ${tip('?', '各モデルで実際に処理した商品の平均トークン（属性・タグ・GMC の 3 呼び出し、思考トークン含む）× Vertex AI 公式の標準（オンライン）単価。Batch / Flex / Priority の価格や割引、キャッシュ割引、税は含みません')}</h2>
        <div class="cost-meta">
          <span class="chip chip-info" id="basis-chip">定価（プロモーション適用なし）・ Batch 割引なし</span>
          <a class="price-link hdr" href="${esc(priceUrl())}" target="_blank" rel="noopener" id="price-link-hdr">公式価格ページ ↗</a>
          <span class="muted small" id="price-date">価格取得日 <b>${esc(retrieved)}</b></span>
        </div>
      </div>
      <div class="cost-ctrl">
        <div class="cc-skus">
          <div class="cc-lab">試算する SKU 数</div>
          <div class="sim-skus"><input class="input sim-num" id="sim-num" type="text" inputmode="numeric" value="${fmtInt(simSkus)}" aria-label="SKU数"><span>SKU</span></div>
          <input type="range" min="0" max="1000" step="1" id="sim-range" value="${toPos(simSkus)}" aria-label="SKU数スライダー">
          <div class="sim-scale"><span>100</span><span>1,000</span><span>1万</span><span>10万</span><span>100万</span></div>
          <div class="sim-presets" id="sim-presets"></div>
        </div>
        <div class="cc-opts">
          <div class="cc-lab">為替レート ${tip('?', '公式価格は USD。円換算はこのレートで計算します（ブラウザに保存）')}</div>
          <label class="fx"><span>1 USD =</span><input class="input fx-in" id="fx-rate" type="number" min="1" max="1000" step="0.1" value="${fxRate()}"><span>円</span></label>
          <div class="cc-lab" style="margin-top:12px">価格の基準 ${tip('?', '既定は公式ページの標準（Standard）価格表の定価で、期間限定プロモーション（クレジットバック等の割引）は適用しません。「参考：期間限定プロモ価格」をオンにすると、本日時点で公式ページに記載のプロモ価格（割引）で再計算します')}</div>
          <div class="basis-row"><span class="basis-list" id="basis-list">定価（プロモーション適用なし）</span>
            <label class="chk promo-toggle" title="割引価格での参考試算（既定はオフ）"><input type="checkbox" id="promo-toggle"><span>参考：期間限定プロモ価格 <span class="mb mb-warn">割引</span></span></label></div>
        </div>
      </div>
      <div id="cost-hero" class="cost-hero">${skeleton(1, 'skel-row')}</div>
      <div id="cost-table">${skeleton(4, 'skel-row')}</div>
      <div id="cost-notes" class="cost-notes"></div>
    </div>

    <div class="grid-batch one">
      <div class="panel"><div class="panel-head"><h2>Batch ジョブ ${tip('?', 'Vertex AI Batch Prediction: 大量の商品をまとめて非同期で処理する方式。ヘッダーで選択中のモデルで投入します（対応モデルのみ）。コスト列は上の試算と同じ「定価（標準オンライン）」換算で、Batch 割引は反映していません')}</h2><span class="muted small" id="b-upd"></span></div>
        <div id="b-jobs">${skeleton(3, 'skel-row')}</div></div>
    </div>
    <div class="panel"><div class="panel-head"><h2>ゴールデンレコード ${tip('?', '承認済みの属性・タグ・検索キーワード・要約をまとめた、そのまま商品マスタや検索に使えるデータ')}</h2>
      <div class="head-actions">${goldenCsvUrl ? `<a class="btn btn-primary btn-sm" href="${goldenCsvUrl}" download>⬇ CSV エクスポート</a>` : '<button class="btn btn-primary btn-sm" disabled title="モックでは無効">⬇ CSV エクスポート</button>'}</div></div>
      <div id="golden">${skeleton(3, 'skel-row')}</div></div>`;

  let cost = null;            // last /api/cost/models response
  const listCost = (j) => {    // list-price cost (JPY) of a finished job from its tokens (output incl. thinking)
    const i = modelInfo(j.model);
    if (!i || i.price_in == null || !(j.input_tokens > 0)) return null;
    return ((j.input_tokens || 0) * i.price_in + (j.output_tokens || 0) * i.price_out) / 1e6 * fxRate();
  };

  // ── Jobs
  const paintJobs = (jobs) => {
    $('#b-upd', root).textContent = '最終更新 ' + fmtDate(new Date().toISOString());
    const box = $('#b-jobs', root);
    if (!jobs.length) { box.innerHTML = emptyState('🗂️', 'バッチジョブはまだありません', '「新規バッチ投入」から実行できます'); return; }
    box.innerHTML = `<table class="table"><thead><tr><th>ジョブ</th><th>モデル</th><th>状態</th><th class="r">SKU</th><th class="r">トークン(入/出)</th><th class="r">コスト（定価換算）</th><th>作成</th></tr></thead><tbody>
      ${jobs.map((j) => {
        const st = JOB_STATE[j.state] || [String(j.state || '').replace('JOB_STATE_', '') || '—', 'mute', ''];
        const c = listCost(j);
        return `<tr><td><div class="job-name">${esc(j.display_name || '—')}</div><div class="muted small mono" title="${esc(j.job_id)}">${esc(String(j.job_id || '').split('/').pop())}</div></td>
          <td class="mono small">${esc(j.model || '—')}</td>
          <td><span class="jstate js-${st[1]}">${st[1] === 'run' ? '<span class="spin"></span>' : ''}${esc(st[0])}</span><div class="muted small">${esc(st[2])}${j.ingested ? ' ・ 取込済' : ''}${j.error ? ` ・ <span class="dc-err" title="${esc(j.error)}">エラー</span>` : ''}</div></td>
          <td class="r"><b>${fmtInt(j.sku_count)}</b></td>
          <td class="r mono small">${fmtInt(j.input_tokens)} / ${fmtInt(j.output_tokens)}</td>
          <td class="r"><b>${c != null ? fmtJpy(c, 2) : '—'}</b>${c != null && j.sku_count ? `<div class="muted small">${fmtJpy(c / j.sku_count, 3)}/SKU</div>` : ''}</td>
          <td class="small">${fmtDate(j.created_at)}</td></tr>`;
      }).join('')}</tbody></table>`;
  };
  const loadJobs = async (refresh = false) => {
    const btn = $('#b-refresh', root);
    if (refresh) { btn.disabled = true; btn.classList.add('loading'); }
    try {
      const d = refresh ? await api.batchRefresh() : await api.batchJobs();
      if (stale()) return;
      paintJobs(d.jobs || []);
      if (refresh) { toast('ジョブ状態を更新しました', 'ok'); refreshShell(); loadGolden(); }
    } catch (e) {
      if (stale()) return;
      if (refresh) toast('更新に失敗しました: ' + e.message, 'err');
      else $('#b-jobs', root).innerHTML = errorState(e);
    } finally { if (btn) { btn.disabled = false; btn.classList.remove('loading'); } }
  };
  $('#b-refresh', root).onclick = () => loadJobs(true);
  $('#b-new', root).onclick = () => {
    const groups = (state.config && state.config.groups) || {};
    const model = selectedModel();
    const info = modelInfo(model) || {};
    const reason = info.batch ? '' : (info.batch_note || 'このモデルは Batch Prediction に対応していません');
    const m = openModal('新規バッチ投入', `
      <p class="muted">Vertex AI Batch Prediction にジョブを投入します。完了まで数分〜数十分かかります。</p>
      <div class="nb-model"><span class="muted small">使用モデル（ヘッダーで選択中）</span><b class="mono" id="nb-model">${esc(model)}</b>${info.batch ? '<span class="mb mb-info">Batch 対応</span>' : '<span class="mb mb-bad">Batch 非対応</span>'}</div>
      ${reason ? `<div class="banner warn nb-reason">⚠️ <div>${esc(modelLabel(model))}: ${esc(reason)}<br><span class="small">ヘッダーで Batch 対応モデルに切り替えるか、ライブ実行（エンリッチ・スタジオ / CSV）をご利用ください。</span></div></div>` : ''}
      <label class="field"><span>カテゴリ</span><select class="select" id="nb-group"><option value="">すべて</option>${Object.entries(groups).map(([k, v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join('')}</select></label>
      <label class="field"><span>件数上限 (SKU)</span><input class="input" id="nb-limit" type="number" min="1" max="100000" value="10"></label>
      <div class="field-note" id="nb-est"></div>`, {
      okLabel: '投入する',
      onOk: async (el) => {
        const limit = parseInt($('#nb-limit', el).value, 10);
        if (!(limit > 0)) { toast('件数を正しく入力してください', 'warn'); return false; }
        const group = $('#nb-group', el).value || null;
        const res = await api.batchSubmit({ group, limit }, model);
        toast(`バッチを投入しました: ${res.job ? res.job.display_name : ''}（${model}）`, 'ok');
        loadJobs(false);
        return true;
      },
    });
    if (reason) { const ok = $('.modal-ok', m.el); ok.disabled = true; ok.title = reason; }
    const est = () => {
      const n = parseInt($('#nb-limit', m.el).value, 10) || 0;
      const el = $('#nb-est', m.el); if (!el || n <= 0) return;
      const row = cost && cost.models.find((r) => r.id === model);
      const ms = row && row.measurement;
      const pr = row && row.price;
      if (!ms) { el.textContent = 'このモデルのトークン実績がまだありません（下の表で「サンプル1件で計測」できます）'; return; }
      if (!pr || !pr.available) { el.innerHTML = '定価: <b>価格は公式ページで確認</b>'; return; }
      const usd = n * (ms.input_tokens * pr.input_usd_per_mtok + (ms.output_tokens + ms.thinking_tokens) * pr.output_usd_per_mtok) / 1e6;
      el.innerHTML = `定価（標準オンライン）換算: <b>${fmtJpy(usd * fxRate(), 2)}</b>（${fmtUsd(usd)}）・ 実測 ${fmtInt(ms.input_tokens + ms.output_tokens + ms.thinking_tokens)} tokens/SKU`;
    };
    $('#nb-limit', m.el).addEventListener('input', est); est();
  };

  // ── List-price cost table
  let costSeq = 0;
  const presets = () => {
    const cat = cost && cost.catalog_count;
    const list = [[100, '100'], [1000, '1,000'], [8807, '8,807']];
    if (cat && cat !== 8807) list.push([cat, `全カタログ ${fmtInt(cat)}`]);
    else if (cat) list[2] = [8807, '8,807（全カタログ）'];
    list.push([100000, '100,000']);
    return list;
  };
  const paintPresets = () => {
    $('#sim-presets', root).innerHTML = presets().map(([n, l]) => `<button class="fchip ${n === simSkus ? 'on' : ''}" data-n="${n}">${esc(l)}</button>`).join('')
      + (cost && cost.catalog_count ? `<span class="muted small cat-src" title="BigQuery cymbal.products の件数">BQ cymbal.products: ${fmtInt(cost.catalog_count)} SKU</span>` : '');
    $$('#sim-presets .fchip', root).forEach((b) => b.addEventListener('click', () => setSkus(+b.dataset.n)));
  };
  const paintHero = () => {
    const box = $('#cost-hero', root);
    const sel = selectedModel();
    const row = cost.models.find((r) => r.id === sel);
    const ms = row && row.measurement;
    const e = row && row.estimate;
    if (!row) { box.innerHTML = `<div class="ch-main muted">ヘッダーで選択中のモデル（${esc(sel)}）は試算対象外です</div>`; return; }
    if (!ms) { box.innerHTML = `<div class="ch-main"><span class="ch-model">${esc(row.label)}</span> のトークン実績を計測しています…</div>`; return; }
    const base = ms.only_sample ? `この商品（${esc(ms.sample_title || ms.sample_sku)}）のトークン実績` : `実測 ${fmtInt(ms.skus)} SKU（${fmtInt(ms.runs)} 回）の平均トークン`;
    const promo = cost.basis === 'promo';
    const basisTag = promo ? '<span class="mb mb-warn" title="期間限定プロモ価格（割引）での参考試算">参考：プロモ価格（割引）</span>' : '<span class="mb mb-blue">定価・割引なし</span>';
    box.innerHTML = `<div class="ch-main" data-hero-model="${esc(row.id)}" data-basis="${esc(cost.basis)}">${basisTag}<span class="ch-model">${esc(row.label)}</span>
      ${e && e.price_available
        ? `<span>${base}から、<b>${fmtInt(cost.skus)} SKU</b> なら${promo ? '（プロモ価格で）' : '定価で'}約 <b class="ch-big">${fmtJpy(e.total_jpy)}</b> <span class="muted">（${fmtUsd(e.total_usd)}・1 SKU ${fmtJpy(e.per_sku_jpy, 3)}）</span></span>`
        : `<span>${base}: 1 SKU あたり ${fmtInt(ms.input_tokens + ms.output_tokens + ms.thinking_tokens)} tokens ・ <b>価格は公式ページで確認</b>（<a href="${esc(priceUrl())}" target="_blank" rel="noopener">公式価格ページ</a>）</span>`}</div>`;
  };
  const measureCell = (r) => {
    const m = measuring[r.id];
    if (m && !m.done) {
      return `<div class="measure-prog" data-model="${esc(r.id)}"><span class="spin"></span> 計測中…<div class="mp-stages">${Object.entries(STAGE_LABEL).map(([k, l]) => `<span class="mps ${m.stages[k] ? 'done' : ''}">${m.stages[k] ? '✓' : '…'} ${l}</span>`).join('')}</div>${m.title ? `<div class="muted small ellipsis" title="${esc(m.title)}">${esc(m.title)}</div>` : ''}</div>`;
    }
    return `<button class="btn btn-outline btn-xs btn-measure" data-model="${esc(r.id)}" title="代表 SKU 1 件をこのモデルで実行してトークンを計測（結果は token_usage に保存。エンリッチ結果は上書きしません）">${r.measurement ? '↻ 再計測' : 'サンプル1件で計測'}</button>${m && m.error ? `<div class="dc-err small" title="${esc(m.error)}">失敗: ${esc(m.error.slice(0, 60))}</div>` : ''}`;
  };
  const paintTable = () => {
    const box = $('#cost-table', root);
    const sel = selectedModel();
    const rows = cost.models;
    const priced = rows.filter((r) => r.estimate && r.estimate.price_available);
    const max = Math.max(...priced.map((r) => r.estimate.total_jpy), 1e-9);
    box.innerHTML = `<div class="cost-scroll"><table class="table cost-table" id="cost-tbl"><thead><tr>
        <th>モデル</th><th class="r">トークン / SKU<div class="th-sub">入力 ・ 出力 ・ 思考</div></th><th>計測の根拠</th>
        <th class="r">${cost.basis === 'promo' ? '参考：プロモ単価（割引）' : '公式定価'}（USD / 100万 tokens）<div class="th-sub">入力 ・ 出力（思考含む）</div></th>
        <th class="r">${fmtInt(cost.skus)} SKU の費用<div class="th-sub">入力 ・ 出力 ・ 思考</div></th><th></th></tr></thead><tbody>
      ${rows.map((r) => {
        const ms = r.measurement, e = r.estimate, pr = r.price;
        const tok = ms ? `<b>${fmtInt(ms.input_tokens + ms.output_tokens + ms.thinking_tokens)}</b><div class="tok3 mono small">${fmtInt(ms.input_tokens)} ・ ${fmtInt(ms.output_tokens)} ・ ${fmtInt(ms.thinking_tokens)}</div>` : '<span class="muted">未計測</span>';
        const basis = ms ? (ms.only_sample
          ? `<span class="mb mb-warn">サンプル1件</span><div class="small ellipsis" title="${esc(ms.sample_title)}">${esc(ms.sample_title || '')}</div><div class="muted small mono">SKU ${esc(ms.sample_sku)}</div>`
          : `<span class="mb mb-ok">実測 ${fmtInt(ms.skus)} SKU</span><div class="muted small">${fmtInt(ms.runs)} 回の平均・最新 ${esc(ms.sample_title || ms.sample_sku)}</div>`) : '<span class="muted small">—</span>';
        const price = pr && pr.available
          ? `<div class="mono"><b>$${pr.input_usd_per_mtok}</b> ・ <b>$${pr.output_usd_per_mtok}</b></div>${pr.promo ? '<span class="mb mb-warn">参考：プロモ価格（割引）</span>' : ''}${pr.note ? `<div class="muted small price-note">${esc(pr.note)}</div>` : ''}`
          : '<div class="price-missing">価格は公式ページで確認</div><div class="muted small">合計から除外</div>';
        let costCell = '<span class="muted">—</span>';
        if (e && e.price_available) {
          const b = e.breakdown;
          costCell = `<div class="cost-big">${fmtJpy(e.total_jpy)}</div><div class="muted small">${fmtUsd(e.total_usd)} ・ ${fmtJpy(e.per_sku_jpy, 3)}/SKU</div>
            <div class="cbar" title="入力 ${fmtJpy(b.input.jpy)} / 出力 ${fmtJpy(b.output.jpy)} / 思考 ${fmtJpy(b.thinking.jpy)}"><i class="ci" style="width:${b.input.jpy / max * 100}%"></i><i class="co" style="width:${b.output.jpy / max * 100}%"></i><i class="ct" style="width:${b.thinking.jpy / max * 100}%"></i></div>
            <div class="cbd small mono">${fmtJpy(b.input.jpy)} ・ ${fmtJpy(b.output.jpy)} ・ ${fmtJpy(b.thinking.jpy)}</div>
            <div class="muted small mono">${fmtInt(e.tokens.input)} ・ ${fmtInt(e.tokens.output)} ・ ${fmtInt(e.tokens.thinking)} tokens</div>`;
        } else if (e) {
          costCell = `<div class="price-missing">価格は公式ページで確認</div><div class="muted small mono">${fmtInt(e.tokens.input)} ・ ${fmtInt(e.tokens.output)} ・ ${fmtInt(e.tokens.thinking)} tokens</div>`;
        }
        return `<tr data-model="${esc(r.id)}" class="${r.id === sel ? 'sel' : ''} ${r.id === cost.cheapest ? 'cheap' : ''}">
          <td><div class="cm-name">${esc(r.label)}${r.id === sel ? '<span class="mb mb-blue">選択中</span>' : ''}${r.default ? '<span class="mb mb-mute">既定</span>' : ''}${r.id === cost.cheapest ? '<span class="mb mb-ok">最安</span>' : ''}</div>
            <div class="muted small mono">${esc(r.id)}</div><div class="cm-badges">${r.batch ? '<span class="mb mb-info">Batch 対応</span>' : `<span class="mb mb-mute" title="${esc(r.batch_note || '')}">Batch 無効</span>`}${r.reason ? `<span class="mb mb-warn">${esc(r.reason)}</span>` : ''}</div></td>
          <td class="r">${tok}</td><td class="basis">${basis}</td>
          <td class="r">${price}<a class="price-link" href="${esc((pr && pr.url) || priceUrl())}" target="_blank" rel="noopener">公式価格ページ ↗</a></td>
          <td class="r">${costCell}</td>
          <td class="r act">${measureCell(r)}</td></tr>`;
      }).join('')}</tbody></table></div>
      <div class="cost-legend small"><span><i class="ci"></i>入力</span><span><i class="co"></i>出力</span><span><i class="ct"></i>思考</span><span class="muted">バーは表内の最大費用に対する比率</span></div>`;
    $$('.btn-measure', box).forEach((b) => b.addEventListener('click', () => measure(b.dataset.model, true)));
  };
  const paintNotes = () => {
    const sp = cost.sample_sku;
    const un = cost.unavailable || [];
    const excluded = cost.models.filter((r) => !(r.price && r.price.available));
    $('#cost-notes', root).innerHTML = `<div class="note-title">前提・注意</div><ul>
      <li>トークン数は<b>商品説明の長さによって変動</b>します。表の値は各モデルで実際に処理した商品の平均（無い場合は代表 SKU 1 件の実績）で、N SKU への単純な比例換算です。</li>
      <li>1 SKU = <b>3 回の呼び出し</b>（属性抽出 / タグ・要約 / GMC 会話属性）。思考（thinking）トークンは公式ページの記載どおり<b>出力単価</b>で計算（thinking level: LOW）。</li>
      <li>「サンプル1件で計測」の代表 SKU: ${sp ? `<b>${esc(sp.title)}</b>（SKU <span class="mono">${esc(sp.sku)}</span>・原文 ${fmtInt(sp.chars)} 文字＝デモ ${fmtInt(cost.demo_skus)} SKU の中央値）` : '—'}。全モデル同じ商品で計測するため比較できます。</li>
      <li>価格: <a href="${esc(cost.pricing_url)}" target="_blank" rel="noopener">Vertex AI 生成 AI の料金（公式）</a> の<b>標準（Standard）・Global・入力 20 万 tokens 以下</b>の${cost.basis === 'promo' ? '<b>期間限定プロモ価格（割引・参考値）</b>' : '<b>定価（期間限定プロモーション・クレジットバック等の割引は適用なし）</b>'}。価格取得日 <b>${esc(cost.price_retrieved_at)}</b>、適用日 ${esc(cost.as_of)}、1 USD = ${esc(String(cost.usd_jpy))} 円。Batch / Flex / Priority、キャッシュ割引、税・為替手数料は含みません。</li>
      ${excluded.length ? `<li>公式ページに価格（入力・出力とも）の記載がないモデルは「価格は公式ページで確認」と表示し、合計・比較から除外: ${excluded.map((r) => `<span class="mono">${esc(r.id)}</span>`).join(', ')}</li>` : ''}
      ${un.length ? `<li>このプロジェクトで利用できず一覧から除外したモデル: ${un.map((m) => `<span class="mono" title="${esc(m.reason || '')}">${esc(m.id)}</span>`).join(', ')}</li>` : ''}
    </ul>`;
  };
  const loadCost = async () => {
    const my = ++costSeq;
    let d;
    try { d = await api.costModels({ skus: simSkus, usd_jpy: fxRate(), basis: basisPref() }); } catch (e) {
      if (my === costSeq && !stale()) $('#cost-table', root).innerHTML = errorState(e);
      return;
    }
    if (my !== costSeq || stale()) return;
    cost = d;
    paintPresets(); paintHero(); paintTable(); paintNotes();
    autoMeasure();
  };
  const setSkus = (n) => {
    simSkus = Math.max(1, Math.min(10000000, Math.round(n)));
    $('#sim-num', root).value = fmtInt(simSkus);
    $('#sim-range', root).value = toPos(simSkus);
    loadCost();
  };
  let simT;
  $('#sim-range', root).addEventListener('input', (e) => {
    const n = toSkus(+e.target.value);
    $('#sim-num', root).value = fmtInt(n);
    clearTimeout(simT); simT = setTimeout(() => setSkus(n), 150);
  });
  $('#sim-num', root).addEventListener('change', (e) => setSkus(parseInt(String(e.target.value).replace(/[^\d]/g, ''), 10) || MIN));
  $('#fx-rate', root).addEventListener('change', (e) => {
    const v = parseFloat(e.target.value);
    if (!(v > 0)) { e.target.value = fxRate(); return; }
    localStorage.setItem(FX_KEY, String(v)); loadCost();
  });
  const paintBasis = () => {
    const promo = basisPref() === 'promo';
    $('#promo-toggle', root).checked = promo;
    $('#basis-list', root).classList.toggle('off', promo);
    $('#basis-chip', root).textContent = promo ? '参考：期間限定プロモ価格（割引）で表示中' : '定価（プロモーション適用なし）・ Batch 割引なし';
    $('#basis-chip', root).className = 'chip ' + (promo ? 'chip-warn' : 'chip-info');
    $('#cost-panel', root).classList.toggle('promo', promo);
  };
  $('#promo-toggle', root).addEventListener('change', (e) => { localStorage.setItem(BASIS_KEY, e.target.checked ? 'promo' : 'list'); paintBasis(); loadCost(); });
  paintBasis();

  // 「サンプル1件で計測」 (button + auto on first view; at most 2 in parallel)
  const queue = [];
  let active = 0;
  const pump = () => {
    while (active < 2 && queue.length) {
      const id = queue.shift();
      active++;
      runMeasure(id).finally(() => { active--; pump(); });
    }
  };
  async function runMeasure(id) {
    measuring[id] = { stages: {}, done: false };
    if (!stale() && cost) paintTable();
    try {
      await api.costMeasure(id, (ev) => {
        const m = measuring[id];
        if (ev.event === 'start') { m.sku = ev.sku; m.title = ev.title; }
        else if (ev.event === 'stage') m.stages[ev.stage] = ev;
        else if (ev.event === 'error') m.error = ev.message || 'error';
        else if (ev.event === 'result') m.result = ev;
        if (!stale() && cost) { const row = $(`tr[data-model="${CSS.escape(id)}"] .act`, root); if (row) row.innerHTML = measureCell({ id, measurement: null }); }
      });
      if (measuring[id].error) toast(`${modelLabel(id)} の計測に失敗しました: ${measuring[id].error}`, 'err', 6000);
      else toast(`${modelLabel(id)}: サンプル1件のトークンを計測しました`, 'ok');
    } catch (e) {
      measuring[id].error = e.message || String(e);
      toast(`${modelLabel(id)} の計測に失敗しました: ${e.message}`, 'err', 6000);
    } finally {
      measuring[id].done = true;
      if (!stale()) loadCost();
    }
  }
  function measure(id, manual = false) {
    if (measuring[id] && !measuring[id].done) return;
    if (queue.includes(id)) return;
    if (manual) autoTried.add(id);
    queue.push(id);
    measuring[id] = { stages: {}, done: false, queued: true };
    if (cost) paintTable();
    pump();
  }
  function autoMeasure() {
    if (isMock && !cost) return;
    cost.models.filter((r) => !r.measurement && r.status === 'available' && !autoTried.has(r.id)).forEach((r) => { autoTried.add(r.id); measure(r.id); });
  }
  const onModel = () => { if (!root.isConnected || !$('#cost-panel', root)) { window.removeEventListener('enrich:model', onModel); return; } if (cost) { paintHero(); paintTable(); } };
  window.addEventListener('enrich:model', onModel);

  // Golden
  const loadGolden = async () => {
    const box = $('#golden', root);
    let d;
    try { d = await api.golden({}); } catch (e) { if (!stale()) box.innerHTML = errorState(e); return; }
    if (stale()) return;
    const items = d.items || [];
    if (!items.length) { box.innerHTML = emptyState('⭐', 'ゴールデンレコードはまだありません', 'エンリッチ・承認が完了した商品がここに並びます'); return; }
    const groups = (state.config && state.config.groups) || {};
    const show = items.slice(0, 8);
    box.innerHTML = `<div class="muted small gold-cnt">${fmtInt(items.length)} SKU${items.length > show.length ? `(先頭 ${show.length} 件を表示)` : ''}</div>
      <table class="table gold"><thead><tr><th>商品</th><th>主要属性</th><th>機能タグ</th><th class="r">充足率</th><th>更新</th></tr></thead><tbody>
      ${show.map((g) => {
        const attrs = Object.entries(g.attributes || {}).slice(0, 5);
        const more = Object.keys(g.attributes || {}).length - attrs.length;
        return `<tr><td><a href="#/studio/${encodeURIComponent(g.sku)}" class="gold-title">${esc(g.title)}</a><div class="muted small">${esc(groups[g.group] || g.group)} ・ ${esc(g.sku)}</div></td>
          <td><div class="kv">${attrs.map(([k, v]) => `<span class="kvp" title="${esc(k)}">${esc(label(k))} <b>${esc(fmtValue(v && v.value))}${esc(v && v.unit || '')}</b></span>`).join('')}${more > 0 ? `<span class="kvp more">+${more}</span>` : ''}</div></td>
          <td><div class="tags">${(g.feature_tags || []).slice(0, 4).map((t) => `<span class="tag">${esc(t)}</span>`).join('')}</div></td>
          <td class="r nowrap"><span class="muted">${fmtPct(g.fill_rate_before)}</span> ➜ <b class="after-text">${fmtPct(g.fill_rate_after)}</b></td>
          <td class="small nowrap">${fmtDate(g.updated_at)}</td></tr>`;
      }).join('')}</tbody></table>`;
  };

  await Promise.all([loadCost().then(() => loadJobs(false)), loadGolden()]);
  return () => { clearTimeout(simT); window.removeEventListener('enrich:model', onModel); };
}

const label = (k) => ((state.config && state.config.attr_labels) || {})[k] || k;
