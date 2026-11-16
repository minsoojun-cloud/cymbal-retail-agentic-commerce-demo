#!/usr/bin/env python3
"""Playwright layout check for the dinner-set board + chat set card (CONTRACT v6 layout fix).

Renders show_products_on_page(theme, sections) with sections of 1 / 2 / 3 items (real catalog ids from /api/search)
and asserts, at several viewport widths with the chat panel closed and open:
  - no two set cards overlap; every card is inside its section and inside the viewport (no horizontal overflow)
  - all set cards have the same height and the same width
  - cards line up in columns across sections (same x for the n-th card of every section)
  - every section spans the full board width (one row per section)
  - chat set card: one role cell per section (rowspan), product rows do not overflow the card
Screenshots → --out.

usage: python tests/e2e_set_layout.py --base-url http://127.0.0.1:8096 [--out DIR] [--id-token]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

OUT_DEFAULT = os.environ.get("E2E_OUT", "/tmp/cymbal_e2e/layout")

QUERIES = [("主菜", ["秋鮭", "豚ロース", "鶏もも"], 1), ("副菜", ["ほうれん草", "コーン", "しめじ"], 2),
           ("汁物", ["みそ汁", "豚汁", "スープ"], 3), ("デザート・果物", ["りんご", "みかん", "梨"], 1)]

CHECK_JS = r"""
() => {
  const r = (el) => el.getBoundingClientRect();
  const board = document.querySelector('#cr-set-board');
  if (!board) return { error: 'no board' };
  const b = r(board);
  const secs = Array.from(board.querySelectorAll('.cr-set-sec'));
  const cards = Array.from(board.querySelectorAll('.cr-card--h'));
  const issues = [];
  const rects = cards.map((c) => r(c));
  for (let i = 0; i < rects.length; i++) for (let j = i + 1; j < rects.length; j++) {
    const a = rects[i], c = rects[j];
    const ov = Math.min(a.right, c.right) - Math.max(a.left, c.left) > 1 && Math.min(a.bottom, c.bottom) - Math.max(a.top, c.top) > 1;
    if (ov) issues.push('overlap ' + i + '/' + j);
  }
  const hs = rects.map((x) => Math.round(x.height)), ws = rects.map((x) => Math.round(x.width));
  if (Math.max(...hs) - Math.min(...hs) > 1) issues.push('heights differ ' + hs.join(','));
  if (Math.max(...ws) - Math.min(...ws) > 1) issues.push('widths differ ' + ws.join(','));
  const cols = {};
  secs.forEach((s, si) => {
    const sr = r(s);
    if (Math.abs(sr.width - b.width) > 1) issues.push('section ' + si + ' not full width');
    Array.from(s.querySelectorAll('.cr-card--h')).forEach((c, ci) => {
      const cr = r(c);
      if (cr.left < sr.left - 1 || cr.right > sr.right + 1 || cr.top < sr.top - 1 || cr.bottom > sr.bottom + 1) issues.push('card outside section ' + si + '/' + ci);
      // first row only: column alignment across sections
      if (Math.abs(cr.top - r(s.querySelector('.cr-card--h')).top) < 2) (cols[ci] = cols[ci] || []).push(Math.round(cr.left));
      // content clipped? (title / price / add button visible)
      const add = c.querySelector('.cr-card__add'); const ar = add && r(add);
      if (!ar || ar.bottom > cr.bottom + 1 || ar.right > cr.right + 1) issues.push('add button clipped ' + si + '/' + ci);
      const pr = r(c.querySelector('.cr-price')); if (pr.bottom > cr.bottom || pr.right > cr.right + 1) issues.push('price clipped ' + si + '/' + ci);
    });
  });
  Object.entries(cols).forEach(([k, xs]) => { if (Math.max(...xs) - Math.min(...xs) > 1) issues.push('column ' + k + ' misaligned ' + xs.join(',')); });
  const docW = document.documentElement.scrollWidth, vw = window.innerWidth;
  if (docW > vw + 1) issues.push('horizontal overflow ' + docW + '>' + vw);
  // chat set card
  let chatCard = null;
  const rich = Array.from(document.querySelectorAll('#cr-chat-log .crc-rich')).pop();
  if (document.body.classList.contains('chat-open') && rich) {
    const root = rich.shadowRoot || rich;
    const tbl = root.querySelector('.crc-settable');
    if (!tbl) issues.push('chat set table missing');
    else {
      const roles = Array.from(tbl.querySelectorAll('td.crc-setrole')).map((td) => ({ label: td.textContent, span: td.rowSpan }));
      const card = r(root.querySelector('.crc-card'));
      Array.from(tbl.querySelectorAll('tbody tr')).forEach((tr, i) => { const tr_ = r(tr); if (tr_.right > card.right + 1) issues.push('chat row overflow ' + i); });
      chatCard = { roles, rows: tbl.querySelectorAll('tbody tr').length };
      const want = secs.map((s) => s.querySelectorAll('.cr-card--h').length);
      if (roles.length !== want.length || roles.some((x, i) => x.span !== want[i])) issues.push('chat role rowspans ' + JSON.stringify(roles) + ' vs ' + want);
    }
  }
  // chat header subtitle must be fully legible (voice controls must not squeeze it); voice bar must fit the panel
  if (document.body.classList.contains('chat-open')) {
    const sub = document.getElementById('cr-chat-sub');
    if (sub && sub.scrollWidth > sub.clientWidth + 1) issues.push('chat subtitle truncated ' + sub.scrollWidth + '>' + sub.clientWidth);
    const bar = document.querySelector('.cr-voice-bar'), panel = document.getElementById('cr-chat');
    if (bar) Array.from(bar.children).forEach((el) => { if (!el.classList.contains('cr-voice-hint') && r(el).right > r(panel).right - 1) issues.push('voice bar overflow ' + el.id); });
  }
  return { sections: secs.map((s) => s.querySelectorAll('.cr-card--h').length), cards: cards.length, card_h: hs[0], card_w: ws[0],
           board_w: Math.round(b.width), issues, chat_card: chatCard };
}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8096")
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--id-token", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    headers = {}
    if a.id_token:
        tok = subprocess.run(["gcloud", "auth", "print-identity-token"], capture_output=True, text=True, check=True).stdout.strip()
        headers = {"Authorization": "Bearer " + tok}
    sections, used = [], set()
    with httpx.Client(base_url=a.base_url, headers=headers, timeout=60) as h:
        for label, qs, n in QUERIES:
            ids = []
            for q in qs:
                for p in h.get("/api/search", params={"q": q, "page_size": 10}).json().get("results", []):
                    if p["id"] not in used and p.get("image") and len(ids) < n:
                        ids.append(p["id"]); used.add(p["id"])
                        break
                if len(ids) >= n:
                    break
            reasons = ["さくらさんの好きな食材・今週の特価（30%OFF）でお得です" if i == 0 else "よく購入されている定番品" for i in range(len(ids))]
            tags = [["家族の好み", "特価", "旬", "時短"] if i == 0 else ["よく購入"] for i in range(len(ids))]
            sections.append({"label": label, "product_ids": ids, "reasons": reasons, "tags": tags})
    args = {"theme": "さくらさんご家族の今夜の夕食セット（秋鮭の和定食）", "message": "レイアウト検証用のセットです。",
            "sections": sections, "product_ids": [i for s in sections for i in s["product_ids"]],
            "reasons": [r for s in sections for r in s["reasons"]]}
    print("sections:", [(s["label"], len(s["product_ids"])) for s in sections])
    results, ok = [], True
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        for w, hgt, chat in [(1280, 900, False), (1280, 900, True), (1440, 900, False), (1440, 900, True),
                             (1920, 1080, False), (1920, 1080, True), (1024, 800, True), (420, 900, True), (390, 844, False)]:
            ctx = br.new_context(viewport={"width": w, "height": hgt}, extra_http_headers=headers)
            pg = ctx.new_page()
            pg.goto(a.base_url + "/", wait_until="networkidle")
            if chat:
                pg.evaluate("() => window.CRChat.open()")
                pg.wait_for_timeout(400)
            pg.evaluate("(a) => window.CRClientTools.show_products_on_page(a)", args)
            pg.wait_for_selector("#cr-set-board .cr-card--h")
            pg.wait_for_timeout(900)
            res = pg.evaluate(CHECK_JS)
            res.update({"viewport": f"{w}x{hgt}", "chat": chat})
            name = f"set_{w}_{'chat' if chat else 'nochat'}.png"
            pg.screenshot(path=str(out / name))
            if chat:
                rich = pg.locator("#cr-chat-log .crc-rich").last
                rich.scroll_into_view_if_needed()
                rich.screenshot(path=str(out / f"chatcard_{w}.png"))
            res["screenshot"] = name
            results.append(res)
            print(json.dumps(res, ensure_ascii=False))
            if res.get("error") or res["issues"]:
                ok = False
            ctx.close()
        br.close()
    (out / "layout_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
