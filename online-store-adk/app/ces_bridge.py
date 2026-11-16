"""CES bridge (CONTRACT v4): POST /api/agent/stream → GECX AI Studio (CES) runtime, same SSE contract as v3.

Browser → cymbal-site `POST /api/agent/stream` → this module → `ces.googleapis.com/v1/{CES_APP_NAME}/sessions/{id}:
streamRunSession?alt=sse` (fallback `:runSession`) as the site service account (roles/ces.client).

One chat turn:
  1. emit `status`「考えています…」; seed the per-session ShopState (shop.py, same logic as the ADK agent) from
     `page_state`; send session variables (customer_id, customer_name, visitor_id, persona_summary, page_context,
     cart_summary) + the user text to CES (session id = stable hash of the browser session_id, deployment pinned).
  2. CES runs the agent; MCP tools (search / dinner set / compare …) execute inside CES (toolset cymbal-commerce-mcp).
     When the output contains client-function tool calls, the bridge resolves the tool name (displayName / resource id
     via CES_TOOL_ID_MAP), computes the result server-side (catalog prices + page_state), emits `status` + `action`
     events in order (`suggest_replies` → `chips`), and sends the tool responses back to CES. Repeat until CES returns
     no further client tool calls (max CES_MAX_ROUNDS).
  3. emit `text` (streamed deltas when CES text streaming is on), `chips`, `done` {session_id, model, timings}.
  HTTP 429 (per-minute LLM token quota) → backoff + retry (status 「混み合っています…」), then a friendly `error`.

Env: CES_APP_NAME, CES_DEPLOYMENT_NAME, CES_TOOL_ID_MAP (JSON), CES_MODEL (label), CES_ENDPOINT
(default https://ces.googleapis.com), CES_STREAM (1|0, default 1), CES_TEXT_STREAMING (1|0, default 1),
CES_MAX_ROUNDS (8), CES_RETRY_DELAYS (429 backoff seconds, default "3,6,12,20" ≈ one quota minute),
CES_TIMEOUT_SEC (120).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Optional

import httpx

from .shop import Catalog, ShopState

log = logging.getLogger("cymbal-site.ces")

AUTHOR = "cymbal_concierge"
THINKING = "考えています…"
BUSY_STATUS = "ただいま混み合っています。少々お待ちください…"
BUSY_ERROR = "ただいまAIコンシェルジュが混み合っています。少し時間をおいてから、もう一度お試しください。"
GENERIC_ERROR = "申し訳ございません、AIコンシェルジュでエラーが発生しました。もう一度お試しください。"
CLIENT_FUNCTIONS = ("show_products_on_page", "show_comparison", "add_to_cart", "get_cart", "start_checkout",
                    "select_delivery_slot", "place_order", "get_order_status", "suggest_replies")
STATUS_LABELS = {  # same texts as shared/adk_agent/cymbal_agent/tools.py
    "search_products": "商品を検索しています…",
    "get_product_details": "商品の詳細を確認しています…",
    "get_purchase_history": "いつものお買い物を確認しています…",
    "compare_products": "比較表を作成しています…",
    "recommend_dinner_set": "ご家族に合う夕食セットを考えています…",
    "show_products_on_page": "おすすめ商品を表示しています…",
    "show_comparison": "比較表を表示しています…",
    "add_to_cart": "カートに追加しています…",
    "get_cart": "カートを確認しています…",
    "start_checkout": "ご注文手続きを準備しています…",
    "select_delivery_slot": "お届け日時を設定しています…",
    "place_order": "ご注文を確定しています…",
    "get_order_status": "配送状況を確認しています…",
}
FALLBACK_TEXT = {
    "show_products_on_page": "おすすめの商品を画面に表示しました。",
    "show_comparison": "比較表を画面に表示しました。",
    "add_to_cart": "カートに追加しました。このままレジに進むこともできます。",
    "get_cart": "カートの内容を表示しました。",
    "start_checkout": "ご注文手続きを始めます。チャットのボタンからお届け日時をお選びください。",
    "select_delivery_slot": "この内容でご注文を確定してよろしいですか？",
    "place_order": "ご注文ありがとうございます。",
    "get_order_status": "配送状況を表示しました。",
}
# While CES works on the first request we only learn about server-side MCP tools afterwards, so a keyword
# heuristic picks the typing-indicator label shown after ~1 s (purely cosmetic).
_HINTS = (
    (re.compile(r"夕食|晩ご飯|晩御飯|夕飯|献立|今日のご飯|おかず|何を作ろ|鍋にしたい|別の案|ほかのセット|予算"), "recommend_dinner_set"),
    (re.compile(r"比較|比べ|違い"), "compare_products"),
    (re.compile(r"おすすめ|オススメ|探し|ほしい|欲しい|セール|お買い得|ありますか"), "search_products"),
)


# ── config ───────────────────────────────────────────────────────────────────────────────────
def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def app_name() -> str:
    return _env("CES_APP_NAME").rstrip("/")


def configured() -> bool:
    return bool(app_name())


def model_label() -> str:
    return _env("CES_MODEL", "gecx")


def endpoint() -> str:
    return _env("CES_ENDPOINT", "https://ces.googleapis.com").rstrip("/")


def deployment() -> str:
    """CES_DEPLOYMENT_NAME normalised to the app's project form (projects/<id>/…/deployments/<dep>)."""
    dep = _env("CES_DEPLOYMENT_NAME")
    if not dep or not app_name():
        return ""
    return f"{app_name()}/deployments/{dep.rsplit('/', 1)[-1]}"


