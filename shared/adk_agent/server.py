"""FastAPI + ADK Runner server for the Cymbal Retail AIコンシェルジュ.

Endpoints
  POST /api/chat/stream  SSE: status / text / action / chips / done / error  (one JSON per `data:` line)
  POST /api/chat         same turn, non-streaming JSON (tests / debugging)
  GET  /api/health

Sessions live in an InMemorySessionService keyed by session_id, so the service is deployed with
--min-instances=1 --max-instances=1. Cart / checkout / orders are re-seeded from `page_state` every turn.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import time
import uuid
from typing import Any, Optional

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, Field

from cymbal_agent import mcp_client
from cymbal_agent.agent import AGENT_MODEL, build_agent, root_agent
from cymbal_agent.tools import CATALOG, STATES, STATUS_LABELS, shop_state

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("cymbal_adk_server")

APP_NAME = "cymbal_concierge"
AUTHOR = "cymbal_concierge"
_session_service = InMemorySessionService()
_runners: dict[str, Runner] = {
    AGENT_MODEL: Runner(app_name=APP_NAME, agent=root_agent, session_service=_session_service)
}
_ALLOWED_MODELS = {m.strip() for m in os.environ.get(
    "AGENT_MODELS_ALLOWED",
    "gemini-3.8-flash,gemini-3.7-flash,gemini-3.6-flash,gemini-3.5-flash,gemini-3-flash-preview,gemini-2.5-flash,gemini-3.5-flash-lite",
).split(",") if m.strip()} | {AGENT_MODEL}


def _runner(model: Optional[str]) -> tuple[str, Runner]:
  m = (model or "").strip() or AGENT_MODEL
  if m not in _ALLOWED_MODELS:
    m = AGENT_MODEL
  if m not in _runners:
    _runners[m] = Runner(app_name=APP_NAME, agent=build_agent(m), session_service=_session_service)
  return m, _runners[m]


class ChatRequest(BaseModel):
  session_id: Optional[str] = None
  customer_id: str = ""
  customer_name: str = ""
  visitor_id: str = ""
  message: str = Field(..., min_length=1)
  page_state: Optional[dict[str, Any]] = None
  model: Optional[str] = Field(default=None, description="optional model override (benchmarking)")


# ── persona (get_customer_profile, cached) ───────────────────────────────────────────────────
_PERSONA_TTL = 600
_PERSONA_CACHE: dict[str, tuple[float, str, list[str]]] = {}


def _persona_summary(p: dict[str, Any]) -> tuple[str, list[str]]:
  fam = []
  for m in p.get("family_preferences") or []:
    s = f"{m.get('call_name') or m.get('name')}（{m.get('relation')}・{m.get('age')}歳）好き: {'・'.join(m.get('likes') or [])}"
    if m.get("ng"):
      s += f" / NG: {'・'.join(m['ng'])}"
    fam.append(s)
  allergies = [f"{a.get('member')}: {a.get('allergen')}（{a.get('severity')}）" for a in p.get("allergies") or []]
  parts = {
      "名前": p.get("name") or p.get("customer_name"),
      "家族": " / ".join(fam) or p.get("household"),
      "アレルギー": " / ".join(allergies),
      "除外キーワード": "・".join(p.get("exclude_keywords") or []),
      "味の好み": json.dumps(p.get("taste_preferences") or {}, ensure_ascii=False),
      "料理スタイル": p.get("cooking_style"),
      "買い物スタイル": p.get("shopping_style"),
      "品質の好み": p.get("quality_preference"),
      "苦手": "・".join(p.get("dislikes") or []),
      "季節の関心": p.get("seasonal_interest"),
      "会員": (p.get("loyalty") or {}).get("tier"),
  }
  text = " | ".join(f"{k}: {v}" for k, v in parts.items() if v)
  kws = [str(k) for k in (p.get("exclude_keywords") or [])]
  return text, kws


async def get_persona(customer_id: str) -> tuple[str, list[str]]:
  if not customer_id:
    return "", []
  hit = _PERSONA_CACHE.get(customer_id)
  if hit and time.time() - hit[0] < _PERSONA_TTL:
    return hit[1], hit[2]
  try:
    prof = await mcp_client.call_tool("get_customer_profile", {"customer_id": customer_id})
    if isinstance(prof, dict) and not prof.get("error"):
      text, kws = _persona_summary(prof)
      _PERSONA_CACHE[customer_id] = (time.time(), text, kws)
      return text, kws
    logger.warning("profile lookup failed for %s: %s", customer_id, str(prof)[:200])
  except Exception as exc:
    logger.warning("profile lookup failed for %s: %s", customer_id, exc)
  return "", []


# ── turn handling ────────────────────────────────────────────────────────────────────────────
async def _prepare(req: ChatRequest) -> dict[str, Any]:
  session_id = (req.session_id or f"s-{uuid.uuid4().hex}").strip()
  user_id = (req.customer_id or req.visitor_id or "anonymous").strip()
  model, runner = _runner(req.model)
  persona, kws = await get_persona(req.customer_id.strip())
  state_delta = {
      "customer_id": req.customer_id.strip(),
      "customer_name": req.customer_name.strip(),
      "visitor_id": req.visitor_id.strip(),
      "persona_summary": persona,
      "exclude_keywords": kws,
  }
  existing = await _session_service.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
  if existing is None:
    await _session_service.create_session(app_name=APP_NAME, user_id=user_id, session_id=session_id,
                                          state=dict(state_delta))
  st = shop_state(session_id)
  st.seed(req.page_state)
  st.drain_actions()
  return {"session_id": session_id, "user_id": user_id, "model": model, "runner": runner,
          "state_delta": state_delta, "shop": st,
          "content": types.Content(role="user", parts=[types.Part.from_text(text=req.message)])}


def _chips(actions: list[dict[str, Any]], shop, had_text: bool) -> list[str]:
  names = [a["name"] for a in actions]
  last = actions[-1] if actions else None
  if not last:
    return ["今夜の夕食をお勧めしてね", "フライパンのおすすめ", "お買い得商品を見せて"]
  r = last.get("result") or {}
  n = last["name"]
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
    return ["1番目をカートに入れて", "2番目をカートに入れて", "3番目をカートに入れて"][:max(2, len(last["args"].get("product_ids") or []))]
  if n == "show_products_on_page":
    if last["args"].get("sections"):
      chips = ["セットをカートに入れる"]
      if shop.last_dinner and len(shop.last_dinner.get("sets") or []) > 1:
        chips.append("別の案")
      chips.append("予算1,500円で")
      return chips
    return ["上位3つを比較して", "1番目をカートに入れて"]
  if n == "get_order_status":
    return ["今夜の夕食をお勧めしてね"]
  return []


_FALLBACK_TEXT = {
    "show_products_on_page": "おすすめの商品を画面に表示しました。",
    "show_comparison": "比較表を画面に表示しました。",
    "add_to_cart": "カートに追加しました。このままレジに進むこともできます。",
    "get_cart": "カートの内容を表示しました。",
    "start_checkout": "ご注文手続きを始めます。チャットのボタンからお届け日時をお選びください。",
    "select_delivery_slot": "この内容でご注文を確定してよろしいですか？",
    "place_order": "ご注文ありがとうございます。",
    "get_order_status": "配送状況を表示しました。",
}


class _Turn:
  """Turns ADK events into CONTRACT v3 SSE payloads (text deltas, status, actions)."""

  def __init__(self, shop, t0: float):
    self.shop = shop
    self.t0 = t0
    self.segments: list[str] = []
    self.seg = ""
    self.actions: list[dict[str, Any]] = []
    self.tool_calls: list[dict[str, Any]] = []
    self._seen_fc: set[str] = set()
    self.timings: dict[str, Optional[int]] = {"first_status_ms": None, "first_action_ms": None,
                                              "first_text_ms": None, "total_ms": None}
    self.llm_calls = 0

  def _ms(self) -> int:
    return int((time.perf_counter() - self.t0) * 1000)

  @property
  def reply(self) -> str:
    parts = [s.strip() for s in self.segments if s.strip()]
    if self.seg.strip():
      parts.append(self.seg.strip())
    return "\n\n".join(parts)

  def _text(self, t: str) -> Optional[dict[str, Any]]:
    if not t:
      return None
    if not self.seg and any(s.strip() for s in self.segments):
      t = "\n\n" + t.lstrip()
    elif not self.seg:
      t = t.lstrip()
      if not t:
        return None
    self.seg += t
    if self.timings["first_text_ms"] is None:
      self.timings["first_text_ms"] = self._ms()
    return {"type": "text", "text": t, "author": AUTHOR}

  def _drain(self) -> list[dict[str, Any]]:
    out = self.shop.drain_actions()
    if out and self.timings["first_action_ms"] is None:
      self.timings["first_action_ms"] = self._ms()
    self.actions.extend(out)
    return out

  def process(self, ev: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if getattr(ev, "author", "") == "user":
      return out
    content = getattr(ev, "content", None)
    parts = list(getattr(content, "parts", None) or []) if content else []
    for p in parts:
      fc = getattr(p, "function_call", None)
      if fc:
        fid = getattr(fc, "id", None) or f"{fc.name}-{len(self._seen_fc)}"
        if fid not in self._seen_fc:
          self._seen_fc.add(fid)
          self.tool_calls.append({"name": fc.name, "args": dict(fc.args or {})})
          label = STATUS_LABELS.get(fc.name)
          if label:
            if self.timings["first_status_ms"] is None:
              self.timings["first_status_ms"] = self._ms()
            out.append({"type": "status", "text": label})
    texts = [p.text for p in parts if getattr(p, "text", None) and not getattr(p, "thought", False)]
    if getattr(ev, "partial", False):
      for t in texts:
        d = self._text(t)
        if d:
          out.append(d)
    else:
      if content is not None and getattr(content, "role", None) == "model":
        self.llm_calls += 1
      full = "".join(texts)
      if full:
        streamed = self.seg.lstrip("\n")
        if not streamed:
          d = self._text(full)
          if d:
            out.append(d)
        elif full.startswith(streamed) and len(full) > len(streamed):
          d = self._text(full[len(streamed):])
          if d:
            out.append(d)
        self.segments.append(full)
        self.seg = ""
      elif self.seg:
        self.segments.append(self.seg.lstrip("\n"))
        self.seg = ""
    out.extend(self._drain())
    return out

  def finish(self) -> list[dict[str, Any]]:
    out = self._drain()
    if self.seg:
      self.segments.append(self.seg.lstrip("\n"))
      self.seg = ""
    if not self.reply:
      last = self.actions[-1]["name"] if self.actions else ""
      d = self._text(_FALLBACK_TEXT.get(last, "申し訳ございません、うまくお答えできませんでした。もう一度お試しください。"))
      if d:
        out.append(d)
        self.segments.append(self.seg)
        self.seg = ""
    self.timings["total_ms"] = self._ms()
    return out


def _sse(payload: dict[str, Any]) -> str:
  return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


async def _run_turn(req: ChatRequest, streaming: bool):
  """Async generator of payload dicts for one turn (shared by stream and non-stream endpoints)."""
  t0 = time.perf_counter()
  turn = await _prepare(req)
  col = _Turn(turn["shop"], t0)
  yield {"type": "status", "text": "考えています…"}
  run_config = RunConfig(streaming_mode=StreamingMode.SSE if streaming else StreamingMode.NONE)
  async for ev in turn["runner"].run_async(user_id=turn["user_id"], session_id=turn["session_id"],
                                           new_message=turn["content"], state_delta=turn["state_delta"],
                                           run_config=run_config):
    for payload in col.process(ev):
      yield payload
  for payload in col.finish():
    yield payload
  chips = _chips(col.actions, turn["shop"], bool(col.reply))
  if chips:
    yield {"type": "chips", "items": chips[:4]}
  logger.info("turn session=%s model=%s timings=%s llm_calls=%d tools=%s", turn["session_id"], turn["model"],
              col.timings, col.llm_calls, [t["name"] for t in col.tool_calls])
  yield {"type": "done", "session_id": turn["session_id"], "model": turn["model"], "timings": col.timings,
         "_internal": {"reply": col.reply, "tool_calls": col.tool_calls, "llm_calls": col.llm_calls}}


# ── app ──────────────────────────────────────────────────────────────────────────────────────
async def _warmup() -> None:
  t0 = time.perf_counter()
  try:
    tools = await mcp_client.list_tools()
    logger.info("MCP tools: %s", tools)
  except Exception as exc:
    logger.warning("MCP warmup failed: %s", exc)
  await get_persona(os.environ.get("WARMUP_CUSTOMER_ID", "CR-0001"))
  try:
    from google import genai
    client = genai.Client(vertexai=True)
    await client.aio.models.generate_content(
        model=AGENT_MODEL, contents="ping",
        config=types.GenerateContentConfig(max_output_tokens=8, thinking_config=types.ThinkingConfig(thinking_budget=0)))
  except Exception as exc:
    logger.warning("model warmup failed: %s", exc)
  logger.info("warmup done in %.1fs (catalog=%d products, model=%s)", time.perf_counter() - t0, len(CATALOG), AGENT_MODEL)


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
  task = asyncio.create_task(_warmup())
  yield
  task.cancel()


app = FastAPI(title="cymbal-adk-agent", lifespan=lifespan)


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
  async def gen():
    try:
      async for payload in _run_turn(req, streaming=True):
        payload.pop("_internal", None)
        yield _sse(payload)
    except Exception as exc:
      logger.exception("stream turn failed")
      yield _sse({"type": "error", "message": "申し訳ございません、エラーが発生しました。もう一度お試しください。",
                  "detail": str(exc)[:300]})
  return StreamingResponse(gen(), media_type="text/event-stream",
                           headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/chat")
async def chat(req: ChatRequest) -> dict[str, Any]:
  events: list[dict[str, Any]] = []
  done: dict[str, Any] = {}
  try:
    async for payload in _run_turn(req, streaming=False):
      if payload["type"] == "done":
        done = payload
      else:
        events.append(payload)
  except Exception as exc:
    logger.exception("turn failed")
    return {"error": str(exc), "events": events}
  internal = done.pop("_internal", {})
  return {
      "reply": internal.get("reply", ""),
      "actions": [e for e in events if e["type"] == "action"],
      "chips": next((e["items"] for e in events if e["type"] == "chips"), []),
      "tool_calls": internal.get("tool_calls", []),
      "llm_calls": internal.get("llm_calls"),
      "session_id": done.get("session_id"),
      "model": done.get("model"),
      "timings": done.get("timings"),
      "events": events,
  }


@app.get("/api/health")
async def health() -> dict[str, Any]:
  return {"status": "ok", "model": AGENT_MODEL, "models_allowed": sorted(_ALLOWED_MODELS),
          "catalog_products": len(CATALOG), "mcp_url": mcp_client.MCP_URL, "sessions": len(STATES),
          "persona_cached": list(_PERSONA_CACHE.keys())}


if __name__ == "__main__":
  import uvicorn
  uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
