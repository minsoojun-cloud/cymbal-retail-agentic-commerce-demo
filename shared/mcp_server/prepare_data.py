#!/usr/bin/env python3
"""ペルソナおよび購買履歴フォールバックデータを shared/mcp_server/data/ にバンドルする。

BigQuery (${BQ_DATASET}.customers / ${BQ_DATASET}.purchase_history) に接続できない場合のフォールバックとして使用する。
参照元: ${PERSONAS_DIR:-../../seed/personas}/{personas.json,purchase_history.jsonl}

使い方: python3 prepare_data.py [--force]
"""
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
SRC = pathlib.Path(os.environ.get("PERSONAS_DIR", REPO_ROOT / "seed" / "personas"))
DST = HERE / "data"

REBRAND = [
    ("トップバリュ ベストプライス", "Cymbal ベーシック"),
    ("トップバリュ セレクト", "Cymbal セレクト"),
    ("トップバリュ グリーンアイ オーガニック", "Cymbal オーガニック"),
    ("トップバリュ", "Cymbal"),
    ("WAONポイント", "Cymbalポイント"),
    ("グリーンビーンズ", "Cymbal Retail"),
    ("Green Beans", "Cymbal Retail"),
    ("イオン", "Cymbal Retail"),
]


def rebrand(v):
    if isinstance(v, str):
        for a, b in REBRAND:
            v = v.replace(a, b)
        return v.replace("GB-0001", "CR-0001").replace("gb_customer_id", "cr_customer").replace("gb_visitor_id", "cr_visitor")
    if isinstance(v, list):
        return [rebrand(x) for x in v]
    if isinstance(v, dict):
        return {k: rebrand(x) for k, x in v.items()}
    return v


def convert_persona(p: dict) -> dict:
    if p.get("customer_id", "").startswith("CR-"):
        return p
    p = rebrand(p)
    p["customer_id"] = "CR-0001"
    old = p.get("name")
    p["name"] = "さくら"
    p["name_kana"] = "サクラ"
    for m in p.get("household", []):
        if m.get("relation") == "本人" or m.get("name") == old:
            m["name"] = "さくら"
    p["cookie"] = {"name": "cr_customer", "value": "CR-0001", "example_header": "Cookie: cr_customer=CR-0001; cr_visitor=v-7f3a9c21"}
    p["note"] = "デモ用の架空ペルソナです（実在の人物・会員情報ではありません）"
    return p


def main() -> int:
    force = "--force" in sys.argv
    DST.mkdir(exist_ok=True)
    src_p = SRC / "personas.json"
    out_p = DST / "personas.json"
    if not src_p.exists():
        if out_p.exists():
            print(f"{src_p} が未配置のため既存の {out_p} を使用します")
            return 0
        sys.exit(f"ペルソナ定義ファイルが見つかりません: {src_p}")

    personas = json.loads(src_p.read_text(encoding="utf-8"))
    personas = personas if isinstance(personas, list) else [personas]
    src_is_cr = any(p.get("customer_id", "").startswith("CR-") for p in personas)
    if out_p.exists() and not force and not src_is_cr:
        print(f"既存の {out_p} を維持します（再生成する場合は --force を指定）")
    else:
        out_p.write_text(json.dumps([convert_persona(p) for p in personas], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out_p}")

    hist = SRC / "purchase_history.jsonl"
    out_h = DST / "purchase_history.jsonl"
    if hist.exists() and (force or src_is_cr or not out_h.exists()):
        rows = [json.loads(line) for line in hist.read_text(encoding="utf-8").splitlines() if line.strip()]
        with out_h.open("w", encoding="utf-8") as f:
            for r in rows:
                r = rebrand(r)
                if str(r.get("customer_id", "")).startswith("GB-"):
                    r["customer_id"] = "CR-" + r["customer_id"][3:]
                if str(r.get("order_id", "")).startswith("GB"):
                    r["order_id"] = "CR" + r["order_id"][2:]
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"wrote {out_h} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
