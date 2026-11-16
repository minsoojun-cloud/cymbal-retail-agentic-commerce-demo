(function () {
  'use strict';

  const state = {
    user: null,
    availableUsers: [],
    templates: [],
    frameShapes: [],
    layoutModes: [],
    overlayPositions: [],
    slotSpans: [],
    numeralStyles: [],
    slotBgPalettes: [],
    bgPresets: [],
    priceStyles: [],
    badgePresets: [],
    paperFormats: [],
    categories: [],
    currentFlyer: null,
    selectedSlotId: null,
    zoomScale: 0,
    fsZoomScale: 0,
    editingTemplate: null,
    selectedTplZoneIdx: 0,
    selectedTplSlotId: null,
    toastTimer: null,
  };

  const $ = (id) => document.getElementById(id);

  function showToast(msg, isError = false) {
    const bar = $('toast-bar');
    if (!bar) return;
    bar.textContent = msg;
    bar.classList.toggle('is-error', Boolean(isError));
    bar.hidden = false;
    if (state.toastTimer) clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => {
      bar.hidden = true;
    }, 4200);
  }

  async function api(path, opts = {}) {
    const headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {});
    if (state.user && state.user.id) {
      headers['X-Flyer-User'] = state.user.id;
    }
    const res = await fetch(path, Object.assign({}, opts, { headers }));
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.error || `エラーが発生しました (${res.status})`);
    }
    return data;
  }

  function switchTab(tabName) {
    ['editor', 'templates', 'archive'].forEach((t) => {
      const btn = $(`tab-btn-${t}`);
      const view = $(`view-${t}`);
      if (btn) btn.classList.toggle('active', t === tabName);
      if (view) view.hidden = t !== tabName;
    });
    if (tabName === 'editor') {
      setTimeout(() => applySheetScale('editor'), 50);
    } else if (tabName === 'templates') {
      initTemplateStudioIfNeeded();
    } else if (tabName === 'archive') {
      loadArchiveList();
    }
  }

  function getSheetPixelDimensions(paperId) {
    const isPortrait = String(paperId || '').includes('portrait');
    return isPortrait ? { w: 971, h: 1375 } : { w: 1375, h: 971 };
  }

  function applySheetScale(mode = 'editor') {
    if (mode === 'editor') {
      const stage = $('sheet-stage');
      const scaler = $('sheet-scaler');
      const frame = $('preview-frame');
      if (!stage || !scaler || !frame || !state.currentFlyer) return;
      const dims = getSheetPixelDimensions(state.currentFlyer.paper);
      frame.style.width = `${dims.w}px`;
      frame.style.height = `${dims.h}px`;

      let scale = state.zoomScale;
      if (!scale || scale <= 0) {
        const availW = Math.max(320, stage.clientWidth - 28);
        const availH = Math.max(260, stage.clientHeight - 28);
        scale = Math.min(availW / dims.w, availH / dims.h, 1.0);
      }
      scaler.style.width = `${Math.round(dims.w * scale)}px`;
      scaler.style.height = `${Math.round(dims.h * scale)}px`;
      frame.style.transform = `scale(${scale.toFixed(4)})`;
      frame.style.transformOrigin = 'top left';
    } else if (mode === 'fullscreen') {
      const stage = $('fs-modal-stage');
      const scaler = $('fs-modal-scaler');
      const frame = $('fs-preview-frame');
      if (!stage || !scaler || !frame || !state.currentFlyer) return;
      const dims = getSheetPixelDimensions(state.currentFlyer.paper);
      frame.style.width = `${dims.w}px`;
      frame.style.height = `${dims.h}px`;

      let scale = state.fsZoomScale;
      if (!scale || scale <= 0) {
        const availW = Math.max(400, stage.clientWidth - 40);
        const availH = Math.max(320, stage.clientHeight - 40);
        scale = Math.min(availW / dims.w, availH / dims.h, 1.35);
      }
      scaler.style.width = `${Math.round(dims.w * scale)}px`;
      scaler.style.height = `${Math.round(dims.h * scale)}px`;
      frame.style.transform = `scale(${scale.toFixed(4)})`;
      frame.style.transformOrigin = 'top left';
    } else if (mode === 'template') {
      const stage = $('tpl-sheet-stage');
      const scaler = $('tpl-sheet-scaler');
      const frame = $('tpl-preview-frame');
      if (!stage || !scaler || !frame || !state.editingTemplate) return;
      const dims = getSheetPixelDimensions(state.editingTemplate.paper);
      frame.style.width = `${dims.w}px`;
      frame.style.height = `${dims.h}px`;
      const availW = Math.max(320, stage.clientWidth - 28);
      const availH = Math.max(260, stage.clientHeight - 28);
      const scale = Math.min(availW / dims.w, availH / dims.h, 1.0);
      scaler.style.width = `${Math.round(dims.w * scale)}px`;
      scaler.style.height = `${Math.round(dims.h * scale)}px`;
      frame.style.transform = `scale(${scale.toFixed(4)})`;
      frame.style.transformOrigin = 'top left';
    }
  }

  function syncUserUI() {
    const sel = $('user-select');
    const badge = $('user-role-badge');
    if (!sel || !state.user) return;
    sel.innerHTML = state.availableUsers
      .map((u) => `<option value="${u.id}" ${u.id === state.user.id ? 'selected' : ''}>${u.name}</option>`)
      .join('');
    if (badge) {
      badge.textContent = state.user.role === 'manager' ? '店舗責任者（承認可）' : '販促担当';
      badge.style.background = state.user.role === 'manager' ? '#e8f5e9' : '#e8f0fe';
      badge.style.color = state.user.role === 'manager' ? '#1b5e20' : '#1a73e8';
    }
    updateToolbarPermissions();
  }

  function updateToolbarPermissions() {
    const f = state.currentFlyer;
    if (!f) return;
    const isApproved = f.status === '承認済み';
    const isManager = state.user && state.user.role === 'manager';
    const hasDisc = (f.discontinued_count || 0) > 0;

    $('btn-submit-review').disabled = isApproved || hasDisc;
    $('btn-approve').hidden = !isManager;
    $('btn-approve').disabled = isApproved || hasDisc;
    $('btn-reject').hidden = !isManager;
    $('btn-reject').disabled = isApproved;
    $('btn-reselect').disabled = isApproved;
  }

  function renderEditorTemplateCards() {
    const box = $('editor-template-cards');
    if (!box) return;
    const curId = (state.currentFlyer && state.currentFlyer.template_id) || ($('sel-template') && $('sel-template').value) || 'T1';
    box.innerHTML = state.templates
      .map((t) => {
        const isAct = t.id === curId;
        const shortName = (t.name || '').split('（')[0];
        return `
          <button type="button" class="tpl-vcard ${isAct ? 'active' : ''}" data-pick-tpl="${t.id}">
            <div class="tpl-vcard__id">${t.id} ${t.is_custom ? '★カスタム' : ''}</div>
            <div class="tpl-vcard__name">${shortName}</div>
            <div class="tpl-vcard__meta">標準${t.default_item_count}品・${(t.zones || []).length}ゾーン</div>
          </button>
        `;
      })
      .join('');
  }

  function populateMetadataSelectors() {
    const tplOptionsHtml = state.templates
      .map((t) => `<option value="${t.id}">${t.id}: ${t.name}（標準${t.default_item_count}品）</option>`)
      .join('');
    if ($('sel-template')) $('sel-template').innerHTML = tplOptionsHtml;
    if ($('sel-toolbar-template')) $('sel-toolbar-template').innerHTML = tplOptionsHtml;
    if ($('tpl-studio-select')) $('tpl-studio-select').innerHTML = tplOptionsHtml;
    renderEditorTemplateCards();

    const paperHtml = state.paperFormats
      .map((p) => `<option value="${p.id}">${p.label}</option>`)
      .join('');
    if ($('sel-paper')) $('sel-paper').innerHTML = paperHtml;
    if ($('tpl-studio-paper')) $('tpl-studio-paper').innerHTML = paperHtml;

    const shapeHtml = state.frameShapes
      .map((s) => `<option value="${s.id}">${s.label}</option>`)
      .join('');
    ['sel-slot-shape', 'sel-tz-hero-shape', 'sel-tz-grid-shape', 'sel-ts-shape'].forEach((id) => {
      if ($(id)) $(id).innerHTML = shapeHtml;
    });

    const layoutHtml = state.layoutModes
      .map((l) => `<option value="${l.id}">${l.label}</option>`)
      .join('');
    ['sel-slot-layout', 'tpl-studio-layout', 'sel-tz-hero-layout', 'sel-tz-grid-layout', 'sel-ts-layout'].forEach((id) => {
      if ($(id)) $(id).innerHTML = layoutHtml;
    });

    const oposHtml = state.overlayPositions
      .map((o) => `<option value="${o.id}">${o.label}</option>`)
      .join('');
    ['sel-slot-opos', 'sel-ts-opos'].forEach((id) => {
      if ($(id)) $(id).innerHTML = oposHtml;
    });

    const spanHtml = state.slotSpans
      .map((s) => `<option value="${s.id}">${s.label}</option>`)
      .join('');
    ['sel-slot-span', 'sel-ts-span'].forEach((id) => {
      if ($(id)) $(id).innerHTML = spanHtml;
    });

    const numHtml = state.numeralStyles
      .map((n) => `<option value="${n.id}">${n.label}</option>`)
      .join('');
    ['sel-slot-numeral', 'sel-sheet-numeral', 'tpl-studio-numeral'].forEach((id) => {
      if ($(id)) $(id).innerHTML = numHtml;
    });

    const bgHtml = state.slotBgPalettes
      .map((b) => `<option value="${b.id}">${b.label}</option>`)
      .join('');
    if ($('sel-slot-bg')) $('sel-slot-bg').innerHTML = bgHtml;

    const bgPresetHtml = state.bgPresets
      .map((p) => `<option value="${p.id}">${p.label}</option>`)
      .join('');
    if ($('sel-bg-preset')) $('sel-bg-preset').innerHTML = bgPresetHtml;

    const priceHtml = state.priceStyles
      .map((p) => `<option value="${p.id}">${p.label}</option>`)
      .join('');
    if ($('sel-slot-price-style')) $('sel-slot-price-style').innerHTML = priceHtml;

    const badgeRow = $('badge-preset-chips');
    if (badgeRow) {
      badgeRow.innerHTML = state.badgePresets
        .slice(0, 10)
        .map((b) => `<button type="button" class="chip" data-badge-chip="${b}">${b}</button>`)
        .join('');
    }
    const selCat = $('sel-prod-cat');
    if (selCat) {
      selCat.innerHTML =
        '<option value="">すべてのカテゴリ</option>' +
        state.categories.map((c) => `<option value="${c.name}">${c.name} (${c.count})</option>`).join('');
    }
    const tzCats = $('tz-cat-checkboxes');
    if (tzCats) {
      tzCats.innerHTML = state.categories
        .map(
          (c) => `<label><input type="checkbox" value="${c.name}" class="chk-tz-cat"/> <span>${c.name}</span></label>`
        )
        .join('');
    }
  }

  async function applyTemplateToCurrentFlyer(tplId) {
    if ($('sel-template')) $('sel-template').value = tplId;
    if ($('sel-toolbar-template')) $('sel-toolbar-template').value = tplId;
    const tpl = state.templates.find((t) => t.id === tplId);
    if (tpl) {
      $('inp-item-count').value = tpl.default_item_count || 20;
      if (tpl.paper) $('sel-paper').value = tpl.paper;
      if (tpl.default_tone) $('sel-tone').value = tpl.default_tone;
      if (tpl.default_numeral_style) $('sel-sheet-numeral').value = tpl.default_numeral_style;
    }
    renderEditorTemplateCards();

    if (!state.currentFlyer) {
      showToast(`テンプレート「${tpl ? tpl.name : tplId}」を選択しました。「✨ 今週のチラシを自動作成」ボタンを押してください。`);
      return;
    }
    if (state.currentFlyer.status === '承認済み') {
      await generateFlyer(null);
      return;
    }
    try {
      const res = await api(`/api/flyers/${encodeURIComponent(state.currentFlyer.id)}/apply_template`, {
        method: 'POST',
        body: JSON.stringify({
          template_id: tplId,
          item_count: Number($('inp-item-count').value || (tpl && tpl.default_item_count) || 20),
        }),
      });
      renderCurrentFlyer(res.flyer);
      showToast(`テンプレート「${tpl ? tpl.name : tplId}」を適用しました。`);
    } catch (e) {
      showToast(e.message, true);
    }
  }

  function renderCurrentFlyer(flyer, opts = {}) {
    state.currentFlyer = flyer;
    if (!flyer) return;

    $('inp-theme').value = flyer.theme || '';
    $('inp-target').value = flyer.target || '';
    if (flyer.period) {
      if (flyer.period.from) $('inp-period-from').value = flyer.period.from;
      if (flyer.period.to) $('inp-period-to').value = flyer.period.to;
    }
    if (flyer.template_id) {
      if ($('sel-template')) $('sel-template').value = flyer.template_id;
      if ($('sel-toolbar-template')) $('sel-toolbar-template').value = flyer.template_id;
    }
    renderEditorTemplateCards();
    if (flyer.paper && $('sel-paper')) $('sel-paper').value = flyer.paper;
    if (flyer.tone && $('sel-tone')) $('sel-tone').value = flyer.tone;
    if (flyer.numeral_style && $('sel-sheet-numeral')) $('sel-sheet-numeral').value = flyer.numeral_style;
    if ($('sel-sheet-bg')) $('sel-sheet-bg').value = flyer.sheet_bg || '';
    $('inp-item-count').value = (flyer.slots || []).length || 20;

    $('inp-flyer-title').value = flyer.title || '';
    $('inp-flyer-subtitle').value = flyer.subtitle || '';

    const stBadge = $('flyer-status-badge');
    stBadge.textContent = flyer.status || '下書き';
    stBadge.className =
      'status-badge ' +
      (flyer.status === '承認済み' ? 'is-approved' : flyer.status === '確認待ち' ? 'is-pending' : '');

    $('flyer-meta-title').textContent = `${flyer.title || '無題のチラシ'} （${(flyer.slots || []).length}品・${flyer.template_id}）`;
    const creator = (flyer.created_by && flyer.created_by.name) || '—';
    const approver = (flyer.approved_by && flyer.approved_by.name) || '';
    const qaPassed = flyer.qa_report && flyer.qa_report.passed ? ' ／ ✅ 品質検証済（配置・文字重なり・雰囲気OK）' : '';
    $('flyer-meta-people').textContent =
      `作成者: ${creator}` + (approver ? ` ／ 承認者: ${approver}` : '') + qaPassed;

    const discBanner = $('discontinued-banner');
    const discCount = flyer.discontinued_count || 0;
    const nowDiscCount = flyer.currently_discontinued_count || 0;
    if (discCount > 0) {
      discBanner.hidden = false;
      discBanner.textContent = `⚠️ 販売終了の商品が ${discCount} 点含まれています。紙面上の赤い点線枠をクリックし、右パネルで代替商品を検索して差し替えてください（差し替え完了まで確認依頼・承認はできません）。`;
    } else if (flyer.status === '承認済み' && nowDiscCount > 0) {
      discBanner.hidden = false;
      discBanner.textContent = `ℹ️ この保管済みチラシは承認当時のスナップショットを表示しています（うち ${nowDiscCount} 点は現在マスタで販売終了）。「このチラシをもとに新規作成」を押すと代替商品の差し替えが行えます。`;
    } else {
      discBanner.hidden = true;
    }

    const densBanner = $('density-banner');
    if (flyer.density_warning) {
      densBanner.hidden = false;
      densBanner.textContent = `ℹ️ ${flyer.density_warning}`;
    } else {
      densBanner.hidden = true;
    }

    updateToolbarPermissions();

    if ($('sheet-empty-state')) $('sheet-empty-state').hidden = true;
    if ($('sheet-loading-overlay')) $('sheet-loading-overlay').hidden = true;
    if ($('sheet-scaler')) $('sheet-scaler').hidden = false;

    const frame = $('preview-frame');
    applySheetScale('editor');
    frame.src = `/api/flyers/${encodeURIComponent(flyer.id)}/preview_html?t=${Date.now()}`;

    frame.onload = () => {
      applySheetScale('editor');
      try {
        const doc = frame.contentDocument;
        if (!doc) return;
        doc.querySelectorAll('.ch-slot').forEach((el) => {
          el.addEventListener('click', (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            const sid = el.getAttribute('data-slot-id');
            selectSlot(sid);
          });
        });
        highlightSelectedSlotInFrame();
      } catch (e) {
        console.warn('Preview frame hook error:', e);
      }
    };

    if (state.selectedSlotId) {
      const stillThere = (flyer.slots || []).some((s) => s.slot_id === state.selectedSlotId);
      if (stillThere) {
        if (!opts.preserveInspectorInputs) {
          selectSlot(state.selectedSlotId);
        } else {
          highlightSelectedSlotInFrame();
        }
      } else {
        clearSlotSelection();
      }
    } else if (discCount > 0) {
      const firstDisc = (flyer.slots || []).find((s) => s.discontinued);
      if (firstDisc) selectSlot(firstDisc.slot_id);
    }
  }

  function highlightSelectedSlotInFrame() {
    const frame = $('preview-frame');
    if (!frame || !frame.contentDocument) return;
    frame.contentDocument.querySelectorAll('.ch-slot').forEach((el) => {
      const isSel = el.getAttribute('data-slot-id') === state.selectedSlotId;
      el.style.outline = isSel ? '1.2mm solid #1a73e8' : '';
      el.style.zIndex = isSel ? '10' : '';
    });
  }

  function clearSlotSelection() {
    state.selectedSlotId = null;
    $('inspector-empty').hidden = false;
    $('inspector-form').hidden = true;
    highlightSelectedSlotInFrame();
  }

  function selectSlot(slotId) {
    const f = state.currentFlyer;
    if (!f) return;
    const slot = (f.slots || []).find((s) => s.slot_id === slotId);
    if (!slot) return;
    state.selectedSlotId = slotId;
    highlightSelectedSlotInFrame();

    $('inspector-empty').hidden = true;
    $('inspector-form').hidden = false;
    $('inspector-title').textContent = `2. 枠編集：${slot.slot_id}`;

    const prod = slot.product || {};
    const priceEx = Number(prod.price_tax_excluded || 0);
    const priceInc = Number(prod.price_tax_included_exact || Math.round(priceEx * 1.08 * 100) / 100);
    const origEx = Number(prod.original_price_tax_excluded || priceEx);

    const discHtml = slot.discontinued
      ? `<div style="color:#c62828;font-weight:900;margin-top:3px">⚠️ 販売終了商品（コード: ${slot.product_id}）— 下の検索から代替商品を選択してください</div>`
      : '';
    const offerHtml = prod.has_flyer_offer
      ? `<div style="color:#ef6c00;font-weight:800;margin-top:2px">🏷️ チラシ特別価格 適用中（入力者: ${prod.offer_entered_by || '担当者'}）</div>`
      : '';

    $('slot-summary-card').innerHTML = `
      <img src="${prod.image || ''}" alt=""/>
      <div class="slot-summary-card__info">
        <div class="slot-summary-card__title">${prod.flyer_name || prod.title || ''}</div>
        <div>コード: ${slot.product_id} ／ 単位: ${prod.unit_label || '-'} ／ 産地: ${prod.origin || '-'}</div>
        <div class="slot-summary-card__price">本体 ${priceEx.toLocaleString()}円（税込 ${priceInc.toFixed(2)}円）${origEx > priceEx ? ` <span style="font-size:11px;color:#666">通常本体 ${origEx.toLocaleString()}円</span>` : ''}</div>
        <div style="color:#1b5e20;font-weight:700;margin-top:2px">選定理由: ${slot.reason || '—'}</div>
        ${discHtml}${offerHtml}
      </div>
    `;

    $('sel-slot-shape').value = slot.shape || 'rect';
    $('sel-slot-span').value = slot.size_span || 'auto';
    $('sel-slot-layout').value = slot.layout_mode || 'overlay_price';
    $('sel-slot-opos').value = slot.overlay_pos || 'bottom_split';
    $('sel-slot-numeral').value = slot.numeral_style || f.numeral_style || 'graphic_pop';
    $('sel-slot-price-style').value = slot.price_style || 'dual';
    $('sel-slot-bg').value = slot.bg_color || 'auto';

    const wWeight = Number(slot.width_weight || 1.0);
    $('inp-slot-w-weight').value = wWeight;
    $('lbl-slot-w').textContent = `${wWeight.toFixed(1)}x`;

    const rWeight = Number(slot.row_weight || 1.0);
    $('inp-slot-r-weight').value = rWeight;
    $('lbl-slot-r').textContent = `${rWeight.toFixed(1)}x`;

    const imgScale = Number(slot.img_scale || 100);
    $('inp-slot-img-scale').value = imgScale;
    $('lbl-img-scale').textContent = `${imgScale}%`;

    $('inp-slot-badge').value = slot.badge || '';
    $('inp-slot-copy').value = slot.catch_copy || '';
    $('chk-slot-locked').checked = Boolean(slot.locked);

    const offer = slot.offer || {};
    $('inp-offer-price').value = offer.offer_price_tax_excluded || '';
    $('inp-offer-limit').value = offer.limit_text || '';
    updateOfferTaxPreview();

    $('sel-prod-cat').value = prod.category || '';
    runProductSearch();
  }

  function updateOfferTaxPreview() {
    const f = state.currentFlyer;
    const slot = f && (f.slots || []).find((s) => s.slot_id === state.selectedSlotId);
    const prod = (slot && slot.product) || {};
    const taxRate = Number(prod.tax_rate || 0.08);
    const val = Number($('inp-offer-price').value || 0);
    const el = $('offer-tax-preview');
    if (!val || val <= 0) {
      el.textContent = '税込参考価格：—（本体価格を入力すると自動計算されます）';
      return;
    }
    const exact = (val * (1 + taxRate)).toFixed(2);
    el.textContent = `自動計算 税込参考価格：${exact}円（税率 ${Math.round(taxRate * 100)}%）`;
  }

  async function saveSelectedSlotChanges(opts = {}) {
    const f = state.currentFlyer;
    const sid = state.selectedSlotId;
    if (!f || !sid) return;
    try {
      const res = await api(`/api/flyers/${encodeURIComponent(f.id)}`, {
        method: 'PUT',
        body: JSON.stringify({
          slot_update: {
            slot_id: sid,
            shape: $('sel-slot-shape').value,
            size_span: $('sel-slot-span').value,
            layout_mode: $('sel-slot-layout').value,
            overlay_pos: $('sel-slot-opos').value,
            width_weight: Number($('inp-slot-w-weight').value || 1.0),
            row_weight: Number($('inp-slot-r-weight').value || 1.0),
            img_scale: Number($('inp-slot-img-scale').value || 100),
            numeral_style: $('sel-slot-numeral').value,
            price_style: $('sel-slot-price-style').value,
            bg_color: $('sel-slot-bg').value,
            badge: $('inp-slot-badge').value.trim(),
            catch_copy: $('inp-slot-copy').value.trim(),
            locked: $('chk-slot-locked').checked,
          },
        }),
      });
      renderCurrentFlyer(res.flyer, { preserveInspectorInputs: true });
      if (!opts.silentToast) {
        showToast('枠の形態・サイズ・写真重ね配置・背景を反映しました。');
      }
    } catch (e) {
      showToast(e.message, true);
    }
  }

  async function applySpecialOffer(clear = false) {
    const f = state.currentFlyer;
    const sid = state.selectedSlotId;
    if (!f || !sid) return;
    try {
      const priceVal = clear ? null : $('inp-offer-price').value;
      const limitTxt = clear ? '' : $('inp-offer-limit').value.trim();
      const res = await api(`/api/flyers/${encodeURIComponent(f.id)}/slots/${encodeURIComponent(sid)}/offer`, {
        method: 'PUT',
        body: JSON.stringify({
          offer_price_tax_excluded: priceVal,
          limit_text: limitTxt,
        }),
      });
      renderCurrentFlyer(res.flyer);
      if (res.warning) {
        showToast(`⚠️ ${res.warning}`, true);
      } else {
        showToast(clear ? '通常マスタ価格に戻しました。' : 'チラシ特別価格を適用しました。');
      }
    } catch (e) {
      showToast(e.message, true);
    }
  }

  async function runProductSearch() {
    const q = $('inp-prod-q').value.trim();
    const cat = $('sel-prod-cat').value;
    const onSale = $('chk-prod-sale').checked;
    const seasonal = $('chk-prod-seasonal').checked;
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    if (cat) params.set('category', cat);
    if (onSale) params.set('on_sale', 'true');
    if (seasonal) params.set('seasonal', 'true');
    params.set('limit', '24');
    try {
      const res = await api(`/api/products/search?${params.toString()}`);
      const list = $('search-results-list');
      const items = res.products || [];
      if (!items.length) {
        list.innerHTML = '<div style="font-size:12px;color:#666;padding:8px">該当する商品が見つかりませんでした。</div>';
        return;
      }
      list.innerHTML = items
        .map(
          (p) => `
          <div class="prod-result-item">
            <img src="${p.image || ''}" alt=""/>
            <div class="prod-result-item__body">
              <div class="prod-result-item__name">${p.flyer_name || p.title}</div>
              <div class="prod-result-item__meta">${p.category} ／ ${p.unit_label || ''} ／ ${p.origin || '-'}</div>
              <div class="prod-result-item__price">本体 ${Number(p.price_tax_excluded).toLocaleString()}円（税込 ${Number(p.price_tax_included_exact).toFixed(2)}円）</div>
            </div>
            <button type="button" class="btn btn--sm btn--primary" data-replace-pid="${p.id}">反映</button>
          </div>
        `
        )
        .join('');
    } catch (e) {
      showToast(e.message, true);
    }
  }

  async function replaceSlotProduct(newProductId) {
    const f = state.currentFlyer;
    const sid = state.selectedSlotId;
    if (!f || !sid) return;
    try {
      const res = await api(`/api/flyers/${encodeURIComponent(f.id)}`, {
        method: 'PUT',
        body: JSON.stringify({
          slot_update: {
            slot_id: sid,
            product_id: newProductId,
          },
        }),
      });
      renderCurrentFlyer(res.flyer);
      showToast('枠の商品を差し替えました。');
    } catch (e) {
      showToast(e.message, true);
    }
  }

  let loadingStepTimers = [];
  function startFlyerLoadingAnimation(customTitle = '✨ AIが今週のチラシを自動作成しています…') {
    loadingStepTimers.forEach((t) => clearTimeout(t));
    loadingStepTimers = [];
    if ($('sheet-empty-state')) $('sheet-empty-state').hidden = true;
    if ($('sheet-scaler')) $('sheet-scaler').hidden = true;
    const overlay = $('sheet-loading-overlay');
    if (overlay) overlay.hidden = false;
    if ($('loading-main-title')) $('loading-main-title').textContent = customTitle;
    if ($('flyer-status-badge')) {
      $('flyer-status-badge').textContent = 'AI作成中…';
      $('flyer-status-badge').className = 'status-badge is-pending';
    }
    if ($('flyer-meta-title')) {
      $('flyer-meta-title').textContent = 'AIが特売商品のピックアップ・背景透過・紙面レイアウトを組版中…';
    }

    const fill = $('loading-progress-fill');
    const steps = document.querySelectorAll('#loading-steps-list .loading-step');
    const setStep = (activeIdx, pct) => {
      if (fill) fill.style.width = `${pct}%`;
      steps.forEach((el, idx) => {
        el.classList.remove('is-active', 'is-done');
        if (idx < activeIdx) el.classList.add('is-done');
        else if (idx === activeIdx) el.classList.add('is-active');
      });
    };
    setStep(0, 18);
    loadingStepTimers.push(setTimeout(() => setStep(1, 40), 400));
    loadingStepTimers.push(setTimeout(() => setStep(2, 62), 850));
    loadingStepTimers.push(setTimeout(() => setStep(3, 82), 1300));
    loadingStepTimers.push(setTimeout(() => setStep(4, 96), 1700));
  }

  function stopFlyerLoadingAnimation(showEmptyOnError = false) {
    loadingStepTimers.forEach((t) => clearTimeout(t));
    loadingStepTimers = [];
    const fill = $('loading-progress-fill');
    if (fill) fill.style.width = '100%';
    if ($('sheet-loading-overlay')) $('sheet-loading-overlay').hidden = true;
    if (showEmptyOnError && !state.currentFlyer && $('sheet-empty-state')) {
      $('sheet-empty-state').hidden = false;
    }
  }

  async function generateFlyer(baseFlyerId = null) {
    const btn = $('btn-generate');
    const emptyBtn = $('btn-empty-generate');
    btn.disabled = true;
    if (emptyBtn) emptyBtn.disabled = true;
    const origText = btn.textContent;
    btn.textContent = '⏳ AIが商品選定・チラシ作成中…';
    switchTab('editor');
    const startedAt = Date.now();
    startFlyerLoadingAnimation(
      baseFlyerId ? '✨ 過去のチラシをもとに最新マスタ価格で再構成しています…' : '✨ AIが今週のチラシを自動作成しています…'
    );
    try {
      const payload = {
        theme: $('inp-theme').value.trim() || '秋の味覚フェア',
        target: $('inp-target').value.trim() || '40代主婦・4人家族',
        period: {
          from: $('inp-period-from').value || '2026-11-11',
          to: $('inp-period-to').value || '2026-11-17',
        },
        template_id: $('sel-template').value || 'T1',
        item_count: Number($('inp-item-count').value || 20),
        paper: $('sel-paper').value || 'B4-landscape',
        tone: $('sel-tone').value || 'にぎやか',
        numeral_style: $('sel-sheet-numeral').value || 'graphic_pop',
        sheet_bg: $('sel-sheet-bg').value || '',
        store: {
          name: $('inp-store-name').value.trim(),
          prefecture: $('inp-store-pref').value.trim(),
          hours: $('inp-store-hours').value.trim(),
          tel: $('inp-store-tel').value.trim(),
        },
        community: {
          regular_events: $('inp-reg-events').value.trim(),
          announcement: $('inp-announcement').value.trim(),
          reservation: $('inp-reservation').value.trim(),
        },
      };
      if (baseFlyerId) {
        payload.base_flyer_id = baseFlyerId;
      }
      const res = await api('/api/flyers/generate', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      const elapsed = Date.now() - startedAt;
      if (elapsed < 1750) {
        await new Promise((r) => setTimeout(r, 1750 - elapsed));
      }
      stopFlyerLoadingAnimation(false);
      renderCurrentFlyer(res.flyer);
      if (baseFlyerId) {
        showToast('過去のチラシをもとに新規下書きを作成しました（商品マスタから最新情報を反映）。');
      } else {
        showToast('今週のチラシを自動作成しました！枠をクリックして微調整できます。');
      }
    } catch (e) {
      stopFlyerLoadingAnimation(true);
      showToast(e.message, true);
    } finally {
      btn.disabled = false;
      if (emptyBtn) emptyBtn.disabled = false;
      btn.textContent = origText;
    }
  }

  // =========================================================================
  // Fullscreen Modal (`🔍 チラシ全体表示`)
  // =========================================================================
  function openFullscreenModal() {
    if (!state.currentFlyer) return;
    const modal = $('fs-modal');
    modal.hidden = false;
    state.fsZoomScale = 0;
    $('fs-modal-title').textContent = `🔍 チラシ全体表示：${state.currentFlyer.title || ''} （${(state.currentFlyer.slots || []).length}品・${state.currentFlyer.paper}）`;
    const frame = $('fs-preview-frame');
    applySheetScale('fullscreen');
    frame.src = `/api/flyers/${encodeURIComponent(state.currentFlyer.id)}/preview_html?t=${Date.now()}`;
    frame.onload = () => {
      applySheetScale('fullscreen');
    };
  }

  function closeFullscreenModal() {
    $('fs-modal').hidden = true;
  }

  // =========================================================================
  // Tab 2: 3-Column Interactive Template Studio (`📐 チラシテンプレート管理`)
  // =========================================================================
  function initTemplateStudioIfNeeded() {
    if (!state.editingTemplate) {
      const curId = ($('sel-template') && $('sel-template').value) || 'T1';
      loadTemplateIntoStudio(curId);
    } else {
      refreshTemplateStudioPreview();
    }
  }

  function getTemplateSlotIds(tpl) {
    const ids = [];
    (tpl.zones || []).forEach((z) => {
      const hc = Number(z.hero_count || 0);
      const gc = Number(z.grid_count || 0);
      for (let h = 1; h <= hc; h++) ids.push(`${z.id}-hero-${h}`);
      for (let g = 1; g <= gc; g++) ids.push(`${z.id}-grid-${g}`);
    });
    return ids;
  }

  function populateTplSlotSelector(opts = {}) {
    const tpl = state.editingTemplate;
    const sel = $('sel-tpl-slot-id');
    if (!tpl || !sel) return;
    const ids = getTemplateSlotIds(tpl);
    if (!state.selectedTplSlotId || !ids.includes(state.selectedTplSlotId)) {
      state.selectedTplSlotId = ids[0] || '';
    }
    sel.innerHTML = ids
      .map((sid) => `<option value="${sid}" ${sid === state.selectedTplSlotId ? 'selected' : ''}>${sid}</option>`)
      .join('');
    if (!opts.skipLoadForm) {
      loadSelectedTplSlotIntoRightForm();
    }
  }

  function loadSelectedTplSlotIntoRightForm() {
    const tpl = state.editingTemplate;
    const sid = state.selectedTplSlotId;
    if (!tpl || !sid) return;
    const isHero = sid.includes('-hero-');
    const zoneId = sid.split(isHero ? '-hero-' : '-grid-')[0];
    const z = (tpl.zones || []).find((x) => x.id === zoneId) || (tpl.zones || [])[0] || {};
    const ov = ((tpl.slot_overrides || {})[sid]) || {};

    const shape = ov.shape || (isHero ? z.hero_shape || 'overflow_cutout' : z.grid_shape || 'rect');
    const span = ov.size_span || (isHero ? 'hero_2x2' : 'auto');
    const layout = ov.layout_mode || (isHero ? z.hero_layout_mode || 'overlay_full' : z.grid_layout_mode || 'overlay_price');
    const opos = ov.overlay_pos || 'bottom_split';
    const wWeight = Number(ov.width_weight || (isHero ? 1.8 : 1.0));
    const rWeight = Number(ov.row_weight || (isHero ? 1.4 : 1.0));
    const imgScale = Number(ov.img_scale || (shape === 'overflow_cutout' ? 122 : 105));

    if ($('sel-ts-shape')) $('sel-ts-shape').value = shape;
    if ($('sel-ts-span')) $('sel-ts-span').value = span;
    if ($('sel-ts-layout')) $('sel-ts-layout').value = layout;
    if ($('sel-ts-opos')) $('sel-ts-opos').value = opos;
    if ($('inp-ts-w')) {
      $('inp-ts-w').value = wWeight;
      $('lbl-ts-w').textContent = `${wWeight.toFixed(1)}x`;
    }
    if ($('inp-ts-r')) {
      $('inp-ts-r').value = rWeight;
      $('lbl-ts-r').textContent = `${rWeight.toFixed(1)}x`;
    }
    if ($('inp-ts-scale')) {
      $('inp-ts-scale').value = imgScale;
      $('lbl-ts-scale').textContent = `${imgScale}%`;
    }
  }

  function applySelectedTplSlotOverride(opts = {}) {
    const tpl = state.editingTemplate;
    const sid = state.selectedTplSlotId;
    if (!tpl || !sid) return;
    if (!tpl.slot_overrides) tpl.slot_overrides = {};
    const prevOv = tpl.slot_overrides[sid] || {};
    tpl.slot_overrides[sid] = {
      ...prevOv,
      shape: $('sel-ts-shape').value,
      size_span: $('sel-ts-span').value,
      layout_mode: $('sel-ts-layout').value,
      overlay_pos: $('sel-ts-opos').value,
      width_weight: Number($('inp-ts-w').value || 1.0),
      row_weight: Number($('inp-ts-r').value || 1.0),
      img_scale: Number($('inp-ts-scale').value || 110),
    };
    refreshTemplateStudioPreview({ skipSlotFormReset: true });
    if (!opts.silentToast) {
      showToast(`枠「${sid}」のサイズ・形態・重ね配置をプレビューに反映しました。`);
    }
  }

  function loadTemplateIntoStudio(tplId) {
    const found = state.templates.find((t) => t.id === tplId) || state.templates[0];
    if (!found) return;
    state.editingTemplate = JSON.parse(JSON.stringify(found));
    if (!state.editingTemplate.slot_overrides) state.editingTemplate.slot_overrides = {};
    state.selectedTplZoneIdx = 0;
    state.selectedTplSlotId = null;

    if ($('tpl-studio-select')) $('tpl-studio-select').value = found.id;
    $('tpl-studio-name').value = found.name || '';
    $('tpl-studio-paper').value = found.paper || 'B4-landscape';
    $('tpl-studio-tone').value = found.default_tone || 'にぎやか';
    $('tpl-studio-numeral').value = found.default_numeral_style || 'graphic_pop';
    if ($('tpl-studio-layout')) $('tpl-studio-layout').value = found.default_layout_mode || 'overlay_full';

    renderTemplateZoneList();
    loadSelectedTplZoneIntoRightForm();
    populateTplSlotSelector();
    refreshTemplateStudioPreview();
  }

  function renderTemplateZoneList() {
    const list = $('tpl-zone-list');
    if (!list || !state.editingTemplate) return;
    const zones = state.editingTemplate.zones || [];
    list.innerHTML = zones
      .map(
        (z, idx) => `
        <div class="tpl-zone-item ${idx === state.selectedTplZoneIdx ? 'active' : ''}" data-tpl-zidx="${idx}">
          <div>
            <div class="tpl-zone-item__title">${idx + 1}. ${z.title}</div>
            <div class="tpl-zone-item__meta">目玉 ${z.hero_count}枠(${z.hero_shape || 'overflow_cutout'}) ＋ 一般 ${z.grid_count}枠(${z.grid_shape || 'rect'}) ${z.bg_image_url ? '・🎨背景画像あり' : ''}</div>
          </div>
          <span style="font-weight:800;color:#1a73e8">編集 ▶</span>
        </div>
      `
      )
      .join('');
  }

  function loadSelectedTplZoneIntoRightForm() {
    const tpl = state.editingTemplate;
    if (!tpl || !tpl.zones || !tpl.zones.length) return;
    const idx = Math.max(0, Math.min(state.selectedTplZoneIdx, tpl.zones.length - 1));
    state.selectedTplZoneIdx = idx;
    const z = tpl.zones[idx];

    $('tpl-zone-editor-title').textContent = `3. 要素編集：ゾーン #${idx + 1} ＆ 個別枠`;
    $('inp-tz-title').value = z.title || '';
    $('inp-tz-sub').value = z.subtitle || '';
    $('sel-tz-type').value = z.zone_type || 'day_block';
    $('sel-tz-color').value = z.frame_color || 'red';
    $('inp-tz-hero-cnt').value = z.hero_count != null ? z.hero_count : 1;
    $('inp-tz-grid-cnt').value = z.grid_count != null ? z.grid_count : 3;
    $('inp-tz-weight').value = z.weight != null ? z.weight : 1.0;
    $('sel-tz-hero-shape').value = z.hero_shape || 'overflow_cutout';
    $('sel-tz-grid-shape').value = z.grid_shape || 'rect';
    if ($('sel-tz-hero-layout')) $('sel-tz-hero-layout').value = z.hero_layout_mode || 'overlay_full';
    if ($('sel-tz-grid-layout')) $('sel-tz-grid-layout').value = z.grid_layout_mode || 'overlay_price';
    $('inp-tz-badge').value = z.default_badge || '特価';
    $('inp-tz-uniform').value = z.uniform_price_ex || '';

    const cats = new Set(z.categories || []);
    document.querySelectorAll('.chk-tz-cat').forEach((chk) => {
      chk.checked = cats.has(chk.value);
    });
  }

  function pullTplZoneFormIntoState() {
    const tpl = state.editingTemplate;
    if (!tpl || !tpl.zones || !tpl.zones.length) return;
    tpl.name = $('tpl-studio-name').value.trim() || tpl.name;
    tpl.paper = $('tpl-studio-paper').value || 'B4-landscape';
    tpl.default_tone = $('tpl-studio-tone').value || 'にぎやか';
    tpl.default_numeral_style = $('tpl-studio-numeral').value || 'graphic_pop';
    if ($('tpl-studio-layout')) tpl.default_layout_mode = $('tpl-studio-layout').value || 'overlay_full';

    const z = tpl.zones[state.selectedTplZoneIdx];
    if (z) {
      z.title = $('inp-tz-title').value.trim() || '特売コーナー';
      z.subtitle = $('inp-tz-sub').value.trim();
      z.zone_type = $('sel-tz-type').value;
      z.frame_color = $('sel-tz-color').value;
      z.hero_count = Math.max(0, Number($('inp-tz-hero-cnt').value || 0));
      z.grid_count = Math.max(0, Number($('inp-tz-grid-cnt').value || 0));
      if (z.hero_count + z.grid_count === 0) z.grid_count = 1;
      z.weight = Math.max(0.4, Number($('inp-tz-weight').value || 1.0));
      z.hero_shape = $('sel-tz-hero-shape').value;
      z.grid_shape = $('sel-tz-grid-shape').value;
      if ($('sel-tz-hero-layout')) z.hero_layout_mode = $('sel-tz-hero-layout').value;
      if ($('sel-tz-grid-layout')) z.grid_layout_mode = $('sel-tz-grid-layout').value;
      z.default_badge = $('inp-tz-badge').value.trim() || '特価';
      const uVal = Number($('inp-tz-uniform').value || 0);
      z.uniform_price_ex = uVal > 0 ? uVal : null;
      z.uniform_price_inc = uVal > 0 ? Math.round(uVal * 1.08) : null;
      const selectedCats = [];
      document.querySelectorAll('.chk-tz-cat:checked').forEach((chk) => selectedCats.push(chk.value));
      z.categories = selectedCats;
    }
    tpl.default_item_count = tpl.zones.reduce((acc, item) => acc + Number(item.hero_count || 0) + Number(item.grid_count || 0), 0);
  }

  async function refreshTemplateStudioPreview(opts = {}) {
    if (!state.editingTemplate) return;
    pullTplZoneFormIntoState();
    renderTemplateZoneList();
    populateTplSlotSelector({ skipLoadForm: Boolean(opts.skipSlotFormReset) });
    $('tpl-preview-title').textContent = `${state.editingTemplate.name} （標準 ${state.editingTemplate.default_item_count}品・${state.editingTemplate.zones.length}ゾーン）`;
    try {
      const res = await fetch('/api/templates/preview_html', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(state.editingTemplate),
      });
      const htmlStr = await res.text();
      const frame = $('tpl-preview-frame');
      applySheetScale('template');
      frame.srcdoc = htmlStr;
      frame.onload = () => {
        applySheetScale('template');
        try {
          const doc = frame.contentDocument;
          if (!doc) return;
          doc.querySelectorAll('.ch-zone').forEach((zEl, idx) => {
            zEl.addEventListener('click', (ev) => {
              ev.preventDefault();
              ev.stopPropagation();
              state.selectedTplZoneIdx = idx;
              renderTemplateZoneList();
              loadSelectedTplZoneIntoRightForm();
            });
          });
          doc.querySelectorAll('.ch-slot').forEach((sEl) => {
            sEl.addEventListener('click', (ev) => {
              ev.preventDefault();
              ev.stopPropagation();
              const sid = sEl.getAttribute('data-slot-id');
              const zid = sEl.getAttribute('data-zone-id');
              const zIdx = (state.editingTemplate.zones || []).findIndex((z) => z.id === zid);
              if (zIdx >= 0) {
                state.selectedTplZoneIdx = zIdx;
                renderTemplateZoneList();
                loadSelectedTplZoneIntoRightForm();
              }
              state.selectedTplSlotId = sid;
              if ($('sel-tpl-slot-id')) $('sel-tpl-slot-id').value = sid;
              loadSelectedTplSlotIntoRightForm();
              doc.querySelectorAll('.ch-slot').forEach((el) => {
                el.style.outline = el.getAttribute('data-slot-id') === sid ? '1.3mm solid #1a73e8' : '';
              });
            });
          });
          if (state.selectedTplSlotId) {
            doc.querySelectorAll('.ch-slot').forEach((el) => {
              el.style.outline = el.getAttribute('data-slot-id') === state.selectedTplSlotId ? '1.3mm solid #1a73e8' : '';
            });
          }
        } catch (e) {
          console.warn(e);
        }
      };
    } catch (e) {
      showToast('テンプレートプレビューの更新に失敗しました。', true);
    }
  }

  async function generateAndApplyTemplateBgImage(clear = false) {
    const tpl = state.editingTemplate;
    if (!tpl) return;
    const target = $('sel-bg-target').value || 'slot';
    if (clear) {
      if (target === 'sheet') {
        tpl.bg_image_url = '';
      } else if (target === 'zone' && tpl.zones[state.selectedTplZoneIdx]) {
        tpl.zones[state.selectedTplZoneIdx].bg_image_url = '';
      } else if (target === 'slot' && state.selectedTplSlotId) {
        if (!tpl.slot_overrides) tpl.slot_overrides = {};
        if (tpl.slot_overrides[state.selectedTplSlotId]) {
          tpl.slot_overrides[state.selectedTplSlotId].bg_image_url = '';
        }
      }
      $('bg-gen-preview').hidden = true;
      await refreshTemplateStudioPreview();
      showToast('背景画像を解除しました。');
      return;
    }

    const btn = $('btn-gen-bg');
    btn.disabled = true;
    const origTxt = btn.textContent;
    btn.textContent = '⏳ 背景AI生成中…';
    try {
      const res = await api('/api/bg_images/generate', {
        method: 'POST',
        body: JSON.stringify({
          preset_id: $('sel-bg-preset').value || 'autumn_wood',
          prompt: $('inp-bg-prompt').value.trim(),
        }),
      });
      const bgUrl = res.bg.url;
      if (target === 'sheet') {
        tpl.bg_image_url = bgUrl;
      } else if (target === 'zone' && tpl.zones[state.selectedTplZoneIdx]) {
        tpl.zones[state.selectedTplZoneIdx].bg_image_url = bgUrl;
      } else if (target === 'slot' && state.selectedTplSlotId) {
        if (!tpl.slot_overrides) tpl.slot_overrides = {};
        tpl.slot_overrides[state.selectedTplSlotId] = {
          ...(tpl.slot_overrides[state.selectedTplSlotId] || {}),
          bg_image_url: bgUrl,
        };
      }
      const prevBox = $('bg-gen-preview');
      prevBox.hidden = false;
      prevBox.innerHTML = `<img src="${bgUrl}" alt="生成背景"/><span>背景画像を生成・適用しました（適用先: ${target === 'slot' ? state.selectedTplSlotId : target === 'zone' ? '選択ゾーン' : '紙面全体'}）</span>`;
      await refreshTemplateStudioPreview();
      showToast('商品の背景画像をAI生成し、テンプレートに適用しました！');
    } catch (e) {
      showToast(e.message, true);
    } finally {
      btn.disabled = false;
      btn.textContent = origTxt;
    }
  }

  async function saveTemplateFromStudio() {
    if (!state.editingTemplate) return;
    pullTplZoneFormIntoState();
    try {
      const res = await api('/api/templates', {
        method: 'POST',
        body: JSON.stringify({
          base_template_id: state.editingTemplate.id || 'T1',
          name: state.editingTemplate.name,
          description: state.editingTemplate.description || '',
          paper: state.editingTemplate.paper,
          default_tone: state.editingTemplate.default_tone,
          default_numeral_style: state.editingTemplate.default_numeral_style,
          default_layout_mode: state.editingTemplate.default_layout_mode || 'overlay_full',
          bg_image_url: state.editingTemplate.bg_image_url || '',
          slot_overrides: state.editingTemplate.slot_overrides || {},
          default_item_count: state.editingTemplate.default_item_count,
          zones: state.editingTemplate.zones,
        }),
      });
      const meta = await api('/api/templates');
      state.templates = meta.templates || [];
      populateMetadataSelectors();
      state.editingTemplate = res.template;
      $('tpl-studio-select').value = res.template.id;
      $('sel-template').value = res.template.id;
      if ($('sel-toolbar-template')) $('sel-toolbar-template').value = res.template.id;
      $('inp-item-count').value = res.template.default_item_count;
      showToast(`テンプレート「${res.template.name}」(${res.template.id}) を保存しました！`);
    } catch (e) {
      showToast(e.message, true);
    }
  }

  // =========================================================================
  // Tab 3: Archive List (`🗂️ 過去のチラシ・GCS保管庫`)
  // =========================================================================
  async function loadArchiveList() {
    const q = $('inp-arch-q') ? $('inp-arch-q').value.trim() : '';
    try {
      const res = await api(`/api/archive?q=${encodeURIComponent(q)}`);
      const appGrid = $('approved-list');
      const drGrid = $('drafts-list');

      const renderCard = (d, isApproved) => {
        const pFrom = (d.period && d.period.from) || '';
        const pTo = (d.period && d.period.to) || '';
        const discBadge =
          d.currently_discontinued_count > 0
            ? `<span style="background:#ffebee;color:#c62828;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:800">現在販売終了商品 ${d.currently_discontinued_count}点含む</span>`
            : '';
        const sampleBadge = d.is_sample
          ? `<span style="background:#fff3e0;color:#e65100;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:800">販売終了テスト用サンプル</span>`
          : '';
        return `
          <div class="arch-card">
            <div>
              <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">
                <span class="status-badge ${isApproved ? 'is-approved' : ''}">${d.status}</span>
                ${sampleBadge}${discBadge}
              </div>
              <div class="arch-card__title">${d.title || '無題のチラシ'}</div>
              <div class="arch-card__meta">
                <div>テーマ: <strong>${d.theme || '-'}</strong> ／ ターゲット: ${d.target || '-'}</div>
                <div>売出期間: ${pFrom} 〜 ${pTo} ／ テンプレ: ${d.template_id}（${d.item_count}品）</div>
                <div>作成: ${(d.created_by && d.created_by.name) || '-'} ${d.approved_by ? `／ 承認: <strong>${d.approved_by.name}</strong>` : ''}</div>
                ${d.gcs_prefix ? `<div style="color:#1b5e20">GCS保管先: ${d.gcs_prefix}</div>` : ''}
              </div>
            </div>
            <div class="arch-card__actions">
              <button type="button" class="btn btn--sm btn--secondary" data-open-flyer="${d.id}">👁️ 紙面を確認する</button>
              <button type="button" class="btn btn--sm btn--primary" data-reuse-flyer="${d.id}">✨ このチラシをもとに新規作成</button>
              <a class="btn btn--sm btn--export" href="/api/flyers/${encodeURIComponent(d.id)}/export?format=pdf" target="_blank">PDF</a>
            </div>
          </div>
        `;
      };

      appGrid.innerHTML =
        (res.archived || []).map((d) => renderCard(d, true)).join('') ||
        '<div style="color:#666;font-size:13px">承認済みのチラシはまだありません。</div>';
      drGrid.innerHTML =
        (res.drafts || []).map((d) => renderCard(d, false)).join('') ||
        '<div style="color:#666;font-size:13px">作業中の下書きはありません。</div>';
    } catch (e) {
      showToast(e.message, true);
    }
  }

  async function saveCurrentAsTemplate() {
    const f = state.currentFlyer;
    if (!f) return;
    const name = window.prompt('保存するテンプレート名を入力してください：', `${f.theme || 'マイ'}テンプレート（${(f.slots || []).length}品）`);
    if (!name || !name.trim()) return;
    try {
      const res = await api('/api/templates', {
        method: 'POST',
        body: JSON.stringify({
          name: name.trim(),
          base_template_id: f.template_id || 'T1',
          paper: f.paper || 'B4-landscape',
          default_tone: f.tone || 'にぎやか',
          default_numeral_style: f.numeral_style || 'graphic_pop',
          bg_image_url: f.bg_image_url || '',
          default_item_count: (f.slots || []).length,
          zones: f.zones || [],
        }),
      });
      const meta = await api('/api/templates');
      state.templates = meta.templates || [];
      populateMetadataSelectors();
      $('sel-template').value = res.template.id;
      showToast(`テンプレート「${res.template.name}」を保存しました。`);
    } catch (e) {
      showToast(e.message, true);
    }
  }

  function wireEvents() {
    window.addEventListener('resize', () => {
      applySheetScale('editor');
      if (!$('fs-modal').hidden) applySheetScale('fullscreen');
      if (!$('view-templates').hidden) applySheetScale('template');
    });

    // Tabs
    ['editor', 'templates', 'archive'].forEach((t) => {
      const btn = $(`tab-btn-${t}`);
      if (btn) btn.addEventListener('click', () => switchTab(t));
    });
    if ($('brand-home-link')) {
      $('brand-home-link').addEventListener('click', (e) => {
        e.preventDefault();
        switchTab('editor');
      });
    }
    if ($('btn-open-tpl-studio')) {
      $('btn-open-tpl-studio').addEventListener('click', () => {
        const curId = ($('sel-template') && $('sel-template').value) || 'T1';
        loadTemplateIntoStudio(curId);
        switchTab('templates');
      });
    }

    // Visual template cards & dropdowns in Editor
    if ($('editor-template-cards')) {
      $('editor-template-cards').addEventListener('click', (e) => {
        const card = e.target.closest('[data-pick-tpl]');
        if (!card) return;
        applyTemplateToCurrentFlyer(card.getAttribute('data-pick-tpl'));
      });
    }
    $('sel-template').addEventListener('change', (e) => applyTemplateToCurrentFlyer(e.target.value));
    if ($('sel-toolbar-template')) {
      $('sel-toolbar-template').addEventListener('change', (e) => applyTemplateToCurrentFlyer(e.target.value));
    }

    // Zoom & Fullscreen Modal controls
    $('btn-zoom-fit').addEventListener('click', () => {
      state.zoomScale = 0;
      applySheetScale('editor');
    });
    $('btn-zoom-in').addEventListener('click', () => {
      const cur = state.zoomScale || 0.65;
      state.zoomScale = Math.min(1.5, cur + 0.12);
      applySheetScale('editor');
    });
    $('btn-zoom-out').addEventListener('click', () => {
      const cur = state.zoomScale || 0.65;
      state.zoomScale = Math.max(0.35, cur - 0.12);
      applySheetScale('editor');
    });
    $('btn-fullscreen-view').addEventListener('click', openFullscreenModal);
    $('btn-fs-close').addEventListener('click', closeFullscreenModal);
    $('btn-fs-zoom-fit').addEventListener('click', () => {
      state.fsZoomScale = 0;
      applySheetScale('fullscreen');
    });
    $('btn-fs-zoom-100').addEventListener('click', () => {
      state.fsZoomScale = 1.0;
      applySheetScale('fullscreen');
    });
    $('btn-fs-zoom-in').addEventListener('click', () => {
      const cur = state.fsZoomScale || 0.85;
      state.fsZoomScale = Math.min(1.8, cur + 0.15);
      applySheetScale('fullscreen');
    });
    $('btn-fs-zoom-out').addEventListener('click', () => {
      const cur = state.fsZoomScale || 0.85;
      state.fsZoomScale = Math.max(0.4, cur - 0.15);
      applySheetScale('fullscreen');
    });
    $('btn-fs-pdf').addEventListener('click', () => {
      if (state.currentFlyer) window.open(`/api/flyers/${encodeURIComponent(state.currentFlyer.id)}/export?format=pdf`, '_blank');
    });
    $('btn-fs-jpeg').addEventListener('click', () => {
      if (state.currentFlyer) window.open(`/api/flyers/${encodeURIComponent(state.currentFlyer.id)}/export?format=jpeg&dpi=300`, '_blank');
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !$('fs-modal').hidden) closeFullscreenModal();
    });

    // User switcher
    $('user-select').addEventListener('change', async (e) => {
      try {
        const res = await api('/api/me/switch', {
          method: 'POST',
          body: JSON.stringify({ user_id: e.target.value }),
        });
        state.user = res.user;
        syncUserUI();
        showToast(`ログインユーザーを「${state.user.name}」に切り替えました。`);
      } catch (err) {
        showToast(err.message, true);
      }
    });

    // Theme & Target preset chips
    $('theme-presets').addEventListener('click', (e) => {
      const btn = e.target.closest('[data-theme]');
      if (!btn) return;
      $('inp-theme').value = btn.getAttribute('data-theme');
      if (btn.getAttribute('data-target')) {
        $('inp-target').value = btn.getAttribute('data-target');
      }
    });
    $('target-presets').addEventListener('click', (e) => {
      const btn = e.target.closest('[data-target-only]');
      if (!btn) return;
      $('inp-target').value = btn.getAttribute('data-target-only');
    });

    // Generate & Reselect & Save Template
    $('btn-generate').addEventListener('click', () => generateFlyer(null));
    if ($('btn-empty-generate')) {
      $('btn-empty-generate').addEventListener('click', () => generateFlyer(null));
    }
    $('btn-reselect').addEventListener('click', async () => {
      if (!state.currentFlyer) {
        await generateFlyer(null);
        return;
      }
      startFlyerLoadingAnimation('🔄 固定枠以外の商品を再ピックアップしています…');
      const startedAt = Date.now();
      try {
        const res = await api(`/api/flyers/${encodeURIComponent(state.currentFlyer.id)}/reselect`, {
          method: 'POST',
          body: JSON.stringify({
            theme: $('inp-theme').value.trim(),
            target: $('inp-target').value.trim(),
            item_count: Number($('inp-item-count').value || 20),
          }),
        });
        const elapsed = Date.now() - startedAt;
        if (elapsed < 1200) await new Promise((r) => setTimeout(r, 1200 - elapsed));
        stopFlyerLoadingAnimation(false);
        renderCurrentFlyer(res.flyer);
        showToast('固定枠以外の商品を再ピックアップしました。');
      } catch (e) {
        stopFlyerLoadingAnimation(false);
        showToast(e.message, true);
      }
    });
    $('btn-save-as-tpl').addEventListener('click', saveCurrentAsTemplate);

    // Headlines & Sheet Background / Numeral update
    $('btn-apply-headlines').addEventListener('click', async () => {
      if (!state.currentFlyer) return;
      try {
        const res = await api(`/api/flyers/${encodeURIComponent(state.currentFlyer.id)}`, {
          method: 'PUT',
          body: JSON.stringify({
            title: $('inp-flyer-title').value.trim(),
            subtitle: $('inp-flyer-subtitle').value.trim(),
            numeral_style: $('sel-sheet-numeral').value,
            sheet_bg: $('sel-sheet-bg').value,
            paper: $('sel-paper').value,
            tone: $('sel-tone').value,
          }),
        });
        renderCurrentFlyer(res.flyer);
        showToast('見出し・紙面背景・全体設定を反映しました。');
      } catch (e) {
        showToast(e.message, true);
      }
    });
    $('sel-sheet-bg').addEventListener('change', () => $('btn-apply-headlines').click());
    $('sel-sheet-numeral').addEventListener('change', () => $('btn-apply-headlines').click());

    // Approval workflow buttons
    $('btn-submit-review').addEventListener('click', async () => {
      if (!state.currentFlyer) return;
      try {
        const res = await api(`/api/flyers/${encodeURIComponent(state.currentFlyer.id)}/submit`, { method: 'POST' });
        renderCurrentFlyer(res.flyer);
        showToast('店舗責任者へ確認を依頼しました。');
      } catch (e) {
        showToast(e.message, true);
      }
    });
    $('btn-approve').addEventListener('click', async () => {
      if (!state.currentFlyer) return;
      try {
        const res = await api(`/api/flyers/${encodeURIComponent(state.currentFlyer.id)}/approve`, { method: 'POST' });
        renderCurrentFlyer(res.flyer);
        showToast(`✅ ${state.user.name}として承認し、GCSにスナップショット・PDF・JPEGを保管しました。`);
      } catch (e) {
        showToast(e.message, true);
      }
    });
    $('btn-reject').addEventListener('click', async () => {
      if (!state.currentFlyer) return;
      try {
        const res = await api(`/api/flyers/${encodeURIComponent(state.currentFlyer.id)}/reject`, {
          method: 'POST',
          body: JSON.stringify({ comment: '一部商品の価格・コピーを再調整してください。' }),
        });
        renderCurrentFlyer(res.flyer);
        showToast('チラシを下書きに差し戻しました。');
      } catch (e) {
        showToast(e.message, true);
      }
    });

    // Export buttons (High-Resolution 300 DPI standard / 400 DPI print master)
    $('btn-export-pdf').addEventListener('click', () => {
      if (!state.currentFlyer) return;
      window.open(`/api/flyers/${encodeURIComponent(state.currentFlyer.id)}/export?format=pdf`, '_blank');
    });
    $('btn-export-jpeg').addEventListener('click', () => {
      if (!state.currentFlyer) return;
      window.open(`/api/flyers/${encodeURIComponent(state.currentFlyer.id)}/export?format=jpeg&dpi=300`, '_blank');
    });
    $('btn-export-jpeg-print').addEventListener('click', () => {
      if (!state.currentFlyer) return;
      window.open(`/api/flyers/${encodeURIComponent(state.currentFlyer.id)}/export?format=jpeg&dpi=400`, '_blank');
    });

    // Right slot inspector sliders & events — AUTO-APPLY IMMEDIATELY on change / debounced input
    let slotAutoSaveTimer = null;
    const scheduleSlotAutoSave = (delay = 180) => {
      if (slotAutoSaveTimer) clearTimeout(slotAutoSaveTimer);
      slotAutoSaveTimer = setTimeout(() => {
        saveSelectedSlotChanges({ silentToast: true });
      }, delay);
    };

    const syncSpanPresetToSliders = (spanVal, wElId, wLblId, rElId, rLblId) => {
      const map = {
        hero_2x2: [2.1, 1.5],
        wide_2x1: [1.8, 1.0],
        tall_1x2: [1.3, 1.6],
        std_1x1: [1.0, 1.0],
        auto: [1.0, 1.0],
      };
      const pair = map[spanVal];
      if (!pair) return;
      if ($(wElId)) {
        $(wElId).value = pair[0];
        if ($(wLblId)) $(wLblId).textContent = `${pair[0].toFixed(1)}x`;
      }
      if ($(rElId)) {
        $(rElId).value = pair[1];
        if ($(rLblId)) $(rLblId).textContent = `${pair[1].toFixed(1)}x`;
      }
    };

    const liveMutateFrameSlot = (frameId, slotId, wVal, rVal, scaleVal) => {
      const frame = $(frameId);
      if (!frame || !frame.contentDocument || !slotId) return;
      const el = frame.contentDocument.querySelector(`.ch-slot[data-slot-id="${slotId}"]`);
      if (!el) return;
      if (wVal != null) el.style.flex = `${Number(wVal).toFixed(2)} 1 0%`;
      if (scaleVal != null) el.style.setProperty('--img-scale', (Number(scaleVal) / 100).toFixed(2));
      if (rVal != null && el.parentElement && el.parentElement.classList.contains('ch-bento-row')) {
        el.parentElement.style.flex = `${Number(rVal).toFixed(2)} 1 0%`;
      }
    };

    [
      'sel-slot-shape',
      'sel-slot-layout',
      'sel-slot-opos',
      'sel-slot-numeral',
      'sel-slot-price-style',
      'sel-slot-bg',
      'chk-slot-locked',
    ].forEach((id) => {
      if ($(id)) {
        $(id).addEventListener('change', () => saveSelectedSlotChanges({ silentToast: true }));
      }
    });

    if ($('sel-slot-span')) {
      $('sel-slot-span').addEventListener('change', (e) => {
        syncSpanPresetToSliders(e.target.value, 'inp-slot-w-weight', 'lbl-slot-w', 'inp-slot-r-weight', 'lbl-slot-r');
        saveSelectedSlotChanges({ silentToast: true });
      });
    }

    $('inp-slot-w-weight').addEventListener('input', (e) => {
      $('lbl-slot-w').textContent = `${Number(e.target.value).toFixed(1)}x`;
      liveMutateFrameSlot('preview-frame', state.selectedSlotId, e.target.value, null, null);
      scheduleSlotAutoSave(180);
    });
    $('inp-slot-r-weight').addEventListener('input', (e) => {
      $('lbl-slot-r').textContent = `${Number(e.target.value).toFixed(1)}x`;
      liveMutateFrameSlot('preview-frame', state.selectedSlotId, null, e.target.value, null);
      scheduleSlotAutoSave(180);
    });
    $('inp-slot-img-scale').addEventListener('input', (e) => {
      $('lbl-img-scale').textContent = `${e.target.value}%`;
      liveMutateFrameSlot('preview-frame', state.selectedSlotId, null, null, e.target.value);
      scheduleSlotAutoSave(180);
    });
    ['inp-slot-badge', 'inp-slot-copy'].forEach((id) => {
      if ($(id)) {
        $(id).addEventListener('input', () => scheduleSlotAutoSave(260));
        $(id).addEventListener('change', () => saveSelectedSlotChanges({ silentToast: true }));
      }
    });
    $('badge-preset-chips').addEventListener('click', (e) => {
      const b = e.target.closest('[data-badge-chip]');
      if (!b) return;
      $('inp-slot-badge').value = b.getAttribute('data-badge-chip');
      saveSelectedSlotChanges({ silentToast: true });
    });
    $('btn-save-slot').addEventListener('click', () => saveSelectedSlotChanges({ silentToast: false }));
    $('btn-ai-suggest-slot').addEventListener('click', async () => {
      if (!state.currentFlyer || !state.selectedSlotId) return;
      try {
        const res = await api(
          `/api/flyers/${encodeURIComponent(state.currentFlyer.id)}/slots/${encodeURIComponent(state.selectedSlotId)}/suggest`,
          { method: 'POST' }
        );
        renderCurrentFlyer(res.flyer);
        showToast('AIが代替のおすすめ商品を提案・反映しました。');
      } catch (e) {
        showToast(e.message, true);
      }
    });

    $('inp-offer-price').addEventListener('input', updateOfferTaxPreview);
    $('inp-offer-price').addEventListener('change', () => {
      if ($('inp-offer-price').value) applySpecialOffer(false);
    });
    $('inp-offer-limit').addEventListener('change', () => {
      if ($('inp-offer-price').value) applySpecialOffer(false);
    });
    $('btn-apply-offer').addEventListener('click', () => applySpecialOffer(false));
    $('btn-clear-offer').addEventListener('click', () => applySpecialOffer(true));

    $('btn-prod-search').addEventListener('click', runProductSearch);
    $('inp-prod-q').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        runProductSearch();
      }
    });
    $('sel-prod-cat').addEventListener('change', runProductSearch);
    $('chk-prod-sale').addEventListener('change', runProductSearch);
    $('chk-prod-seasonal').addEventListener('change', runProductSearch);

    $('search-results-list').addEventListener('click', (e) => {
      const btn = e.target.closest('[data-replace-pid]');
      if (!btn) return;
      replaceSlotProduct(btn.getAttribute('data-replace-pid'));
    });

    // Template Studio events (including Individual Slot Overrides & AI Background Image Generation) — AUTO-APPLY IMMEDIATELY
    let tplSlotAutoTimer = null;
    const scheduleTplSlotAutoApply = (delay = 180) => {
      if (tplSlotAutoTimer) clearTimeout(tplSlotAutoTimer);
      tplSlotAutoTimer = setTimeout(() => {
        applySelectedTplSlotOverride({ silentToast: true });
      }, delay);
    };

    let tplZoneAutoTimer = null;
    const scheduleTplZoneAutoRefresh = (delay = 220) => {
      if (tplZoneAutoTimer) clearTimeout(tplZoneAutoTimer);
      tplZoneAutoTimer = setTimeout(() => {
        refreshTemplateStudioPreview();
      }, delay);
    };

    $('tpl-studio-select').addEventListener('change', (e) => loadTemplateIntoStudio(e.target.value));
    $('sel-tpl-slot-id').addEventListener('change', (e) => {
      state.selectedTplSlotId = e.target.value;
      loadSelectedTplSlotIntoRightForm();
      const frame = $('tpl-preview-frame');
      if (frame && frame.contentDocument) {
        frame.contentDocument.querySelectorAll('.ch-slot').forEach((el) => {
          el.style.outline = el.getAttribute('data-slot-id') === state.selectedTplSlotId ? '1.3mm solid #1a73e8' : '';
        });
      }
    });
    ['sel-ts-shape', 'sel-ts-layout', 'sel-ts-opos'].forEach((id) => {
      if ($(id)) {
        $(id).addEventListener('change', () => applySelectedTplSlotOverride({ silentToast: true }));
      }
    });
    if ($('sel-ts-span')) {
      $('sel-ts-span').addEventListener('change', (e) => {
        syncSpanPresetToSliders(e.target.value, 'inp-ts-w', 'lbl-ts-w', 'inp-ts-r', 'lbl-ts-r');
        applySelectedTplSlotOverride({ silentToast: true });
      });
    }
    $('inp-ts-w').addEventListener('input', (e) => {
      $('lbl-ts-w').textContent = `${Number(e.target.value).toFixed(1)}x`;
      liveMutateFrameSlot('tpl-preview-frame', state.selectedTplSlotId, e.target.value, null, null);
      scheduleTplSlotAutoApply(180);
    });
    $('inp-ts-r').addEventListener('input', (e) => {
      $('lbl-ts-r').textContent = `${Number(e.target.value).toFixed(1)}x`;
      liveMutateFrameSlot('tpl-preview-frame', state.selectedTplSlotId, null, e.target.value, null);
      scheduleTplSlotAutoApply(180);
    });
    $('inp-ts-scale').addEventListener('input', (e) => {
      $('lbl-ts-scale').textContent = `${e.target.value}%`;
      liveMutateFrameSlot('tpl-preview-frame', state.selectedTplSlotId, null, null, e.target.value);
      scheduleTplSlotAutoApply(180);
    });
    $('btn-ts-apply').addEventListener('click', () => applySelectedTplSlotOverride({ silentToast: false }));

    [
      'sel-tz-type',
      'sel-tz-color',
      'sel-tz-hero-shape',
      'sel-tz-grid-shape',
      'sel-tz-hero-layout',
      'sel-tz-grid-layout',
      'tpl-studio-paper',
      'tpl-studio-tone',
      'tpl-studio-numeral',
      'tpl-studio-layout',
    ].forEach((id) => {
      if ($(id)) {
        $(id).addEventListener('change', () => refreshTemplateStudioPreview());
      }
    });
    [
      'inp-tz-title',
      'inp-tz-sub',
      'inp-tz-hero-cnt',
      'inp-tz-grid-cnt',
      'inp-tz-weight',
      'inp-tz-badge',
      'inp-tz-uniform',
      'tpl-studio-name',
    ].forEach((id) => {
      if ($(id)) {
        $(id).addEventListener('input', () => scheduleTplZoneAutoRefresh(240));
        $(id).addEventListener('change', () => refreshTemplateStudioPreview());
      }
    });
    if ($('tz-cat-checkboxes')) {
      $('tz-cat-checkboxes').addEventListener('change', () => refreshTemplateStudioPreview());
    }

    $('btn-gen-bg').addEventListener('click', () => generateAndApplyTemplateBgImage(false));
    $('btn-clear-bg').addEventListener('click', () => generateAndApplyTemplateBgImage(true));

    $('tpl-zone-list').addEventListener('click', (e) => {
      const item = e.target.closest('[data-tpl-zidx]');
      if (!item) return;
      pullTplZoneFormIntoState();
      state.selectedTplZoneIdx = Number(item.getAttribute('data-tpl-zidx'));
      renderTemplateZoneList();
      loadSelectedTplZoneIntoRightForm();
    });
    $('btn-tpl-add-zone').addEventListener('click', () => {
      if (!state.editingTemplate) return;
      pullTplZoneFormIntoState();
      state.editingTemplate.zones.push({
        id: `zone-${Date.now().toString(36)}`,
        title: '新規特売コーナー',
        subtitle: 'バイヤー厳選のお買い得品',
        zone_type: 'day_block',
        frame_color: 'red',
        weight: 1.0,
        bg_image_url: '',
        categories: ['野菜・果物', 'お肉・お肉加工品'],
        hero_count: 1,
        grid_count: 3,
        hero_shape: 'overflow_cutout',
        grid_shape: 'rect',
        hero_layout_mode: 'overlay_full',
        grid_layout_mode: 'overlay_price',
        default_badge: '特価',
      });
      state.selectedTplZoneIdx = state.editingTemplate.zones.length - 1;
      renderTemplateZoneList();
      loadSelectedTplZoneIntoRightForm();
      refreshTemplateStudioPreview();
    });
    $('btn-tz-apply').addEventListener('click', () => {
      refreshTemplateStudioPreview();
      showToast('ゾーン構成をテンプレートプレビューに反映しました。');
    });
    $('btn-tz-delete').addEventListener('click', () => {
      if (!state.editingTemplate || (state.editingTemplate.zones || []).length <= 1) {
        showToast('最低1つのゾーンが必要です。', true);
        return;
      }
      state.editingTemplate.zones.splice(state.selectedTplZoneIdx, 1);
      state.selectedTplZoneIdx = 0;
      loadSelectedTplZoneIntoRightForm();
      refreshTemplateStudioPreview();
      showToast('ゾーンを削除しました。');
    });
    $('btn-tpl-refresh-preview').addEventListener('click', refreshTemplateStudioPreview);
    $('btn-tpl-save').addEventListener('click', saveTemplateFromStudio);
    $('btn-tpl-create-flyer').addEventListener('click', async () => {
      await saveTemplateFromStudio();
      switchTab('editor');
      await generateFlyer(null);
    });

    // Archive list actions
    $('btn-arch-refresh').addEventListener('click', loadArchiveList);
    document.addEventListener('click', async (e) => {
      const openBtn = e.target.closest('[data-open-flyer]');
      if (openBtn) {
        const fid = openBtn.getAttribute('data-open-flyer');
        try {
          const res = await api(`/api/flyers/${encodeURIComponent(fid)}`);
          switchTab('editor');
          renderCurrentFlyer(res.flyer);
          showToast(`チラシ「${res.flyer.title}」を表示しました。`);
        } catch (err) {
          showToast(err.message, true);
        }
        return;
      }
      const reuseBtn = e.target.closest('[data-reuse-flyer]');
      if (reuseBtn) {
        const fid = reuseBtn.getAttribute('data-reuse-flyer');
        await generateFlyer(fid);
        return;
      }
    });
  }

  async function init() {
    wireEvents();
    try {
      const [meRes, tplRes] = await Promise.all([api('/api/me'), api('/api/templates')]);
      state.user = meRes.user;
      state.availableUsers = meRes.available_users || [];
      state.templates = tplRes.templates || [];
      state.frameShapes = tplRes.frame_shapes || [];
      state.layoutModes = tplRes.layout_modes || [];
      state.overlayPositions = tplRes.overlay_positions || [];
      state.slotSpans = tplRes.slot_spans || [];
      state.numeralStyles = tplRes.numeral_styles || [];
      state.slotBgPalettes = tplRes.slot_bg_palettes || [];
      state.bgPresets = tplRes.bg_presets || [];
      state.priceStyles = tplRes.price_styles || [];
      state.badgePresets = tplRes.badge_presets || [];
      state.paperFormats = tplRes.paper_formats || [];
      state.categories = tplRes.categories || [];
      syncUserUI();
      populateMetadataSelectors();

      if (window.location.hash === '#template' || window.location.hash === '#templates') {
        switchTab('templates');
      } else if (window.location.hash === '#archive') {
        switchTab('archive');
      } else if (window.location.hash === '#loading') {
        updateToolbarPermissions();
        startFlyerLoadingAnimation('✨ AIが今週のチラシを自動作成しています…');
      } else {
        // Do NOT auto-generate on initial load: show the welcoming guide screen (#sheet-empty-state)
        updateToolbarPermissions();
      }
    } catch (e) {
      showToast(e.message, true);
    }
  }

  document.addEventListener('DOMContentLoaded', init);
})();