_tool_map_cache: tuple[str, dict[str, str]] = ("", {})


def tool_id_map() -> dict[str, str]:
    global _tool_map_cache
    raw = _env("CES_TOOL_ID_MAP")
    if raw != _tool_map_cache[0]:
        try:
            m = json.loads(raw) if raw else {}
            m = {str(k): str(v) for k, v in m.items()} if isinstance(m, dict) else {}
        except ValueError:
            log.warning("CES_TOOL_ID_MAP is not valid JSON; ignored")
            m = {}
        _tool_map_cache = (raw, m)
    return _tool_map_cache[1]


def resolve_tool_name(tc: dict[str, Any]) -> str:
    """Contract function name for a CES tool call (displayName / resource name / uuid / prefixed MCP name)."""
    tmap = tool_id_map()
    cands = [str(tc.get(k) or "") for k in ("displayName", "tool", "name")]
    tst = tc.get("toolsetTool") or {}
    if isinstance(tst, dict) and tst.get("toolId"):
        cands.append(str(tst["toolId"]))
    for c in cands:
        if not c:
            continue
        for key in (c, c.rsplit("/", 1)[-1], re.sub(r"^projects/\d+/", "projects/", c)):
            if key in tmap:
                return tmap[key]
        last = c.rsplit("/", 1)[-1]
        for fn in CLIENT_FUNCTIONS:
            if last == fn or last.endswith("_" + fn):
                return fn
        for mcp in STATUS_LABELS:
            if last.endswith(mcp):
                return mcp
    return next((c.rsplit("/", 1)[-1] for c in cands if c), "")


def ces_session_name(browser_session_id: str) -> str:
    sid = (browser_session_id or "").strip() or "anonymous"
    return f"{app_name()}/sessions/web-{hashlib.sha256(sid.encode('utf-8')).hexdigest()[:32]}"


# ── persona (local seed/personas copy staged by deploy.sh; ids never leave the server) ────────────
_SITE_DIR = Path(__file__).resolve().parent.parent
_personas: Optional[dict[str, dict]] = None


def _load_personas() -> dict[str, dict]:
    global _personas
    if _personas is None:
        _personas = {}
        env = os.environ.get("PERSONA_DIR") or os.environ.get("PERSONAS_DIR")
        for cand in ([Path(env)] if env else []) + [
            _SITE_DIR / "data" / "personas",
            _SITE_DIR.parent / "seed" / "personas",
            _SITE_DIR.parent / "shared" / "mcp_server" / "data",
        ]:
            f = cand / "personas.json"
            if f.exists():
                try:
                    for p in json.loads(f.read_text(encoding="utf-8")):
                        _personas[str(p.get("customer_id"))] = p
                except (ValueError, OSError) as e:
                    log.warning("personas.json unreadable: %s", e)
                break
    return _personas


