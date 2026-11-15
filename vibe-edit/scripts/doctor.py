# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Is this computer ready to run vibe-edit? Run it first on any new machine.

  uv run doctor.py [--brand <video-style.json>]

Checks: ffmpeg + ffprobe on PATH with libass (needed for captions); the ElevenLabs key
(optional: without it, transcription runs locally for free); npx + the person cut-out model (optional:
the text-behind-the-head hook); the agency brand profile (found in
the vault's machine/vibe-edit/ on the PC or the Mac, or passed with --brand), its fonts and music.
Prints what to do for anything missing. Exit code 0 = ready.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import resolve_font  # noqa: E402

HOME = Path.home()
VAULTS = [HOME / "Claude" / "Vault", HOME / "Documents" / "Business"]  # Windows PC, Mac
KEY_FILE = HOME / ".config" / "vibe-edit" / "keys.env"
ok_all = True


def line(ok: bool, what: str, fix: str = "") -> None:
    global ok_all
    ok_all &= ok
    print(f"  {'OK  ' if ok else 'MISS'}  {what}" + ("" if ok or not fix else f"\n        -> {fix}"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", type=Path, default=None)
    a = ap.parse_args()
    mac = sys.platform == "darwin"
    print("vibe-edit doctor")

    ff = shutil.which("ffmpeg") and shutil.which("ffprobe")
    line(bool(ff), "ffmpeg + ffprobe on PATH",
         "brew install ffmpeg" if mac else "winget install Gyan.FFmpeg (then open a new terminal)")
    if ff:
        filt = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        line(" subtitles " in filt, "ffmpeg has libass (burned captions)",
             "install an ffmpeg build with libass (Homebrew's ffmpeg and gyan.dev 'full' builds have it)")

    key = None
    if KEY_FILE.exists():
        for ln in KEY_FILE.read_text(encoding="utf-8").splitlines():
            if ln.startswith("ELEVENLABS_API_KEY="):
                key = ln.split("=", 1)[1].strip()
    line(bool(key and key.startswith("sk_")), f"ElevenLabs key in {KEY_FILE} (optional)",
         f"create the file with one line ELEVENLABS_API_KEY=sk_... (ElevenLabs > Developers > API Keys); "
         f"without it transcription runs locally with faster-whisper (free, fewer cuts)")

    # the "depth" hook (big text behind the speaker's head) cuts the person out with HyperFrames
    model = HOME / ".cache" / "hyperframes" / "background-removal" / "models" / "u2net_human_seg.onnx"
    npx = shutil.which("npx")
    line(bool(npx), "npx on PATH (HyperFrames, for the text-behind-the-head hook; optional)",
         "install Node.js LTS (brew install node / winget install OpenJS.NodeJS.LTS)")
    line(model.exists(), f"person cut-out model {model} (optional)",
         "one-time 176 MB download of the MIT u2net_human_seg model from the rembg GitHub releases; ask the "
         "user first, then run: npx hyperframes remove-background <any photo of a person>.jpg -o test.png. "
         "Without it, 'depth' hooks fall back to the two-tier hook")

    brand = a.brand
    if not brand:
        brand = next((v / "machine" / "vibe-edit" / "video-style.json" for v in VAULTS
                      if (v / "machine" / "vibe-edit" / "video-style.json").exists()), None)
    line(bool(brand and brand.exists()), f"agency brand profile ({brand or 'vault machine/vibe-edit/video-style.json'})",
         "git pull the vault (business-brain); the profile lives in machine/vibe-edit/")
    if brand and brand.exists():
        b = json.loads(brand.read_text(encoding="utf-8"))
        for sect in ("caption", "hook_title"):
            ff_ = (b.get(sect) or {}).get("font_file")
            if not ff_:
                continue
            try:
                line(True, f"{sect} font -> {resolve_font(ff_, brand.parent)}")
            except SystemExit:
                line(False, f"{sect} font {ff_}", "add this computer's font path to font_file, or drop the .ttf "
                                                   "into a fonts/ folder next to the profile")
        mus = (b.get("music") or {}).get("folder")
        if mus:
            md = (brand.parent / mus) if not Path(mus).is_absolute() else Path(mus)
            n = len([p for p in md.glob("*") if p.suffix.lower() in {".mp3", ".wav", ".m4a"}]) if md.exists() else 0
            line(n > 0, f"music beds: {n} in {md}", "clips will build without music until tracks are added")

    # every style's fonts (a style lists the Windows path, then the Mac fallback)
    styles_dir = Path(__file__).resolve().parent.parent / "styles"
    for sp in sorted(styles_dir.glob("*.json")):
        st = json.loads(sp.read_text(encoding="utf-8"))
        cap, hk, ec = st.get("caption", {}), st.get("hook_title", {}), st.get("end_card", {})
        wanted = [cap.get("font_file"), (cap.get("emphasis") or {}).get("font_file"), hk.get("font_file"),
                  hk.get("small_font_file"), ec.get("text_font")]
        got, missing = [], []
        for ff_ in filter(None, wanted):
            try:
                got.append(Path(resolve_font(ff_, styles_dir)).name)
            except SystemExit:
                missing.append(ff_[0] if isinstance(ff_, list) else ff_)
        line(not missing, f"style '{sp.stem}' fonts: {', '.join(dict.fromkeys(got)) or 'defaults'}",
             f"missing {missing}: add this computer's path to the style's font lists")

    print("READY" if ok_all else "Not fully ready: fix the MISS lines (an optional MISS still lets you edit).")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
