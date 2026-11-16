#!/usr/bin/env python3
"""Playwright E2E for the CONTRACT v5 ADK storefront (cymbal-site-adk) + a no-regression probe of cymbal-site (GECX).

ADK site (with an ID token sent ONLY to the ADK site origin while the service is not public):
  home loads → header 「データエンリッチメント」 icon link (href = ENRICH_URL, tooltip, 36px icon, no mobile overflow)
  → chat subtitle 「Gemini ・ Agent Development Kit」 + footer ADK → 「今夜の夕食をお勧めしてね」 → dinner set
  → 「セットをカートに入れて」 → cart card → レジに進む (card) → slot (card) → typed 「注文を確定してください」
  → order card → 配達完了.
GECX site (anonymous): GET / → 200, /config.js → agentBackend=ces and no enrichUrl.

usage:
  python tests/e2e_site_adk.py --base-url "$ONLINE_STORE_URL" [--enrich-url "$ENRICH_URL"] --id-token [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

ENRICH_DEFAULT = os.environ.get("ENRICH_URL", "")
GECX_DEFAULT = os.environ.get("GECX_URL", "")
OUT_DEFAULT = os.environ.get("E2E_OUT", "/tmp/cymbal_e2e/site_adk")


def parse_cfg(js: str) -> dict:
    assert js.startswith("window.CR_CONFIG = "), js[:80]
    return json.loads(js[len("window.CR_CONFIG = "):].strip().rstrip(";"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=os.environ.get("ONLINE_STORE_URL", ""), required=not bool(os.environ.get("ONLINE_STORE_URL")))
    ap.add_argument("--gecx-url", default=GECX_DEFAULT)
    ap.add_argument("--enrich-url", default=ENRICH_DEFAULT)
    ap.add_argument("--id-token", action="store_true", help="send `gcloud auth print-identity-token` to --base-url only")
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--live-wait", type=float, default=150)
    a = ap.parse_args()
    base = a.base_url.rstrip("/")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    live_wait = a.live_wait * 1000
    results: list[dict] = []
    shots: list[str] = []
    token = subprocess.check_output(["gcloud", "auth", "print-identity-token"], text=True).strip() if a.id_token else ""

    def step(name, fn):
        t0 = time.time()
        try:
            info = fn()
            results.append({"step": name, "ok": True, "sec": round(time.time() - t0, 1), "info": info})
            print(f"  ✓ {name} ({time.time() - t0:.1f}s) {json.dumps(info, ensure_ascii=False)[:600] if info else ''}")
        except Exception as e:  # noqa: BLE001
            results.append({"step": name, "ok": False, "sec": round(time.time() - t0, 1), "error": str(e)[:800]})
            print(f"  ✗ {name}: {e}")
            raise

    # ---------- HTTP probes (no browser) ----------
    def gecx_unchanged():
        with httpx.Client(timeout=30, follow_redirects=True) as c:  # anonymous on purpose
            r = c.get(a.gecx_url.rstrip("/") + "/")
            assert r.status_code == 200, r.status_code
            cfg = parse_cfg(c.get(a.gecx_url.rstrip("/") + "/config.js").text)
        assert cfg["agentBackend"] == "ces" and cfg["agentPlatform"] == "GECX AI Studio", cfg
        assert "enrichUrl" not in cfg, cfg
        return {"GET /": 200, "agentBackend": cfg["agentBackend"], "enrichUrl": cfg.get("enrichUrl")}

    def adk_config():
        h = {"Authorization": "Bearer " + token} if token else {}
        with httpx.Client(timeout=30) as c:
            anon = c.get(base + "/").status_code
            cfg = parse_cfg(c.get(base + "/config.js", headers=h).text)
        assert cfg["agentBackend"] == "adk" and cfg["agentMode"] == "live", cfg
        assert cfg["agentPlatform"] == "Agent Development Kit", cfg
        if a.enrich_url:
            assert cfg.get("enrichUrl") == a.enrich_url, cfg
        return {"anonymous GET / status": anon, "public": anon == 200, "agentBackend": cfg["agentBackend"],
                "enrichUrl": cfg.get("enrichUrl")}

    ok = True
    try:
        if a.gecx_url:
            step("GECX cymbal-site unchanged (anonymous / 200, config ces, no enrich link)", gecx_unchanged)
        step("ADK cymbal-site-adk /config.js (adk, enrichUrl)", adk_config)
    except Exception:  # noqa: BLE001
        ok = False

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="ja-JP")
        if token:
            def _auth(route):
                route.continue_(headers={**route.request.headers, "authorization": "Bearer " + token})
            ctx.route(base + "/**", _auth)  # ID token only to the ADK site origin
            ctx.route(base + "/", _auth)
        page = ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        agent_turns: list[dict] = []

        def _capture(resp):
            if "/api/agent/stream" not in resp.url or resp.request.method != "POST":
                return
            try:
                msg = json.loads(resp.request.post_data or "{}").get("message", "")
                evs = [json.loads(l[6:]) for l in resp.text().split("\n") if l.startswith("data: ")]
                agent_turns.append({"message": msg, "actions": [e["name"] for e in evs if e.get("type") == "action"],
                                    "errors": [e.get("message") for e in evs if e.get("type") == "error"]})
            except Exception as e:  # noqa: BLE001
                agent_turns.append({"message": "?", "error": str(e)[:120]})
        page.on("response", _capture)

        def shot(name, **kw):
            p = str(out / f"{len(shots) + 1:02d}_{name}.png")
            page.screenshot(path=p, **kw)
            shots.append(p)
            return p

        def idle():
            page.wait_for_function("() => !document.getElementById('cr-chat').classList.contains('is-busy')",
                                   timeout=live_wait)

        def send(text):
            ta = page.locator("#cr-chat-input")
            ta.click()
            ta.fill(text)
            ta.press("Enter")

        def home_and_link():
            page.goto(base + "/", wait_until="networkidle")
            expect(page.locator("#cr-home")).to_be_visible()
            link = page.locator(".cr-header__actions #cr-enrich-link")
            expect(link).to_be_visible()
            assert link.get_attribute("href") == a.enrich_url, link.get_attribute("href")
            assert link.get_attribute("title") == "商品データエンリッチメント・スタジオへ"
            assert link.get_attribute("target") in (None, "", "_self")  # same tab
            expect(link.locator(".cr-xlink__label")).to_have_text("データエンリッチメント")
            ib = link.locator(".cr-xlink__icon").bounding_box()
            assert round(ib["width"]) == 36 and round(ib["height"]) == 36, ib
            order = page.locator(".cr-header__actions > *").evaluate_all("els => els.map(e => e.id || e.className)")
            assert order.index("cr-enrich-link") < order.index("cr-orders-btn") < order.index("cr-cart-btn"), order
            page.evaluate("window.scrollTo(0, 0)")
            shot("adk_home", full_page=False)
            shot("adk_header_desktop", clip={"x": 0, "y": 0, "width": 1440, "height": 80})
            link.hover()
            page.wait_for_timeout(400)
            shot("adk_header_hover", clip={"x": 720, "y": 0, "width": 720, "height": 80})
            page.mouse.move(5, 400)
            return {"href": a.enrich_url, "header_order": order, "icon": [ib["width"], ib["height"]]}

        def mobile_header():
            mp = ctx.new_page()
            mp.set_viewport_size({"width": 360, "height": 740})
            mp.goto(base + "/", wait_until="networkidle")
            expect(mp.locator("#cr-enrich-link")).to_be_visible()
            sw = mp.evaluate("document.documentElement.scrollWidth")
            assert sw <= 360, f"horizontal overflow: scrollWidth={sw}"
            p = str(out / f"{len(shots) + 1:02d}_adk_header_mobile360.png")
            mp.screenshot(path=p, clip={"x": 0, "y": 0, "width": 360, "height": 72})
            shots.append(p)
            mp.close()
            return {"scrollWidth": sw}

        def chat_dinner_set():
            page.goto(base + "/", wait_until="networkidle")
            page.evaluate("Cart.clear(); sessionStorage.removeItem('cr_chat_v3')")
            page.reload(wait_until="networkidle")
            page.locator("#cr-fab").click()
            assert not page.evaluate("window.CRChat.mock"), "chat is in mock mode"
            sub = page.locator("#cr-chat-sub").inner_text()
            powered = page.locator("#cr-powered-agent").inner_text()
            assert sub == "Gemini ・ Agent Development Kit", sub
            assert powered == "Agent Development Kit", powered
            send("今夜の夕食をお勧めしてね")
            expect(page.locator("#cr-agent-view[data-mode='set'] .cr-set-sec").first).to_be_visible(timeout=live_wait)
            set_card = page.locator(".crc-rich--set").last
            expect(set_card).to_be_visible(timeout=15000)
            idle()
            page.wait_for_timeout(1200)
            shot("adk_chat_dinner_set")
            return {"subtitle": sub, "footer": powered, "set_rows": set_card.locator("tbody tr").count(),
                    "sections": page.locator("#cr-agent-view .cr-set-sec").count(),
                    "set_total": page.locator("#cr-set-total").inner_text()}

        def chat_cart():
            send("セットをカートに入れて")
            cart = page.locator(".crc-rich--cart:not(.is-collapsed)")
            expect(cart).to_have_count(1, timeout=live_wait)
            idle()
            page.wait_for_timeout(1200)
            rows = cart.locator("tbody tr").count()
            assert rows >= 2, rows
            shot("adk_chat_cart_card")
            return {"cart_rows": rows, "cart_count": page.locator("#cr-cart-count").inner_text()}

        def chat_checkout():
            cart = page.locator(".crc-rich--cart:not(.is-collapsed)")
            cart.locator("[data-crc-act='checkout']").click()  # sends 「レジに進みます」
            expect(page.locator(".crc-rich--slots").last).to_be_visible(timeout=live_wait)
            idle()
            page.locator(".crc-rich--slots").last.locator("[data-slot-id='d1_pm']").click()
            expect(page.locator(".crc-rich--confirm").last).to_be_visible(timeout=live_wait)
            idle()
            shot("adk_chat_confirm")
            send("注文を確定してください")  # typed, not the button
            order = page.locator(".crc-rich--order").last
            expect(order).to_be_visible(timeout=live_wait)
            idle()
            oid = order.locator("[data-crc-order]").get_attribute("data-crc-order")
            assert re.fullmatch(r"CR-\d{8}-\d{4}", oid or ""), oid
            speed = float(page.evaluate("window.CR_CONFIG.deliverySpeedSec") or 8)
            page.wait_for_selector(".crc-rich--order [data-status='delivered']", timeout=(speed * 3 + 20) * 1000)
            expect(order).to_contain_text("配達完了")
            page.wait_for_timeout(800)
            shot("adk_chat_delivered")
            po = next((t for t in reversed(agent_turns) if t.get("message") == "注文を確定してください"), None)
            assert po and "place_order" in po["actions"], po
            return {"order_id": oid, "place_order_turn": po["actions"]}

        try:
            step("ADK home + header enrichment icon link", home_and_link)
            step("ADK header at 360px (no overflow)", mobile_header)
            step("ADK chat: 今夜の夕食をお勧めしてね → set", chat_dinner_set)
            step("ADK chat: セットをカートに入れて → cart card", chat_cart)
            step("ADK chat: checkout → typed 注文を確定してください → 配達完了", chat_checkout)
        except Exception:  # noqa: BLE001
            ok = False
            try:
                shot("FAIL")
            except Exception:  # noqa: BLE001
                pass
        browser.close()

    report = {"ok": ok and all(s["ok"] for s in results), "base": base, "steps": results, "screens": shots,
              "agent_turns": agent_turns, "page_errors": errors}
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(("PASS" if report["ok"] else "FAIL"), out / "report.json")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