def persona_summary(customer_id: str) -> str:
    """Compact profile text for the agent (same fields as the ADK server's persona summary). Allergies are listed
    without the family member so that the agent cannot attribute them (CONTRACT: never say whose allergy)."""
    p = _load_personas().get(customer_id or "")
    if not p:
        return "（なし）"
    fam = []
    for m in p.get("family_preferences") or []:
        s = f"{m.get('call_name') or m.get('name')}（{m.get('relation')}・{m.get('age')}歳）好き: {'・'.join(m.get('likes') or [])}"
        ng = [x for x in (m.get("ng") or []) if "アレルギー" not in str(x)]
        if ng:
            s += f" / 苦手: {'・'.join(ng)}"
        fam.append(s)
    allergies = sorted({f"{a.get('allergen')}（{a.get('severity')}）" for a in p.get("allergies") or [] if isinstance(a, dict)})
    parts = {
        "名前": p.get("name"),
        "家族": " / ".join(fam) or str(p.get("household_size") or ""),
        "アレルギー（ご家族の登録情報。誰のアレルギーかは言わない）": "・".join(allergies),
        "除外キーワード": "・".join(p.get("exclude_keywords") or []),
        "味の好み": json.dumps(p.get("taste_preferences") or {}, ensure_ascii=False),
        "料理スタイル": p.get("cooking_style"),
        "買い物スタイル": p.get("shopping_style"),
        "品質の好み": p.get("quality_preference"),
        "苦手": "・".join(p.get("dislikes") or []),
        "季節の関心": p.get("seasonal_interest"),
        "会員": (p.get("loyalty") or {}).get("tier"),
    }
    return " | ".join(f"{k}: {v}" for k, v in parts.items() if v)


# ── shop state per browser session (re-seeded from page_state every turn) ───────────────────────
CATALOG = Catalog.load()
STATES: dict[str, ShopState] = {}
_LOCKS: dict[str, asyncio.Lock] = {}
MAX_STATES = 2000


def shop_state(session_id: str) -> ShopState:
    st = STATES.get(session_id)
    if st is None:
        if len(STATES) >= MAX_STATES:
            for k in list(STATES)[: MAX_STATES // 4]:
                STATES.pop(k, None)
                _LOCKS.pop(k, None)
        st = STATES[session_id] = ShopState()
    return st


def _norm_show_args(args: dict[str, Any]) -> dict[str, Any]:
    ids = [str(x) for x in (args.get("product_ids") or []) if x][:24]
    sections = args.get("sections") if isinstance(args.get("sections"), list) else None
    if not ids and sections:
        ids = [str(i) for s in sections if isinstance(s, dict) for i in (s.get("product_ids") or []) if i][:24]
    rs = [str(r) for r in (args.get("reasons") or [])][: len(ids)]
    rs += [""] * (len(ids) - len(rs))
    out: dict[str, Any] = {"message": str(args.get("message") or ""), "product_ids": ids, "reasons": rs}
    for k in ("theme", "quantities"):
        if args.get(k):
            out[k] = args[k]
    if sections:
        out["sections"] = sections
    return out


def execute_client_function(st: ShopState, name: str, args: dict[str, Any], turn: dict[str, Any]) -> dict[str, Any]:
    """Compute the client-function result server-side (records the page action on `st`)."""
    args = args if isinstance(args, dict) else {}
    if name == "show_products_on_page":
        a = _norm_show_args(args)
        if a["product_ids"] and a["product_ids"] == st.last_shown_ids and turn.get("shown_this_turn"):
            return {"shown": len(a["product_ids"])}
        turn["shown_this_turn"] = True
        return st.show_products(a)
    if name == "show_comparison":
        return st.show_comparison({"title": str(args.get("title") or "商品の比較"),
                                   "product_ids": [str(x) for x in (args.get("product_ids") or [])][:4],
                                   "rows": args.get("rows") or []})
    if name == "add_to_cart":
        return st.add_to_cart(CATALOG, str(args.get("product_id") or ""), args.get("quantity") or 1)
    if name == "get_cart":
        return st.get_cart()
    if name == "start_checkout":
        return st.start_checkout()
    if name == "select_delivery_slot":
        return st.select_delivery_slot(str(args.get("slot_id") or ""))
    if name == "place_order":
        return st.place_order()
    if name == "get_order_status":
        return st.get_order_status(str(args.get("order_id") or ""))
    if name == "suggest_replies":
        items = [str(x).strip() for x in (args.get("items") or []) if str(x).strip()][:4]
        turn["chips"] = items
        return {"shown": len(items)}
    return {"ok": False, "error": "UNKNOWN_CLIENT_FUNCTION", "name": name}


def fallback_chips(actions: list[dict[str, Any]], st: ShopState) -> list[str]:
    """Deterministic chips (same rules as the ADK server) when the agent did not call suggest_replies."""
    last = actions[-1] if actions else None
    if not last:
        return ["今夜の夕食をお勧めしてね", "フライパンのおすすめ", "お買い得商品を見せて"]
    r, n = last.get("result") or {}, last["name"]
    if n == "place_order" and r.get("ok"):
        return ["配送状況は？", "今夜の夕食をお勧めしてね"]
    if n == "select_delivery_slot" and r.get("ok"):
        return ["注文を確定してください", "配送日時を変更したい"]
    if n == "start_checkout":
        if r.get("ok"):
            return ["明日 14:00-17:00 でお願いします", "明日 18:00-21:00 でお願いします", "明後日 9:00-12:00 でお願いします"]
        return ["今夜の夕食をお勧めしてね", "お買い得商品を見せて"]
    if n == "add_to_cart":
        return ["レジに進みます", "カートの中身は？"]
    if n == "get_cart":
        return ["レジに進みます"] if r.get("cart_count") else ["今夜の夕食をお勧めしてね", "お買い得商品を見せて"]
    if n == "show_comparison":
        return ["1番目をカートに入れて", "2番目をカートに入れて", "3番目をカートに入れて"][: max(2, len(last["args"].get("product_ids") or []))]
    if n == "show_products_on_page":
        if last["args"].get("sections"):
            return ["セットをカートに入れる", "別の案", "予算1,500円で"]
        return ["上位3つを比較して", "1番目をカートに入れて"]
    if n == "get_order_status":
        return ["今夜の夕食をお勧めしてね"]
    return []


# ── CES REST client ─────────────────────────────────────────────────────────────────────────
class CesHTTPError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"CES HTTP {status}: {body[:300]}")
        self.status = status
        self.body = body


