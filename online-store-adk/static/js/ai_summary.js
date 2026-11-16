/* 「✨ AI による概要」 panel — POST /api/ai-summary (Gemini). */
(function () {
  'use strict';
  const { esc, SPARK, fetchJSON, featureLabel, setFeatureStatus } = window.CR;
  let seq = 0;

  function shell() {
    return '<section class="cr-ai" id="cr-ai" aria-live="polite">' +
      '<div class="cr-ai__head"><span class="cr-ai__title"><span class="cr-ai__spark">' + SPARK + '</span>AI による概要</span>' + featureLabel('AI Summary', 'ai_summary') + '</div>' +
      '<div class="cr-shimmer" id="cr-ai-body"><i></i><i></i><i></i></div>' +
      '</section>';
  }

  /** load(q, products, mount) → Promise<data|null> */
  async function load(q, products, mount) {
    const my = ++seq;
    if (!mount) return null;
    if (!products.length) { mount.innerHTML = ''; return null; }
    mount.innerHTML = shell();
    let data;
    try {
      data = await fetchJSON('/api/ai-summary', { method: 'POST', body: JSON.stringify({ q, product_ids: products.slice(0, 8).map((p) => p.id) }) });
    } catch (e) {
      if (my === seq) mount.innerHTML = '';
      return null;
    }
    if (my !== seq) return null;
    setFeatureStatus({ ai_summary: data.source === 'gemini' ? 'live' : 'fallback' });
    const byId = Object.fromEntries(products.map((p) => [p.id, p]));
    const hl = (data.highlights || []).filter((h) => byId[h.product_id]);
    const body = mount.querySelector('#cr-ai-body');
    const wrap = document.createElement('div');
    wrap.innerHTML =
      '<p class="cr-ai__summary" id="cr-ai-summary">' + esc(data.summary) + '</p>' +
      (hl.length ? '<div class="cr-ai__hl">' + hl.map((h) => {
        const p = byId[h.product_id];
        return '<button type="button" class="cr-ai__hlitem" data-open="' + esc(p.id) + '"><img src="' + esc(p.image) + '" alt=""><span><b>' + esc(p.title) + '</b><span>' + esc(h.reason) + '</span></span></button>';
      }).join('') + '</div>' : '') +
      '<div class="cr-ai__foot">' + (data.source === 'gemini' ? 'Gemini（' + esc(data.model || '') + '）が検索結果をもとに生成しました。' : '検索結果から自動生成した概要です。') + ' 内容は商品ページでご確認ください。</div>';
    body.replaceWith(wrap);
    return Object.assign({}, data, { highlights: hl });
  }

  window.AISummary = { load };
})();
