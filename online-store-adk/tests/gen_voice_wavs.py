#!/usr/bin/env python3
"""Generate the voice-ordering utterances as WAV files with Cloud TTS (for Chromium fake-media E2E).

  u1..u5.wav            single utterances (48 kHz mono s16, 0.6 s lead-in, 2.5 s trailing silence)
  handsfree.wav         u1 … u5 separated by GAP seconds of silence (hands-free continuous conversation run)

usage: python tests/gen_voice_wavs.py OUT_DIR [--gap 45] [--voice ja-JP-Chirp3-HD-Charon]
"""
from __future__ import annotations

import argparse
import base64
import os
import subprocess
import sys
from pathlib import Path

import google.auth
import google.auth.transport.requests
import httpx

UTTERANCES = ["今夜の夕食をお勧めして", "セットをカートに入れて", "レジに進みます", "明日の午後でお願いします", "注文を確定して"]
PROJECT = os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT") or ""


def synth(text: str, voice: str) -> bytes:
    creds, default_proj = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    proj = PROJECT or default_proj or ""
    headers = {"Authorization": "Bearer " + creds.token}
    if proj:
        headers["x-goog-user-project"] = proj
    r = httpx.post("https://texttospeech.googleapis.com/v1/text:synthesize", timeout=60,
                   headers=headers,
                   json={"input": {"text": text}, "voice": {"languageCode": "ja-JP", "name": voice},
                         "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": 48000}})
    r.raise_for_status()
    return base64.b64decode(r.json()["audioContent"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--gap", type=float, default=45)
    ap.add_argument("--voice", default="ja-JP-Chirp3-HD-Charon")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for i, t in enumerate(UTTERANCES, 1):
        raw = out / f"u{i}_raw.wav"
        raw.write_bytes(synth(t, a.voice))
        f = out / f"u{i}.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-af", "adelay=600:all=1,apad=pad_dur=2.5",
                        "-ar", "48000", "-ac", "1", "-sample_fmt", "s16", str(f)], check=True)
        raw.unlink()
        files.append(f)
        print(f, t)
    # hands-free sequence: 1.5 s lead + u1 + gap + u2 …
    inputs, filt = [], []
    for i, f in enumerate(files):
        inputs += ["-i", str(f)]
        pad = a.gap if i < len(files) - 1 else 5
        filt.append(f"[{i}:a]apad=pad_dur={pad}[a{i}]")
    filt.append("".join(f"[a{i}]" for i in range(len(files))) + f"concat=n={len(files)}:v=0:a=1,adelay=1500:all=1[out]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filt), "-map", "[out]",
                    "-ar", "48000", "-ac", "1", "-sample_fmt", "s16", str(out / "handsfree.wav")], check=True)
    print(out / "handsfree.wav")
    return 0


if __name__ == "__main__":
    sys.exit(main())