class TokenSource:
    """Access token for CES: ADC (metadata server on Cloud Run = site SA; locally the gcloud user ADC)."""

    def __init__(self) -> None:
        self._creds = None
        self._user_project = ""
        self._lock = asyncio.Lock()

    def _refresh_sync(self) -> None:
        import google.auth
        import google.auth.transport.requests

        if self._creds is None:
            self._creds, project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            # user ADC needs a quota project header; service accounts bill to their own project
            if not getattr(self._creds, "service_account_email", None):
                self._user_project = _env("PROJECT_ID") or project or ""
        self._creds.refresh(google.auth.transport.requests.Request())

    async def headers(self) -> dict[str, str]:
        async with self._lock:
            c = self._creds
            if c is None or not c.valid or (getattr(c, "expiry", None) and c.expiry.timestamp() - time.time() < 300):
                await asyncio.to_thread(self._refresh_sync)
        h = {"Authorization": f"Bearer {self._creds.token}", "Content-Type": "application/json"}
        if self._user_project:
            h["X-Goog-User-Project"] = self._user_project
        return h

    def clear(self) -> None:
        self._creds = None


class CesClient:
    def __init__(self, http: Optional[httpx.AsyncClient] = None, tokens: Optional[TokenSource] = None,
                 stream: Optional[bool] = None):
        self.http = http
        self.tokens = tokens or TokenSource()
        self.stream = (_env("CES_STREAM", "1") != "0") if stream is None else stream

    async def _headers(self) -> dict[str, str]:
        return await self.tokens.headers()

    async def run(self, session: str, body: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        """Yield SessionOutput dicts for one runSession request (streamed when possible)."""
        http = self.http
        assert http is not None
        headers = await self._headers()
        if self.stream:
            url = f"{endpoint()}/v1/{session}:streamRunSession?alt=sse"
            async with http.stream("POST", url, json=body, headers={**headers, "Accept": "text/event-stream"}) as r:
                if r.status_code != 200:
                    detail = (await r.aread()).decode("utf-8", "replace")
                    if r.status_code in (404, 501) and "streamRunSession" in url:
                        log.warning("streamRunSession unavailable (%s) → runSession", r.status_code)
                        self.stream = False
                    else:
                        raise CesHTTPError(r.status_code, detail)
                else:
                    buf = ""
                    async for line in r.aiter_lines():
                        line = line.rstrip("\r")
                        if line.startswith("data:"):
                            buf += line[5:].strip()
                            continue
                        if line.strip() == "" and buf:
                            for o in _outputs(buf):
                                yield o
                            buf = ""
                    if buf:
                        for o in _outputs(buf):
                            yield o
                    return
        url = f"{endpoint()}/v1/{session}:runSession"
        r = await http.post(url, json=body, headers=headers)
        if r.status_code != 200:
            raise CesHTTPError(r.status_code, r.text)
        for o in (r.json() or {}).get("outputs") or []:
            yield o


def _outputs(raw: str) -> list[dict[str, Any]]:
    try:
        d = json.loads(raw)
    except ValueError:
        log.warning("unparseable CES event: %s", raw[:200])
        return []
    if isinstance(d, list):  # JSON-array streaming form
        return [o for x in d if isinstance(x, dict) for o in (x.get("outputs") or [])]
    return list(d.get("outputs") or []) if isinstance(d, dict) else []


# ── turn ─────────────────────────────────────────────────────────────────────────────────────
def sse(obj: dict) -> bytes:
    return ("data: " + json.dumps(obj, ensure_ascii=False, default=str) + "\n\n").encode("utf-8")


class _Turn:
    def __init__(self, t0: float):
        self.t0 = t0
        self.segments: list[str] = []
        self.seg = ""
        self.actions: list[dict[str, Any]] = []
        self.tool_calls: list[str] = []
        self.mcp_calls: list[str] = []
        self.ctx: dict[str, Any] = {}
        self.last_status = ""
        self.ces_calls = 0
        self.ces_ms: list[int] = []
        self.usage = {"llm_calls": 0, "input_tokens": 0, "output_tokens": 0}
        self.timings: dict[str, Optional[int]] = {"first_status_ms": None, "first_action_ms": None,
                                                  "first_text_ms": None, "total_ms": None}

    def ms(self) -> int:
        return int((time.perf_counter() - self.t0) * 1000)

    def status(self, text: str) -> dict[str, Any]:
        self.last_status = text
        if self.timings["first_status_ms"] is None:
            self.timings["first_status_ms"] = self.ms()
        return {"type": "status", "text": text}

    @property
    def reply(self) -> str:
        parts = [s.strip() for s in self.segments if s.strip()]
        if self.seg.strip():
            parts.append(self.seg.strip())
        return "\n\n".join(parts)

    def end_segment(self) -> None:
        if self.seg.strip():
            self.segments.append(self.seg)
        self.seg = ""

    def text(self, t: str) -> Optional[dict[str, Any]]:
        """Accept a CES text output (either an incremental chunk or the full text of the current segment)."""
        if not t:
            return None
        if self.seg and t.startswith(self.seg):  # cumulative / repeated full text
            delta = t[len(self.seg):]
        else:
            delta = t
        if not delta:
            return None
        out = delta
        if not self.seg:
            out = delta.lstrip()
            if not out:
                return None
            if any(s.strip() for s in self.segments):
                out = "\n\n" + out
        self.seg += delta if self.seg else delta.lstrip()
        if self.timings["first_text_ms"] is None:
            self.timings["first_text_ms"] = self.ms()
        return {"type": "text", "text": out, "author": AUTHOR}


def _hint_status(message: str) -> Optional[str]:
    for rx, tool in _HINTS:
        if rx.search(message):
            return STATUS_LABELS[tool]
    return None


def _harvest_diag(diag: Any, turn: _Turn) -> None:
    """Server-side MCP tool names + LLM token usage (rootSpan) of one CES request, for logs / done.usage."""
    if not isinstance(diag, dict):
        return
    stack = [diag.get("rootSpan") or {}]
    while stack:
        sp = stack.pop()
        if not isinstance(sp, dict):
            continue
        if sp.get("name") == "LLM":
            at = sp.get("attributes") or {}
            turn.usage["llm_calls"] += 1
            turn.usage["input_tokens"] += int(at.get("input token count") or 0)
            turn.usage["output_tokens"] += int(at.get("output token count") or 0)
        stack.extend(sp.get("childSpans") or [])
    for m in diag.get("messages") or []:
        for ch in m.get("chunks") or []:
            tc = ch.get("toolCall") or {}
            if tc and not tc.get("tool"):  # server-side (toolset) call
                n = str(tc.get("displayName") or "").replace("cymbal_commerce_mcp_", "")
                if n:
                    turn.mcp_calls.append(n)


async def _with_hint(agen: AsyncIterator[dict[str, Any]], hint: Optional[str], after: float
                     ) -> AsyncIterator[tuple[str, Any]]:
    """Iterate CES outputs; yield ('hint', text) once if nothing arrived within `after` seconds."""
    q: asyncio.Queue = asyncio.Queue()
    done = object()

    async def pump() -> None:
        try:
            async for o in agen:
                await q.put(("out", o))
        except BaseException as e:  # noqa: BLE001 (re-raised in the consumer)
            await q.put(("exc", e))
        finally:
            await q.put(("end", done))

    task = asyncio.create_task(pump())
    try:
        hinted = hint is None
        while True:
            try:
                kind, val = await (asyncio.wait_for(q.get(), timeout=after) if not hinted else q.get())
            except asyncio.TimeoutError:
                hinted = True
                yield ("hint", hint)
                continue
            if kind == "end":
                return
            if kind == "exc":
                raise val
            hinted = True
            yield (kind, val)
    finally:
        if not task.done():
            task.cancel()


async def run_turn(body: dict[str, Any], ces: CesClient, sleep: Callable[[float], Any] = asyncio.sleep
                   ) -> AsyncIterator[dict[str, Any]]:
    """Async generator of v3 SSE payload dicts for one chat turn."""
    t0 = time.perf_counter()
    turn = _Turn(t0)
    browser_sid = str(body.get("session_id") or "")
    message = str(body.get("message") or "")
    yield turn.status(THINKING)
    session = ces_session_name(browser_sid)
    lock = _LOCKS.setdefault(browser_sid, asyncio.Lock())
    async with lock:
        st = shop_state(browser_sid)
        st.seed(body.get("page_state") if isinstance(body.get("page_state"), dict) else None)
        st.drain_actions()
        variables = {
            "customer_id": str(body.get("customer_id") or ""),
            "customer_name": str(body.get("customer_name") or ""),
            "visitor_id": str(body.get("visitor_id") or ""),
            "persona_summary": persona_summary(str(body.get("customer_id") or "")),
            "page_context": json.dumps(st.page_context or {}, ensure_ascii=False)[:1000],
            "cart_summary": st.summary_text(),
        }
        cfg: dict[str, Any] = {"session": session, "timeZone": "Asia/Tokyo"}
        if deployment():
            cfg["deployment"] = deployment()
        if ces.stream and _env("CES_TEXT_STREAMING", "1") != "0":
            cfg["enableTextStreaming"] = True
        inputs: list[dict[str, Any]] = [{"variables": variables}, {"text": message}]
        hint = _hint_status(message)
        max_rounds = int(_env("CES_MAX_ROUNDS", "8") or 8)
        delays = [float(x) for x in _env("CES_RETRY_DELAYS", "3,6,12,20").split(",") if x.strip()]
        for rnd in range(max_rounds):
            responses: list[dict[str, Any]] = []
            attempt = 0
            while True:
                got_output = False
                t_call = time.perf_counter()
                turn.ces_calls += 1
                try:
                    async for kind, o in _with_hint(ces.run(session, {"config": cfg, "inputs": inputs}),
                                                    hint if rnd == 0 and attempt == 0 else None, 1.0):
                        if kind == "hint":
                            yield turn.status(o)
                            continue
                        got_output = True
                        for payload in _handle_output(o, st, turn, responses):
                            yield payload
                    break
                except CesHTTPError as e:
                    if e.status == 429 and not got_output and attempt < len(delays):
                        wait = delays[attempt]
                        attempt += 1
                        log.warning("CES 429 (attempt %d) → retry in %.0fs", attempt, wait)
                        yield turn.status(BUSY_STATUS)
                        await sleep(wait)
                        continue
                    if e.status in (401, 403):
                        ces.tokens.clear()
                    log.error("CES error %s: %s", e.status, e.body[:500])
                    turn.timings["total_ms"] = turn.ms()
                    yield {"type": "error", "message": BUSY_ERROR if e.status == 429 else GENERIC_ERROR,
                           "status": e.status}
                    yield {"type": "done", "session_id": browser_sid, "model": model_label(),
                           "timings": dict(turn.timings, ces_calls=turn.ces_calls)}
                    return
                finally:
                    turn.ces_ms.append(int((time.perf_counter() - t_call) * 1000))
            turn.end_segment()
            if not responses:
                break
            inputs = [{"toolResponses": {"toolResponses": responses}}]
        else:
            log.warning("CES turn hit CES_MAX_ROUNDS=%d (session %s)", max_rounds, browser_sid[:12])

        if not turn.reply:
            last = turn.actions[-1]["name"] if turn.actions else ""
            d = turn.text(FALLBACK_TEXT.get(last, "申し訳ございません、うまくお答えできませんでした。もう一度お試しください。"))
            if d:
                yield d
            turn.end_segment()
        chips = turn.ctx.get("chips") or fallback_chips(turn.actions, st)
        if chips:
            yield {"type": "chips", "items": chips[:4]}
        turn.timings["total_ms"] = turn.ms()
        log.info("ces turn session=%s timings=%s ces_ms=%s usage=%s client=%s mcp=%s", browser_sid[:12], turn.timings,
                 turn.ces_ms, turn.usage, turn.tool_calls, turn.mcp_calls)
        yield {"type": "done", "session_id": browser_sid, "model": model_label(),
               "timings": dict(turn.timings, ces_calls=turn.ces_calls, ces_ms=turn.ces_ms), "usage": turn.usage,
               "_internal": {"reply": turn.reply, "tool_calls": turn.tool_calls, "mcp_calls": turn.mcp_calls}}


def _handle_output(o: dict[str, Any], st: ShopState, turn: _Turn, responses: list[dict[str, Any]]
                   ) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if o.get("text"):
        d = turn.text(str(o["text"]))
        if d:
            out.append(d)
    if o.get("progress"):
        log.debug("CES progress: %s", str(o["progress"])[:200])
    calls = (o.get("toolCalls") or {}).get("toolCalls") or []
    if calls:
        turn.end_segment()
    for tc in calls:
        name = resolve_tool_name(tc)
        args = tc.get("args") if isinstance(tc.get("args"), dict) else {}
        turn.tool_calls.append(name)
        if name in STATUS_LABELS and STATUS_LABELS[name] != turn.last_status:
            out.append(turn.status(STATUS_LABELS[name]))
        result = execute_client_function(st, name, args, turn.ctx)
        for a in st.drain_actions():
            if turn.timings["first_action_ms"] is None:
                turn.timings["first_action_ms"] = turn.ms()
            turn.actions.append(a)
            out.append(a)
        resp: dict[str, Any] = {"response": result}
        for k in ("id", "tool", "toolsetTool"):
            if tc.get(k):
                resp[k] = tc[k]
        responses.append(resp)
    if o.get("diagnosticInfo"):
        _harvest_diag(o["diagnosticInfo"], turn)
    return out


# ── HTTP entry point (used by main.py) ──────────────────────────────────────────────────────
_client: Optional[CesClient] = None


def get_client() -> CesClient:
    global _client
    if _client is None:
        timeout = float(_env("CES_TIMEOUT_SEC", "120") or 120)
        _client = CesClient(http=httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=timeout, write=30, pool=10)))
    return _client


async def stream(body: dict[str, Any], ces: Optional[CesClient] = None) -> AsyncIterator[bytes]:
    ces = ces or get_client()
    try:
        async for payload in run_turn(body, ces):
            payload.pop("_internal", None)
            yield sse(payload)
    except (httpx.HTTPError, OSError) as e:
        log.error("CES stream failed: %r", e)
        yield sse({"type": "error", "message": "AIコンシェルジュとの通信が途切れました。もう一度お試しください。"})
        yield sse({"type": "done", "session_id": body.get("session_id", "")})
    except Exception as e:  # noqa: BLE001
        log.exception("CES turn failed")
        yield sse({"type": "error", "message": GENERIC_ERROR, "detail": str(e)[:200]})
        yield sse({"type": "done", "session_id": body.get("session_id", "")})
