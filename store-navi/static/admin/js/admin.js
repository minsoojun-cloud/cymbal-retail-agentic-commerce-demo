/* Cymbal Retail 棚番管理 — controller (CONTRACT v12).
   Flow: 店舗の平面図で棚を選択 / 新しく描く → 棚番号（A01）を入力 → 詳細棚番（A01-101…）は段数・幅から自動生成。
   区域（化粧品・野菜・鮮魚…）は棚をまとめて名前を付ける。公開時に、削除された棚番に登録されていた商品は
   「棚番未指定」になり、棚登録アプリの再登録フロー（撮影不要）で新しい棚番を付け直す。 */
(function () {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const clone = (o) => JSON.parse(JSON.stringify(o));
  const r2 = (v) => Math.round(v * 100) / 100;
  const NUM_RE = /^[A-Z]{1,2}\d{2}$/;
  const FLAT = window.FloorPlan.FLAT;
  const TYPES = [
    ["gondola", "ゴンドラ棚"], ["wall", "壁面棚"], ["endcap", "エンド棚"], ["multideck", "冷蔵多段ケース"],
    ["reach_in", "冷凍リーチイン"], ["chest", "平型冷凍ケース"], ["flat_table", "平台（青果など）"],
    ["deli_table", "惣菜・ベーカリー台"], ["flower", "花売場"], ["counter", "医薬品カウンター"],
  ];
  const TYPE_JA = Object.fromEntries(TYPES);
  const ZONE_COLORS = ["#e8f0fe", "#fce4ec", "#e6f4ea", "#fef7e0", "#f3e8fd", "#e0f7fa", "#fff3e0", "#f1f8e9", "#ede7f6", "#e3f2fd"];
  const CMP_KEYS = ["id", "x", "y", "w", "h", "face", "tiers", "slot_width_cm", "slots_per_tier", "zone", "label", "type"];

  const ED = {
    stores: [], storeId: "", version: 2, published: null, layout: null, hasDraft: false, dirty: false,
    selected: new Set(), tab: "shelf", counts: {}, unassigned: [], undo: [], activeZone: "",
    pubByUid: {}, dups: new Set(), unUids: new Set(), zoneRects: [],
  };

  // ------------------------------------------------------------------ utils
  async function api(path, opts = {}) {
    const o = { headers: { "Content-Type": "application/json" }, credentials: "same-origin", ...opts };
    if (o.body && typeof o.body !== "string") o.body = JSON.stringify(o.body);
    const r = await fetch(path, o);
    let data = null;
    try { data = await r.json(); } catch { /* empty */ }
    if (!r.ok) { const e = new Error((data && (data.detail || data.error)) || `HTTP ${r.status}`); e.status = r.status; throw e; }
    return data;
  }
  let toastT;
  function toast(msg, err = false) {
    const t = $("#toast"); t.textContent = msg; t.classList.toggle("err", err); t.classList.add("show");
    clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove("show"), 3200);
  }
  const fxByUid = (uid) => (ED.layout.fixtures || []).find((f) => f.uid === uid);
  const selFixtures = () => (ED.layout ? ED.layout.fixtures.filter((f) => ED.selected.has(f.uid)) : []);
  const horizontal = (f) => f.face === "N" || f.face === "S";
  const lengthCm = (f) => Math.round((horizontal(f) ? f.w : f.h) * 100);
  const zoneOf = (id) => (ED.layout.zones || []).find((z) => z.id === id);
  const pubIdOf = (f) => (ED.pubByUid[f.uid] || {}).id;
  const productsOn = (f) => ED.counts[pubIdOf(f)] || 0;
  const slotId = (fid, t, i) => `${fid}-${t}${String(i).padStart(2, "0")}`;

  // ------------------------------------------------------------------ derived state
  function recompute() {
    const seen = {};
    ED.layout.fixtures.forEach((f) => { if (f.id) seen[f.id] = (seen[f.id] || 0) + 1; });
    ED.dups = new Set(Object.keys(seen).filter((k) => seen[k] > 1));
    // unassigned products → the shelf they were on (by published id → uid)
    const pubIdToUid = {};
    Object.values(ED.pubByUid).forEach((f) => { pubIdToUid[f.id] = f.uid; });
    ED.unUids = new Set(ED.unassigned.map((u) => pubIdToUid[u.previous_fixture_id]).filter(Boolean));
    // zone rects (same rule as the server: bounding box of the zone's shelves + 0.2 m)
    const lay = ED.layout;
    ED.zoneRects = (lay.zones || []).map((z) => {
      if (z.auto_rect === false) return z;
      const m = lay.fixtures.filter((f) => f.zone === z.id);
      if (!m.length) return Object.assign({}, z, { rect: null });
      const x1 = Math.max(0, Math.min(...m.map((f) => f.x)) - 0.2), y1 = Math.max(0, Math.min(...m.map((f) => f.y)) - 0.2);
      const x2 = Math.min(lay.width, Math.max(...m.map((f) => f.x + f.w)) + 0.2), y2 = Math.min(lay.height, Math.max(...m.map((f) => f.y + f.h)) + 0.2);
      return Object.assign({}, z, { rect: [r2(x1), r2(y1), r2(x2 - x1), r2(y2 - y1)] });
    });
  }
  function numberError(f) {
    if (!f.id) return "棚番号が未設定です";
    if (f.type === "counter" && f.id === "RX") return "";
    if (!NUM_RE.test(f.id)) return "英大文字1〜2字＋数字2桁で入力（例: A01）";
    if (ED.dups.has(f.id)) return `「${f.id}」は他の棚で使われています`;
    return "";
  }
  function changed(f) {
    const p = ED.pubByUid[f.uid];
    if (!p) return true;
    return CMP_KEYS.some((k) => String(p[k] ?? "") !== String(f[k] ?? ""));
  }
  function annot(f) {
    const err = numberError(f);
    return { sel: ED.selected.has(f.uid), none: !f.id, err: !!err, changed: changed(f), unassigned: ED.unUids.has(f.uid) };
  }

  // ------------------------------------------------------------------ plan
  const plan = new window.FloorPlan($("#plan-canvas"), $("#plan-svg"), {
    getState: () => ({ layout: ED.layout, selected: ED.selected, zoneRects: ED.zoneRects, annot }),
    onSelect: (uid, additive) => {
      if (!uid) { ED.selected.clear(); }
      else if (additive) { ED.selected.has(uid) ? ED.selected.delete(uid) : ED.selected.add(uid); }
      else { ED.selected = new Set([uid]); }
      if (ED.tab !== "shelf" && uid && !additive) setTab("shelf");
      renderAll();
    },
    onMoveStart: () => snapshot(),
    onMoved: () => { markDirty(); renderAll(); },
    onDrawn: (r) => addFixture(r),
  });

  // ------------------------------------------------------------------ undo / dirty
  function snapshot() {
    ED.undo.push(JSON.stringify(ED.layout));
    if (ED.undo.length > 60) ED.undo.shift();
    $("#btn-undo").disabled = false;
  }
  function undo() {
    const s = ED.undo.pop();
    if (!s) return;
    ED.layout = JSON.parse(s);
    ED.selected = new Set([...ED.selected].filter((u) => fxByUid(u)));
    $("#btn-undo").disabled = !ED.undo.length;
    markDirty(); renderAll();
  }
  function markDirty(d = true) { ED.dirty = d; renderStatus(); }
  function renderStatus() {
    const b = $("#status-badge");
    if (ED.dirty) { b.className = "badge badge--dirty"; b.textContent = "未保存の変更あり"; }
    else if (ED.hasDraft) { b.className = "badge badge--draft"; b.textContent = `下書き（公開中 v${ED.version}）`; }
    else { b.className = "badge"; b.textContent = `公開中 v${ED.version}`; }
  }

  // ------------------------------------------------------------------ load
  async function loadStore(storeId) {
    ED.storeId = storeId;
    localStorage.setItem("sn_staff_store", storeId);
    const qp = new URLSearchParams(location.search); qp.set("store", storeId);
    history.replaceState(null, "", `${location.pathname}?${qp}`);
    $("#store-select").value = storeId;
    $("#staff-link").href = `/?store=${encodeURIComponent(storeId)}`;
    let data;
    try { data = await api(`/api/admin/stores/${encodeURIComponent(storeId)}/editor`); }
    catch (e) { if (e.status === 403) { $("#gate").hidden = false; return; } toast(`読み込みに失敗しました: ${e.message}`, true); return; }
    ED.version = data.current_version;
    ED.published = data.layout;
    ED.pubByUid = {};
    (data.layout.fixtures || []).forEach((f) => { ED.pubByUid[f.uid || f.id] = f; });
    ED.layout = clone(data.draft || data.layout);
    ED.layout.fixtures.forEach((f) => { if (!f.uid) f.uid = f.id; });
    ED.layout.zones = ED.layout.zones || [];
    ED.hasDraft = !!data.has_draft;
    ED.counts = data.fixture_product_counts || {};
    ED.unassigned = data.unassigned_items || data.unassigned_sample || [];
    ED.selected.clear(); ED.undo = []; $("#btn-undo").disabled = true;
    markDirty(false);
    plan._fitted = false;
    recompute();
    plan.fit();
    renderAll();
  }

  // ------------------------------------------------------------------ mutations
  function addFixture(r) {
    snapshot();
    const hor = r.w >= r.h;
    const depth = hor ? r.h : r.w, len = hor ? r.w : r.h;
    const flat = depth >= 1.2;
    const type = flat ? "flat_table" : "gondola";
    const sw = flat ? 60 : 30;
    const cx = r.x + r.w / 2, cy = r.y + r.h / 2;
    const z = ED.zoneRects.find((zz) => zz.rect && cx >= zz.rect[0] && cx <= zz.rect[0] + zz.rect[2] && cy >= zz.rect[1] && cy <= zz.rect[1] + zz.rect[3]);
    const f = {
      uid: `NEW-${Date.now().toString(36)}`, id: "", body_id: null, type, zone: z ? z.id : "", label: "",
      x: r.x, y: r.y, w: r.w, h: r.h, face: hor ? "S" : "E", length_cm: Math.round(len * 100),
      tiers: flat ? 1 : 5, slot_width_cm: sw, slots_per_tier: Math.max(1, Math.floor(Math.round(len * 100) / sw)),
      categories: [], tier_slots: {}, disabled_slots: [],
    };
    ED.layout.fixtures.push(f);
    ED.selected = new Set([f.uid]);
    setTool("select");
    markDirty(); setTab("shelf"); renderAll();
    setTimeout(() => { const i = $("#f-num"); if (i) i.focus(); }, 30);
    toast("棚を追加しました。棚番号を入力してください");
  }
  function deleteSelected() {
    const fs = selFixtures(); if (!fs.length) return;
    const n = fs.reduce((a, f) => a + productsOn(f), 0);
    const names = fs.map((f) => f.id || "（未設定）").join("、");
    const msg = `棚 ${names} を削除します。` + (n ? `\nこの棚に登録されている商品 ${n}件 は公開後「棚番未指定」になり、棚登録アプリで再登録が必要です。` : "");
    if (!confirm(msg)) return;
    snapshot();
    const del = new Set(fs.map((f) => f.uid));
    ED.layout.fixtures = ED.layout.fixtures.filter((f) => !del.has(f.uid));
    ED.selected.clear();
    markDirty(); renderAll();
  }
  function setLength(f, cm) {
    const m = Math.max(30, Math.round(cm / 30) * 30) / 100;
    if (horizontal(f)) f.w = r2(Math.min(m, ED.layout.width - f.x)); else f.h = r2(Math.min(m, ED.layout.height - f.y));
    f.length_cm = lengthCm(f);
    reslot(f);
  }
  function reslot(f) {
    f.slots_per_tier = Math.max(1, Math.floor(f.length_cm / (f.slot_width_cm || 30)));
    f.tier_slots = {};
    f.disabled_slots = [];
  }
  function rotate(f) {
    const cx = f.x + f.w / 2, cy = f.y + f.h / 2;
    [f.w, f.h] = [f.h, f.w];
    f.x = r2(Math.min(Math.max(cx - f.w / 2, 0), ED.layout.width - f.w));
    f.y = r2(Math.min(Math.max(cy - f.h / 2, 0), ED.layout.height - f.h));
    f.face = { N: "E", E: "S", S: "W", W: "N" }[f.face || "S"];
  }
  function suggestNumber(f, typed) {
    let pre = (typed || "").replace(/[^A-Z]/g, "").slice(0, 2);
    if (!pre) {
      const cnt = {};
      ED.layout.fixtures.forEach((x) => { if (x !== f && x.zone && x.zone === f.zone && x.id) { const p = (/^[A-Z]+/.exec(x.id) || [""])[0]; cnt[p] = (cnt[p] || 0) + 1; } });
      pre = Object.keys(cnt).sort((a, b) => cnt[b] - cnt[a])[0] || "X";
    }
    const used = new Set(ED.layout.fixtures.filter((x) => x !== f).map((x) => x.id));
    for (let n = 1; n < 100; n++) { const c = `${pre}${String(n).padStart(2, "0")}`; if (!used.has(c)) return c; }
    return "";
  }

  // ------------------------------------------------------------------ side panel
  function setTab(t) {
    ED.tab = t;
    $$(".tabs__btn").forEach((b) => b.classList.toggle("active", b.dataset.ptab === t));
    renderSide();
  }
  function renderSide() {
    const body = $("#side-body");
    if (!ED.layout) { body.innerHTML = ""; return; }
    if (ED.tab === "zone") return renderZones(body);
    const fs = selFixtures();
    if (!fs.length) return renderOverview(body);
    if (fs.length > 1) return renderMulti(body, fs);
    return renderShelf(body, fs[0]);
  }
  function renderOverview(body) {
    const fx = ED.layout.fixtures;
    const none = fx.filter((f) => !f.id), bad = fx.filter((f) => f.id && numberError(f));
    body.innerHTML = `
      <div class="empty-state">
        <svg viewBox="0 0 24 24"><path d="M7 2l12 11.2-5.8.5 3.3 7.3-2.2 1-3.2-7.4L7 18.5z"/></svg>
        <p>平面図の棚をクリックして<br/><b>棚番号</b>を設定してください。</p>
      </div>
      <div class="stats">
        <div class="stat"><b>${fx.length}</b><span>棚</span></div>
        <div class="stat ${none.length ? "stat--warn" : ""}"><b>${none.length}</b><span>番号未設定</span></div>
        <div class="stat"><b>${(ED.layout.zones || []).length}</b><span>区域</span></div>
      </div>
      <div class="note note--info">
        <b>使い方</b><br/>
        ① 棚をクリック → 棚番号（例: A01）を入力<br/>
        ② 「棚を描く」で平面図をドラッグ → 新しい棚を追加<br/>
        ③ Shift＋クリック（タブレットは長押し）で複数選択 → まとめて区域を設定<br/>
        ④ 「確認して公開」で、お客さまアプリ・棚登録アプリに反映
      </div>
      ${none.length || bad.length ? `<div class="note note--err">公開前に、番号未設定・重複の棚 ${none.length + bad.length}台 を修正してください（下の一覧から選択できます）。</div>` : ""}`;
  }
  function renderMulti(body, fs) {
    const n = fs.reduce((a, f) => a + productsOn(f), 0);
    body.innerHTML = `
      <div class="sel-head"><h3>${fs.length}台の棚を選択中</h3><button type="button" class="btn btn--text btn--sm" id="m-clear">選択解除</button></div>
      <p class="muted small">${esc(fs.map((f) => f.id || "未設定").join("、"))}</p>
      <div class="field"><label for="m-zone">区域をまとめて設定</label>
        <select class="select" id="m-zone"><option value="">（区域なし）</option>${(ED.layout.zones || []).map((z) => `<option value="${esc(z.id)}">${esc(z.label)}</option>`).join("")}</select>
      </div>
      <button type="button" class="btn btn--tonal btn--block" id="m-apply">選択した棚をこの区域にする</button>
      <hr class="divider"/>
      <button type="button" class="btn btn--danger btn--block" id="m-del">選択した${fs.length}台を削除${n ? `（商品 ${n}件が棚番未指定に）` : ""}</button>`;
    $("#m-clear").onclick = () => { ED.selected.clear(); renderAll(); };
    $("#m-apply").onclick = () => { snapshot(); const z = $("#m-zone").value; fs.forEach((f) => { f.zone = z; }); markDirty(); renderAll(); toast("区域を設定しました"); };
    $("#m-del").onclick = deleteSelected;
  }
  function notesHTML(f) {
    const pid = pubIdOf(f);
    const n = productsOn(f);
    const p = ED.pubByUid[f.uid];
    const notes = [];
    if (!p) notes.push(`<div class="note note--info">新しく追加した棚です。棚番号を入力すると詳細棚番（${esc(f.id || "A01")}-101 …）が自動で決まります。</div>`);
    else if (pid && f.id && pid !== f.id) notes.push(`<div class="note note--info">番号変更: <b>${esc(pid)}</b> → <b>${esc(f.id)}</b><br/>この棚の商品 ${n}件 は公開時に <b>${esc(f.id)}-xxx</b> へ自動で移ります（棚番未指定にはなりません）。</div>`);
    if (p && (f.tiers < p.tiers || f.slots_per_tier < p.slots_per_tier) && n) notes.push(`<div class="note note--warn">段数・区切り数を減らしました。なくなる詳細棚番に登録されている商品は、公開後「棚番未指定」になります（公開前の確認画面で件数を表示します）。</div>`);
    return notes.join("");
  }
  function renderShelf(body, f) {
    const n = productsOn(f);
    const isNew = !ED.pubByUid[f.uid];
    const zones = ED.layout.zones || [];
    body.innerHTML = `
      <div class="sel-head"><h3>${isNew ? "新しい棚" : "棚の設定"} <span class="muted small">${esc(TYPE_JA[f.type] || f.type)}</span></h3>
        <button type="button" class="btn btn--text btn--sm" id="s-center">平面図で表示</button></div>
      <div id="f-notes">${notesHTML(f)}</div>
      <div class="field">
        <label for="f-num">棚番号</label>
        <div class="num-row">
          <input class="input input--num" id="f-num" value="${esc(f.id)}" maxlength="4" placeholder="A01" autocomplete="off" autocapitalize="characters" spellcheck="false" ${f.type === "counter" ? "readonly" : ""}/>
          ${f.type === "counter" ? "" : '<button type="button" class="btn btn--tonal" id="f-suggest" title="空いている番号を入力">空き番号</button>'}
        </div>
        <div class="msg" id="f-num-msg"></div>
      </div>
      <div class="field">
        <label for="f-label">売場名（お客さまアプリに表示）</label>
        <input class="input" id="f-label" value="${esc(f.label || "")}" maxlength="40" placeholder="例: かぜ薬・解熱鎮痛薬"/>
      </div>
      <div class="field">
        <label for="f-zone">区域</label>
        <select class="select" id="f-zone"><option value="">（区域なし）</option>${zones.map((z) => `<option value="${esc(z.id)}" ${z.id === f.zone ? "selected" : ""}>${esc(z.label)}</option>`).join("")}</select>
      </div>
      <div class="row">
        <div class="field"><label for="f-type">棚の種類</label>
          <select class="select" id="f-type">${TYPES.map(([k, v]) => `<option value="${k}" ${k === f.type ? "selected" : ""}>${v}</option>`).join("")}</select></div>
        <div class="field"><span class="field__label">陳列面（お客さま側）</span>
          <div class="chips">${(horizontal(f) ? ["N", "S"] : ["E", "W"]).map((d) => `<button type="button" class="chip ${f.face === d ? "on" : ""}" data-face="${d}">${{ N: "上側", S: "下側", E: "右側", W: "左側" }[d]}</button>`).join("")}
            <button type="button" class="chip" id="f-rotate" title="90°回転">↻</button></div></div>
      </div>
      <div class="row">
        <div class="field"><label for="f-len">幅（cm）</label><input class="input" id="f-len" type="number" min="30" step="30" value="${lengthCm(f)}"/></div>
        <div class="field"><span class="field__label">段数</span>
          <div class="stepper"><button type="button" id="t-dec" aria-label="段を減らす">−</button><span id="t-val">${f.tiers}</span><button type="button" id="t-inc" aria-label="段を増やす">＋</button></div></div>
      </div>
      <div class="field"><span class="field__label">詳細棚番の区切り幅</span>
        <div class="chips">${[30, 60, 90].map((w) => `<button type="button" class="chip ${Number(f.slot_width_cm) === w ? "on" : ""}" data-sw="${w}">${w}cm</button>`).join("")}</div>
      </div>
      <div class="field"><span class="field__label">詳細棚番（自動） — ${f.tiers}段 × ${f.slots_per_tier}枠 = ${f.tiers * f.slots_per_tier}番号</span>
        <div id="elev">${elevHTML(f)}</div>
      </div>
      <hr class="divider"/>
      <p class="muted small">${isNew ? "まだ商品は登録されていません。" : `現在この棚に登録されている商品: <b>${n}件</b>`}</p>
      <button type="button" class="btn btn--danger btn--block" id="f-del">この棚を削除</button>`;

    const num = $("#f-num");
    const msg = () => {
      const m = $("#f-num-msg"); const e = numberError(f);
      m.className = `msg ${e ? "bad" : "ok"}`; m.textContent = e || "OK — 詳細棚番は下のとおりです";
      num.classList.toggle("bad", !!e);
    };
    msg();
    let snapped = false;
    num.addEventListener("focus", () => { snapped = false; });
    num.addEventListener("input", () => {
      if (!snapped) { snapshot(); snapped = true; }
      const v = num.value.toUpperCase().replace(/[^A-Z0-9]/g, "");
      if (v !== num.value) num.value = v;
      f.id = v; markDirty(); recompute(); msg();
      $("#elev").innerHTML = elevHTML(f);
      $("#f-notes").innerHTML = notesHTML(f);
      plan.render(); renderErrors();
    });
    num.addEventListener("keydown", (e) => { if (e.key === "Enter") num.blur(); });
    if ($("#f-suggest")) $("#f-suggest").onclick = () => { snapshot(); f.id = suggestNumber(f, num.value); markDirty(); renderAll(); };
    $("#s-center").onclick = () => plan.centerOn(f);
    const lab = $("#f-label"); let ls = false;
    lab.addEventListener("input", () => { if (!ls) { snapshot(); ls = true; } f.label = lab.value; markDirty(); });
    $("#f-zone").onchange = (e) => { snapshot(); f.zone = e.target.value; markDirty(); renderAll(); };
    $("#f-type").onchange = (e) => {
      snapshot(); f.type = e.target.value;
      if (FLAT.has(f.type)) { f.tiers = 1; f.slot_width_cm = 60; } else if (f.tiers === 1) { f.tiers = 5; f.slot_width_cm = 30; }
      reslot(f); markDirty(); renderAll();
    };
    $$("[data-face]", body).forEach((b) => b.onclick = () => { snapshot(); f.face = b.dataset.face; markDirty(); renderAll(); });
    $("#f-rotate").onclick = () => { snapshot(); rotate(f); markDirty(); renderAll(); };
    $("#f-len").onchange = (e) => { snapshot(); setLength(f, Number(e.target.value) || 30); markDirty(); renderAll(); };
    $("#t-dec").onclick = () => { if (f.tiers > 1) { snapshot(); f.tiers -= 1; f.tier_slots = {}; markDirty(); renderAll(); } };
    $("#t-inc").onclick = () => { if (f.tiers < 6) { snapshot(); f.tiers += 1; f.tier_slots = {}; markDirty(); renderAll(); } };
    $$("[data-sw]", body).forEach((b) => b.onclick = () => { snapshot(); f.slot_width_cm = Number(b.dataset.sw); f.length_cm = lengthCm(f); reslot(f); markDirty(); renderAll(); });
    $("#f-del").onclick = deleteSelected;
  }
  function elevHTML(f) {
    const id = f.id || "＿＿＿";
    const rows = [];
    for (let t = f.tiers; t >= 1; t--) {
      const n = Number((f.tier_slots || {})[t] || (f.tier_slots || {})[String(t)] || f.slots_per_tier || 1);
      const cells = [];
      for (let i = 1; i <= n; i++) {
        if ((f.disabled_slots || []).includes(slotId(f.id, t, i))) continue;
        cells.push(`<div class="elev__cell ${f.slot_width_cm >= 60 ? "wide" : ""}">${esc(f.id ? slotId(id, t, i) : `${t}${String(i).padStart(2, "0")}`)}</div>`);
      }
      rows.push(`<div class="elev__row"><div class="elev__tier">${t}段</div>${cells.join("")}</div>`);
    }
    return `<div class="elev">${rows.join("")}<div class="elev__floor"></div>
      <div class="elev__cap"><span>← 左（お客さまから見て）</span><span>区切り ${f.slot_width_cm || 30}cm</span><span>右 →</span></div></div>`;
  }
  function renderZones(body) {
    const zones = ED.layout.zones || [];
    const cnt = {};
    ED.layout.fixtures.forEach((f) => { cnt[f.zone] = (cnt[f.zone] || 0) + 1; });
    const sel = selFixtures();
    body.innerHTML = `
      <p class="muted small" style="margin-top:0">棚が集まっている売場に名前を付けます（例: 化粧品・野菜・鮮魚）。名前をクリックするとその区域の棚を選択します。</p>
      ${sel.length ? `<div class="note note--info">${sel.length}台の棚を選択中 — 区域の「＋割当」で設定できます。</div>` : ""}
      <ul class="zone-list">${zones.map((z) => `
        <li class="zone ${ED.activeZone === z.id ? "active" : ""}" data-zid="${esc(z.id)}">
          <input type="color" value="${esc(z.color || "#e8f0fe")}" data-zcolor aria-label="色"/>
          <input class="input" value="${esc(z.label || "")}" data-zname aria-label="区域名"/>
          <div class="zone__btns">
            <button type="button" class="btn btn--text btn--sm" data-zsel title="この区域の棚を選択">${cnt[z.id] || 0}台</button>
            ${sel.length ? `<button type="button" class="btn btn--tonal btn--sm" data-zassign>＋割当</button>` : ""}
            <button type="button" class="icon-btn" data-zdel aria-label="区域を削除" title="区域を削除">✕</button>
          </div>
        </li>`).join("")}</ul>
      <div class="zone-add">
        <input class="input" id="z-new" placeholder="新しい区域名（例: 化粧品）" maxlength="20"/>
        <button type="button" class="btn btn--primary" id="z-add">追加</button>
      </div>`;
    $$(".zone", body).forEach((li) => {
      const z = zoneOf(li.dataset.zid);
      let s1 = false;
      $("[data-zname]", li).addEventListener("input", (e) => { if (!s1) { snapshot(); s1 = true; } z.label = e.target.value; markDirty(); recompute(); plan.render(); });
      $("[data-zcolor]", li).addEventListener("change", (e) => { snapshot(); z.color = e.target.value; markDirty(); recompute(); plan.render(); });
      $("[data-zsel]", li).onclick = () => {
        ED.activeZone = z.id;
        ED.selected = new Set(ED.layout.fixtures.filter((f) => f.zone === z.id).map((f) => f.uid));
        renderAll();
      };
      const as = $("[data-zassign]", li);
      if (as) as.onclick = () => { snapshot(); selFixtures().forEach((f) => { f.zone = z.id; }); markDirty(); renderAll(); toast(`「${z.label}」に設定しました`); };
      $("[data-zdel]", li).onclick = () => {
        if (!confirm(`区域「${z.label}」を削除しますか？（棚と棚番号はそのまま残ります）`)) return;
        snapshot();
        ED.layout.zones = ED.layout.zones.filter((x) => x.id !== z.id);
        ED.layout.fixtures.forEach((f) => { if (f.zone === z.id) f.zone = ""; });
        markDirty(); renderAll();
      };
    });
    const add = () => {
      const name = $("#z-new").value.trim();
      if (!name) { toast("区域名を入力してください", true); return; }
      snapshot();
      let n = 1; while (zoneOf(`Z-U${String(n).padStart(2, "0")}`)) n++;
      const z = { id: `Z-U${String(n).padStart(2, "0")}`, label: name, color: ZONE_COLORS[(zones.length) % ZONE_COLORS.length], rect: [0, 0, 0, 0], auto_rect: true };
      ED.layout.zones.push(z);
      if (sel.length) sel.forEach((f) => { f.zone = z.id; });
      markDirty(); renderAll();
      toast(sel.length ? `区域「${name}」を作成し、${sel.length}台を設定しました` : `区域「${name}」を作成しました`);
    };
    $("#z-add").onclick = add;
    $("#z-new").addEventListener("keydown", (e) => { if (e.key === "Enter") add(); });
  }

  // ------------------------------------------------------------------ errors panel
  function renderErrors() {
    const fx = ED.layout.fixtures;
    const items = fx.filter((f) => numberError(f));
    $("#val-count").textContent = items.length;
    $("#val-count").classList.toggle("zero", !items.length);
    $("#val-list").innerHTML = items.length ? items.slice(0, 100).map((f) => `
      <li class="click" data-uid="${esc(f.uid)}"><span class="tag tag--red">${esc(f.id || "未設定")}</span>
        <div class="t"><b>${esc(numberError(f))}</b><span>${esc(TYPE_JA[f.type] || f.type)}・${esc((zoneOf(f.zone) || {}).label || "区域なし")}</span></div></li>`).join("")
      : `<li class="ok">すべての棚に正しい棚番号が付いています</li>`;
    $$("#val-list li.click").forEach((li) => li.onclick = () => { ED.selected = new Set([li.dataset.uid]); setTab("shelf"); plan.centerOn(fxByUid(li.dataset.uid)); renderAll(); });
    const un = ED.unassigned;
    $("#un-count").textContent = un.length;
    $("#un-count").classList.toggle("zero", !un.length);
    $("#un-count").classList.toggle("cnt--red", !!un.length);
    $("#un-list").innerHTML = un.length ? un.map((u) => `
      <li><img src="${esc(u.thumbnail || "/static/shared/img/favicon.svg")}" alt="" loading="lazy"/>
        <div class="t"><b>${esc(u.title)}</b><span>旧棚番 ${esc((u.previous_slot_ids || []).join(", ") || "—")}</span></div>
        <a class="btn btn--primary btn--sm" href="/?store=${encodeURIComponent(ED.storeId)}&staff=${encodeURIComponent("店長")}&reassign=${encodeURIComponent(u.product_id)}&from=admin">棚を指定</a></li>`).join("")
      : `<li class="ok">棚番未指定の商品はありません</li>`;
    $("#errs-sub").textContent = items.length || un.length ? "" : "問題はありません";
  }

  function renderAll() {
    if (!ED.layout) return;
    recompute();
    plan.render();
    renderSide();
    renderErrors();
    renderStatus();
  }

  // ------------------------------------------------------------------ tools
  function setTool(t) {
    plan.setTool(t);
    $$("[data-tool]").forEach((b) => b.classList.toggle("active", b.dataset.tool === t));
    const h = $("#plan-hint");
    h.classList.toggle("draw", t !== "select");
    h.textContent = t === "draw" ? "平面図の上をドラッグして棚の大きさを描いてください（0.3m 単位）。描き終わったら棚番号を入力します。"
      : t === "move" ? "棚をドラッグして移動します（0.3m 単位）。矢印キーでも動かせます。"
        : "棚をクリックすると右側で棚番号を設定できます。Shift＋クリック（タブレットは長押し）で複数選択。";
  }
  $$("[data-tool]").forEach((b) => b.addEventListener("click", () => setTool(b.dataset.tool)));
  $("#zoom-fit").onclick = () => plan.fit();
  $("#zoom-in").onclick = () => plan.zoom(1.3);
  $("#zoom-out").onclick = () => plan.zoom(1 / 1.3);
  $$(".tabs__btn").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.ptab)));
  $("#btn-undo").onclick = undo;
  document.addEventListener("keydown", (e) => {
    const inField = e.target.closest("input, select, textarea");
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && !inField) { e.preventDefault(); undo(); return; }
    if (inField || !ED.layout) return;
    if ((e.key === "Delete" || e.key === "Backspace") && ED.selected.size) { e.preventDefault(); deleteSelected(); return; }
    if (e.key === "Escape") { ED.selected.clear(); setTool("select"); renderAll(); return; }
    const d = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
    if (d && ED.selected.size) {
      e.preventDefault(); snapshot();
      selFixtures().forEach((f) => {
        f.x = r2(Math.min(Math.max(f.x + d[0] * 0.3, 0), ED.layout.width - f.w));
        f.y = r2(Math.min(Math.max(f.y + d[1] * 0.3, 0), ED.layout.height - f.h));
      });
      markDirty(); renderAll();
    }
  });

  // ------------------------------------------------------------------ draft / publish / history
  async function saveDraft(quiet = false) {
    await api(`/api/admin/stores/${ED.storeId}/draft`, { method: "PUT", body: { draft: ED.layout, editor_name: "店長" } });
    ED.hasDraft = true; markDirty(false);
    if (!quiet) toast("下書きを保存しました");
  }
  $("#btn-save").onclick = () => saveDraft().catch((e) => toast(`保存に失敗しました: ${e.message}`, true));
  $("#btn-discard").onclick = async () => {
    if (!confirm("下書きを破棄して、公開中の内容に戻しますか？")) return;
    try { await api(`/api/admin/stores/${ED.storeId}/draft`, { method: "DELETE" }); await loadStore(ED.storeId); toast("下書きを破棄しました"); }
    catch (e) { toast(`破棄に失敗しました: ${e.message}`, true); }
  };
  function openModal(id) { $("#scrim").hidden = false; $(id).hidden = false; }
  function closeModals() { $("#scrim").hidden = true; $$(".modal").forEach((m) => { m.hidden = true; }); }
  $$("[data-close]").forEach((b) => b.addEventListener("click", closeModals));
  $("#scrim").addEventListener("click", closeModals);

  $("#btn-publish").onclick = async () => {
    const btn = $("#btn-publish"); btn.disabled = true; btn.textContent = "確認中…";
    try {
      await saveDraft(true);
      const pv = await api(`/api/admin/stores/${ED.storeId}/draft/preview`, { method: "POST", body: { draft: ED.layout } });
      renderPublish(pv);
      openModal("#publish-modal");
    } catch (e) { toast(`確認に失敗しました: ${e.message}`, true); }
    finally { btn.disabled = false; btn.textContent = "確認して公開"; }
  };
  function renderPublish(pv) {
    const d = pv.diff, imp = pv.impact;
    const nu = imp.new_unassigned_products || [];
    const total = d.added_fixtures.length + d.removed_fixtures.length + d.renamed_fixtures.length + d.modified_fixtures.length;
    let h = "";
    if (!pv.valid) h += `<div class="note note--err"><b>公開できません — 修正が必要です</b><br/>${pv.errors.map(esc).join("<br/>")}</div>`;
    h += `<div class="sum">
      <div><b>${d.added_fixtures.length}</b><span>追加した棚</span></div>
      <div><b>${d.removed_fixtures.length}</b><span>削除した棚</span></div>
      <div><b>${d.renamed_fixtures.length}</b><span>番号変更</span></div>
      <div class="${nu.length ? "warn" : ""}"><b>${nu.length}</b><span>棚番未指定になる商品</span></div></div>`;
    if (!total) h += `<p class="muted">公開中の内容から変更はありません。</p>`;
    const li = (arr, fn) => (arr.length ? `<ul class="diff-list">${arr.slice(0, 60).map(fn).join("")}${arr.length > 60 ? `<li>…ほか ${arr.length - 60}件</li>` : ""}</ul>` : "");
    if (d.renamed_fixtures.length) h += `<h3>番号変更（商品は新しい番号へ自動で移ります）</h3>` + li(d.renamed_fixtures, (x) => `<li><code>${esc(x.old.id)}</code> → <code>${esc(x.new.id)}</code>　${esc(x.new.label || "")}</li>`);
    if (d.added_fixtures.length) h += `<h3>追加した棚</h3>` + li(d.added_fixtures, (x) => `<li><code>${esc(x.id || "未設定")}</code>　${esc(TYPE_JA[x.type] || "")} ${x.tiers}段×${x.slots_per_tier}枠</li>`);
    if (d.removed_fixtures.length) h += `<h3>削除した棚</h3>` + li(d.removed_fixtures, (x) => `<li><code>${esc(x.id)}</code>　${esc(x.label || "")}（商品 ${ED.counts[x.id] || 0}件）</li>`);
    if (d.modified_fixtures.length) h += `<h3>位置・段数・区域などを変更した棚</h3>` + li(d.modified_fixtures, (x) => `<li><code>${esc(x.new.id)}</code>　${esc(x.new.label || "")}</li>`);
    if (imp.reassigned_count) h += `<p class="muted small">番号変更に伴い ${imp.reassigned_count}件 の商品の詳細棚番を自動更新します。</p>`;
    if (nu.length) {
      h += `<div class="note note--err"><b>次の商品は棚番がなくなるため「棚番未指定」になります。</b><br/>公開後、棚登録アプリの「棚番未指定」一覧から新しい棚番を登録してください。</div>`;
      h += li(nu, (u) => `<li>${esc(u.title)}　<span class="muted">（旧 ${esc((u.previous_slot_ids || []).join(", "))}）</span></li>`);
      h += `<label class="confirm-row"><input type="checkbox" id="pm-confirm"/>上記 ${nu.length}件 が棚番未指定になることを確認しました</label>`;
    }
    $("#pm-body").innerHTML = h;
    const sub = $("#pm-submit");
    const upd = () => { sub.disabled = !pv.valid || !total || (nu.length && !($("#pm-confirm") || {}).checked); };
    upd();
    const c = $("#pm-confirm"); if (c) c.onchange = upd;
    sub.onclick = async () => {
      sub.disabled = true; sub.textContent = "公開中…";
      try {
        const res = await api(`/api/admin/stores/${ED.storeId}/publish`, { method: "POST", body: { base_version: ED.version, by: "店長", confirm_unassigned: !!nu.length } });
        closeModals();
        toast(`v${res.version} を公開しました${res.unassigned_count ? `（棚番未指定 ${res.unassigned_count}件）` : ""}`);
        await loadStore(ED.storeId);
      } catch (e) { toast(`公開に失敗しました: ${e.message}`, true); }
      finally { sub.textContent = "公開する"; upd(); }
    };
  }
  $("#btn-history").onclick = async () => {
    try {
      const data = await api(`/api/admin/stores/${ED.storeId}/versions`);
      const vs = data.versions || [];
      $("#hm-body").innerHTML = vs.map((v) => `
        <div class="ver"><div><b>v${v.version}</b> ${v.version === ED.version ? '<span class="badge">公開中</span>' : ""}
          <div class="muted small">${esc(v.summary || "")}</div>
          <div class="muted small">${esc(v.published_by || "system")}・${v.published_at ? esc(new Date(v.published_at).toLocaleString("ja-JP")) : "初期データ"}</div></div>
          ${v.version !== ED.version ? `<button type="button" class="btn btn--tonal btn--sm" data-rb="${v.version}">この版に戻す</button>` : ""}</div>`).join("");
      $$("[data-rb]").forEach((b) => b.onclick = async () => {
        const ver = Number(b.dataset.rb);
        if (!confirm(`v${ver} の棚・棚番号に戻しますか？（新しい版として公開されます）`)) return;
        b.disabled = true; b.textContent = "戻しています…";
        try {
          const r = await api(`/api/admin/stores/${ED.storeId}/rollback`, { method: "POST", body: { to_version: ver, by: "店長", restore_products: true } });
          closeModals(); toast(`v${ver} の内容に戻しました（v${r.version}）`); await loadStore(ED.storeId);
        } catch (e) { toast(`戻せませんでした: ${e.message}`, true); b.disabled = false; }
      });
      openModal("#history-modal");
    } catch (e) { toast(`履歴の取得に失敗しました: ${e.message}`, true); }
  };

  // ------------------------------------------------------------------ init
  $("#gate-login").onclick = () => {
    document.cookie = "sn_role=manager; path=/; max-age=604800; samesite=lax";
    localStorage.setItem("sn_role", "manager");
    $("#gate").hidden = true;
    loadStore(ED.storeId || "S01");
  };
  $("#store-select").addEventListener("change", (e) => {
    if (ED.dirty && !confirm("保存していない変更があります。店舗を切り替えますか？")) { e.target.value = ED.storeId; return; }
    loadStore(e.target.value);
  });
  window.addEventListener("beforeunload", (e) => { if (ED.dirty) { e.preventDefault(); e.returnValue = ""; } });

  async function init() {
    const qp = new URLSearchParams(location.search);
    if (qp.get("role") === "manager") document.cookie = "sn_role=manager; path=/; max-age=604800; samesite=lax";
    try { ED.stores = (await api("/api/stores")).stores || []; } catch { ED.stores = []; }
    if (!ED.stores.length) ED.stores = ["S01", "S02", "S03"].map((id) => ({ store_id: id, name: id }));
    $("#store-select").innerHTML = ED.stores.map((s) => `<option value="${esc(s.store_id)}">${esc(s.short_name || s.name || s.store_id)}</option>`).join("");
    const sid = qp.get("store") || localStorage.getItem("sn_staff_store") || "S01";
    setTool("select");
    await loadStore(ED.stores.some((s) => s.store_id === sid) ? sid : ED.stores[0].store_id);
  }
  window.ShelfNumberAdmin = { ED, plan, loadStore };
  init();
})();
