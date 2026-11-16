#!/usr/bin/env python3
"""対象 Google Cloud プロジェクトで利用可能な最新 Gemini モデルを自動検出するスクリプト。

Vertex AI (既定ロケーション: global) に対して最新順で軽量な generateContent リクエストを送信し、
テキスト生成・ツール呼び出し (Function Calling)・画像生成モデルの利用可否を検証します。
検出結果は install/.state/models.env に書き出されます（標準ライブラリのみで動作）。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

# 最新モデル優先の候補リスト（PACKAGE_CONTRACT 準拠）
FAST_TEXT_CANDIDATES: list[str] = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
]

ENRICH_TEXT_CANDIDATES: list[str] = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
]

IMAGE_CANDIDATES: list[str] = [
    "gemini-3.1-flash-image",
    "gemini-3-pro-image",
    "gemini-2.5-flash-image",
]

TransportFn = Callable[[str, str, str, dict], tuple[int, dict]]


def get_access_token() -> str:
    """gcloud CLI から現在のアクセストークンを取得します。"""
    env = dict(os.environ)
    sdk_bin = os.path.expanduser("~/google-cloud-sdk/bin")
    if os.path.isdir(sdk_bin) and sdk_bin not in env.get("PATH", ""):
        env["PATH"] = f"{sdk_bin}:{env.get('PATH', '')}"
    res = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if res.returncode != 0 or not res.stdout.strip():
        raise RuntimeError(
            "gcloud からアクセストークンを取得できませんでした。`gcloud auth login` を実行してください。"
        )
    return res.stdout.strip()


def make_rest_transport(token: str, timeout: float = 35.0) -> TransportFn:
    """Vertex AI REST API (v1beta1) へ generateContent を送信するトランスポート関数を返します。"""

    def _call(project: str, location: str, model: str, body: dict) -> tuple[int, dict]:
        host = (
            "https://aiplatform.googleapis.com"
            if location == "global"
            else f"https://{location}-aiplatform.googleapis.com"
        )
        url = (
            f"{host}/v1beta1/projects/{project}/locations/{location}"
            f"/publishers/google/models/{model}:generateContent"
        )
        req = urllib.request.Request(
            url,
            method="POST",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Goog-User-Project": project,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8") or "{}"
                return resp.status, json.loads(raw)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                return exc.code, json.loads(raw)
            except json.JSONDecodeError:
                return exc.code, {"error": {"message": raw[:400]}}
        except Exception as exc:  # noqa: BLE001
            return 599, {"error": {"message": str(exc)[:400]}}

    return _call


def _error_msg(payload: dict) -> str:
    err = payload.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err)
    return str(err or "")


def probe_text_model(
    project: str,
    location: str,
    model: str,
    transport: TransportFn,
) -> tuple[bool, str]:
    """テキスト生成モデルの疎通を確認します（429 は一時的な混雑のため利用可能として扱います）。"""
    body = {
        "contents": [{"role": "user", "parts": [{"text": "ping"}]}],
        "generationConfig": {"maxOutputTokens": 8, "temperature": 0},
    }
    for attempt in range(2):
        status, data = transport(project, location, model, body)
        if status == 200:
            return True, "応答確認 (HTTP 200)"
        msg = _error_msg(data)
        if status == 429 or "RESOURCE_EXHAUSTED" in msg:
            if attempt == 0:
                time.sleep(1.5)
                continue
            return True, "利用可能（現在クォータ混雑中: 429）"
        return False, f"HTTP {status}: {msg[:120]}"
    return False, "疎通失敗"


def probe_tool_calling(
    project: str,
    location: str,
    model: str,
    transport: TransportFn,
) -> tuple[bool, str]:
    """ADK エージェント用に Function Calling（ツール呼び出し）が正常動作するか検証します。"""
    base_body = {
        "contents": [{"role": "user", "parts": [{"text": "ping_tool を x=1 で呼び出してください。"}]}],
        "tools": [
            {
                "functionDeclarations": [
                    {
                        "name": "ping_tool",
                        "description": "疎通確認用ツール",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {"x": {"type": "INTEGER"}},
                            "required": ["x"],
                        },
                    }
                ]
            }
        ],
        "toolConfig": {"functionCallingConfig": {"mode": "ANY"}},
    }
    # Gemini 3.x 系は thinkingBudget=0 で高速確認、非対応モデルは通常設定にフォールバック
    configs = [
        {"maxOutputTokens": 64, "temperature": 0, "thinkingConfig": {"thinkingBudget": 0}},
        {"maxOutputTokens": 256, "temperature": 0},
    ]
    for cfg_idx, gen_cfg in enumerate(configs):
        body = {**base_body, "generationConfig": gen_cfg}
        status, data = transport(project, location, model, body)
        msg = _error_msg(data)
        if status == 400 and cfg_idx == 0 and "thinking" in msg.lower():
            continue
        if status == 429 or "RESOURCE_EXHAUSTED" in msg:
            return True, "ツール呼び出し対応（現在クォータ混雑中: 429）"
        if status != 200:
            return False, f"ツール呼び出し失敗 HTTP {status}: {msg[:120]}"
        candidates = data.get("candidates") or []
        parts = ((candidates[0].get("content") or {}).get("parts") or []) if candidates else []
        if any("functionCall" in p for p in parts):
            return True, "ツール呼び出し確認済み (functionCall)"
        # 200 だが thinking で出力トークンを使い切った場合は次の設定で再試行
    return False, "functionCall パートが返却されませんでした"


def resolve_models(
    project: str,
    location: str = "global",
    transport: TransportFn | None = None,
    verbose: bool = True,
) -> dict[str, str]:
    """全候補モデルを最新順で検証し、用途別の最適モデル辞書を返します。"""
    if transport is None:
        transport = make_rest_transport(get_access_token())

    text_cache: dict[str, tuple[bool, str]] = {}

    def check_text(m: str) -> tuple[bool, str]:
        if m not in text_cache:
            text_cache[m] = probe_text_model(project, location, m, transport)
        return text_cache[m]

    if verbose:
        print(f"[モデル検出] プロジェクト '{project}' (location={location}) で利用可能な最新 Gemini モデルを確認しています...")

    # 1. 高速テキストモデル (GEMINI_MODEL)
    gemini_model = ""
    for cand in FAST_TEXT_CANDIDATES:
        ok, detail = check_text(cand)
        if verbose:
            mark = "✓" if ok else "×"
            print(f"  [{mark}] テキスト候補 {cand:<26} -> {detail}")
        if ok:
            gemini_model = cand
            break

    if not gemini_model:
        raise RuntimeError(
            f"プロジェクト '{project}' で利用可能な Gemini テキストモデルが見つかりませんでした。"
            " Vertex AI API (aiplatform.googleapis.com) の有効化状態と権限を確認してください。"
        )

    # 2. エージェント用モデル (AGENT_MODEL: テキスト疎通 + ツール呼び出し確認)
    agent_model = ""
    for cand in FAST_TEXT_CANDIDATES:
        ok, _ = check_text(cand)
        if not ok:
            continue
        tok_ok, detail = probe_tool_calling(project, location, cand, transport)
        if verbose:
            mark = "✓" if tok_ok else "×"
            print(f"  [{mark}] エージェント候補 {cand:<22} -> {detail}")
        if tok_ok:
            agent_model = cand
            break
    if not agent_model:
        if verbose:
            print(f"  [!] ツール呼び出し検証で確定できなかったため、AGENT_MODEL に {gemini_model} を使用します。")
        agent_model = gemini_model

    # 3. エンリッチメント用モデル (ENRICH_GEMINI_MODEL: Gemini 3.x 優先)
    enrich_model = ""
    for cand in ENRICH_TEXT_CANDIDATES:
        ok, _ = check_text(cand)
        if ok:
            enrich_model = cand
            break
    if not enrich_model:
        if verbose:
            print(f"  [!] Gemini 3.x 系候補が利用できないため、ENRICH_GEMINI_MODEL に {gemini_model} を使用します。")
        enrich_model = gemini_model

    # 4. 画像生成モデル (IMAGE_MODEL)
    image_model = ""
    for cand in IMAGE_CANDIDATES:
        ok, detail = probe_text_model(project, location, cand, transport)
        if verbose:
            mark = "✓" if ok else "×"
            print(f"  [{mark}] 画像生成候補 {cand:<26} -> {detail}")
        if ok:
            image_model = cand
            break
    if not image_model:
        image_model = IMAGE_CANDIDATES[-1]
        if verbose:
            print(f"  [!] 画像生成モデルが未応答のため既定値 {image_model} を設定します。")

    return {
        "GEMINI_MODEL": gemini_model,
        "AGENT_MODEL": agent_model,
        "ENRICH_GEMINI_MODEL": enrich_model,
        "IMAGE_MODEL": image_model,
    }


def write_models_env(path: Path, models: dict[str, str], project: str, location: str) -> None:
    """解決されたモデル設定を env ファイル形式で保存します。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# probe_models.py により自動検出された最新 Gemini モデル (project={project}, location={location})",
        f'GEMINI_MODEL="{models["GEMINI_MODEL"]}"',
        f'AGENT_MODEL="{models["AGENT_MODEL"]}"',
        f'ENRICH_GEMINI_MODEL="{models["ENRICH_GEMINI_MODEL"]}"',
        f'IMAGE_MODEL="{models["IMAGE_MODEL"]}"',
    ]
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="対象プロジェクトで利用可能な最新の Gemini モデルを検出し models.env に出力します。"
    )
    parser.add_argument("--project", default=os.environ.get("PROJECT_ID", ""), help="Google Cloud プロジェクト ID")
    parser.add_argument("--location", default=os.environ.get("GEMINI_LOCATION", "global"), help="Vertex AI ロケーション")
    parser.add_argument(
        "--out",
        default="",
        help="出力先 env ファイルパス（省略時は install/.state/models.env、--no-write 指定時は出力しない）",
    )
    parser.add_argument("--no-write", action="store_true", help="ファイル書き出しを行わず標準出力のみ表示（読み取り専用確認用）")
    parser.add_argument("--json", action="store_true", help="結果を JSON 形式で標準出力に表示")
    args = parser.parse_args(argv)

    if not args.project:
        print("エラー: --project または環境変数 PROJECT_ID を指定してください。", file=sys.stderr)
        return 1

    try:
        models = resolve_models(args.project, args.location, verbose=not args.json)
    except Exception as exc:  # noqa: BLE001
        print(f"エラー: モデル自動検出に失敗しました: {exc}", file=sys.stderr)
        return 1

    if not args.no_write:
        default_out = Path(__file__).resolve().parent.parent / ".state" / "models.env"
        out_path = Path(args.out) if args.out else default_out
        write_models_env(out_path, models, args.project, args.location)
        if not args.json:
            print(f"[完了] 検出結果を保存しました: {out_path}")

    if args.json:
        print(json.dumps(models, ensure_ascii=False, indent=2))
    else:
        print("  選択されたモデル:")
        for k, v in models.items():
            print(f"    {k:<22} = {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
