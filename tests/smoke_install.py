#!/usr/bin/env python3
"""Cymbal Retail デモ インストール後の総合スモークテスト (smoke_install.py)。

公開アクセス (匿名) と IAM 認証 (`--id-token` または 401/403 時の自動フォールバック) の両方に対応し、
4 つのユーザー向け Cloud Run アプリ + ADK エージェント連携・相互リンク URL を一括検証します。
外部パッケージ不要（Python 3 標準ライブラリのみで動作）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_DIR = REPO_ROOT / "install"
STATE_DIR = INSTALL_DIR / ".state"
SHRIMP_WORDS = ("えび", "エビ", "海老", "シュリンプ")
RUN_APP_URL_RE = re.compile(r"https?://[a-z0-9-]+(?:\.[a-z0-9-]+)*\.run\.app")


@dataclass
class CheckResult:
    service: str
    name: str
    passed: bool
    detail: str
    latency_ms: int


def _gcloud_env() -> dict[str, str]:
    env = dict(os.environ)
    sdk_bin = os.path.expanduser("~/google-cloud-sdk/bin")
    if os.path.isdir(sdk_bin) and sdk_bin not in env.get("PATH", ""):
        env["PATH"] = f"{sdk_bin}:{env.get('PATH', '')}"
    env.setdefault("CLOUDSDK_CORE_DISABLE_PROMPTS", "1")
    return env


def parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if "#" in v and not (v.startswith('"') or v.startswith("'")):
            v = v.split("#", 1)[0].strip()
        v = v.strip('"').strip("'")
        out[k.strip()] = v
    return out


def resolve_service_url(project: str, region: str, service_name: str, fallback_url: str) -> str:
    res = subprocess.run(
        [
            "gcloud",
            "run",
            "services",
            "describe",
            service_name,
            f"--project={project}",
            f"--region={region}",
            "--format=value(status.url)",
        ],
        capture_output=True,
        text=True,
        env=_gcloud_env(),
        check=False,
    )
    url = (res.stdout or "").strip()
    return url if url.startswith("https://") else fallback_url


def resolve_target_config(config_path: Path | None, cli_project: str, cli_region: str) -> dict[str, str]:
    cfg: dict[str, str] = {}
    if STATE_DIR.joinpath("models.env").is_file():
        cfg.update(parse_env_file(STATE_DIR / "models.env"))
    if config_path and config_path.is_file():
        cfg.update(parse_env_file(config_path))
    for k in (
        "PROJECT_ID",
        "PROJECT_NUMBER",
        "REGION",
        "SERVICE_PREFIX",
        "ONLINE_STORE_URL",
        "CUSTOMER_URL",
        "STAFF_URL",
        "ENRICH_URL",
        "ADK_AGENT_URL",
        "MCP_URL",
    ):
        if os.environ.get(k):
            cfg[k] = os.environ[k]

    if cli_project:
        cfg["PROJECT_ID"] = cli_project
    if cli_region:
        cfg["REGION"] = cli_region

    project = cfg.get("PROJECT_ID", "").strip()
    if not project:
        raise ValueError("PROJECT_ID が設定されていません。--project または --config install/config.env を指定してください。")
    region = cfg.get("REGION", "").strip() or "asia-northeast1"
    prefix = cfg.get("SERVICE_PREFIX", "").strip() or "cymbal"

    project_number = cfg.get("PROJECT_NUMBER", "").strip()
    if not project_number:
        res = subprocess.run(
            ["gcloud", "projects", "describe", project, "--format=value(projectNumber)"],
            capture_output=True,
            text=True,
            env=_gcloud_env(),
            check=True,
        )
        project_number = res.stdout.strip()

    suffix = f"{project_number}.{region}.run.app"
    services = {
        "ONLINE_STORE_SERVICE": cfg.get("ONLINE_STORE_SERVICE") or f"{prefix}-site-adk",
        "STORE_APP_SERVICE": cfg.get("STORE_APP_SERVICE") or f"{prefix}-store-app",
        "STORE_STAFF_SERVICE": cfg.get("STORE_STAFF_SERVICE") or f"{prefix}-store-staff",
        "ENRICH_SERVICE": cfg.get("ENRICH_SERVICE") or f"{prefix}-data-enrichment",
        "ADK_AGENT_SERVICE": cfg.get("ADK_AGENT_SERVICE") or f"{prefix}-adk-agent",
        "MCP_SERVICE": cfg.get("MCP_SERVICE") or f"{prefix}-commerce-mcp",
    }

    urls_state = parse_env_file(STATE_DIR / "urls.env")
    if urls_state.get("URLS_PROJECT_ID") == project and urls_state.get("URLS_REGION") == region:
        for uk in ("ONLINE_STORE_URL", "CUSTOMER_URL", "STAFF_URL", "ENRICH_URL", "ADK_AGENT_URL", "MCP_URL"):
            cfg.setdefault(uk, urls_state.get(uk, ""))

    online_url = resolve_service_url(
        project, region, services["ONLINE_STORE_SERVICE"], cfg.get("ONLINE_STORE_URL") or f"https://{services['ONLINE_STORE_SERVICE']}-{suffix}"
    )
    customer_url = resolve_service_url(
        project, region, services["STORE_APP_SERVICE"], cfg.get("CUSTOMER_URL") or f"https://{services['STORE_APP_SERVICE']}-{suffix}"
    )
    staff_url = resolve_service_url(
        project, region, services["STORE_STAFF_SERVICE"], cfg.get("STAFF_URL") or f"https://{services['STORE_STAFF_SERVICE']}-{suffix}"
    )
    enrich_url = resolve_service_url(
        project, region, services["ENRICH_SERVICE"], cfg.get("ENRICH_URL") or f"https://{services['ENRICH_SERVICE']}-{suffix}"
    )
    adk_url = resolve_service_url(
        project, region, services["ADK_AGENT_SERVICE"], cfg.get("ADK_AGENT_URL") or f"https://{services['ADK_AGENT_SERVICE']}-{suffix}"
    )
    mcp_url = resolve_service_url(
        project, region, services["MCP_SERVICE"], cfg.get("MCP_URL") or f"https://{services['MCP_SERVICE']}-{suffix}"
    )

    return {
        "PROJECT_ID": project,
        "PROJECT_NUMBER": project_number,
        "REGION": region,
        **services,
        "ONLINE_STORE_URL": online_url.rstrip("/"),
        "CUSTOMER_URL": customer_url.rstrip("/"),
        "STAFF_URL": staff_url.rstrip("/"),
        "ENRICH_URL": enrich_url.rstrip("/"),
        "ADK_AGENT_URL": adk_url.rstrip("/"),
        "MCP_URL": mcp_url.rstrip("/"),
    }


def get_identity_token() -> str:
    res = subprocess.run(
        ["gcloud", "auth", "print-identity-token"],
        capture_output=True,
        text=True,
        env=_gcloud_env(),
        check=False,
    )
    if res.returncode != 0 or not res.stdout.strip():
        raise RuntimeError("ID トークンを取得できませんでした (`gcloud auth print-identity-token` 失敗)。")
    return res.stdout.strip()


class HttpClient:
    """公開アクセスと ID トークン認証の自動切り替えに対応する HTTP クライアント。"""

    def __init__(self, force_id_token: bool = False, public_only: bool = False):
        self.force_id_token = force_id_token
        self.public_only = public_only
        self._token: str | None = get_identity_token() if force_id_token else None
        self.auth_modes: dict[str, str] = {}

    def _ensure_token(self) -> str:
        if not self._token:
            self._token = get_identity_token()
        return self._token

    def request(
        self,
        service_label: str,
        method: str,
        url: str,
        json_body: dict | None = None,
        timeout: float = 45.0,
        require_token: bool = False,
    ) -> tuple[int, str, int]:
        t0 = time.perf_counter()
        use_token = self.force_id_token or require_token or (self.auth_modes.get(service_label) == "id_token")

        for attempt in range(2):
            headers = {"Accept": "application/json, text/html, application/javascript, */*"}
            if json_body is not None:
                headers["Content-Type"] = "application/json"
            if use_token:
                headers["Authorization"] = f"Bearer {self._ensure_token()}"

            req = urllib.request.Request(
                url,
                method=method,
                data=json.dumps(json_body).encode("utf-8") if json_body is not None else None,
                headers=headers,
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                    self.auth_modes.setdefault(service_label, "id_token" if use_token else "public")
                    return resp.status, body, int((time.perf_counter() - t0) * 1000)
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code in (401, 403) and not use_token and not self.public_only and attempt == 0:
                    use_token = True
                    self.auth_modes[service_label] = "id_token"
                    continue
                return exc.code, body, int((time.perf_counter() - t0) * 1000)
            except Exception as exc:  # noqa: BLE001
                return 599, str(exc), int((time.perf_counter() - t0) * 1000)
        return 599, "リトライ上限超過", int((time.perf_counter() - t0) * 1000)

    def stream_sse(
        self,
        service_label: str,
        url: str,
        json_body: dict,
        timeout: float = 90.0,
    ) -> tuple[int, list[dict], int, str]:
        t0 = time.perf_counter()
        use_token = self.force_id_token or (self.auth_modes.get(service_label) == "id_token")
        for attempt in range(2):
            headers = {
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "Cookie": "cr_customer=CR-0001",
            }
            if use_token:
                headers["Authorization"] = f"Bearer {self._ensure_token()}"
            req = urllib.request.Request(url, method="POST", data=json.dumps(json_body).encode("utf-8"), headers=headers)
            try:
                events: list[dict] = []
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    for raw_line in resp:
                        line = raw_line.decode("utf-8", errors="replace").strip()
                        if line.startswith("data:"):
                            payload = line[5:].strip()
                            if payload:
                                try:
                                    ev = json.loads(payload)
                                    events.append(ev)
                                    if ev.get("type") in ("done", "error"):
                                        break
                                except json.JSONDecodeError:
                                    pass
                    self.auth_modes.setdefault(service_label, "id_token" if use_token else "public")
                    return resp.status, events, int((time.perf_counter() - t0) * 1000), ""
            except urllib.error.HTTPError as exc:
                err_txt = exc.read().decode("utf-8", errors="replace")[:300]
                if exc.code in (401, 403) and not use_token and not self.public_only and attempt == 0:
                    use_token = True
                    self.auth_modes[service_label] = "id_token"
                    continue
                return exc.code, [], int((time.perf_counter() - t0) * 1000), err_txt
            except Exception as exc:  # noqa: BLE001
                return 599, [], int((time.perf_counter() - t0) * 1000), str(exc)[:300]
        return 599, [], int((time.perf_counter() - t0) * 1000), "SSE リトライ失敗"


def parse_window_config(js_text: str, var_name: str) -> dict[str, Any]:
    m = re.search(rf"window\.{re.escape(var_name)}\s*=\s*(\{{.*\}})\s*;?\s*$", js_text.strip(), re.DOTALL)
    if not m:
        raise ValueError(f"window.{var_name} が見つかりません")
    return json.loads(m.group(1))


def has_foreign_run_url(text: str, allowed_urls: set[str], project_number: str) -> str | None:
    """レスポンス内の *.run.app URL に、対象プロジェクト以外の URL が混入していないか検証します。"""
    for m in RUN_APP_URL_RE.findall(text):
        u = m.rstrip("/")
        if u in allowed_urls or f"-{project_number}." in u:
            continue
        return u
    return None


def run_all_checks(cfg: dict[str, str], client: HttpClient, skip_agent: bool = False) -> list[CheckResult]:
    results: list[CheckResult] = []
    online_url = cfg["ONLINE_STORE_URL"]
    customer_url = cfg["CUSTOMER_URL"]
    staff_url = cfg["STAFF_URL"]
    enrich_url = cfg["ENRICH_URL"]
    allowed_urls = {
        online_url,
        customer_url,
        staff_url,
        enrich_url,
        cfg["ADK_AGENT_URL"],
        cfg["MCP_URL"],
    }
    proj_num = cfg["PROJECT_NUMBER"]

    # ==========================================================================
    # 1. ADK オンラインストア (online-store-adk)
    # ==========================================================================
    svc_os = "online-store-adk"

    st, body, ms = client.request(svc_os, "GET", f"{online_url}/api/health")
    ok = st == 200 and '"ok"' in body
    results.append(CheckResult(svc_os, "ヘルスチェック (/api/health)", ok, f"HTTP {st}", ms))

    st, body, ms = client.request(svc_os, "GET", f"{online_url}/api/features")
    try:
        feat = json.loads(body) if st == 200 else {}
        cat_size = int(feat.get("catalog_size") or 0)
        eng = feat.get("engine", "?")
        ok = st == 200 and cat_size >= 20000
        detail = f"catalog_size={cat_size:,}, engine={eng}, model={feat.get('gemini_model', '?')}"
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, f"HTTP {st} ({exc})"
    results.append(CheckResult(svc_os, "カタログ件数・検索エンジン確認 (/api/features)", ok, detail, ms))

    st, body, ms = client.request(svc_os, "GET", f"{online_url}/config.js")
    try:
        wcfg = parse_window_config(body, "CR_CONFIG") if st == 200 else {}
        bad = has_foreign_run_url(body, allowed_urls, proj_num)
        got_enrich = str(wcfg.get("enrichUrl") or "").rstrip("/")
        ok = (
            st == 200
            and bad is None
            and wcfg.get("agentBackend") == "adk"
            and wcfg.get("agentMode") == "live"
            and got_enrich == enrich_url
        )
        detail = f"agentBackend={wcfg.get('agentBackend')}, enrichUrl={got_enrich or '未設定'}"
        if bad:
            detail += f" [別プロジェクトURL混入: {bad}]"
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, f"HTTP {st} ({exc})"
    results.append(CheckResult(svc_os, "設定・相互リンク確認 (/config.js)", ok, detail, ms))

    q_enc = urllib.parse.quote("お弁当")
    st, body, ms = client.request(svc_os, "GET", f"{online_url}/api/search?q={q_enc}&page_size=8")
    try:
        sr = json.loads(body) if st == 200 else {}
        hits = sr.get("results") or []
        ok = st == 200 and "error" not in sr
        detail = f"検索ヒット={len(hits)} 件 (total={sr.get('total', 0)})"
        if st == 200 and len(hits) == 0:
            detail += " ※初回インポート直後のインデックス反映待ちの可能性あり"
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, f"HTTP {st} ({exc})"
    results.append(CheckResult(svc_os, "商品検索 API (/api/search?q=お弁当)", ok, detail, ms))

    st, body, ms = client.request(svc_os, "GET", f"{online_url}/api/recommendations?type=for_you&limit=8")
    try:
        rec = json.loads(body) if st == 200 else {}
        items = rec.get("items") if isinstance(rec, dict) else (rec if isinstance(rec, list) else [])
        items = items or (rec.get("products") if isinstance(rec, dict) else []) or []
        ok = st == 200 and len(items) > 0
        detail = f"おすすめ件数={len(items)} 件"
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, f"HTTP {st} ({exc})"
    results.append(CheckResult(svc_os, "パーソナライズ推薦 (/api/recommendations)", ok, detail, ms))

    if not skip_agent:
        st, events, ms, err_msg = client.stream_sse(
            svc_os,
            f"{online_url}/api/agent/stream",
            {"message": "今夜の夕食をお勧めしてね", "session_id": f"smoke-{int(time.time())}"},
        )
        err_ev = next((e for e in events if e.get("type") == "error"), None)
        done_ev = next((e for e in events if e.get("type") == "done"), None)
        actions = [e.get("name") for e in events if e.get("type") == "action"]
        text_out = "".join(str(e.get("text") or "") for e in events if e.get("type") == "text")
        ok = st == 200 and err_ev is None and (done_ev is not None or bool(actions) or bool(text_out))
        if err_ev:
            detail = f"SSE エラーイベント: {err_ev}"
        elif st != 200:
            detail = f"HTTP {st}: {err_msg}"
        else:
            detail = f"actions={actions}, 応答文字数={len(text_out)}"
        results.append(CheckResult(svc_os, "ADK AIコンシェルジュ 夕食提案 SSE (/api/agent/stream)", ok, detail, ms))

    # ==========================================================================
    # 2. 店舗ナビ お客様向けアプリ (cymbal-store-app)
    # ==========================================================================
    svc_ca = "store-navi (customer)"

    st, body, ms = client.request(svc_ca, "GET", f"{customer_url}/api/health")
    try:
        h = json.loads(body) if st == 200 else {}
        ok = st == 200 and h.get("ok") is True and h.get("app_mode") == "customer" and int(h.get("catalog") or 0) >= 20000
        detail = f"app_mode={h.get('app_mode')}, data_mode={h.get('data_mode')}, catalog={h.get('catalog')}"
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, f"HTTP {st} ({exc})"
    results.append(CheckResult(svc_ca, "ヘルスチェック (/api/health)", ok, detail, ms))

    st, body, ms = client.request(svc_ca, "GET", f"{customer_url}/config.js")
    try:
        scfg = parse_window_config(body, "SN_CONFIG") if st == 200 else {}
        bad = has_foreign_run_url(body, allowed_urls, proj_num)
        got_os = str(scfg.get("onlineStoreUrl") or "").rstrip("/")
        got_st = str(scfg.get("staffUrl") or "").rstrip("/")
        ok = st == 200 and bad is None and scfg.get("appMode") == "customer" and got_os == online_url and got_st == staff_url
        detail = f"onlineStoreUrl={got_os}, staffUrl={got_st}"
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, f"HTTP {st} ({exc})"
    results.append(CheckResult(svc_ca, "設定・相互リンク確認 (/config.js)", ok, detail, ms))

    st, body, ms = client.request(svc_ca, "GET", f"{customer_url}/api/stores")
    first_store = "S01"
    try:
        st_data = json.loads(body) if st == 200 else []
        stores_list = st_data.get("stores", st_data) if isinstance(st_data, dict) else st_data
        if stores_list and isinstance(stores_list[0], dict):
            first_store = stores_list[0].get("store_id", "S01")
        ok = st == 200 and len(stores_list) >= 1
        detail = f"店舗数={len(stores_list)} (先頭: {first_store})"
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, f"HTTP {st} ({exc})"
    results.append(CheckResult(svc_ca, "店舗一覧取得 (/api/stores)", ok, detail, ms))

    q_curry = urllib.parse.quote("カレー")
    st, body, ms = client.request(svc_ca, "GET", f"{customer_url}/api/search?q={q_curry}&store_id={first_store}&in_store_only=1")
    route_pid = ""
    try:
        inv_sr = json.loads(body) if st == 200 else {}
        inv_rows = inv_sr.get("results") or []
        if inv_rows:
            route_pid = inv_rows[0].get("id", "")
        ok = st == 200 and "error" not in inv_sr
        detail = f"店内在庫ヒット={len(inv_rows)} 件 (store={first_store})"
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, f"HTTP {st} ({exc})"
    results.append(CheckResult(svc_ca, "店内在庫検索 (/api/search?in_store_only=1)", ok, detail, ms))

    st, body, ms = client.request(
        svc_ca,
        "POST",
        f"{customer_url}/api/route",
        json_body={"store_id": first_store, "product_ids": [route_pid] if route_pid else []},
    )
    ok = st == 200
    results.append(CheckResult(svc_ca, "店内ルート案内計算 (/api/route)", ok, f"HTTP {st}", ms))

    # ==========================================================================
    # 3. 店舗ナビ スタッフ向けアプリ (cymbal-store-staff)
    # ==========================================================================
    svc_st = "store-navi (staff)"

    st, body, ms = client.request(svc_st, "GET", f"{staff_url}/api/health")
    try:
        sh = json.loads(body) if st == 200 else {}
        ok = st == 200 and sh.get("ok") is True and sh.get("app_mode") == "staff" and sh.get("staff_router") is True
        detail = f"app_mode={sh.get('app_mode')}, staff_router={sh.get('staff_router')}"
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, f"HTTP {st} ({exc})"
    results.append(CheckResult(svc_st, "ヘルスチェック (/api/health)", ok, detail, ms))

    st, body, ms = client.request(svc_st, "GET", f"{staff_url}/config.js")
    try:
        stcfg = parse_window_config(body, "SN_CONFIG") if st == 200 else {}
        bad = has_foreign_run_url(body, allowed_urls, proj_num)
        got_os = str(stcfg.get("onlineStoreUrl") or "").rstrip("/")
        got_cu = str(stcfg.get("customerUrl") or "").rstrip("/")
        ok = st == 200 and bad is None and stcfg.get("appMode") == "staff" and got_os == online_url and got_cu == customer_url
        detail = f"onlineStoreUrl={got_os}, customerUrl={got_cu}"
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, f"HTTP {st} ({exc})"
    results.append(CheckResult(svc_st, "設定・相互リンク確認 (/config.js)", ok, detail, ms))

    st, body, ms = client.request(svc_st, "GET", f"{staff_url}/api/staff/demo-photos")
    try:
        dp = json.loads(body) if st == 200 else {}
        photos = dp.get("photos") or []
        ok = st == 200 and len(photos) > 0
        detail = f"デモ棚写真={len(photos)} 枚"
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, f"HTTP {st} ({exc})"
    results.append(CheckResult(svc_st, "スタッフ棚写真一覧 (/api/staff/demo-photos)", ok, detail, ms))

    q_milk = urllib.parse.quote("牛乳")
    st, body, ms = client.request(svc_st, "GET", f"{staff_url}/api/staff/stock-search?q={q_milk}")
    try:
        ss = json.loads(body) if st == 200 else {}
        srows = ss.get("results") or []
        ok = st == 200 and len(srows) > 0
        detail = f"横断在庫検索ヒット={len(srows)} 件"
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, f"HTTP {st} ({exc})"
    results.append(CheckResult(svc_st, "横断在庫検索 (/api/staff/stock-search)", ok, detail, ms))

    st, body, ms = client.request(svc_st, "GET", f"{staff_url}/api/staff/registrations?store_id={first_store}")
    try:
        rg = json.loads(body) if st == 200 else {}
        ok = st == 200 and "registrations" in rg
        detail = f"登録済み棚位置={len(rg.get('registrations') or [])} 件"
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, f"HTTP {st} ({exc})"
    results.append(CheckResult(svc_st, "棚位置登録一覧 (/api/staff/registrations)", ok, detail, ms))

    # ==========================================================================
    # 4. 商品情報エンリッチメント スタジオ (cymbal-data-enrichment)
    # ==========================================================================
    svc_en = "data-enrichment"

    st, body, ms = client.request(svc_en, "GET", f"{enrich_url}/api/health")
    try:
        eh = json.loads(body) if st == 200 else {}
        prods = int(eh.get("products") or 0)
        ok = st == 200 and eh.get("status") == "ok" and prods > 0
        detail = f"products={prods}, enriched={eh.get('enriched')}, gmc={eh.get('gmc')}"
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, f"HTTP {st} ({exc})"
    results.append(CheckResult(svc_en, "ヘルスチェック (/api/health)", ok, detail, ms))

    st, body, ms = client.request(svc_en, "GET", f"{enrich_url}/")
    bad = has_foreign_run_url(body, allowed_urls, proj_num) if st == 200 else None
    ok = st == 200 and (online_url in body) and bad is None
    detail = f"STORE_URL 埋め込み確認={'OK' if online_url in body else 'NG'}"
    if bad:
        detail += f" [別プロジェクトURL混入: {bad}]"
    results.append(CheckResult(svc_en, "トップ HTML・相互リンク確認 (/)", ok, detail, ms))

    st, body, ms = client.request(svc_en, "GET", f"{enrich_url}/api/dashboard")
    try:
        db = json.loads(body) if st == 200 else {}
        skus = int((db.get("totals") or {}).get("skus") or 0)
        fr = db.get("fill_rate") or {}
        ok = st == 200 and skus > 0
        detail = f"対象SKU={skus}, 充足率 {fr.get('before')} -> {fr.get('after')}"
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, f"HTTP {st} ({exc})"
    results.append(CheckResult(svc_en, "ダッシュボード集計 (/api/dashboard)", ok, detail, ms))

    st, body, ms = client.request(svc_en, "GET", f"{enrich_url}/api/models")
    try:
        md = json.loads(body) if st == 200 else {}
        mlist = md.get("models") or []
        ok = st == 200 and len(mlist) > 0
        detail = f"候補モデル数={len(mlist)}, default={md.get('default')}"
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, f"HTTP {st} ({exc})"
    results.append(CheckResult(svc_en, "モデルレジストリ (/api/models)", ok, detail, ms))

    st, body, ms = client.request(svc_en, "GET", f"{enrich_url}/api/cost/models")
    try:
        cm = json.loads(body) if st == 200 else {}
        ok = st == 200 and "models" in cm
        detail = f"見積対象モデル数={len(cm.get('models') or [])}"
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, f"HTTP {st} ({exc})"
    results.append(CheckResult(svc_en, "コスト試算 API (/api/cost/models)", ok, detail, ms))

    return results


def print_summary(cfg: dict[str, str], results: list[CheckResult], client: HttpClient) -> None:
    passed_cnt = sum(1 for r in results if r.passed)
    failed_cnt = len(results) - passed_cnt

    print("\n" + "=" * 96)
    print(f"Cymbal Retail スモークテスト結果サマリー — プロジェクト: {cfg['PROJECT_ID']} ({cfg['REGION']})")
    print("=" * 96)
    print(f"{'状態':<6} | {'サービス':<22} | {'検証項目':<38} | {'所要時間':>8} | 詳細")
    print("-" * 96)
    for r in results:
        mark = "PASS" if r.passed else "FAIL"
        print(f"{mark:<6} | {r.service:<22} | {r.name:<38} | {r.latency_ms:>6}ms | {r.detail}")
    print("-" * 96)

    auth_summary = ", ".join(
        f"{svc}: {'IAM認証(IDトークン)' if mode == 'id_token' else '公開(匿名)'}"
        for svc, mode in client.auth_modes.items()
    )
    print(f"認証モード: {auth_summary or '未実行'}")
    print(f"合計: {len(results)} 項目中 {passed_cnt} 件成功 / {failed_cnt} 件失敗")

    print("\n■ デプロイ済みサービス URL 一覧:")
    print(f"  1. ADK オンラインストア           : {cfg['ONLINE_STORE_URL']}")
    print(f"  2. 店舗ナビ（お客様向けアプリ）   : {cfg['CUSTOMER_URL']}")
    print(f"  3. 店舗ナビ（スタッフ向けアプリ） : {cfg['STAFF_URL']}")
    print(f"  4. 商品情報エンリッチメント       : {cfg['ENRICH_URL']}")
    print(f"  5. ADK AIコンシェルジュ (内部)    : {cfg['ADK_AGENT_URL']}")
    print(f"  6. Commerce MCP サーバー (内部)   : {cfg['MCP_URL']}")
    print("=" * 96)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cymbal Retail デモ環境のインストール後スモークテストを実行します。")
    parser.add_argument("--config", default=str(INSTALL_DIR / "config.env"), help="設定ファイルパス (既定: install/config.env)")
    parser.add_argument("--project", default="", help="Google Cloud プロジェクト ID（config.env より優先）")
    parser.add_argument("--region", default="", help="リージョン（config.env より優先）")
    parser.add_argument("--id-token", action="store_true", help="全リクエストで gcloud ID トークン認証を強制使用")
    parser.add_argument("--public-only", action="store_true", help="匿名アクセスのみ検証（401/403 時の ID トークン自動切替を無効化）")
    parser.add_argument("--skip-agent", action="store_true", help="ADK エージェントの SSE 対話テストをスキップ")
    parser.add_argument("--json", default="", help="テスト結果 JSON の出力先パス")
    args = parser.parse_args(argv)

    cfg_path = Path(args.config) if args.config else None
    try:
        cfg = resolve_target_config(cfg_path, args.project, args.region)
    except Exception as exc:  # noqa: BLE001
        print(f"エラー: 設定の解決に失敗しました: {exc}", file=sys.stderr)
        return 1

    client = HttpClient(force_id_token=args.id_token, public_only=args.public_only)
    results = run_all_checks(cfg, client, skip_agent=args.skip_agent)
    print_summary(cfg, results, client)

    if args.json:
        out = {
            "project_id": cfg["PROJECT_ID"],
            "region": cfg["REGION"],
            "urls": {k: cfg[k] for k in ("ONLINE_STORE_URL", "CUSTOMER_URL", "STAFF_URL", "ENRICH_URL", "ADK_AGENT_URL", "MCP_URL")},
            "auth_modes": client.auth_modes,
            "passed": all(r.passed for r in results),
            "results": [r.__dict__ for r in results],
        }
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
