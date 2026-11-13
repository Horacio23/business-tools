"""Shared helpers for the vibe-edit scripts (imported, not run)."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

# Spoken fillers / hesitations (ES + EN). Only pure hesitation sounds: real words
# like "este", "pues", "o sea", "like" are judged in context by the editor, not here.
FILLERS = {"eh", "ehh", "ehm", "em", "emm", "mm", "mmm", "hmm", "um", "uh", "uhm", "ah", "ahh", "erm"}


# Immediate repeats of these short words are stutters ("con el, el negocio"); the builder drops the
# first copy. Content words ("no, no", "muy muy") are left alone because repeating them is often emphasis.
STUTTER_WORDS = {"el", "la", "los", "las", "lo", "un", "una", "de", "del", "que", "y", "a", "en", "con", "se",
                 "me", "te", "le", "mi", "tu", "su", "por", "para", "es", "the", "an", "to", "of", "and", "i",
                 "that", "it", "in", "is", "we", "you"}

# Number words -> digits for captions ("ocho de diez" -> "8 de 10"). "uno/una/un" stay words (articles).
_NUM = {
    "es": {"dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
           "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15, "dieciséis": 16,
           "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20,
           "veintiuno": 21, "veintidós": 22, "veintidos": 22, "veintitrés": 23, "veintitres": 23,
           "veinticuatro": 24, "veinticinco": 25, "veintiséis": 26, "veintiseis": 26, "veintisiete": 27,
           "veintiocho": 28, "veintinueve": 29, "treinta": 30, "cuarenta": 40, "cincuenta": 50,
           "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90, "cien": 100},
    "en": {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
           "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
           "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
           "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100},
}
_TENS = {30, 40, 50, 60, 70, 80, 90, 20}


def digits_for(words: list[str], lang: str) -> list[str]:
    """Replace standalone number words with digits. Compounds joined by 'y'/'and'
    ("treinta y cinco") are left as words rather than becoming "30 y 5"."""
    table = _NUM.get((lang or "es")[:2], {})
    low = [w.lower() for w in words]
    out = list(words)
    for k, w in enumerate(low):
        n = table.get(w)
        if n is None:
            continue
        nxt = low[k + 1] if k + 1 < len(low) else ""
        prv2 = low[k - 2] if k >= 2 else ""
        if n in _TENS and nxt in ("y", "and"):
            continue
        if k >= 2 and low[k - 1] in ("y", "and") and table.get(prv2) in _TENS:
            continue
        out[k] = str(n)
    return out


FONT_DIRS = [Path("C:/Windows/Fonts"), Path.home() / "AppData/Local/Microsoft/Windows/Fonts",
             Path("/System/Library/Fonts/Supplemental"), Path("/System/Library/Fonts"), Path("/Library/Fonts"),
             Path.home() / "Library/Fonts", Path("/usr/share/fonts/truetype"), Path.home() / ".fonts"]


def resolve_font(value, root: Path) -> str:
    """A brand's font_file may be one path or a list (e.g. the Windows and the Mac location of the
    same font), absolute or relative to the profile. The first one that exists wins; failing that,
    each file name is looked up in the usual Windows/macOS/Linux font folders."""
    cands = value if isinstance(value, list) else [value]
    for c in cands:
        p = Path(c) if Path(c).is_absolute() else (root / c)
        if p.exists():
            return str(p.resolve())
    for c in cands:
        for d in FONT_DIRS:
            p = d / Path(c).name
            if p.exists():
                return str(p)
    raise SystemExit(f"font not found on this computer: {cands}. Put the .ttf in the brand's fonts/ folder "
                     f"or add this machine's path to font_file (run scripts/doctor.py).")


def norm(text: str) -> str:
    return re.sub(r"[^\wáéíóúüñ$%]", "", text.lower())


def load_words(transcript: Path) -> list[dict]:
    """Scribe JSON -> list of real words: {i, text, start, end, speaker, filler}."""
    data = json.loads(Path(transcript).read_text(encoding="utf-8"))
    out = []
    for w in data.get("words", []):
        if w.get("type") != "word":
            continue
        t = w["text"].strip()
        if not t:
            continue
        out.append({"i": len(out), "text": t, "start": float(w["start"]), "end": float(w["end"]),
                    "speaker": w.get("speaker_id"), "filler": norm(t) in FILLERS, "repeat": False})
    for a, b in zip(out, out[1:]):
        if norm(a["text"]) == norm(b["text"]) and norm(a["text"]) in STUTTER_WORDS:
            a["repeat"] = True
    return out


def probe(path: Path) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def video_stream(info: dict) -> dict:
    return next(s for s in info["streams"] if s["codec_type"] == "video")


def display_size(vs: dict) -> tuple[int, int]:
    """Width/height after applying rotation metadata (phone footage)."""
    w, h = int(vs["width"]), int(vs["height"])
    rot = 0
    for sd in vs.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(sd["rotation"])
    if "rotate" in (vs.get("tags") or {}):
        rot = int(vs["tags"]["rotate"])
    return (h, w) if abs(rot) % 180 == 90 else (w, h)


def ass_color(hex_rgb: str, alpha: int = 0) -> str:
    """#RRGGBB -> ASS &HAABBGGRR."""
    h = hex_rgb.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def fmt_ass_time(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def fmt_srt_time(t: float) -> str:
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise SystemExit(f"command failed: {' '.join(cmd[:6])} ...\n{r.stderr[-2500:]}")
