/* Location: navigator.geolocation + 位置シミュレーション (demo venues without GPS). */
(function () {
  'use strict';
  const { esc, toast } = window.SN;
  const ICON_STORE = '<svg viewBox="0 0 24 24"><path d="M20 4H4v2h16V4zm1 10v-2l-1-5H4l-1 5v2h1v6h10v-6h4v6h2v-6h1zm-9 4H6v-4h6v4z"/></svg>';
  const ICON_FAR = '<svg viewBox="0 0 24 24"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5a2.5 2.5 0 0 1 0-5 2.5 2.5 0 0 1 0 5z"/></svg>';
  const ICON_GPS = '<svg viewBox="0 0 24 24"><path d="M12 8c-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4-1.79-4-4-4zm8.94 3A8.994 8.994 0 0 0 13 3.06V1h-2v2.06A8.994 8.994 0 0 0 3.06 11H1v2h2.06A8.994 8.994 0 0 0 11 20.94V23h2v-2.06A8.994 8.994 0 0 0 20.94 13H23v-2h-2.06zM12 19c-3.87 0-7-3.13-7-7s3.13-7 7-7 7 3.13 7 7-3.13 7-7 7z"/></svg>';

  function options() {
    const S = window.SNC.state;
    const opts = [];
    const names = { S01: '川崎駅前店の店内', S02: '武蔵小杉店の店内', S03: '渋谷店の店内' };
    S.stores.slice().sort((a, b) => a.store_id.localeCompare(b.store_id)).forEach((s) => {
      opts.push({ key: 'in_' + s.store_id, name: names[s.store_id] || (s.short_name + 'の店内'), meta: s.address || '',
        lat: Number(s.lat) + 0.00012, lng: Number(s.lng) + 0.00008, icon: ICON_STORE });
    });
    opts.push({ key: 'far_tokyo', name: '東京駅付近（遠方）', meta: '店舗から離れた場所（店外モード）', lat: 35.6812, lng: 139.7671, icon: ICON_FAR });
    opts.push({ key: 'gps', name: '実際の現在地（GPS）を使う', meta: '端末の位置情報を利用します', icon: ICON_GPS });
    return opts;
  }

  async function apply(coords, src, key) {
    const S = window.SNC.state;
    S.coords = coords; S.geoSource = src; S.simKey = key || '';
    window.SNC.save();
    await window.SNC.loadStores();
    if (S.view === 'home') await window.SNC.route();
    else window.SNC.renderHeader();
  }

  function gps(silent) {
    if (!navigator.geolocation) { if (!silent) toast('この端末では位置情報を利用できません'); return; }
    navigator.geolocation.getCurrentPosition(
      (pos) => apply({ lat: pos.coords.latitude, lng: pos.coords.longitude, acc: pos.coords.accuracy }, 'gps', ''),
      () => { if (!silent) toast('位置情報を取得できませんでした。位置シミュレーションをお使いください'); },
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 });
  }

  function open() {
    const S = window.SNC.state;
    const list = document.getElementById('geo-list');
    list.innerHTML = options().map((o) => '<button type="button" class="geo-opt' + (S.simKey === o.key || (o.key === 'gps' && S.geoSource === 'gps') ? ' is-on' : '') +
      '" data-key="' + o.key + '"><span class="geo-opt__ic">' + o.icon + '</span><span><span class="geo-opt__name">' + esc(o.name) +
      '</span><br><span class="geo-opt__meta">' + esc(o.meta) + '</span></span><span></span></button>').join('');
    list.querySelectorAll('[data-key]').forEach((b) => b.addEventListener('click', () => {
      const o = options().find((x) => x.key === b.dataset.key);
      window.SNC.closeSheets();
      if (o.key === 'gps') gps(false);
      else { apply({ lat: o.lat, lng: o.lng }, 'sim', o.key); toast('位置シミュレーション: ' + o.name); }
    }));
    window.SNC.openSheet('sheet-geo');
  }

  function label() {
    const S = window.SNC.state;
    if (S.geoSource === 'sim') {
      const o = options().find((x) => x.key === S.simKey);
      return { text: o ? o.name : 'シミュレーション中', sim: true };
    }
    if (S.geoSource === 'gps') return { text: '現在地（GPS）', sim: false };
    return { text: '位置情報未取得', sim: false };
  }

  window.Geo = { open, auto: () => gps(true), gps, label, apply };
})();
