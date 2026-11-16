#!/usr/bin/env python3
"""商品カタログ JSONL 内のストア URL・画像 URL を対象プロジェクトの URL に書き換えるスクリプト。

seed/catalog/products_retail.jsonl（元ファイルは変更しない）をストリーミング読み込みし、
`uri` および `images[].uri` に含まれる `__ONLINE_STORE_URL__` プレースホルダーや
`https://cymbal-site...` / `http://cymbal-site...` を `$ONLINE_STORE_URL` に置換して出力します。
全行の JSON 構文と必須フィールド (`id`, `title`) を検証します。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# 元のデモ環境 URL またはテンプレートプレースホルダーに一致する正規表現
STORE_URL_RE = re.compile(r"(?:__ONLINE_STORE_URL__|https?://cymbal-site[^/\"'\s]*)")


def rewrite_url_value(val: str, target_base_url: str) -> tuple[str, bool]:
    """単一の URL 文字列内のストア URL プレフィックスを置換し、(置換後文字列, 変更有無) を返します。"""
    if not val:
        return val, False
    new_val = STORE_URL_RE.sub(target_base_url, val)
    return new_val, (new_val != val)


def rewrite_product_record(record: dict, target_base_url: str, line_no: int = 0) -> tuple[dict, int]:
    """1 商品レコード内の URI フィールドを書き換え、(更新済み辞書, 書き換え箇所数) を返します。"""
    if not isinstance(record, dict):
        raise ValueError(f"{line_no} 行目: JSON オブジェクトではありません。")
    if not record.get("id") or not record.get("title"):
        raise ValueError(f"{line_no} 行目: 必須フィールド 'id' または 'title' が欠落しています。")

    changed = 0
    if isinstance(record.get("uri"), str):
        new_uri, mod = rewrite_url_value(record["uri"], target_base_url)
        record["uri"] = new_uri
        changed += int(mod)

    images = record.get("images")
    if isinstance(images, list):
        for img in images:
            if isinstance(img, dict) and isinstance(img.get("uri"), str):
                new_img_uri, mod = rewrite_url_value(img["uri"], target_base_url)
                img["uri"] = new_img_uri
                changed += int(mod)

    return record, changed


def rewrite_catalog_file(src_path: Path, dst_path: Path, online_store_url: str) -> dict[str, int]:
    """カタログ JSONL をストリーミング変換し、統計情報 `{rows, rewritten_fields}` を返します。"""
    base_url = online_store_url.strip().rstrip("/")
    if not base_url.startswith(("https://", "http://")):
        raise ValueError(f"ONLINE_STORE_URL は http(s):// で始まる必要があります: '{online_store_url}'")
    if not src_path.is_file():
        raise FileNotFoundError(f"入力カタログファイルが見つかりません: {src_path}")

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dst_path.with_suffix(dst_path.suffix + ".tmp")

    rows = 0
    rewritten_fields = 0
    with src_path.open("r", encoding="utf-8") as fin, tmp_path.open("w", encoding="utf-8") as fout:
        for idx, raw_line in enumerate(fin, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{src_path} の {idx} 行目で JSON 解析エラーが発生しました: {exc}") from exc
            updated, cnt = rewrite_product_record(obj, base_url, line_no=idx)
            fout.write(json.dumps(updated, ensure_ascii=False) + "\n")
            rows += 1
            rewritten_fields += cnt

    if rows == 0:
        tmp_path.unlink(missing_ok=True)
        raise ValueError(f"入力カタログファイルが空です: {src_path}")

    os.replace(tmp_path, dst_path)
    return {"rows": rows, "rewritten_fields": rewritten_fields}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="products_retail.jsonl 内の URL を対象環境の ONLINE_STORE_URL に書き換えます。"
    )
    parser.add_argument(
        "--src",
        default=os.environ.get("SEED_CATALOG_JSONL", ""),
        help="入力元の products_retail.jsonl パス（省略時は seed/catalog/products_retail.jsonl）",
    )
    parser.add_argument(
        "--dst",
        required=True,
        help="書き換え後の JSONL 出力先パス（元ファイルと別パスを指定してください）",
    )
    parser.add_argument(
        "--online-store-url",
        default=os.environ.get("ONLINE_STORE_URL", ""),
        help="置換先のオンラインストア URL（例: https://cymbal-site-adk-123456.asia-northeast1.run.app）",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent.parent.parent
    src_path = Path(args.src) if args.src else (repo_root / "seed" / "catalog" / "products_retail.jsonl")
    dst_path = Path(args.dst)

    if src_path.resolve() == dst_path.resolve():
        print("エラー: 入力ファイル (--src) と出力ファイル (--dst) に同じパスは指定できません。", file=sys.stderr)
        return 1

    try:
        stats = rewrite_catalog_file(src_path, dst_path, args.online_store_url)
    except Exception as exc:  # noqa: BLE001
        print(f"エラー: カタログ URL 書き換えに失敗しました: {exc}", file=sys.stderr)
        return 1

    print(
        f"[完了] カタログ URL 書き換え完了: {stats['rows']:,} 件処理 / "
        f"URL 置換 {stats['rewritten_fields']:,} 箇所 -> {dst_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
