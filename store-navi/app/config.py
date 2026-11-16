"""Store Navi 共通ランタイム設定モジュール。

APP_MODE      customer | staff            （配信する SPA と API ルートの切り替え）
DATA_MODE     local | bq                  local = DATA_DIR 内の JSON ファイル + LocalSearch / bq = BigQuery + Retail API
DATA_DIR      店舗データディレクトリ（既定: store-navi/data、不在時は tests/fixtures/data）
SN_STATE_DIR  ローカルモード時の追記状態ディレクトリ（棚登録・在庫イベント・アップロード写真）
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
SN_DIR = APP_DIR.parent                       # store-navi（コンテナ内では /srv）
REPO_DIR = SN_DIR.parent

APP_MODE = (os.environ.get("APP_MODE") or "customer").strip().lower()
if APP_MODE not in ("customer", "staff"):
    APP_MODE = "customer"


def data_mode() -> str:
    m = (os.environ.get("DATA_MODE") or "").strip().lower()
    if m in ("local", "bq"):
        return m
    return "bq" if os.environ.get("K_SERVICE") else "local"


def data_dir() -> Path:
    env = os.environ.get("DATA_DIR")
    if env:
        return Path(env)
    real = SN_DIR / "data"
    if (real / "stores.json").exists():
        return real
    return SN_DIR / "tests" / "fixtures" / "data"


def state_dir() -> Path:
    p = Path(os.environ.get("SN_STATE_DIR") or (Path(tempfile.gettempdir()) / "store_navi_state"))
    p.mkdir(parents=True, exist_ok=True)
    return p


STATIC_DIR = Path(os.environ.get("STATIC_DIR") or (SN_DIR / "static"))

PROJECT_ID = os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT") or ""
PROJECT_NUMBER = os.environ.get("PROJECT_NUMBER") or ""
BQ_DATASET = os.environ.get("BQ_DATASET", "cymbal")
PHOTO_BUCKET = (
    os.environ.get("STORE_NAVI_BUCKET")
    or os.environ.get("PHOTO_BUCKET")
    or (f"{PROJECT_ID}-store-navi" if PROJECT_ID else "cymbal-store-navi")
)
REFRESH_SEC = float(os.environ.get("STORE_DATA_REFRESH_SEC", "20"))
BRAND_NAME = (os.environ.get("BRAND_NAME") or "Cymbal Retail").strip() or "Cymbal Retail"

ONLINE_STORE_URL = (
    os.environ.get("ONLINE_STORE_URL")
    or os.environ.get("STORE_URL")
    or "https://cymbal-store.example.com"
).rstrip("/")
DEFAULT_CUSTOMER = "CR-0001"
DEFAULT_STORE = "S01"


def http_url(name: str) -> str:
    v = (os.environ.get(name) or "").strip()
    return v if v.startswith(("https://", "http://")) else ""


def product_images_dir() -> Path:
    env = os.environ.get("PRODUCT_IMAGES_DIR")
    if env:
        return Path(env)
    staged = SN_DIR / "product_images"
    if staged.exists():
        return staged
    return REPO_DIR / "online-store-adk" / "static" / "img" / "products"
