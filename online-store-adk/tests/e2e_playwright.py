#!/usr/bin/env python3
"""Playwright E2E for the Cymbal Retail storefront.

Flow: home (first load = retail home with recommendation rows, never the empty agent view) → search → (tiles / facets / AI summary / conversational refine visible) → refine → product modal
→ add to cart → drawer → checkout → slot → payment → confirm → order placed → 配達完了 (+ history),
plus the agent client functions (window.CRClientTools) exercised directly, the AIコンシェルジュ panel (CONTRACT v3: own
slide-over panel; mock agent when ADK_AGENT_URL is unset, otherwise the real ADK agent through /api/agent/stream) with
cart / slot / confirm / order / dinner-set cards inside the chat, and chat history persistence.

usage:
  python tests/e2e_playwright.py --base-url http://127.0.0.1:8080 [--query カレー] [--out DIR] [--headed]
The site should run with a short DELIVERY_SPEED_SEC (e.g. 3) so the delivery timeline completes quickly;
the script reads CR_CONFIG.deliverySpeedSec and waits accordingly.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

DEFAULT_OUT = os.environ.get("E2E_OUT", "/tmp/cymbal_e2e/screens")


class Run:
    def __init__(self, page: Page, out: Path, only: str = ""):
        self.page, self.out, self.steps, self.n, self.only = page, out, [], 0, only

    def shot(self, name: str, full: bool = False) -> str:
        self.n += 1
        p = self.out / f"{self.n:02d}_{name}.png"
        self.page.screenshot(path=str(p), full_page=full)
        return str(p)

    def step(self, name: str, fn):
        if self.only and self.only not in name:
            return
        t0 = time.time()
        try:
            info = fn()
            self.steps.append({"step": name, "ok": True, "sec": round(time.time() - t0, 2), "info": info})
            print(f"  ✓ {name} ({time.time() - t0:.1f}s) {info or ''}")
        except Exception as e:  # noqa: BLE001
            self.steps.append({"step": name, "ok": False, "sec": round(time.time() - t0, 2), "error": str(e)[:500]})
            print(f"  ✗ {name}: {e}")
            try:
                self.shot("FAIL_" + name.replace(" ", "_"))
            except Exception:  # noqa: BLE001
                pass
            raise


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=os.environ.get("BASE_URL", "http://127.0.0.1:8080"))
    ap.add_argument("--query", default="カレー")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--max-delivery-wait", type=float, default=90)
    ap.add_argument("--only", default="", help="run only steps whose name contains this text (e.g. 'chat:')")
    ap.add_argument("--id-token", action="store_true",
                    help="send `gcloud auth print-identity-token` to the site origin only (for non-public Cloud Run)")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    base = a.base_url.rstrip("/")
    console_errors: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not a.headed)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="ja-JP", device_scale_factor=1)
        if a.id_token:
            import subprocess
            token = subprocess.check_output(["gcloud", "auth", "print-identity-token"], text=True).strip()

            def _auth(route):
                route.continue_(headers={**route.request.headers, "authorization": "Bearer " + token})
            ctx.route(base + "/**", _auth)
            ctx.route(base + "/", _auth)
        page = ctx.new_page()
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append("pageerror: " + str(e)))
        r = Run(page, out, a.only)
        ok = True
        try:
            HOME_ROWS = ["cr-row-foryou", "cr-row-sale", "cr-row-seasonal", "cr-row-new", "cr-row-again", "cr-row-popular"]

            def home():
                # a stale agent URL (reload / shared link) must still open the home page
                page.goto(base + "/?view=agent", wait_until="networkidle")
                expect(page.locator("#cr-home")).to_be_visible()
                assert "view=agent" not in page.url, page.url
                page.goto(base + "/", wait_until="networkidle")
                expect(page.locator("#cr-home")).to_be_visible()
                for row in HOME_ROWS:
                    expect(page.locator(f"#{row} .cr-card").first).to_be_visible(timeout=15000)
                assert "まだありません" not in page.locator("#cr-view").inner_text()
                expect(page.locator("#cr-hero .cr-slide")).to_have_count(3)
                expect(page.locator("#cr-sec-foryou h2")).to_have_text("さくらさんへのおすすめ")
                expect(page.locator("#cr-row-popular .cr-card__rank").first).to_have_text("1")
                expect(page.locator("#cr-cats .cr-cat").first).to_be_visible(timeout=10000)
                counts = {row: page.locator(f"#{row} .cr-card").count() for row in HOME_ROWS}
                assert all(n >= 6 for n in counts.values()), counts
                cookies = {c["name"]: c["value"] for c in ctx.cookies()}
                assert cookies.get("cr_customer") == "CR-0001", cookies
                assert cookies.get("cr_visitor"), "cr_visitor cookie missing"
                page.evaluate("localStorage.removeItem('cr_cart_v1'); sessionStorage.removeItem('cr_chat_v3')")
                page.wait_for_timeout(600)
                r.shot("home")
                r.shot("home_full", full=True)
                # carousel + 「カートに追加」 from a home row
                page.locator("#cr-hero .cr-hero2__dot").nth(2).click()
                page.wait_for_timeout(900)
                r.shot("home_carousel_new")
                page.locator("#cr-row-foryou .cr-card [data-add]").first.click()
                expect(page.locator("#cr-cart-count")).to_have_text("1")
                page.evaluate("Cart.clear()")
                return {"engine": page.evaluate("window.CR_CONFIG.searchEngine"), "agentMode": page.evaluate("window.CR_CONFIG.agentMode"),
                        "deliverySpeedSec": page.evaluate("window.CR_CONFIG.deliverySpeedSec"), "rows": counts}
            r.step("home page (first load: hero + recommendation rows)", home)

            def autocomplete():
                inp = page.locator("#cr-search-input")
                inp.click()
                inp.press_sequentially(a.query[:2], delay=80)
                expect(page.locator("#cr-ac-list li").first).to_be_visible(timeout=10000)
                n = page.locator("#cr-ac-list li").count()
                r.shot("autocomplete")
                inp.fill(a.query)
                inp.press("Enter")
                return {"suggestions": n}
            r.step("autocomplete + submit", autocomplete)

            def results():
                expect(page.locator("#cr-grid .cr-card").first).to_be_visible(timeout=20000)
                expect(page.locator("#cr-tiles .cr-chip").first).to_be_visible(timeout=10000)
                expect(page.locator("#cr-facets .cr-facet").first).to_be_visible()
                expect(page.locator("#cr-ai-summary")).to_be_visible(timeout=40000)
                expect(page.locator("#cr-refine")).to_be_visible(timeout=10000)
                time.sleep(0.6)
                r.shot("search_results")
                feats = page.evaluate("Object.fromEntries([...document.querySelectorAll('.cr-feature[data-feature]')].map(e=>[e.dataset.feature,e.dataset.status]))")
                return {"cards": page.locator("#cr-grid .cr-card").count(), "tiles": page.locator("#cr-tiles .cr-chip").count(),
                        "facets": page.locator("#cr-facets .cr-facet").count(), "features": feats,
                        "refine_source": page.locator("#cr-refine").get_attribute("data-source"),
                        "ai_summary": page.locator("#cr-ai-summary").inner_text()[:120]}
            r.step("search results (tiles/facets/AI summary/refine)", results)

            def refine():
                before = page.locator("#cr-results-head").inner_text()
                page.locator("#cr-refine-answers .cr-chip").first.click()
                page.wait_for_timeout(400)
                expect(page.locator("#cr-grid .cr-card").first).to_be_visible(timeout=20000)
                page.wait_for_timeout(800)
                r.shot("after_refine")
                return {"before": before[:60], "after": page.locator("#cr-results-head").inner_text()[:60]}
            r.step("conversational refine answer", refine)

            def tile():
                chip = page.locator("#cr-tiles .cr-chip:not(.is-selected)").first
                label = chip.inner_text()
                chip.click()
                expect(page.locator("#cr-tiles .cr-chip.is-selected").first).to_be_visible(timeout=15000)
                expect(page.locator("#cr-grid .cr-card").first).to_be_visible(timeout=20000)
                r.shot("after_tile")
                page.locator("#cr-tiles .cr-chip.is-selected").first.click()
                expect(page.locator("#cr-grid .cr-card").first).to_be_visible(timeout=20000)
                return {"tile": label}
            r.step("tile navigation", tile)

            def kana_and_conversation():
                info = {}
                page.goto(base + "/?q=" + "ふらいぱん", wait_until="networkidle")
                expect(page.locator("#cr-grid .cr-card").first).to_be_visible(timeout=30000)
                head = page.locator("#cr-results-head").inner_text()
                assert "フライパン" in head, head
                info["kana_head"] = head.replace("\n", " ")[:80]
                page.goto(base + "/?q=" + "今夜の夕飯に鍋をしたい", wait_until="networkidle")
                expect(page.locator("#cr-grid .cr-card").first).to_be_visible(timeout=40000)
                expect(page.locator("#cr-refine")).to_be_visible(timeout=40000)
                page.wait_for_timeout(1500)
                info["refine_source"] = page.locator("#cr-refine").get_attribute("data-source")
                info["question"] = page.locator("#cr-refine").inner_text().replace("\n", " ")[:160]
                r.shot("conversational_search")
                return info
            r.step("hiragana→katakana + conversational search", kana_and_conversation)

            def modal():
                page.locator("#cr-grid .cr-card .cr-card__title").first.click()
                expect(page.locator("#cr-product-modal")).to_be_visible()
                expect(page.locator("#cr-pm-add")).to_be_visible()
                assert "product=" in page.url
                page.wait_for_timeout(400)
                r.shot("product_modal")
                page.locator("#cr-product-modal [data-qstep='1']").click()
                page.locator("#cr-pm-add").click()
                expect(page.locator("#cr-product-modal")).to_be_hidden()
                expect(page.locator("#cr-cart-count")).to_have_text("2")
                return None
            r.step("product modal → add 2", modal)

            def add_more():
                page.locator("#cr-grid .cr-card [data-add]").nth(1).click()
                page.locator("#cr-grid .cr-card [data-add]").nth(2).click()
                expect(page.locator("#cr-cart-count")).to_have_text("4")
                page.locator("#cr-cart-btn").click()
                expect(page.locator("#cr-drawer.is-open")).to_be_visible()
                page.locator("#cr-drawer-list .cr-line button[data-act='inc']").first.click()
                expect(page.locator("#cr-cart-count")).to_have_text("5")
                page.wait_for_timeout(400)
                r.shot("cart_drawer")
                return {"subtotal": page.locator("#cr-drawer-total").inner_text()}
            r.step("add from grid + drawer qty ±", add_more)

            def checkout_delivery():
                page.locator("#cr-checkout-btn").click()
                expect(page.locator("#cr-checkout[data-state='delivery']")).to_be_visible()
                ids = page.eval_on_selector_all("[data-slot]", "els => els.map(e => e.dataset.slot)")
                assert ids == ["d1_am", "d1_pm", "d1_eve", "d2_am", "d2_pm"], ids
                page.wait_for_timeout(500)
                r.shot("checkout_delivery")
                page.locator("#slot-d1_pm").click()
                expect(page.locator("#cr-checkout[data-state='payment']")).to_be_visible()
                assert "Cymbal Pay（VISA **** 4242）" in page.locator("#cr-step-payment").inner_text()
                page.wait_for_timeout(450)
                r.shot("checkout_payment")
                page.locator("#cr-pay-next").click()
                expect(page.locator("#cr-checkout[data-state='confirm']")).to_be_visible()
                page.wait_for_timeout(450)
                r.shot("checkout_confirm")
                sub = page.evaluate("Checkout.totals()")
                exp_ship = 0 if sub["subtotal"] >= 3000 else 330
                assert sub["shipping"] == exp_ship, sub
                return {"slots": ids, "totals": sub}
            r.step("checkout: slot → payment → confirm", checkout_delivery)

            order_id = {}

            def place():
                page.locator("#cr-place-order").click()
                expect(page.locator("#cr-order")).to_be_visible(timeout=10000)
                oid = page.locator("#cr-order").get_attribute("data-order")
                import re
                assert re.fullmatch(r"CR-\d{8}-\d{4}", oid or ""), oid
                assert page.locator("#cr-cart-count").inner_text() == "0"
                page.wait_for_timeout(700)
                r.shot("order_placed")
                order_id["id"] = oid
                return {"order_id": oid}
            r.step("place order", place)

            def delivered():
                speed = float(page.evaluate("window.CR_CONFIG.deliverySpeedSec") or 8)
                wait = min(a.max_delivery_wait, speed * 3 + 6)
                page.wait_for_selector("#cr-order[data-status='shipping']", timeout=(speed * 2 + 5) * 1000)
                r.shot("order_shipping")
                page.wait_for_selector("#cr-delivered", timeout=wait * 1000)
                expect(page.locator("#cr-toast")).to_contain_text("配達が完了", timeout=5000)
                page.wait_for_timeout(600)
                r.shot("order_delivered")
                st = page.evaluate(f"Orders.toAgent('{order_id['id']}')")
                assert st["status"] == "delivered", st
                return st
            r.step("delivery timeline → 配達完了", delivered)

            def history():
                page.locator("#cr-orders-btn").click()
                expect(page.locator(f".cr-history__item[data-order='{order_id['id']}']")).to_be_visible()
                r.shot("order_history")
                return None
            r.step("order history", history)

            def agent_functions():
                page.goto(base + "/", wait_until="networkidle")
                ids = page.evaluate("fetch('/api/search?q=' + encodeURIComponent('フライパン') + '&page_size=6').then(r=>r.json()).then(j=>j.results.map(p=>p.id))")
                if len(ids) < 3:
                    ids = page.evaluate("fetch('/api/search?q=' + encodeURIComponent('カレー') + '&page_size=6').then(r=>r.json()).then(j=>j.results.map(p=>p.id))")
                T = "window.CRClientTools"
                res = {}
                res["show_products_on_page"] = page.evaluate(f"{T}.show_products_on_page({{message:'テスト用のおすすめです', product_ids:{json.dumps(ids[:4])}, reasons:['理由A','理由B','理由C','理由D']}})")
                expect(page.locator("#cr-agent-view .cr-card").first).to_be_visible()
                page.wait_for_timeout(500)
                r.shot("agent_show_products")
                # back-to-home path from the agent result view, and forward again via history
                page.locator("#cr-back-home").click()
                expect(page.locator("#cr-home")).to_be_visible()
                page.go_back()
                expect(page.locator("#cr-agent-view .cr-card").first).to_be_visible()
                res["show_comparison"] = page.evaluate(f"{T}.show_comparison({{title:'比較テスト', product_ids:{json.dumps(ids[:3])}, rows:[{{label:'特徴', values:['A','B','C']}}]}})")
                expect(page.locator("#cr-compare-view table")).to_be_visible()
                page.wait_for_timeout(400)
                r.shot("agent_comparison")
                res["start_checkout_empty"] = page.evaluate(f"{T}.start_checkout({{}})")
                assert res["start_checkout_empty"] == {"ok": False, "error": "EMPTY_CART"}, res["start_checkout_empty"]
                res["add_to_cart"] = page.evaluate(f"{T}.add_to_cart({{product_id:'{ids[0]}', quantity:2}})")
                assert res["add_to_cart"]["ok"] and res["add_to_cart"]["cart_count"] == 2
                res["get_cart"] = page.evaluate(f"{T}.get_cart({{}})")
                res["place_order_noslot"] = page.evaluate(f"{T}.place_order({{}})")
                assert res["place_order_noslot"]["ok"] is False
                page.wait_for_timeout(16000)  # once() dedupe window for place_order
                res["start_checkout"] = page.evaluate(f"{T}.start_checkout({{}})")
                assert [s["slot_id"] for s in res["start_checkout"]["slots"]] == ["d1_am", "d1_pm", "d1_eve", "d2_am", "d2_pm"]
                res["select_delivery_slot"] = page.evaluate(f"{T}.select_delivery_slot({{slot_id:'d2_am'}})")
                s = res["select_delivery_slot"]
                assert s["ok"] and s["next"] == "confirm" and s["payment_method"] == "Cymbal Pay（VISA **** 4242）", s
                expect(page.locator("#cr-checkout[data-state='confirm']")).to_be_visible()
                page.wait_for_timeout(450)
                r.shot("agent_checkout_confirm")
                # CONTRACT v3: the agent generates the order id → the page must use args.order_id
                agent_oid = "CR-" + time.strftime("%Y%m%d") + "-" + str(4000 + int(time.time()) % 5000)
                res["place_order"] = page.evaluate(f"{T}.place_order({{order_id:'{agent_oid}'}})")
                assert res["place_order"]["ok"] and res["place_order"]["slot_label"] == "明後日 9:00-12:00"
                assert res["place_order"]["order_id"] == agent_oid, res["place_order"]
                expect(page.locator("#cr-order")).to_be_visible()
                res["get_order_status"] = page.evaluate(f"{T}.get_order_status({{}})")
                assert res["get_order_status"]["order_id"] == res["place_order"]["order_id"]
                return res
            r.step("agent client functions", agent_functions)

            # ---------------- CONTRACT v2: cart / checkout / dinner set INSIDE the chat window ----------------
            live_wait = 120000

            def chat_cart_card():
                page.goto(base + "/?q=" + a.query, wait_until="networkidle")
                expect(page.locator("#cr-grid .cr-card").first).to_be_visible(timeout=30000)
                page.evaluate("Cart.clear()")
                page.locator("#cr-fab").click()
                page.wait_for_timeout(2500)
                mock = page.evaluate("window.CRChat.mock")
                expect(page.locator("#cr-chat-log .cr-msg--bot").first).to_be_visible()
                page.locator("#cr-grid .cr-card [data-add]").first.click()
                live = page.locator(".crc-rich--cart:not(.is-collapsed)")
                expect(live).to_have_count(1, timeout=10000)
                expect(live.locator("[data-crc-act='checkout']")).to_be_visible()
                assert not page.locator("#cr-drawer.is-open").count(), "drawer must stay closed while chat is open"
                live.locator("[data-crc-act='inc']").first.click()
                expect(page.locator("#cr-cart-count")).to_have_text("2")
                expect(live.locator("tbody tr").first).to_contain_text("2")
                live.locator("[data-crc-act='dec']").first.click()
                expect(page.locator("#cr-cart-count")).to_have_text("1")
                page.locator("#cr-grid .cr-card [data-add]").nth(1).click()
                page.locator("#cr-grid .cr-card [data-add]").nth(2).click()
                expect(page.locator("#cr-cart-count")).to_have_text("3")
                expect(page.locator(".crc-rich--cart:not(.is-collapsed)")).to_have_count(1)
                expect(page.locator(".crc-rich--cart:not(.is-collapsed) tbody tr")).to_have_count(3)
                # remove one line, then header カート → card (not drawer)
                page.locator(".crc-rich--cart:not(.is-collapsed) [data-crc-act='rm']").nth(2).click()
                expect(page.locator("#cr-cart-count")).to_have_text("2")
                page.locator("#cr-cart-btn").click()
                page.wait_for_timeout(500)
                assert not page.locator("#cr-drawer.is-open").count(), "header cart opened the drawer while chat is open"
                expect(page.locator(".crc-rich--cart:not(.is-collapsed)")).to_have_count(1)
                page.wait_for_timeout(600)
                r.shot("chat_cart_card")
                card = page.locator(".crc-rich--cart:not(.is-collapsed)").inner_text()
                for k in ("小計", "送料", "合計", "レジに進む"):
                    assert k in card, (k, card)
                return {"mock": mock, "cart_cards": page.locator(".crc-rich--cart").count(), "count": page.locator("#cr-cart-count").inner_text()}
            r.step("chat: cart card (add / qty ± / remove / header cart)", chat_cart_card)

            def chat_checkout():
                mock = page.evaluate("window.CRChat.mock")
                info = {"mock": mock}
                page.locator(".crc-rich--cart:not(.is-collapsed) [data-crc-act='checkout']").click()
                try:
                    expect(page.locator(".crc-rich--slots").last).to_be_visible(timeout=10000 if mock else live_wait)
                except Exception as e:  # noqa: BLE001
                    if mock:
                        raise
                    info["slots_card"] = "not observed (agent did not call start_checkout): " + str(e)[:80]
                    r.shot("chat_checkout_no_slots")
                    return info
                ids = page.locator(".crc-rich--slots").last.locator("[data-crc-act='slot']").evaluate_all("els => els.map(e => e.dataset.slotId)")
                assert ids == ["d1_am", "d1_pm", "d1_eve", "d2_am", "d2_pm"], ids
                page.wait_for_timeout(700 if mock else 4000)
                r.shot("chat_slots_card")
                page.locator(".crc-rich--slots").last.locator("[data-slot-id='d1_pm']").click()
                expect(page.locator(".crc-rich--confirm").last).to_be_visible(timeout=10000 if mock else live_wait)
                conf = page.locator(".crc-rich--confirm").last.inner_text()
                assert "Cymbal Pay（VISA **** 4242）" in conf, conf
                assert "注文を確定する" in conf
                info["slot_state"] = page.evaluate("Checkout.state")
                page.wait_for_timeout(700 if mock else 4000)
                r.shot("chat_confirm_card")
                page.locator(".crc-rich--confirm").last.locator("[data-crc-act='place']").click()
                order = page.locator(".crc-rich--order").last
                expect(order).to_be_visible(timeout=10000 if mock else live_wait)
                oid = order.locator("[data-crc-order]").get_attribute("data-crc-order")
                import re
                assert re.fullmatch(r"CR-\d{8}-\d{4}", oid or ""), oid
                page.wait_for_timeout(600)
                r.shot("chat_order_card_placed")
                speed = float(page.evaluate("window.CR_CONFIG.deliverySpeedSec") or 8)
                page.wait_for_selector(".crc-rich--order [data-status='shipping']", timeout=(speed * 2 + 6) * 1000)
                r.shot("chat_order_card_shipping")
                page.wait_for_selector(".crc-rich--order [data-status='delivered']", timeout=(speed * 3 + 10) * 1000)
                expect(order).to_contain_text("配達完了")
                page.wait_for_timeout(800)
                r.shot("chat_order_card_delivered")
                info.update({"order_id": oid, "collapsed_cart": page.locator(".crc-rich--cart.is-collapsed").count()})
                return info
            r.step("chat: レジに進む → slots → confirm → order → 配達完了", chat_checkout)

            def chat_dinner_set():
                page.goto(base + "/", wait_until="networkidle")
                page.locator("#cr-fab").click()
                page.wait_for_timeout(2000)
                roles = [("主菜", "鮭"), ("副菜", "ひじき"), ("汁物", "豚汁"), ("主食", "ごはん"), ("デザート・果物", "みかん")]
                sections, used = [], set()
                tagsets = [["よく購入", "家族の好み"], ["時短", "特価"], ["家族の好み"], ["よく購入"], ["旬"]]
                for (label, q), tags in zip(roles, tagsets):
                    ids = page.evaluate("q => fetch('/api/search?q=' + encodeURIComponent(q) + '&page_size=4').then(r => r.json()).then(j => j.results.map(p => p.id))", q)
                    ids = [i for i in ids if i not in used][:1]
                    if not ids:
                        continue
                    used.update(ids)
                    sections.append({"label": label, "product_ids": ids, "reasons": [label + "のおすすめ理由"], "tags": [tags]})
                assert len(sections) >= 3, sections
                # optional quantities (CONTRACT v2.1): 主菜 ×2, 副菜 ×3, others default 1
                sections[0]["quantities"] = [2]
                sections[1]["quantities"] = [3]
                flat = [i for s in sections for i in s["product_ids"]]
                args = {"theme": "さくらさんご家族の今夜の夕食セット（秋鮭の和定食）", "message": "テスト: よく購入・家族の好み・特価・旬から組み合わせ",
                        "product_ids": flat, "reasons": [x for s in sections for x in s["reasons"]], "sections": sections}
                res = page.evaluate("a => window.CRClientTools.show_products_on_page(a)", args)
                assert res["shown"] == len(flat), res
                expect(page.locator("#cr-agent-view[data-mode='set']")).to_be_visible()
                expect(page.locator("#cr-agent-view .cr-set-sec")).to_have_count(len(sections))
                expect(page.locator("#cr-set-total")).to_be_visible()
                expect(page.locator("#cr-agent-view .cr-tag--freq").first).to_be_visible()
                set_card = page.locator(".crc-rich--set").last
                expect(set_card).to_be_visible(timeout=5000)
                expect(set_card.locator("tbody tr")).to_have_count(len(flat))
                assert "セット合計" in set_card.inner_text()
                # quantities: ×N on page + chat card, total = Σ price × qty
                prices = page.evaluate("ids => fetch('/api/products?ids=' + ids.join(',')).then(r => r.json()).then(j => Object.fromEntries(j.products.map(p => [p.id, p.price])))", flat)
                qty_of = {s["product_ids"][0]: (s.get("quantities") or [1])[0] for s in sections}
                expected_total = sum(prices[i] * qty_of[i] for i in flat)
                total_txt = page.locator("#cr-set-total").inner_text()
                assert int(total_txt.replace("¥", "").replace(",", "")) == expected_total, (total_txt, expected_total)
                expect(page.locator("#cr-agent-view .cr-price__qty[data-qty='2']")).to_have_count(1)
                expect(page.locator("#cr-agent-view .cr-price__qty[data-qty='3']")).to_have_count(1)
                expect(set_card.locator("[data-qty='3']")).to_have_count(1)
                assert f"¥{expected_total:,}" in set_card.inner_text(), set_card.inner_text()
                page.wait_for_timeout(900)
                # line-clamped titles must show their first line (regression: chat auto-scroll scrolled them)
                assert set_card.locator(".crc-prod__t").evaluate_all("els => els.every(e => e.scrollTop === 0)")
                r.shot("dinner_set_page_and_chat")
                r.shot("dinner_set_full", full=True)
                if page.evaluate("window.CRChat.mock"):
                    page.evaluate("Cart.clear()")
                    page.locator("#cr-set-add").click()
                    lines = {l["product_id"]: l["qty"] for l in page.evaluate("Cart.toAgent()")["lines"]}
                    assert lines == qty_of, (lines, qty_of)
                    page.evaluate("Cart.clear()")
                # flat grid unchanged when sections are absent
                page.evaluate("a => window.CRClientTools.show_products_on_page(a)", {"message": "flat", "product_ids": flat[:3], "reasons": ["a", "b", "c"]})
                expect(page.locator("#cr-agent-grid .cr-card")).to_have_count(3)
                info = {"sections": [s["label"] for s in sections]}
                if page.evaluate("window.CRChat.mock"):
                    page.wait_for_timeout(4500)  # once() dedupe window
                    page.evaluate("window.CRMockChat.send('今夜の夕食のおすすめは？')")
                    expect(page.locator("#cr-agent-view[data-mode='set'] .cr-set-sec").first).to_be_visible(timeout=20000)
                    expect(page.locator(".crc-rich--set")).to_have_count(2, timeout=10000)
                    info["mock_set_sections"] = page.locator("#cr-agent-view .cr-set-sec").count()
                    page.wait_for_timeout(900)
                    r.shot("dinner_set_mock_reply")
                    page.locator(".crc-rich--set").last.locator("[data-crc-act='addset']").click()
                    expect(page.locator(".crc-rich--cart:not(.is-collapsed)")).to_have_count(1, timeout=5000)
                    page.wait_for_timeout(700)
                    r.shot("dinner_set_added_to_cart")
                    info["cart_count"] = page.locator("#cr-cart-count").inner_text()
                return info
            r.step("chat: dinner set (sections → grouped page + chat set card)", chat_dinner_set)

            def idle(timeout=live_wait):
                page.wait_for_function("() => !document.getElementById('cr-chat').classList.contains('is-busy')", timeout=timeout)

            def chat_panel_ui():
                """own slide-over panel: launcher, greeting + chips, IME-safe Enter, typing indicator, markdown, persistence"""
                page.goto(base + "/", wait_until="networkidle")
                page.evaluate("sessionStorage.removeItem('cr_chat_v3')")
                page.reload(wait_until="networkidle")
                expect(page.locator("#cr-chat")).to_be_hidden()
                page.locator("#cr-fab").click()
                expect(page.locator("#cr-chat")).to_be_visible()
                expect(page.locator("#cr-chat-log .cr-msg--bot").first).to_contain_text("AIコンシェルジュ")
                expect(page.locator("#cr-chat-log .cr-quick__chip").first).to_be_visible()
                ta = page.locator("#cr-chat-input")
                # Enter while the IME is composing must NOT send
                n_user = page.locator(".cr-msg--user").count()
                ta.fill("ふらいぱん")
                page.evaluate("""() => { const t = document.getElementById('cr-chat-input');
                    t.dispatchEvent(new CompositionEvent('compositionstart'));
                    t.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', keyCode: 229, isComposing: true, bubbles: true, cancelable: true}));
                    t.dispatchEvent(new CompositionEvent('compositionend', {data: 'フライパン'})); }""")
                page.wait_for_timeout(300)
                assert page.locator(".cr-msg--user").count() == n_user, "Enter during IME composition sent the message"
                ta.fill("フライパンを探して")
                page.wait_for_timeout(200)
                ta.press("Enter")
                expect(page.locator(".cr-msg--user").last).to_have_text("フライパンを探して")
                expect(page.locator("#cr-chat-typing")).to_be_visible(timeout=5000)
                r.shot("chat_typing")
                idle()
                if page.evaluate("window.CRChat.mock"):
                    expect(page.locator("#cr-agent-view .cr-card").first).to_be_visible(timeout=live_wait)
                expect(page.locator("#cr-chat-log .cr-msg--bot").last).not_to_be_empty()
                page.wait_for_timeout(600)
                r.shot("chat_panel_reply")
                sid = page.evaluate("JSON.parse(sessionStorage.getItem('cr_chat_v3')).session_id")
                n_msgs = page.locator("#cr-chat-log .cr-msg").count()
                page.reload(wait_until="networkidle")
                expect(page.locator("#cr-home")).to_be_visible()  # reload → home, chat history kept
                page.locator("#cr-fab").click()
                expect(page.locator("#cr-chat-log .cr-msg")).to_have_count(n_msgs)
                assert page.evaluate("JSON.parse(sessionStorage.getItem('cr_chat_v3')).session_id") == sid
                bold = page.locator("#cr-chat-log .cr-msg--bot strong").count()
                page.locator("#cr-chat-reset").click()
                expect(page.locator("#cr-chat-log .cr-msg")).to_have_count(1)
                assert page.evaluate("JSON.parse(sessionStorage.getItem('cr_chat_v3')).session_id") != sid
                page.locator("#cr-chat-close").click()
                expect(page.locator("#cr-chat")).to_be_hidden()
                return {"mock": page.evaluate("window.CRChat.mock"), "restored_msgs": n_msgs, "bold": bold}
            r.step("chat: panel UI (IME Enter, typing, persistence, reset)", chat_panel_ui)

            agent_turns: list[dict] = []  # live: every /api/agent/stream turn (message, events, done.timings)

            def _capture(resp):
                if "/api/agent/stream" not in resp.url or resp.request.method != "POST":
                    return
                try:
                    msg = json.loads(resp.request.post_data or "{}").get("message", "")
                    evs = [json.loads(l[6:]) for l in resp.text().split("\n") if l.startswith("data: ")]
                except Exception as e:  # noqa: BLE001
                    agent_turns.append({"message": "?", "error": str(e)[:120]})
                    return
                done = next((e for e in evs if e.get("type") == "done"), {})
                agent_turns.append({
                    "message": msg, "timings": done.get("timings"), "model": done.get("model"),
                    "actions": [{"name": e["name"], "args": e.get("args"), "result": e.get("result")} for e in evs if e.get("type") == "action"],
                    "status": [e["text"] for e in evs if e.get("type") == "status"],
                    "text": "".join(e.get("text", "") for e in evs if e.get("type") == "text"),
                    "chips": next((e["items"] for e in evs if e.get("type") == "chips"), []),
                    "errors": [e.get("message") for e in evs if e.get("type") == "error"]})
            page.on("response", _capture)

            def turn_for(msg):
                return next((t for t in reversed(agent_turns) if t.get("message") == msg), None)

            def live_agent_dinner_set():
                """REAL agent: typed request → set board + chat set card → セットをカートに入れて → cart card → checkout → 配達完了."""
                page.goto(base + "/", wait_until="networkidle")
                if page.evaluate("window.CRChat.mock"):
                    return {"skipped": "mock chat"}
                page.evaluate("Cart.clear(); sessionStorage.removeItem('cr_chat_v3')")
                page.reload(wait_until="networkidle")
                page.locator("#cr-fab").click()
                backend = page.evaluate("window.CR_CONFIG.agentBackend")
                sub = page.locator("#cr-chat-sub").inner_text()
                powered = page.locator("#cr-powered-agent").inner_text()
                if backend == "ces":
                    assert sub == "Gemini ・ GECX AI Studio" and powered == "GECX AI Studio", (sub, powered)
                ta = page.locator("#cr-chat-input")
                ta.click()
                ta.fill("今夜の夕食をお勧めしてね")
                ta.press("Enter")
                expect(page.locator("#cr-agent-view[data-mode='set'] .cr-set-sec").first).to_be_visible(timeout=live_wait)
                set_card = page.locator(".crc-rich--set").last
                expect(set_card).to_be_visible(timeout=10000)
                idle()
                page.wait_for_timeout(1500)
                info = {"backend": backend, "subtitle": sub, "footer": powered,
                        "sections": page.locator("#cr-agent-view .cr-set-sec").evaluate_all("els => els.map(e => e.dataset.role + ':' + e.querySelectorAll('.cr-card').length)"),
                        "set_rows": set_card.locator("tbody tr").count(), "set_total": page.locator("#cr-set-total").inner_text()}
                assert set_card.locator(".crc-prod__t").evaluate_all("els => els.every(e => e.scrollTop === 0)")
                dinner_text = page.locator("#cr-chat-log .cr-msg--bot").last.inner_text()
                info["dinner_text"] = dinner_text
                import re as _re
                for sent in _re.split(r"[。\n]", dinner_text):
                    if "アレルギー" in sent:
                        assert not any(w in sent for w in ("陽菜", "長女", "お子", "娘")), sent  # never say whose allergy
                info["allergy_sentence_exact"] = "以前お知らせいただいたアレルギー情報を反映し、えびを含む商品は除いています" in dinner_text
                show = next((x for t in agent_turns for x in t.get("actions", []) if x["name"] == "show_products_on_page"), None)
                set_qty = {}
                if show:
                    for sec in show["args"].get("sections") or []:
                        for pid, q in zip(sec.get("product_ids") or [], sec.get("quantities") or [1] * len(sec.get("product_ids") or [])):
                            set_qty[pid] = set_qty.get(pid, 0) + int(q or 1)
                r.shot("live_agent_dinner_set")
                ta.click()
                ta.fill("セットをカートに入れて")
                ta.press("Enter")
                cart = page.locator(".crc-rich--cart:not(.is-collapsed)")
                expect(cart).to_have_count(1, timeout=live_wait)
                idle()
                page.wait_for_timeout(1500)
                info["cart_rows"] = cart.locator("tbody tr").count()
                info["cart_count"] = page.locator("#cr-cart-count").inner_text()
                assert info["cart_rows"] >= 2, info
                lines = {l["product_id"]: l["qty"] for l in page.evaluate("Cart.toAgent()")["lines"]}
                info["set_quantities"], info["cart_quantities"] = set_qty, lines
                if set_qty:
                    assert lines == set_qty, (lines, set_qty)  # set → cart with the set's exact quantities
                r.shot("live_agent_set_to_cart")
                # checkout through the card buttons (each sends a natural-language message to the agent)
                cart.locator("[data-crc-act='checkout']").click()
                expect(page.locator(".crc-rich--slots").last).to_be_visible(timeout=live_wait)
                idle()
                r.shot("live_agent_slots")
                page.locator(".crc-rich--slots").last.locator("[data-slot-id='d1_pm']").click()
                expect(page.locator(".crc-rich--confirm").last).to_be_visible(timeout=live_wait)
                idle()
                r.shot("live_agent_confirm")
                page.locator(".crc-rich--confirm").last.locator("[data-crc-act='place']").click()
                order = page.locator(".crc-rich--order").last
                expect(order).to_be_visible(timeout=live_wait)
                idle()
                oid = order.locator("[data-crc-order]").get_attribute("data-crc-order")
                import re as _re2
                assert _re2.fullmatch(r"CR-\d{8}-\d{4}", oid or ""), oid
                info["order_id"] = oid
                r.shot("live_agent_order_placed")
                speed = float(page.evaluate("window.CR_CONFIG.deliverySpeedSec") or 8)
                page.wait_for_selector(".crc-rich--order [data-status='delivered']", timeout=(speed * 3 + 15) * 1000)
                expect(order).to_contain_text("配達完了")
                page.wait_for_timeout(800)
                r.shot("live_agent_delivered")
                info["user_msgs"] = page.locator("#cr-chat-log .cr-msg--user").all_inner_texts()
                info["agent_texts"] = page.locator("#cr-chat-log .cr-msg--bot").all_inner_texts()[-4:]
                po = turn_for("注文を確定してください")
                info["place_order_turn"] = po and [x["name"] for x in po["actions"]]
                assert po and "place_order" in info["place_order_turn"], po
                return info
            r.step("live agent: 今夜の夕食をお勧めしてね → set → セットをカートに入れて → checkout → 配達完了", live_agent_dinner_set)

            def live_agent_search_compare():
                """REAL agent: フライパンのおすすめ → product grid; 上位3つを比較して → comparison table."""
                if page.evaluate("window.CRChat.mock"):
                    return {"skipped": "mock chat"}
                if not page.locator("#cr-chat").is_visible():
                    page.locator("#cr-fab").click()
                ta = page.locator("#cr-chat-input")
                ta.click()
                ta.fill("フライパンのおすすめ")
                ta.press("Enter")
                expect(page.locator("#cr-agent-view .cr-card").first).to_be_visible(timeout=live_wait)
                idle()
                page.wait_for_timeout(1200)
                r.shot("live_agent_frypan")
                ta.click()
                ta.fill("上位3つを比較して")
                ta.press("Enter")
                expect(page.locator("#cr-compare-view")).to_be_visible(timeout=live_wait)
                idle()
                page.wait_for_timeout(1200)
                r.shot("live_agent_compare")
                return {"cards": page.locator("#cr-compare-view .cr-compare__prod").count(),
                        "agent_texts": page.locator("#cr-chat-log .cr-msg--bot").all_inner_texts()[-2:]}
            r.step("live agent: フライパンのおすすめ → 上位3つを比較して", live_agent_search_compare)

            def chat_panel():
                page.goto(base + "/", wait_until="networkidle")
                page.locator("#cr-fab").click()
                page.wait_for_timeout(2500)
                r.shot("concierge_open")
                mock = page.evaluate("window.CRChat.mock")
                info = {"mock": mock}
                # soft check: real agent round-trip (search → show_products_on_page client function)
                page.evaluate("window.CRChat.ask('フライパンを探しています。おすすめを画面に表示してください')")
                try:
                    page.wait_for_selector("#cr-agent-view .cr-card", timeout=90000)
                    info["agent_show_products"] = page.locator("#cr-agent-view .cr-card").count()
                except Exception as e:  # noqa: BLE001
                    info["agent_show_products"] = "not observed: " + str(e)[:80]
                page.wait_for_timeout(3000)
                r.shot("concierge_agent_reply")
                return info
            r.step("AIコンシェルジュ panel", chat_panel)
        except Exception:  # noqa: BLE001
            ok = False
        finally:
            browser.close()

    report = {"base_url": base, "ok": ok and all(s["ok"] for s in r.steps), "steps": r.steps,
              "console_errors": console_errors[:20], "screenshots": str(out)}
    (out / "e2e_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({"ok": report["ok"], "steps": len(r.steps), "console_errors": len(console_errors), "report": str(out / "e2e_report.json")}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
