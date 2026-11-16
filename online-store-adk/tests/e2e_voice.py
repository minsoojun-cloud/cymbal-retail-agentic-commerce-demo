#!/usr/bin/env python3
"""Voice E2E for the AIコンシェルジュ chat (CONTRACT v6) with Chromium fake media (real MediaRecorder → /api/voice/stt).

Modes
  ptt        tap the mic, say 「今夜の夕食をお勧めして」 (u1.wav), auto-stop on silence → transcript sent → dinner set
             board + chat set card + reply read aloud (/api/voice/tts 200, audio played).
  handsfree  「ハンズフリー」 on, handsfree.wav = u1 … u5 separated by silence: 夕食 → セットをカートに入れて → レジに進みます
             → 明日の午後でお願いします → 注文を確定して. Asserts set board, cart card, slot card, confirm card, order card
             (CR-YYYYMMDD-NNNN). Listening pauses while the agent answers / speaks and resumes automatically.
  denied     no fake-ui flag + no permission → tapping the mic shows the friendly 「マイクの使用が許可されていません」 message.
  gecx       (optional --gecx-url) voice UI must be absent and /api/voice/* 404 on cymbal-site.

WAVs: python tests/gen_voice_wavs.py <wav dir>   (Cloud TTS, voice ja-JP-Chirp3-HD-Charon)
usage: python tests/e2e_voice.py --base-url http://127.0.0.1:8096 --wav-dir DIR [--modes ptt,handsfree,denied]
       python tests/e2e_voice.py --base-url "$ONLINE_STORE_URL" --id-token ...
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
from urllib.parse import urlparse

import httpx
from playwright.sync_api import sync_playwright

OUT_DEFAULT = os.environ.get("E2E_OUT", "/tmp/cymbal_e2e/voice")
STEPS = [  # (expected transcript regex, page condition JS, label)
    (r"夕食", "() => !!document.querySelector('#cr-set-board .cr-card--h')", "dinner set board"),
    (r"セット.*カート", "() => window.Cart.lines().length >= 3", "set in cart"),
    (r"レジ", "() => ['delivery','payment','confirm'].includes(window.Checkout.state)", "checkout started (slot card)"),
    (r"明日.*午後", "() => window.Checkout.state === 'confirm' && window.Checkout.slot && window.Checkout.slot.slot_id === 'd1_pm'", "slot d1_pm → confirm"),
    (r"注文.*確定", "() => window.Orders.all().length > 0 && /^CR-\\d{8}-\\d{4}$/.test(window.Orders.all()[0].id)", "order placed"),
]


def launch(pw, wav: str | None, fake_ui: bool = True):
    args = ["--use-fake-device-for-media-stream", "--autoplay-policy=no-user-gesture-required"]
    if fake_ui:
        args.append("--use-fake-ui-for-media-stream")
    if wav:
        args.append("--use-file-for-fake-audio-capture=" + wav)
    try:
        return pw.chromium.launch(channel="chromium", args=args)
    except Exception:  # noqa: BLE001 (older playwright: headless shell)
        return pw.chromium.launch(args=args)


def new_page(br, base: str, token: str | None, out: Path, name: str, permissions=("microphone",)):
    ctx = br.new_context(viewport={"width": 1440, "height": 900}, permissions=list(permissions) if permissions else [])
    origin = "{0.scheme}://{0.netloc}".format(urlparse(base))
    if token:
        ctx.route(origin + "/**", lambda route: route.continue_(headers={**route.request.headers, "authorization": "Bearer " + token}))
    pg = ctx.new_page()
    logs: list[str] = []
    pg.on("console", lambda m: logs.append(m.text) if "[CR-" in m.text or m.type == "error" else None)
    tts: list[dict] = []
    pg.on("response", lambda r: tts.append({"url": r.url, "status": r.status, "cache": r.headers.get("x-tts-cache")}) if "/api/voice/" in r.url else None)
    pg.goto(base + "/", wait_until="networkidle")
    return ctx, pg, logs, tts


def user_msgs(pg) -> list[str]:
    return pg.eval_on_selector_all("#cr-chat-log .cr-msg--user", "els => els.map(e => e.textContent)")


def wait_until(pg, js: str, timeout_s: float) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            if pg.evaluate(js):
                return True
        except Exception:  # noqa: BLE001
            pass
        pg.wait_for_timeout(250)
    return False


def run_ptt(pw, a, token, out: Path) -> dict:
    br = launch(pw, str(Path(a.wav_dir) / "u1.wav"))
    ctx, pg, logs, voice = new_page(br, a.base_url, token, out, "ptt")
    res = {"mode": "ptt", "ok": False}
    try:
        assert pg.evaluate("() => !!(window.CR_CONFIG.voiceEnabled)"), "voiceEnabled missing in /config.js"
        pg.click("#cr-fab")
        pg.wait_for_selector("#cr-voice-mic")
        pg.screenshot(path=str(out / "ptt_0_idle.png"))
        t0 = time.time()
        pg.click("#cr-voice-mic")
        pg.wait_for_selector("#cr-voice-mic.is-recording", timeout=5000)
        pg.wait_for_timeout(1200)
        pg.screenshot(path=str(out / "ptt_1_recording.png"))
        ok = wait_until(pg, "() => document.querySelectorAll('#cr-chat-log .cr-msg--user').length > 0", 30)
        res["transcript"] = user_msgs(pg)
        res["t_transcript_s"] = round(time.time() - t0, 2)
        assert ok and re.search(STEPS[0][0], res["transcript"][-1]), f"transcript {res['transcript']}"
        assert wait_until(pg, STEPS[0][1], 90), "dinner set board not shown"
        res["t_board_s"] = round(time.time() - t0, 2)
        wait_until(pg, "() => !window.CRChat.isBusy()", 90)
        wait_until(pg, "() => window.CRVoice.timings().some(t => t.kind === 'turn_first_audio')", 20)
        pg.wait_for_timeout(1500)
        pg.screenshot(path=str(out / "ptt_2_reply.png"))
        res["timings"] = pg.evaluate("() => window.CRVoice.timings()")
        res["voice_http"] = voice
        assert any("/api/voice/stt" in v["url"] and v["status"] == 200 for v in voice) or any(t.get("engine") == "webspeech" for t in res["timings"] if t.get("kind") == "utterance"), "no STT call"
        assert any("/api/voice/tts" in v["url"] and v["status"] == 200 for v in voice), "no TTS 200"
        assert any(t["kind"] == "turn_first_audio" for t in res["timings"]), "reply was not played"
        assert pg.locator("#cr-chat-log .crc-rich").count() >= 1, "no chat set card"
        res["ok"] = True
    except AssertionError as e:
        res["error"] = str(e)
        pg.screenshot(path=str(out / "ptt_fail.png"))
    finally:
        res["console_tail"] = logs[-25:]
        ctx.close(); br.close()
    return res


def run_handsfree(pw, a, token, out: Path) -> dict:
    br = launch(pw, str(Path(a.wav_dir) / "handsfree.wav") + "%noloop")
    ctx, pg, logs, voice = new_page(br, a.base_url, token, out, "hf")
    res = {"mode": "handsfree", "ok": False, "steps": []}
    try:
        pg.click("#cr-fab")
        pg.wait_for_selector("#cr-voice-handsfree")
        t0 = time.time()
        pg.click("#cr-voice-handsfree")  # opens the mic → fake file starts playing
        assert pg.get_attribute("#cr-voice-handsfree", "aria-checked") == "true"
        for i, (pat, cond, label) in enumerate(STEPS):
            ts = time.time()
            ok_msg = wait_until(pg, f"() => document.querySelectorAll('#cr-chat-log .cr-msg--user').length > {i}", 75)
            msgs = user_msgs(pg)
            got = msgs[i] if len(msgs) > i else ""
            step = {"step": i + 1, "label": label, "transcript": got, "t_heard_s": round(time.time() - t0, 1)}
            ok_cond = ok_msg and bool(re.search(pat, got)) and wait_until(pg, cond, 90)
            step["ok"] = ok_cond
            step["t_done_s"] = round(time.time() - t0, 1)
            step["step_s"] = round(time.time() - ts, 1)
            res["steps"].append(step)
            print(json.dumps(step, ensure_ascii=False), flush=True)
            pg.wait_for_timeout(600)
            pg.screenshot(path=str(out / f"hf_{i + 1}.png"))
            if not ok_cond:
                raise AssertionError(f"step {i + 1} ({label}) failed: transcript={got!r}")
        wait_until(pg, "() => !window.CRChat.isBusy()", 60)
        res["order_id"] = pg.evaluate("() => window.Orders.all()[0].id")
        res["chat_cards"] = pg.locator("#cr-chat-log .crc-rich").count()
        res["timings"] = pg.evaluate("() => window.CRVoice.timings()")
        res["voice_state"] = pg.evaluate("() => window.CRVoice.state()")
        wait_until(pg, "() => window.CRVoice.timings().filter(t => t.kind === 'turn_first_audio').length >= 5", 20)
        res["timings"] = pg.evaluate("() => window.CRVoice.timings()")
        n_audio = sum(1 for t in res["timings"] if t["kind"] == "turn_first_audio")
        assert n_audio >= 5, f"only {n_audio}/5 replies were read aloud"
        res["ok"] = True
    except AssertionError as e:
        res["error"] = str(e)
        pg.screenshot(path=str(out / "hf_fail.png"))
        try:
            res["timings"] = pg.evaluate("() => window.CRVoice.timings()")
        except Exception:  # noqa: BLE001
            pass
    finally:
        res["voice_http"] = [v for v in voice if "/stt" in v["url"]][-6:]
        res["console_tail"] = logs[-40:]
        ctx.close(); br.close()
    return res


def run_denied(pw, a, token, out: Path) -> dict:
    br = launch(pw, None, fake_ui=False)
    ctx, pg, logs, _ = new_page(br, a.base_url, token, out, "denied", permissions=None)
    res = {"mode": "denied", "ok": False}
    try:
        pg.click("#cr-fab")
        pg.click("#cr-voice-mic")
        ok = wait_until(pg, "() => /許可されていません|開始できません|見つかりません/.test(document.getElementById('cr-voice-hint').textContent)", 10)
        res["hint"] = pg.text_content("#cr-voice-hint")
        res["state"] = pg.evaluate("() => window.CRVoice.state()")
        pg.screenshot(path=str(out / "denied.png"))
        assert ok, "no friendly message"
        assert res["state"]["phase"] == "idle"
        # typing still works
        assert pg.is_enabled("#cr-chat-input")
        res["ok"] = True
    except AssertionError as e:
        res["error"] = str(e)
    finally:
        ctx.close(); br.close()
    return res


def run_gecx(pw, a, out: Path) -> dict:
    res = {"mode": "gecx", "ok": False}
    with httpx.Client(timeout=30) as h:
        cfg = h.get(a.gecx_url + "/config.js").text
        stt = h.post(a.gecx_url + "/api/voice/stt", content=b"x").status_code
        tts = h.post(a.gecx_url + "/api/voice/tts", json={"text": "テスト"}).status_code
    res.update({"voiceEnabled_in_config": "voiceEnabled" in cfg, "stt_status": stt, "tts_status": tts})
    br = launch(pw, None)
    ctx, pg, _, _ = new_page(br, a.gecx_url, None, out, "gecx")
    pg.click("#cr-fab")
    pg.wait_for_timeout(500)
    res["mic_present"] = pg.locator("#cr-voice-mic").count() > 0
    ctx.close(); br.close()
    res["ok"] = not res["voiceEnabled_in_config"] and stt in (404, 405) and tts in (404, 405) and not res["mic_present"]  # 405 = pre-v6 build
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=os.environ.get("ONLINE_STORE_URL", "http://127.0.0.1:8096"))
    ap.add_argument("--wav-dir", default=OUT_DEFAULT.replace("/voice", "/wav"))
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--modes", default="ptt,handsfree,denied")
    ap.add_argument("--id-token", action="store_true")
    ap.add_argument("--gecx-url", default="")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    token = None
    if a.id_token:
        token = subprocess.run(["gcloud", "auth", "print-identity-token"], capture_output=True, text=True, check=True).stdout.strip()
    results = []
    with sync_playwright() as pw:
        for m in a.modes.split(","):
            r = {"ptt": run_ptt, "handsfree": run_handsfree, "denied": run_denied}[m](pw, a, token, out)
            print(json.dumps({k: v for k, v in r.items() if k != "console_tail"}, ensure_ascii=False), flush=True)
            results.append(r)
        if a.gecx_url:
            r = run_gecx(pw, a, out)
            print(json.dumps(r, ensure_ascii=False))
            results.append(r)
    (out / "voice_results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))
    ok = all(r["ok"] for r in results)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
