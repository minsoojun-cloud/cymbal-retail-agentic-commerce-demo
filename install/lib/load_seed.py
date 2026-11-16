#!/usr/bin/env python3
"""BigQuery データセット・Cloud Storage バケットを作成し、シードデータ一式を投入するスクリプト。

実行内容（すべて冪等 / 再実行安全）:
1. BigQuery データセット ($BQ_DATASET, $ENRICH_BQ_DATASET) を $REGION に作成
2. Cloud Storage バケット ($CATALOG_BUCKET, $STORE_NAVI_BUCKET, $ENRICH_IMAGE_BUCKET) を均一バケットレベルアクセスで作成
3. seed/gcs/store-navi/* → gs://$STORE_NAVI_BUCKET/、seed/gcs/enrichment-images/* → gs://$ENRICH_IMAGE_BUCKET/ にアップロード
4. seed/catalog/products_retail.jsonl の URL を $ONLINE_STORE_URL に書き換え、$BQ_DATASET.products に WRITE_TRUNCATE でロード
5. seed/bigquery/{cymbal,cymbal_enrichment}/ 内の各 <table>.jsonl.gz (+ <table>.schema.json) について、
   エクスポート元プロジェクトのバケット名・Cloud Run URL・データセット参照を
   対象プロジェクトの値に置換した上で WRITE_TRUNCATE (--replace) でロード
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

# 同ディレクトリの rewrite_urls をインポート
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import rewrite_urls  # noqa: E402

EXCLUDED_TABLE_PREFIXES = (
    "products_backup_",
    "batch_requests_",
    "batch_predictions_",
)


def build_env() -> dict[str, str]:
    env = dict(os.environ)
    sdk_bin = os.path.expanduser("~/google-cloud-sdk/bin")
    if os.path.isdir(sdk_bin) and sdk_bin not in env.get("PATH", ""):
        env["PATH"] = f"{sdk_bin}:{env.get('PATH', '')}"
    env.setdefault("CLOUDSDK_CORE_DISABLE_PROMPTS", "1")
    return env


def run_cmd(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess[str]:
    res = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        env=build_env(),
        check=False,
    )
    if check and res.returncode != 0:
        stderr_txt = (res.stderr or "").strip()
        stdout_txt = (res.stdout or "").strip()
        detail = f"{stdout_txt}\n{stderr_txt}".strip()
        raise RuntimeError(f"コマンド実行失敗 (rc={res.returncode}): {' '.join(cmd[:8])}\n{detail}")
    return res


def ensure_bq_dataset(project: str, dataset: str, location: str, description: str) -> None:
    ref = f"{project}:{dataset}"
    chk = run_cmd(["bq", f"--project_id={project}", "show", ref], check=False, capture=True)
    if chk.returncode == 0:
        print(f"  [確認済] BigQuery データセット {ref} は既に存在します。")
        return
    print(f"  [作成] BigQuery データセット {ref} (location={location}) を作成します...")
    run_cmd([
        "bq",
        f"--project_id={project}",
        f"--location={location}",
        "mk",
        "--dataset",
        "--description",
        description,
        ref,
    ])


def ensure_gcs_bucket(project: str, bucket: str, location: str) -> None:
    uri = f"gs://{bucket}"
    chk = run_cmd(["gcloud", "storage", "buckets", "describe", uri, f"--project={project}"], check=False, capture=True)
    if chk.returncode == 0:
        print(f"  [確認済] Cloud Storage バケット {uri} は既に存在します。")
        return
    print(f"  [作成] Cloud Storage バケット {uri} (location={location}, uniform-bucket-level-access) を作成します...")
    run_cmd([
        "gcloud",
        "storage",
        "buckets",
        "create",
        uri,
        f"--project={project}",
        f"--location={location}",
        "--uniform-bucket-level-access",
    ])


def upload_gcs_seed_dir(project: str, src_dir: Path, bucket: str) -> int:
    if not src_dir.is_dir():
        print(f"  [スキップ] GCS シードディレクトリが存在しません: {src_dir}")
        return 0
    files = [p for p in src_dir.rglob("*") if p.is_file() and not p.name.startswith(".")]
    if not files:
        print(f"  [スキップ] GCS シードディレクトリが空です: {src_dir}")
        return 0
    print(f"  [アップロード] {src_dir} ({len(files)} ファイル) -> gs://{bucket}/ ...")
    run_cmd([
        "gcloud",
        "storage",
        "rsync",
        "--recursive",
        str(src_dir),
        f"gs://{bucket}/",
        f"--project={project}",
    ])
    return len(files)


def normalize_schema_file(schema_path: Path, tmp_dir: Path) -> Path:
    """bq load が受け付ける JSON 配列形式のスキーマファイルに正規化します。"""
    raw = json.loads(schema_path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        if "schema" in raw and isinstance(raw["schema"], dict) and "fields" in raw["schema"]:
            fields = raw["schema"]["fields"]
        elif "fields" in raw and isinstance(raw["fields"], list):
            fields = raw["fields"]
        else:
            raise ValueError(f"未対応のスキーマ JSON 形式です: {schema_path}")
    elif isinstance(raw, list):
        fields = raw
    else:
        raise ValueError(f"不正なスキーマ JSON です: {schema_path}")

    out_path = tmp_dir / schema_path.name
    out_path.write_text(json.dumps(fields, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def build_string_rewriter(cfg: dict[str, str]):
    """元プロジェクトのバケット・Cloud Run URL・プロジェクト名を置換する関数を構築します。"""
    online_url = cfg["ONLINE_STORE_URL"].rstrip("/")
    enrich_url = cfg["ENRICH_URL"].rstrip("/")
    staff_url = cfg["STAFF_URL"].rstrip("/")
    customer_url = cfg["CUSTOMER_URL"].rstrip("/")
    adk_url = cfg["ADK_AGENT_URL"].rstrip("/")
    mcp_url = cfg["MCP_URL"].rstrip("/")
    enrich_bucket = cfg["ENRICH_IMAGE_BUCKET"]
    navi_bucket = cfg["STORE_NAVI_BUCKET"]
    cat_bucket = cfg["CATALOG_BUCKET"]
    flyers_bucket = cfg["FLYERS_BUCKET"]
    spec_bucket = cfg["SPEC_BANNER_BUCKET"]
    flyer_url = cfg["FLYER_STUDIO_URL"].rstrip("/")
    spec_url = cfg["SPEC_BANNER_URL"].rstrip("/")
    project_id = cfg["PROJECT_ID"]
    project_number = cfg.get("PROJECT_NUMBER", "")
    bq_ds = cfg["BQ_DATASET"]
    enrich_ds = cfg["ENRICH_BQ_DATASET"]

    # 順序重要: より具体的な URL / バケットパターンから先に置換する
    rules: list[tuple[re.Pattern[str], str]] = [
        # プレースホルダー
        (re.compile(r"__ONLINE_STORE_URL__"), online_url),
        (re.compile(r"__ENRICH_URL__"), enrich_url),
        (re.compile(r"__STAFF_URL__"), staff_url),
        (re.compile(r"__CUSTOMER_URL__"), customer_url),
        (re.compile(r"__ENRICH_IMAGE_BUCKET__"), enrich_bucket),
        (re.compile(r"__STORE_NAVI_BUCKET__"), navi_bucket),
        (re.compile(r"__CATALOG_BUCKET__"), cat_bucket),
        (re.compile(r"__FLYERS_BUCKET__"), flyers_bucket),
        # GCS バケット名 (gs:// 有無両方に対応、任意の元プロジェクト名を置換)
        (re.compile(r"\bproducts_images_[a-z][a-z0-9-]{4,29}\b"), enrich_bucket),
        (re.compile(r"\b[a-z][a-z0-9-]{4,29}-store-navi\b"), navi_bucket),
        (re.compile(r"\b[a-z][a-z0-9-]{4,29}-catalog\b"), cat_bucket),
        (re.compile(r"\b[a-z][a-z0-9-]{4,29}-flyers\b"), flyers_bucket),
        (re.compile(r"\b[a-z][a-z0-9-]{4,29}-spec-banner\b"), spec_bucket),
        # Cloud Run URL (プロジェクト番号形式 または ハッシュ形式)
        (
            re.compile(r"https?://cymbal-flyer-studio-(?:[0-9]{8,15}\.[a-z0-9-]+\.run\.app|[a-z0-9]{8,14}-[a-z0-9-]+\.a\.run\.app)"),
            flyer_url,
        ),
        (
            re.compile(r"https?://(?:cymbal|edion)-spec-banner-(?:[0-9]{8,15}\.[a-z0-9-]+\.run\.app|[a-z0-9]{8,14}-[a-z0-9-]+\.a\.run\.app)"),
            spec_url,
        ),
        (
            re.compile(r"https?://cymbal-data-enrichment-(?:[0-9]{8,15}\.[a-z0-9-]+\.run\.app|[a-z0-9]{8,14}-[a-z0-9-]+\.a\.run\.app)"),
            enrich_url,
        ),
        (
            re.compile(r"https?://cymbal-store-staff-(?:[0-9]{8,15}\.[a-z0-9-]+\.run\.app|[a-z0-9]{8,14}-[a-z0-9-]+\.a\.run\.app)"),
            staff_url,
        ),
        (
            re.compile(r"https?://cymbal-store-app-(?:[0-9]{8,15}\.[a-z0-9-]+\.run\.app|[a-z0-9]{8,14}-[a-z0-9-]+\.a\.run\.app)"),
            customer_url,
        ),
        (
            re.compile(r"https?://cymbal-adk-agent-(?:[0-9]{8,15}\.[a-z0-9-]+\.run\.app|[a-z0-9]{8,14}-[a-z0-9-]+\.a\.run\.app)"),
            adk_url,
        ),
        (
            re.compile(r"https?://cymbal-commerce-mcp-(?:[0-9]{8,15}\.[a-z0-9-]+\.run\.app|[a-z0-9]{8,14}-[a-z0-9-]+\.a\.run\.app)"),
            mcp_url,
        ),
        (
            re.compile(r"https?://cymbal-site[^/\"'\s\\]*"),
            online_url,
        ),
        # BigQuery データセット参照文字列 (<旧PROJECT_ID>.cymbal_enrichment / <旧PROJECT_ID>.cymbal)
        (re.compile(r"\b[a-z][a-z0-9-]{4,29}\.cymbal_enrichment\b"), f"{project_id}.{enrich_ds}"),
        (re.compile(r"\b[a-z][a-z0-9-]{4,29}\.cymbal\b"), f"{project_id}.{bq_ds}"),
    ]
    if project_number:
        rules.append((re.compile(r"\bprojects/[0-9]{8,15}/"), f"projects/{project_number}/"))

    def rewrite_obj(val: Any) -> tuple[Any, int]:
        if isinstance(val, str):
            cur = val
            changed = 0
            for pat, repl in rules:
                nxt = pat.sub(repl, cur)
                if nxt != cur:
                    changed += 1
                    cur = nxt
            return cur, changed
        if isinstance(val, list):
            total = 0
            out_list = []
            for item in val:
                new_item, c = rewrite_obj(item)
                out_list.append(new_item)
                total += c
            return out_list, total
        if isinstance(val, dict):
            total = 0
            out_dict = {}
            for k, v in val.items():
                new_v, c = rewrite_obj(v)
                out_dict[k] = new_v
                total += c
            return out_dict, total
        return val, 0

    return rewrite_obj


def rewrite_seed_table_jsonl(src_file: Path, dst_jsonl: Path, rewriter) -> tuple[int, int]:
    """シード JSONL(.gz) を展開・URL/バケット置換して一時 JSONL に書き出します。"""
    opener = gzip.open if src_file.name.endswith(".gz") else open
    triggers = ("http", "gs://", "projects/", ".cymbal", "store-navi", "products_images_", "-catalog", "-flyers", "-spec-banner", "__")
    rows = 0
    rewrites = 0
    with opener(src_file, "rt", encoding="utf-8") as fin, dst_jsonl.open("w", encoding="utf-8") as fout:
        for idx, raw in enumerate(fin, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{src_file} の {idx} 行目で JSON 解析エラーが発生しました: {exc}") from exc
            if any(t in line for t in triggers):
                new_obj, cnt = rewriter(obj)
                fout.write(json.dumps(new_obj, ensure_ascii=False) + "\n")
                rewrites += cnt
            else:
                fout.write(line + "\n")
            rows += 1
    return rows, rewrites


def load_bq_table(
    project: str,
    location: str,
    dataset: str,
    table: str,
    jsonl_path: Path,
    schema_path: Path,
    row_count: int,
) -> None:
    """BigQuery テーブルを WRITE_TRUNCATE (--replace) で冪等にロードします（0 件時は空テーブルを再作成）。"""
    table_ref = f"{project}:{dataset}.{table}"
    if row_count == 0:
        run_cmd(["bq", f"--project_id={project}", "rm", "-f", "-t", table_ref], check=False)
        run_cmd([
            "bq",
            f"--project_id={project}",
            f"--location={location}",
            "mk",
            "--table",
            table_ref,
            str(schema_path),
        ])
        return

    run_cmd([
        "bq",
        f"--project_id={project}",
        f"--location={location}",
        "load",
        "--replace",
        "--source_format=NEWLINE_DELIMITED_JSON",
        table_ref,
        str(jsonl_path),
        str(schema_path),
    ])


def discover_seed_tables(seed_bq_dir: Path, skip_products: bool = False) -> list[tuple[str, Path, Path]]:
    """ディレクトリ内の (table_name, data_path, schema_path) 一覧を返します。"""
    if not seed_bq_dir.is_dir():
        return []
    found: dict[str, Path] = {}
    for p in sorted(seed_bq_dir.iterdir()):
        if p.name.endswith(".jsonl.gz"):
            tname = p.name[: -len(".jsonl.gz")]
            found[tname] = p
        elif p.name.endswith(".jsonl") and not p.name.endswith(".schema.json"):
            tname = p.name[: -len(".jsonl")]
            found.setdefault(tname, p)

    result: list[tuple[str, Path, Path]] = []
    for tname, data_path in sorted(found.items()):
        if skip_products and tname == "products":
            continue
        if any(tname.startswith(pref) for pref in EXCLUDED_TABLE_PREFIXES):
            continue
        schema_path = seed_bq_dir / f"{tname}.schema.json"
        if not schema_path.is_file():
            raise FileNotFoundError(f"スキーマファイルが見つかりません: {schema_path} (対象データ: {data_path})")
        result.append((tname, data_path, schema_path))
    return result


def resolve_catalog_schema(repo_root: Path) -> Path:
    candidates = [
        repo_root / "seed" / "catalog" / "products.schema.json",
        repo_root / "shared" / "catalog" / "bq_schema.json",
    ]
    for c in candidates:
        if c.is_file():
            return c
    raise FileNotFoundError(
        "商品カタログ用 BigQuery スキーマが見つかりません: "
        + ", ".join(str(c) for c in candidates)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="BigQuery データセット・GCS バケットを作成し、デモ用シードデータ一式を投入します。"
    )
    parser.add_argument("--project", default=os.environ.get("PROJECT_ID", ""), help="Google Cloud プロジェクト ID")
    parser.add_argument("--region", default=os.environ.get("REGION", "asia-northeast1"), help="リージョン")
    parser.add_argument("--skip-gcs", action="store_true", help="GCS バケット作成・ファイルアップロードをスキップ")
    parser.add_argument("--skip-bq", action="store_true", help="BigQuery ロードをスキップ")
    args = parser.parse_args(argv)

    repo_root = HERE.parent.parent
    state_dir = HERE.parent / ".state"
    state_dir.mkdir(parents=True, exist_ok=True)

    project = args.project.strip()
    if not project:
        print("エラー: PROJECT_ID が未設定です。", file=sys.stderr)
        return 1

    region = args.region.strip()
    bq_dataset = os.environ.get("BQ_DATASET", "cymbal")
    enrich_dataset = os.environ.get("ENRICH_BQ_DATASET", "cymbal_enrichment")
    catalog_bucket = os.environ.get("CATALOG_BUCKET") or f"{project}-catalog"
    store_navi_bucket = os.environ.get("STORE_NAVI_BUCKET") or f"{project}-store-navi"
    enrich_image_bucket = os.environ.get("ENRICH_IMAGE_BUCKET") or f"products_images_{project}"
    flyers_bucket = os.environ.get("FLYERS_BUCKET") or f"{project}-flyers"
    spec_banner_bucket = os.environ.get("SPEC_BANNER_BUCKET") or f"{project}-spec-banner"
    online_store_url = os.environ.get("ONLINE_STORE_URL", "")
    if not online_store_url:
        print("エラー: ONLINE_STORE_URL が未設定です（common.sh 経由で実行してください）。", file=sys.stderr)
        return 1

    project_number = os.environ.get("PROJECT_NUMBER", "").strip()
    if not project_number:
        pnum_res = run_cmd(["gcloud", "projects", "describe", project, "--format=value(projectNumber)"], check=False, capture=True)
        project_number = (pnum_res.stdout or "").strip()

    cfg = {
        "PROJECT_ID": project,
        "PROJECT_NUMBER": project_number,
        "BQ_DATASET": bq_dataset,
        "ENRICH_BQ_DATASET": enrich_dataset,
        "CATALOG_BUCKET": catalog_bucket,
        "STORE_NAVI_BUCKET": store_navi_bucket,
        "ENRICH_IMAGE_BUCKET": enrich_image_bucket,
        "FLYERS_BUCKET": flyers_bucket,
        "SPEC_BANNER_BUCKET": spec_banner_bucket,
        "ONLINE_STORE_URL": online_store_url,
        "ENRICH_URL": os.environ.get("ENRICH_URL", online_store_url),
        "STAFF_URL": os.environ.get("STAFF_URL", online_store_url),
        "CUSTOMER_URL": os.environ.get("CUSTOMER_URL", online_store_url),
        "ADK_AGENT_URL": os.environ.get("ADK_AGENT_URL", online_store_url),
        "MCP_URL": os.environ.get("MCP_URL", online_store_url),
        "FLYER_STUDIO_URL": os.environ.get("FLYER_STUDIO_URL", online_store_url),
        "SPEC_BANNER_URL": os.environ.get("SPEC_BANNER_URL", online_store_url),
    }

    # 1. GCS バケット作成 + シードファイルのアップロード
    if not args.skip_gcs:
        print("[1/3] Cloud Storage バケットの準備とシード画像のアップロードを実行しています...")
        for bkt in (catalog_bucket, store_navi_bucket, enrich_image_bucket, flyers_bucket, spec_banner_bucket):
            ensure_gcs_bucket(project, bkt, region)
        upload_gcs_seed_dir(project, repo_root / "seed" / "gcs" / "store-navi", store_navi_bucket)
        upload_gcs_seed_dir(project, repo_root / "seed" / "gcs" / "enrichment-images", enrich_image_bucket)
        upload_gcs_seed_dir(project, repo_root / "seed" / "gcs" / "flyers", flyers_bucket)

    if args.skip_bq:
        print("[完了] --skip-bq 指定のため BigQuery ロードをスキップしました。")
        return 0

    # 2. BigQuery データセット作成 + カタログ URL 書き換え & products テーブルロード
    print("[2/3] BigQuery データセットの準備と商品カタログのロードを実行しています...")
    ensure_bq_dataset(project, bq_dataset, region, "Cymbal Retail デモ カタログ・店舗・顧客データ")
    ensure_bq_dataset(project, enrich_dataset, region, "Cymbal Retail 商品情報エンリッチメント スタジオ")

    tmp_dir = Path(tempfile.mkdtemp(prefix="cymbal_seed_"))
    try:
        src_catalog = repo_root / "seed" / "catalog" / "products_retail.jsonl"
        rewritten_catalog = state_dir / "products_retail.rewritten.jsonl"
        cat_stats = rewrite_urls.rewrite_catalog_file(src_catalog, rewritten_catalog, online_store_url)
        print(
            f"  [カタログ書き換え] {cat_stats['rows']:,} 件 "
            f"(URL 置換: {cat_stats['rewritten_fields']:,} 箇所) -> {rewritten_catalog}"
        )

        cat_schema = normalize_schema_file(resolve_catalog_schema(repo_root), tmp_dir)
        print(f"  [BigQuery ロード] {project}:{bq_dataset}.products ({cat_stats['rows']:,} 件) ...")
        load_bq_table(
            project=project,
            location=region,
            dataset=bq_dataset,
            table="products",
            jsonl_path=rewritten_catalog,
            schema_path=cat_schema,
            row_count=cat_stats["rows"],
        )

        # 3. seed/bigquery/{cymbal,cymbal_enrichment} の全テーブルを置換ロード
        print("[3/3] BigQuery シードテーブルの URL・バケット名書き換えとロードを実行しています...")
        rewriter = build_string_rewriter(cfg)
        seed_groups = [
            (bq_dataset, repo_root / "seed" / "bigquery" / "cymbal", True),
            (enrich_dataset, repo_root / "seed" / "bigquery" / "cymbal_enrichment", False),
        ]
        total_tables = 0
        for target_ds, seed_dir, skip_prod in seed_groups:
            tables = discover_seed_tables(seed_dir, skip_products=skip_prod)
            if not tables:
                print(f"  [警告] シードテーブルが見つかりませんでした: {seed_dir}")
                continue
            for tname, data_path, raw_schema_path in tables:
                norm_schema = normalize_schema_file(raw_schema_path, tmp_dir)
                out_jsonl = tmp_dir / f"{target_ds}__{tname}.jsonl"
                rows, mod_cnt = rewrite_seed_table_jsonl(data_path, out_jsonl, rewriter)
                mod_note = f", 参照置換 {mod_cnt} 箇所" if mod_cnt else ""
                print(f"  [BigQuery ロード] {project}:{target_ds}.{tname:<26} ({rows:>6,} 件{mod_note})")
                load_bq_table(
                    project=project,
                    location=region,
                    dataset=target_ds,
                    table=tname,
                    jsonl_path=out_jsonl,
                    schema_path=norm_schema,
                    row_count=rows,
                )
                out_jsonl.unlink(missing_ok=True)
                total_tables += 1

        print(f"[完了] カタログ 1 テーブル + シード {total_tables} テーブルの BigQuery ロードが完了しました。")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
