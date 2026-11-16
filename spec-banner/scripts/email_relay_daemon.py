"""Cloudtop Email Relay Daemon for `cymbal-spec-banner`.

Supports two modes:
1. Direct DB polling (`DATABASE_URL` set or default local SQLite) for `banner_mail_log` with `status == 'QUEUED'`.
2. Remote Cloud Run API polling (`RELAY_API_URL`)
   which fetches `/api/email/logs`, downloads the generated JPEG/PDF attachments from Cloud Run or GCS,
   sends the email via `/google/bin/releases/gemini-agents-gmail/gmail mutate send-with-attachment`,
   and marks the log as `RELAYED`.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request

from sqlalchemy import select

from edion_banner.models import BannerMailLog, make_engine, make_session_factory, now_utc

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("email_relay_daemon")

GMAIL_CLI = "/google/bin/releases/gemini-agents-gmail/gmail"
DEFAULT_CLOUD_RUN_URL = os.environ.get("SPEC_BANNER_URL", "")


def process_pending_emails(session_factory) -> int:
    sent_count = 0
    with session_factory() as session:
        queued = session.scalars(
            select(BannerMailLog).where(BannerMailLog.status == "QUEUED").order_by(BannerMailLog.id)
        ).all()
        for row in queued:
            meta = row.meta or {}
            local_dir = os.path.abspath(os.environ.get("LOCAL_STORAGE_DIR", "./data/banners"))
            files_to_attach: list[str] = []
            if row.attachment_format in ("jpeg", "both") and meta.get("jpg_filename"):
                jp = os.path.join(local_dir, meta["jpg_filename"])
                if os.path.exists(jp):
                    files_to_attach.append(jp)
            if row.attachment_format in ("pdf", "both") and meta.get("pdf_filename"):
                pp = os.path.join(local_dir, meta["pdf_filename"])
                if os.path.exists(pp):
                    files_to_attach.append(pp)

            if not os.path.exists(GMAIL_CLI):
                log.warning("Gmail CLI not found at %s; skipping relay for id=%s", GMAIL_CLI, row.id)
                continue

            cmd = [
                GMAIL_CLI,
                "mutate",
                "send-with-attachment",
                "--to",
                row.to_email,
                "--subject",
                row.subject,
                "--body",
                row.body,
            ]
            for fpath in files_to_attach:
                cmd.extend(["--file", fpath])

            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=45, check=False)
            if proc.returncode == 0:
                row.status = "RELAYED"
                row.delivery_method = "gmail_cli_relay"
                row.sent_at = now_utc()
                row.error_message = None
                sent_count += 1
                log.info("Relayed local DB email id=%s to %s", row.id, row.to_email)
            else:
                row.status = "FAILED"
                row.error_message = (proc.stderr or proc.stdout or "")[:300]
                log.error("Failed relaying email id=%s: %s", row.id, row.error_message)
        session.commit()
    return sent_count


def _download_attachment(base_url: str, rel_or_gcs_url: str, filename: str, tmp_dir: str) -> str | None:
    dest = os.path.join(tmp_dir, filename)
    try:
        if rel_or_gcs_url.startswith("gs://"):
            gcloud_bin = "gcloud"
            subprocess.run([gcloud_bin, "storage", "cp", rel_or_gcs_url, dest], check=True, capture_output=True, timeout=30)
            if os.path.exists(dest):
                return dest
        url = rel_or_gcs_url if rel_or_gcs_url.startswith("http") else f"{base_url.rstrip('/')}/{rel_or_gcs_url.lstrip('/')}"
        req = urllib.request.Request(url, headers={"User-Agent": "Cymbal-Relay-Daemon/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            with open(dest, "wb") as f:
                f.write(resp.read())
        return dest
    except Exception as e:
        log.warning("Could not download attachment %s: %s", rel_or_gcs_url, e)
        return None


def process_remote_api_emails(api_base_url: str, relayed_ids: set[int]) -> int:
    if not os.path.exists(GMAIL_CLI):
        return 0
    sent_count = 0
    try:
        req = urllib.request.Request(
            f"{api_base_url.rstrip('/')}/api/email/logs",
            headers={"User-Agent": "Cymbal-Relay-Daemon/1.0"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log.debug("Remote poll skipped: %s", e)
        return 0

    for item in data.get("items", []):
        log_id = item.get("id")
        if not log_id or log_id in relayed_ids:
            continue
        if item.get("status") != "QUEUED":
            continue

        meta = item.get("meta") or {}
        fmt = item.get("attachment_format") or "both"
        to_email = item.get("to_email") or "vmd-team@cymbal-retail.example.com"
        subject = item.get("subject") or "【Cymbal VMD】店舗展示用 機能表（POPバナー）送付のご案内"
        body = (
            item.get("body")
            or f"お疲れ様です。\nCymbal Retail VMD 機能表・POP自動生成スタジオより、型番 {item.get('search_model_no', '')} の機能表データを添付にてお送りいたします。"
        )

        with tempfile.TemporaryDirectory(prefix="cymbal_banner_relay_") as tmp_dir:
            files_to_attach: list[str] = []
            if fmt in ("jpeg", "both"):
                jpg_fname = meta.get("jpg_filename") or f"Cymbal_banner_{log_id}.jpg"
                jpg_src = item.get("jpeg_uri") or meta.get("jpg_download_url") or f"/api/files/banners/{jpg_fname}"
                p = _download_attachment(api_base_url, jpg_src, jpg_fname, tmp_dir)
                if p:
                    files_to_attach.append(p)
            if fmt in ("pdf", "both"):
                pdf_fname = meta.get("pdf_filename") or f"Cymbal_banner_{log_id}.pdf"
                pdf_src = item.get("pdf_uri") or meta.get("pdf_download_url") or f"/api/files/banners/{pdf_fname}"
                p = _download_attachment(api_base_url, pdf_src, pdf_fname, tmp_dir)
                if p:
                    files_to_attach.append(p)

            cmd = [
                GMAIL_CLI,
                "mutate",
                "send-with-attachment",
                "--to",
                to_email,
                "--subject",
                subject,
                "--body",
                body,
            ]
            for fpath in files_to_attach:
                cmd.extend(["--file", fpath])

            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=45, check=False)
            if proc.returncode == 0:
                relayed_ids.add(log_id)
                sent_count += 1
                log.info("Relayed Cloud Run email id=%s to %s (%d attachments)", log_id, to_email, len(files_to_attach))
                # Notify remote API if endpoint is available
                try:
                    ack_url = f"{api_base_url.rstrip('/')}/api/email/logs/{log_id}/relayed?status=RELAYED&delivery_method=gmail_cli_relay"
                    ack_req = urllib.request.Request(ack_url, method="POST")
                    urllib.request.urlopen(ack_req, timeout=10).close()
                except Exception:
                    pass
            else:
                log.error("Failed relaying Cloud Run email id=%s: %s", log_id, (proc.stderr or proc.stdout or "")[:200])

    return sent_count


def main() -> None:
    engine = make_engine()
    session_factory = make_session_factory(engine)
    api_url = os.environ.get("RELAY_API_URL", DEFAULT_CLOUD_RUN_URL)
    relayed_ids: set[int] = set()
    log.info("Starting Cymbal Retail VMD Banner Email Relay Daemon (Remote API: %s)...", api_url)
    while True:
        try:
            process_pending_emails(session_factory)
        except Exception as e:
            log.debug("Local DB poll error: %s", e)
        try:
            if api_url:
                process_remote_api_emails(api_url, relayed_ids)
        except Exception as e:
            log.error("Remote API relay error: %s", e)
        time.sleep(5)


if __name__ == "__main__":
    main()
