# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "faster-whisper"]
# ///
"""Word-level transcript of a video (cached).

Writes <work>/transcripts/<stem>.json in ElevenLabs Scribe's shape: {language_code,
words: [{text, start, end, type: word|spacing|audio_event, speaker_id}]}. Never
re-transcribes a source that already has a transcript, unless --force.

Engines:
  auto        ElevenLabs Scribe if a valid key is saved, else local   (default)
  elevenlabs  Scribe: verbatim (keeps "eh"/"um" so they can be cut), speakers, best timings. ~$0.40/hour.
  local       faster-whisper on this machine, free. Model downloads once (large-v3-turbo ~1.6 GB).
              Whisper tends to smooth over fillers; pauses around them are still cut.

Usage:
    uv run transcribe.py <video> --work <project>/work [--language es] [--engine auto] [--speakers 2]

ElevenLabs key lookup: env ELEVENLABS_API_KEY, ~/.config/vibe-edit/keys.env, ~/Claude/tools/video-use/.env.
Real keys start with "sk_".
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCRIBE_URL = "https://api.elevenlabs.io/v1/speech-to-text"
KEY_FILES = [
    Path.home() / ".config" / "vibe-edit" / "keys.env",
    Path.home() / "Claude" / "tools" / "video-use" / ".env",
]
# Priming whisper with hesitations makes it far more likely to transcribe them verbatim.
FILLER_PROMPT = {"es": "Eh, bueno, este... mmm, o sea, eh, ¿sabes?", "en": "Umm, so, uh... like, hmm, you know?"}


def elevenlabs_key() -> str | None:
    if os.environ.get("ELEVENLABS_API_KEY", "").startswith("sk_"):
        return os.environ["ELEVENLABS_API_KEY"]
    for f in KEY_FILES:
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("ELEVENLABS_API_KEY="):
                    v = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if v.startswith("sk_"):
                        return v
    return None


def scribe(wav: Path, key: str, language: str | None, speakers: int | None) -> dict:
    import requests
    data = {"model_id": "scribe_v1", "diarize": "true", "tag_audio_events": "true",
            "timestamps_granularity": "word"}
    if language:
        data["language_code"] = language
    if speakers:
        data["num_speakers"] = str(speakers)
    with open(wav, "rb") as fh:
        r = requests.post(SCRIBE_URL, headers={"xi-api-key": key},
                          files={"file": ("audio.wav", fh, "audio/wav")}, data=data, timeout=1800)
    if r.status_code != 200:
        sys.exit(f"Scribe error {r.status_code}: {r.text[:400]}")
    out = r.json()
    out["engine"] = "elevenlabs-scribe_v1"
    return out


def local(wav: Path, language: str | None, model_name: str, device: str) -> dict:
    import numpy as np
    from faster_whisper import WhisperModel
    model = WhisperModel(model_name, device=device, compute_type="int8" if device == "cpu" else "float16")
    # hand whisper raw 16k float samples: avoids PyAV, whose newer releases break faster-whisper's decoder
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(wav), "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    audio = np.frombuffer(raw, np.float32)
    segs, info = model.transcribe(audio, language=language, word_timestamps=True, beam_size=5,
                                  condition_on_previous_text=False, vad_filter=False,
                                  initial_prompt=FILLER_PROMPT.get(language or "", None))
    words = []
    for s in segs:
        for w in s.words or []:
            words.append({"text": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3),
                          "type": "word", "speaker_id": None, "probability": round(w.probability, 3)})
    return {"language_code": info.language, "engine": f"faster-whisper-{model_name}", "words": words}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--work", type=Path, required=True, help="project work/ folder")
    ap.add_argument("--language", default=None, help="ISO code, e.g. es or en (default: auto-detect)")
    ap.add_argument("--engine", choices=["auto", "elevenlabs", "local"], default="auto")
    ap.add_argument("--model", default="large-v3-turbo", help="local engine model")
    ap.add_argument("--device", default="cpu", help="local engine: cpu or cuda")
    ap.add_argument("--speakers", type=int, default=None)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    out = a.work / "transcripts" / f"{a.video.stem}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and not a.force:
        print(f"cached: {out}")
        return
    key = elevenlabs_key()
    engine = a.engine if a.engine != "auto" else ("elevenlabs" if key else "local")
    if engine == "elevenlabs" and not key:
        sys.exit("no valid ElevenLabs key (must start with sk_) in env or ~/.config/vibe-edit/keys.env")

    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "audio.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(a.video), "-vn", "-ac", "1",
                        "-ar", "16000", "-c:a", "pcm_s16le", str(wav)], check=True)
        payload = scribe(wav, key, a.language, a.speakers) if engine == "elevenlabs" \
            else local(wav, a.language, a.model, a.device)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    n = sum(1 for w in payload.get("words", []) if w.get("type") == "word")
    print(f"saved: {out}\n  {payload['engine']}, {n} words, language={payload.get('language_code')}, "
          f"{time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
