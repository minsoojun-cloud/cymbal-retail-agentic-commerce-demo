#!/usr/bin/env python3
"""Live catalog check after the v6 catalog expansion (both sites).

Per site: home rows render with images; searches (土鍋 / 牛タン / おせち / 猫砂) return results whose images load from the
site's OWN origin (/img/products/…, no 404, naturalWidth > 0); /config.js expectations; optional one chat dinner-set turn.

usage: python tests/e2e_live_catalog.py --base-url URL [--id-token] [--expect adk|ces] [--chat] [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from playwright.sync_api import sync_playwright

QUERIES = ["土鍋", "牛タン", "おせち", "猫砂"]
OUT_DEFAULT = os.environ.get("E2E_OUT", "/tmp/cymbal_e2e/live_catalog")

IMG_JS = r"""
(sel) => Array.from(document.querySelectorAll(sel)).slice(0, 16).map((i) => ({ src: i.currentSrc || i.src, ok: i.complete && i.naturalWidth > 0 }))
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=os.environ.get("ONLINE_STORE_URL", ""), required=not bool(os.environ.get("ONLINE_STORE_URL")))
    ap.add_argument("--id-token", action="store_true")
    ap.add_argument("--expect", choices=["adk", "ces"], default="adk")
    ap.add_argument("--chat", action="store_true", help="one chat dinner-set turn")
    ap.add_argument("--out", default=OUT_DEFAULT)
    a = ap.parse_args()
    base = a.base_url.rstrip("/")
    origin = "{0.scheme}://{0.netloc}".format(urlparse(base))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tag = a.expect
    token = subprocess.run(["gcloud", "auth", "print-identity-token"], capture_output=True, text=True, check=True).stdout.strip() if a.id_token else ""
    hdr = {"Authorization": "Bearer " + token} if token else {}
    res: dict = {"site": base, "issues": []}
    with httpx.Client(timeout=60, headers=hdr) as h:
        t = time.time()
        r = h.get(base + "/")
        res["get_root"] = {"status": r.status_code, "ms": int((time.time() - t) * 1000)}
        cfg = json.loads(h.get(base + "/config.js").text[len("window.CR_CONFIG = "):].strip().rstrip(";"))
        res["config"] = {k: cfg.get(k) for k in ("agentBackend", "agentPlatform", "enrichUrl", "voiceEnabled", "searchEngine")}
        feat = h.get(base + "/api/features").json()
        res["catalog_size"] = feat.get("catalog_size")
    if res["get_root"]["status"] != 200:
        res["issues"].append("GET / != 200")
    if a.expect == "ces":
        if cfg.get("agentBackend") != "ces" or "enrichUrl" in cfg or "voiceEnabled" in cfg:
            res["issues"].append("GECX config changed: " + json.dumps(res["config"], ensure_ascii=False))
    else:
        if cfg.get("agentBackend") != "adk" or not cfg.get("enrichUrl") or not cfg.get("voiceEnabled"):
            res["issues"].append("ADK config wrong: " + json.dumps(res["config"], ensure_ascii=False))

    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={"width": 1440, "height": 900})
        if token:
            ctx.route(origin + "/**", lambda route: route.continue_(headers={**route.request.headers, "authorization": "Bearer " + token}))
        pg = ctx.new_page()
        imgs: list[dict] = []
        pg.on("response", lambda r: imgs.append({"url": r.url, "status": r.status}) if "/img/" in r.url else None)
        pg.goto(base + "/", wait_until="networkidle")
        pg.wait_for_timeout(1500)
        home = pg.evaluate(IMG_JS, "#cr-home img")
        res["home_images"] = {"n": len(home), "ok": sum(1 for i in home if i["ok"])}
        pg.screenshot(path=str(out / f"{tag}_home.png"))
        res["search"] = {}
        for q in QUERIES:
            pg.goto(base + "/?q=" + q, wait_until="networkidle")
            pg.wait_for_selector("#cr-results-main .cr-card, .cr-empty", timeout=30000)
            pg.wait_for_timeout(1200)
            cards = pg.locator("#cr-results-main .cr-card")
            titles = pg.eval_on_selector_all("#cr-results-main .cr-card .cr-card__title", "els => els.slice(0,3).map(e => e.textContent)")
            ims = pg.evaluate(IMG_JS, "#cr-results-main .cr-card__media img")
            res["search"][q] = {"results": cards.count(), "top": titles, "img_ok": sum(1 for i in ims if i["ok"]), "img_n": len(ims)}
            if not cards.count():
                res["issues"].append(f"no results for {q}")
            if any(not i["ok"] for i in ims):
                res["issues"].append(f"broken image for {q}: " + ", ".join(i["src"] for i in ims if not i["ok"])[:200])
            pg.screenshot(path=str(out / f"{tag}_search_{q}.png"))
        foreign = [i["url"] for i in imgs if "/img/products/" in i["url"] and not i["url"].startswith(origin)]
        bad = [i for i in imgs if i["status"] >= 400]
        res["image_requests"] = {"n": len(imgs), "foreign_origin": len(foreign), "errors": len(bad)}
        if foreign:
            res["issues"].append("product images from another origin: " + foreign[0])
        if bad:
            res["issues"].append("image HTTP errors: " + json.dumps(bad[:3]))
        if a.chat:
            pg.goto(base + "/", wait_until="networkidle")
            pg.click("#cr-fab")
            pg.fill("#cr-chat-input", "今夜の夕食をお勧めしてね")
            t = time.time()
            pg.press("#cr-chat-input", "Enter")
            try:
                pg.wait_for_selector("#cr-set-board .cr-card--h", timeout=150000)
                res["chat_set_s"] = round(time.time() - t, 1)
                pg.wait_for_function("() => !document.getElementById('cr-chat').classList.contains('is-busy')", timeout=120000)
                res["chat_turn_s"] = round(time.time() - t, 1)
                res["set_sections"] = pg.eval_on_selector_all("#cr-set-board .cr-set-sec", "els => els.map(e => e.dataset.role + ':' + e.querySelectorAll('.cr-card--h').length)")
                ims = pg.evaluate(IMG_JS, "#cr-set-board img")
                res["set_img_ok"] = f"{sum(1 for i in ims if i['ok'])}/{len(ims)}"
            except Exception as e:  # noqa: BLE001
                res["issues"].append("chat dinner set failed: " + str(e)[:160])
                res["chat_last_bot"] = pg.eval_on_selector_all("#cr-chat-log .cr-msg--bot", "els => els.slice(-1).map(e => e.textContent)")
            pg.screenshot(path=str(out / f"{tag}_chat_set.png"))
        ctx.close()
        br.close()
    res["ok"] = not res["issues"]
    print(json.dumps(res, ensure_ascii=False, indent=1))
    (out / f"{tag}_results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
