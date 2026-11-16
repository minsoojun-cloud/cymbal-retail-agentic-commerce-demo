"""Catalog & Flyer repository backed by BigQuery (`cymbal.products`, `cymbal.flyer_*`) and GCS (`${PROJECT_ID}-flyers`).

Falls back seamlessly to local JSONL/JSON files when `FLYER_DATA_MODE=local` or offline during unit tests.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

log = logging.getLogger("cymbal-flyer.repo")

APP_DIR = Path(__file__).resolve().parent
SERVICE_DIR = APP_DIR.parent
REPO_DIR = SERVICE_DIR.parent

PROJECT_ID = os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
BQ_DATASET = os.environ.get("BQ_DATASET", "cymbal")
BQ_LOCATION = os.environ.get("BQ_LOCATION", os.environ.get("REGION", "asia-northeast1"))
FLYERS_BUCKET = os.environ.get("FLYERS_BUCKET") or (f"{PROJECT_ID}-flyers" if PROJECT_ID else "")
LOCAL_STORAGE_DIR = Path(os.environ.get("LOCAL_STORAGE_DIR", str(SERVICE_DIR / "data" / "storage")))

_IMG_RE = re.compile(r"/img/products/([^/?#]+)$")


def local_image(uri: str) -> str:
    if not uri:
        return ""
    m = _IMG_RE.search(uri.split("?")[0])
    return f"/img/products/{m.group(1)}" if m else uri


def _attr_map(raw: Any) -> dict[str, dict]:
    if isinstance(raw, dict):
        return raw
    out: dict[str, dict] = {}
    for a in raw or []:
        if isinstance(a, dict) and "key" in a:
            out[a["key"]] = a.get("value") or {}
    return out


def _attr_texts(attrs: dict, key: str) -> list[str]:
    v = attrs.get(key) or {}
    return [str(x) for x in (v.get("text") or [])]


def _attr_text(attrs: dict, key: str) -> str:
    t = _attr_texts(attrs, key)
    return t[0] if t else ""


def _attr_nums(attrs: dict, key: str) -> list[float]:
    v = attrs.get(key) or {}
    out: list[float] = []
    for x in v.get("numbers") or []:
        try:
            out.append(float(x))
        except (TypeError, ValueError):
            pass
    return out


def _attr_num(attrs: dict, key: str) -> float | None:
    ns = _attr_nums(attrs, key)
    return ns[0] if ns else None


def _int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


BRAND_PREFIXES = (
    "Cymbal ベーシック ",
    "Cymbal セレクト ",
    "Cymbal オーガニック ",
    "Cymbal Home ",
    "Cymbal Beauty ",
    "Cymbal Pet ",
    "Cymbal ",
)


def make_flyer_name(title: str) -> str:
    s = (title or "").strip()
    for p in BRAND_PREFIXES:
        if s.startswith(p):
            s = s[len(p):].strip()
            break
    return s or title


def normalize_product(p: dict, ext: dict | None = None) -> dict:
    attrs = _attr_map(p.get("attributes"))
    price_info = p.get("priceInfo") or p.get("price_info") or {}
    price_inc = _int(price_info.get("price")) or 0
    orig_inc = _int(price_info.get("originalPrice", price_info.get("original_price"))) or price_inc

    # Tax rate detection: food is 8%, alcohol / non-food is 10%
    is_food = _attr_text(attrs, "is_food").lower() != "false"
    cats = p.get("categories") or []
    cat_path = cats[0] if cats else ""
    top = _attr_text(attrs, "top_category") or cat_path.split(">")[0].strip()
    tax_rate = 0.10 if (not is_food or "お酒" in top) else 0.08

    price_ex = _int(_attr_num(attrs, "price_tax_excluded")) or max(1, int(round(price_inc / (1.0 + tax_rate))))
    orig_ex = _int(_attr_num(attrs, "original_price_tax_excluded"))
    if not orig_ex:
        orig_ex = price_ex if orig_inc <= price_inc else max(price_ex, int(round(orig_inc / (1.0 + tax_rate))))

    # Accurate tax-included decimal string (Japanese chirashi standard, e.g. 170.64円)
    price_inc_exact = round(price_ex * (1.0 + tax_rate), 2)
    orig_inc_exact = round(orig_ex * (1.0 + tax_rate), 2)

    on_sale = _attr_text(attrs, "on_sale").lower() == "true" or (orig_ex > price_ex > 0) or (orig_inc > price_inc > 0)
    discount = _attr_num(attrs, "discount_rate")
    if discount and discount > 1:
        discount = discount / 100.0
    if not discount and orig_ex > price_ex > 0:
        discount = round((orig_ex - price_ex) / orig_ex, 2)

    images = [i.get("uri") for i in (p.get("images") or []) if isinstance(i, dict) and i.get("uri")]
    rating_info = p.get("rating") or {}
    avg = rating_info.get("averageRating", rating_info.get("average_rating"))
    cnt = _int(rating_info.get("ratingCount", rating_info.get("rating_count")))
    brands = p.get("brands") or []
    title = p.get("title") or ""
    size = _attr_text(attrs, "size")
    origin = _attr_text(attrs, "origin")
    season_months = [int(round(m)) for m in _attr_nums(attrs, "season_months")]

    ext = ext or {}
    flyer_name = ext.get("flyer_name") or make_flyer_name(title)
    unit_label = ext.get("unit_label") or size or "1点"
    price_per_100g = _int(ext.get("price_per_100g"))
    pack_type = ext.get("pack_type") or "標準"
    origin_label = ext.get("origin_label") or origin

    return {
        "id": str(p.get("id") or str(p.get("name", "")).rsplit("/", 1)[-1]),
        "title": title,
        "flyer_name": flyer_name,
        "brand": brands[0] if brands else "",
        "category": top,
        "category_path": cat_path,
        "price_tax_excluded": price_ex,
        "price": price_inc,
        "price_tax_included_exact": price_inc_exact,
        "original_price_tax_excluded": orig_ex,
        "original_price": orig_inc,
        "original_price_tax_included_exact": orig_inc_exact,
        "tax_rate": tax_rate,
        "on_sale": bool(on_sale),
        "discount_rate": float(discount or 0.0),
        "image": local_image(images[0]) if images else "",
        "rating": round(float(avg), 1) if avg is not None else 4.2,
        "rating_count": cnt if cnt is not None else 24,
        "size": size,
        "unit_label": unit_label,
        "price_per_100g": price_per_100g,
        "pack_type": pack_type,
        "origin": origin_label,
        "labels": _attr_texts(attrs, "labels"),
        "dishes": _attr_texts(attrs, "dishes"),
        "is_seasonal": _attr_text(attrs, "is_seasonal").lower() == "true",
        "season_months": season_months,
        "promo_text": " ".join(_attr_text(attrs, "promo_text").split()),
        "availability": p.get("availability") or "IN_STOCK",
        "description": p.get("description") or "",
    }


def compute_tax_included(price_tax_excluded: int, tax_rate: float = 0.08) -> tuple[int, float]:
    exact = round(int(price_tax_excluded) * (1.0 + float(tax_rate)), 2)
    return int(round(exact)), exact


def default_data_file() -> Path:
    env = os.environ.get("DATA_FILE") or os.environ.get("CATALOG_JSONL")
    if env and Path(env).exists():
        return Path(env)
    for cand in (
        SERVICE_DIR / "data" / "products_retail.jsonl",
        REPO_DIR / "seed" / "catalog" / "products_retail.jsonl",
        REPO_DIR / "data" / "products_retail.jsonl",
    ):
        if cand.exists():
            return cand
    return SERVICE_DIR / "data" / "products_retail.jsonl"


def default_ext_file() -> Path:
    return SERVICE_DIR / "data" / "flyer_product_ext.json"


class FlyerRepository:
    """Unified repository for catalog products (BigQuery + local cache), flyer offers, and GCS archives."""

    def __init__(self, force_local: bool = False):
        self.force_local = force_local or (os.environ.get("FLYER_DATA_MODE") == "local")
        self.items: dict[str, dict] = {}
        self.source: str = "uninitialized"
        self._bq_client = None
        self._gcs_client = None
        LOCAL_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        self.load_catalog()

    def _bq(self):
        if self.force_local or not PROJECT_ID:
            return None
        if self._bq_client is None:
            try:
                from google.cloud import bigquery

                self._bq_client = bigquery.Client(project=PROJECT_ID, location=BQ_LOCATION)
            except Exception as e:  # noqa: BLE001
                log.warning("BigQuery client unavailable (%s) -> local fallback", e)
                self._bq_client = False
        return self._bq_client or None

    def _gcs_bucket(self):
        if self.force_local or not PROJECT_ID or not FLYERS_BUCKET:
            return None
        if self._gcs_client is None:
            try:
                from google.cloud import storage

                self._gcs_client = storage.Client(project=PROJECT_ID).bucket(FLYERS_BUCKET)
            except Exception as e:  # noqa: BLE001
                log.warning("GCS client unavailable (%s) -> local fallback", e)
                self._gcs_client = False
        return self._gcs_client or None

    def load_catalog(self) -> None:
        ext_map: dict[str, dict] = {}
        ext_path = default_ext_file()
        if ext_path.exists():
            try:
                ext_map = json.loads(ext_path.read_text(encoding="utf-8"))
            except Exception as e:  # noqa: BLE001
                log.warning("Failed to read local ext cache: %s", e)

        bq = self._bq()
        if bq is not None and os.environ.get("CATALOG_SOURCE", "bq") == "bq":
            try:
                sql = f"""
                SELECT
                  p.id, p.type, p.title, p.brands, p.categories, p.description,
                  p.attributes, p.tags, p.priceInfo, p.rating, p.availability, p.images,
                  e.flyer_name, e.unit_label, e.price_per_100g, e.pack_type, e.origin_label
                FROM `{PROJECT_ID}.{BQ_DATASET}.products` p
                LEFT JOIN `{PROJECT_ID}.{BQ_DATASET}.flyer_product_ext` e
                  ON p.id = CAST(e.product_id AS STRING)
                WHERE IFNULL(p.type, 'PRIMARY') IN ('PRIMARY', '')
                """
                rows = bq.query(sql).result(timeout=25)
                loaded: dict[str, dict] = {}
                for r in rows:
                    d = dict(r.items())
                    ext = {
                        "flyer_name": d.get("flyer_name"),
                        "unit_label": d.get("unit_label"),
                        "price_per_100g": d.get("price_per_100g"),
                        "pack_type": d.get("pack_type"),
                        "origin_label": d.get("origin_label"),
                    }
                    n = normalize_product(d, ext)
                    n["_hay"] = " ".join(
                        [n["title"], n["flyer_name"], n["brand"], n["category_path"], n["origin"],
                         n["promo_text"], " ".join(n["dishes"]), " ".join(n["labels"])]
                    ).lower()
                    loaded[n["id"]] = n
                if loaded:
                    self.items = loaded
                    self.source = f"bigquery:{PROJECT_ID}.{BQ_DATASET}.products"
                    log.info("Loaded %d products from BigQuery (%s)", len(self.items), self.source)
                    return
            except Exception as e:  # noqa: BLE001
                log.warning("BigQuery catalog load failed (%s) -> loading local JSONL", e)

        # Fallback: local JSONL + ext_map
        path = default_data_file()
        loaded = {}
        if path.exists():
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    p = json.loads(line)
                    if p.get("type", "PRIMARY") not in ("PRIMARY", ""):
                        continue
                    pid = str(p.get("id") or "")
                    n = normalize_product(p, ext_map.get(pid))
                    n["_hay"] = " ".join(
                        [n["title"], n["flyer_name"], n["brand"], n["category_path"], n["origin"],
                         n["promo_text"], " ".join(n["dishes"]), " ".join(n["labels"])]
                    ).lower()
                    loaded[n["id"]] = n
        self.items = loaded
        self.source = f"local:{path.name}"
        log.info("Loaded %d products from local file (%s)", len(self.items), path)

    def get_product(self, product_id: str) -> dict | None:
        n = self.items.get(str(product_id))
        if not n:
            return None
        return {k: v for k, v in n.items() if not k.startswith("_")}

    def search_products(self, q: str = "", category: str = "", on_sale: bool = False,
                        seasonal: bool = False, limit: int = 36) -> list[dict]:
        q_terms = [t.lower() for t in (q or "").strip().split() if t.strip()]
        cat = (category or "").strip()
        scored: list[tuple[float, dict]] = []
        for n in self.items.values():
            if not n.get("image"):
                continue
            if on_sale and not n.get("on_sale"):
                continue
            if seasonal and not n.get("is_seasonal"):
                continue
            if cat and cat not in n.get("category", "") and cat not in n.get("category_path", ""):
                continue
            if q_terms and not all(t in n["_hay"] or t in n["id"].lower() for t in q_terms):
                continue
            score = (
                (2.0 if q_terms and all(t in n["flyer_name"].lower() for t in q_terms) else 0.0)
                + (1.0 if n.get("on_sale") else 0.0)
                + float(n.get("discount_rate") or 0.0)
                + (0.4 if n.get("is_seasonal") else 0.0)
                + float(n.get("rating") or 0.0) * 0.1
            )
            scored.append((score, n))
        scored.sort(key=lambda t: -t[0])
        out: list[dict] = []
        for _, n in scored[: max(1, min(int(limit or 36), 120))]:
            out.append({k: v for k, v in n.items() if not k.startswith("_")})
        return out

    def categories(self) -> list[dict]:
        counts: dict[str, int] = {}
        for n in self.items.values():
            c = n.get("category") or ""
            if c:
                counts[c] = counts.get(c, 0) + 1
        return [{"name": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]

    # ---- BigQuery audit logging for flyer_offers and flyers ----
    def record_offer_in_bq(self, offer_row: dict) -> None:
        bq = self._bq()
        if bq is None:
            return
        try:
            table = f"{PROJECT_ID}.{BQ_DATASET}.flyer_offers"
            errors = bq.insert_rows_json(table, [offer_row])
            if errors:
                log.warning("BQ flyer_offers insert warning: %s", errors)
        except Exception as e:  # noqa: BLE001
            log.warning("BQ flyer_offers insert skipped: %s", e)

    def record_flyer_index_in_bq(self, flyer_doc: dict, gcs_prefix: str = "") -> None:
        bq = self._bq()
        if bq is None:
            return
        try:
            table = f"{PROJECT_ID}.{BQ_DATASET}.flyers"
            period = flyer_doc.get("period") or {}
            row = {
                "flyer_id": flyer_doc["id"],
                "title": flyer_doc.get("title") or "",
                "theme": flyer_doc.get("theme") or "",
                "target": flyer_doc.get("target") or "",
                "template_id": flyer_doc.get("template_id") or "T1",
                "period_from": period.get("from") or "",
                "period_to": period.get("to") or "",
                "item_count": len(flyer_doc.get("slots") or []),
                "status": flyer_doc.get("status") or "下書き",
                "created_by": (flyer_doc.get("created_by") or {}).get("name") or "",
                "created_at": flyer_doc.get("created_at") or dt.datetime.now(dt.timezone.utc).isoformat(),
                "approved_by": (flyer_doc.get("approved_by") or {}).get("name") or "",
                "approved_at": flyer_doc.get("approved_at"),
                "gcs_prefix": gcs_prefix,
            }
            errors = bq.insert_rows_json(table, [row])
            if errors:
                log.warning("BQ flyers insert warning: %s", errors)
        except Exception as e:  # noqa: BLE001
            log.warning("BQ flyers insert skipped: %s", e)

    # ---- Object storage (GCS + local mirror) ----
    def write_json(self, rel_path: str, payload: dict) -> str:
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        return self.write_bytes(rel_path, raw, "application/json; charset=utf-8")

    def write_bytes(self, rel_path: str, data: bytes, content_type: str) -> str:
        local_p = LOCAL_STORAGE_DIR / rel_path
        local_p.parent.mkdir(parents=True, exist_ok=True)
        local_p.write_bytes(data)

        bucket = self._gcs_bucket()
        if bucket is not None:
            try:
                blob = bucket.blob(rel_path)
                blob.upload_from_string(data, content_type=content_type)
                return f"gs://{FLYERS_BUCKET}/{rel_path}"
            except Exception as e:  # noqa: BLE001
                log.warning("GCS upload failed for %s (%s) -> kept in local storage", rel_path, e)
        return str(local_p)

    def read_json(self, rel_path: str) -> dict | None:
        local_p = LOCAL_STORAGE_DIR / rel_path
        if local_p.exists():
            try:
                return json.loads(local_p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                pass
        bucket = self._gcs_bucket()
        if bucket is not None:
            try:
                blob = bucket.blob(rel_path)
                if blob.exists():
                    txt = blob.download_as_text(encoding="utf-8")
                    local_p.parent.mkdir(parents=True, exist_ok=True)
                    local_p.write_text(txt, encoding="utf-8")
                    return json.loads(txt)
            except Exception as e:  # noqa: BLE001
                log.warning("GCS read_json failed for %s: %s", rel_path, e)
        return None

    def read_bytes(self, rel_path: str) -> bytes | None:
        local_p = LOCAL_STORAGE_DIR / rel_path
        if local_p.exists():
            return local_p.read_bytes()
        bucket = self._gcs_bucket()
        if bucket is not None:
            try:
                blob = bucket.blob(rel_path)
                if blob.exists():
                    b = blob.download_as_bytes()
                    local_p.parent.mkdir(parents=True, exist_ok=True)
                    local_p.write_bytes(b)
                    return b
            except Exception as e:  # noqa: BLE001
                log.warning("GCS read_bytes failed for %s: %s", rel_path, e)
        return None

    def list_json_prefix(self, prefix: str) -> list[dict]:
        seen: dict[str, dict] = {}
        local_root = LOCAL_STORAGE_DIR / prefix
        if local_root.exists():
            for p in sorted(local_root.rglob("*.json")):
                rel = str(p.relative_to(LOCAL_STORAGE_DIR))
                try:
                    seen[rel] = json.loads(p.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    pass
        bucket = self._gcs_bucket()
        if bucket is not None:
            try:
                for blob in bucket.list_blobs(prefix=prefix):
                    if not blob.name.endswith(".json") or blob.name in seen:
                        continue
                    try:
                        txt = blob.download_as_text(encoding="utf-8")
                        seen[blob.name] = json.loads(txt)
                    except Exception:  # noqa: BLE001
                        pass
            except Exception as e:  # noqa: BLE001
                log.warning("GCS list_blobs failed for %s: %s", prefix, e)
        return list(seen.values())
