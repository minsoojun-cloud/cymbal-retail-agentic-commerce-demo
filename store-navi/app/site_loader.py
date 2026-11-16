"""オンラインストアの検索・カタログモジュール (online-store-adk/app/{catalog,search,ai}.py) を `site_lib` として読み込む。

- コンテナ / デプロイ時: deploy.sh が `<srv>/site_lib/` にコピーしたパッケージを通常 import する。
- ローカル開発時: `../online-store-adk/app` を指す仮想パッケージ `site_lib` を動的に構成する。
"""
from __future__ import annotations

import importlib
import sys
import types

from .config import REPO_DIR, SN_DIR


def ensure_site_lib() -> types.ModuleType:
    mod = sys.modules.get("site_lib")
    if mod is not None:
        return mod
    staged = SN_DIR / "site_lib"
    if (staged / "search.py").exists():
        if str(SN_DIR) not in sys.path:
            sys.path.insert(0, str(SN_DIR))
        return importlib.import_module("site_lib")
    src = REPO_DIR / "online-store-adk" / "app"
    if not (src / "search.py").exists():
        raise ImportError(f"site_lib not found (neither {staged} nor {src})")
    mod = types.ModuleType("site_lib")
    mod.__path__ = [str(src)]  # type: ignore[attr-defined]
    mod.__file__ = str(src / "__init__.py")
    mod.__package__ = "site_lib"
    sys.modules["site_lib"] = mod
    return mod


def catalog_module():
    ensure_site_lib()
    return importlib.import_module("site_lib.catalog")


def search_module():
    ensure_site_lib()
    return importlib.import_module("site_lib.search")
