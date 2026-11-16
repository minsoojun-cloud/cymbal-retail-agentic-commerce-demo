"""runner._Collector: streamed text deltas, final aggregate events, duplicate re-generated segments, post-filter."""
from __future__ import annotations

from types import SimpleNamespace as NS

from app.agent import runner


class _St:
    def drain(self):
        return []


def _ev(text, partial):
    return NS(author="store_concierge", partial=partial, content=NS(role="model", parts=[NS(text=text, function_call=None, thought=False)]))


def _texts(col, events):
    out = []
    for e in events:
        out += [p["text"] for p in col.process(e) if p["type"] == "text"]
    out += [p["text"] for p in col.finish() if p["type"] == "text"]
    return "".join(out)


def test_stream_then_final_not_duplicated():
    col = runner._Collector(_St(), 0)
    txt = _texts(col, [_ev("こんにちは。", True), _ev("お大事に。", True), _ev("こんにちは。お大事に。", False)])
    assert txt == "こんにちは。お大事に。"


def test_regenerated_segment_dropped():
    col = runner._Collector(_St(), 0)
    a = "受診までの補助用品です。"
    b = "「まとめて棚を探す」でご案内します。"
    txt = _texts(col, [_ev(a, True), _ev(b, True), _ev(a + b, False),
                       _ev(a, True), _ev(b, True), _ev(a + b, False)])
    assert txt.count(a) == 1 and txt.count(b) == 1


def test_new_segment_after_tool_kept():
    col = runner._Collector(_St(), 0)
    txt = _texts(col, [_ev("一つ目の回答です。", False), _ev("追加のご案内です。", True), _ev("追加のご案内です。", False)])
    assert "一つ目の回答です。" in txt and "追加のご案内です。" in txt and "\n\n" in txt


def test_banned_words_filtered_in_stream():
    col = runner._Collector(_St(), 0)
    txt = _texts(col, [_ev("この薬で必ず", True), _ev("治ります。", True), _ev("この薬で必ず治ります。", False)])
    assert "必ず治" not in txt
