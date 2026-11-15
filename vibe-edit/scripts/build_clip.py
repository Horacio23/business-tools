# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "opencv-python-headless<5", "pillow", "fonttools"]
# ///
"""Build finished vertical clips from a cut plan.

  uv run build_clip.py <plan.json> [--only <slug>] [--style <name>]

plan.json:
{
  "source": "C:/.../raw.mp4",
  "transcript": "<work>/transcripts/raw.json",
  "brand": "C:/.../video-style.json",
  "work": "<project>/work",
  "deliver": "<project>/deliver",
  "style": "serenity",           # optional: else the brand profile's "style", else "karaoke"
  "clips": [
    {"slug": "3-sistemas", "hook_title": "3 sistemas que ...", "purpose": "organic",
     "segments": [{"words": [0, 41]}, {"start": 20.5, "end": 31.0}],
     "music": "auto",            # "auto" | "none" | "<file path>"
     "style": "serenity-bold",   # optional per clip (render the same cut in two looks)
     "emphasis": [12, 27],       # reveal styles: source word ids set big (+ numbers if the style says so);
                                 # "auto" (default: numbers + the style's pick rule) | "none"
     "hook_kind": "depth",       # optional: override the style's hook ("depth" | "two-tier" | "box")
     "sfx": "none",              # optional: no sound effects on this clip (styles with sfx.enabled)
     "broll": [{"file": "C:/.../laser.mp4", "at_word": 14, "seconds": 2.0, "from": 0.0}]}
  ]
}

A STYLE (../styles/<name>.json) is a look: caption mode and type, hook, end card layout, grade, music level.
The BRAND PROFILE is the identity: logo, contact lines for the end card, music folder, language,
compliance. A profile names its default style ("style"); its own caption/hook/edit/grade settings tweak
that default style only, and "styles": {"<name>": {...}} tweaks any other style for that brand.

Per clip, in this order (order is load-bearing):
  1. snap every segment to word boundaries, drop hesitation fillers, close pauses
     longer than edit.max_pause (jump cuts), pad each piece edge
  2. per piece: face-centred 9:16 crop (+ alternating punch-in; with edit.rhythm also zoom cuts inside a
     take at sentence ends / every few seconds, video only), style grade, 30ms audio fades
  3. end card piece (style layout + brand logo/contact lines), lossless concat -> base.mov
  4. voice clean-up + music bed ducked under the voice -> mix_base.wav
  5. a "depth" hook cuts the speaker out of the hook seconds (HyperFrames remove-background) and draws its
     big word BEHIND the head: base -> behind.ass -> cut-out on top -> everything else
  6. sound effects (sfx.py, synthesized: whoosh on zoom cuts, pop on key words, riser + hit on the hook)
     mixed in at levels relative to the voice -> mix.wav -> two-pass loudnorm
  7. B-roll cutaways, logo overlay, then captions + hook burned LAST
Outputs: <deliver>/<slug>.mp4, <slug>.srt, <slug>-cover.jpg; <work>/<slug>/build.json
(seams, pieces, face boxes, caption lines, effective QA targets) which qa.py reads.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from common import (ass_color, digits_for, display_size, fmt_ass_time, fmt_srt_time, load_words, resolve_font,  # noqa: E402
                    probe, run, video_stream)
import sfx as sfxlib  # noqa: E402

OUT_W, OUT_H, FPS = 1080, 1920, 30
STYLES_DIR = Path(__file__).resolve().parent.parent / "styles"
STYLE_ALIASES = {"accent": "punch"}  # old style names, so older plans and profiles still build
DEFAULTS = {
    "language": "es",
    "caption": {"mode": "karaoke", "font_file": "C:/Windows/Fonts/ariblk.ttf", "size": 78, "uppercase": False,
                "words_per_chunk": 3, "max_line_px": 800, "color": "#FFFFFF", "highlight": "#FFD400",
                "outline": "#000000", "outline_px": 7, "outline_opacity": 1.0, "shadow_px": 0,
                "shadow_color": "#000000", "shadow_opacity": 0.608, "blur": 0, "y": "auto",
                "strip_punctuation": True, "pop": True, "fade_ms": 120,
                # safe_zone: keep every caption and hook line inside {"top", "bottom", "side"} px; Meta's ad
                # zone is 14% top / 35% bottom / 6% sides = {"top": 269, "bottom": 1248, "side": 65}
                "safe_zone": None,
                "emphasis": {"enabled": False, "font_file": None, "size": 104, "color": "#FFFFFF",
                             "uppercase": False, "every_s": 1.6, "min_len": 5, "line_scale": 0.8,
                             # numbers: every number gets the big line; pick: "longest" content word, or
                             # "stress" = the word said loudest/highest/slowest vs nearby words (score >= stress_min),
                             # falling back to the longest after max_gap_s without one
                             "numbers": False, "pick": "longest", "stress_min": 1.2, "max_gap_s": None,
                             "pop": 1.0, "glow": None, "glow_px": 16, "glow_blur": 12, "glow_opacity": 0.8}},
    "hook_title": {"enabled": True, "kind": "box", "font_file": None, "size": 62, "color": "#FFFFFF",
                   "box": "#000000", "y": 430, "seconds": 3.0, "uppercase": False, "max_line_px": 860,
                   "small_font_file": None, "small_size": 62, "small_color": "#FFFFFF", "small_y": 340,
                   "big_color": "#F4CE3C", "big_y": 470, "big_max_px": 900, "glow": None,
                   # kind "depth": hook_title "top line | BIG | label". BIG is sized to the frame width (capped
                   # at max_glyph_px tall) and drawn BEHIND the speaker so the head hides `overlap` of its
                   # height; it rises rise_px from behind the head. The label sits in front across its middle,
                   # never on the head. Falls back to two-tier if BIG would be under min_glyph_px tall, the
                   # head is too high for it, or the cut-out tool/model isn't on this computer.
                   "depth": {"top_size": 110, "label_size": 150, "label_color": "#FFFFFF", "max_glyph_px": 400,
                             "min_glyph_px": 180, "overlap": 0.3, "gap_px": 28, "label_at": 0.55,
                             "label_delay": 0.35, "rise_px": 140, "rise_ms": 420}},
    "end_card": {"enabled": False, "seconds": 2.0, "background": "#FFFFFF", "logo_width": 600, "logo_y": 900,
                 "lines_y": 1400, "line_gap": 125, "text_font": None, "text_size": 70, "small_size": 34,
                 "text_color": "#FFFFFF", "label_color": "#C9A54E", "icon_height": 96, "shadow": True,
                 "shadow_offset": [5, 8], "shadow_blur": 6, "shadow_opacity": 0.6, "fade_in": 0.35,
                 "fade_color": "white"},
    "grade": {"enabled": False, "target_luma": None, "contrast": 1.0, "saturation": 1.0, "black_lift": 0.0,
              "temperature": None},
    "contact": {"logo": None, "lines": []},
    "logo": {"enabled": False, "path": None, "width": 130, "corner": "top-left", "opacity": 0.9},
    "music": {"enabled": True, "folder": None, "track": None, "volume_db": -22, "duck": True},
    "audio": {"lufs": -14, "true_peak": -1.5, "voice_cleanup": True},
    "length": {"min": 15, "max": 60},
    "edit": {"pad_in": 0.06, "pad_out": 0.12, "max_pause": 0.4, "drop_fillers": True,
             "punch_in": 1.12, "min_piece_for_punch": 0.8,
             # rhythm: extra zoom cuts inside a continuous take, at each sentence end (once the shot is
             # min_shot_s long) or at the first word gap after every_s; zooms cycle, capped so the face
             # never fills more than max_face_area of the frame
             "rhythm": {"enabled": False, "every_s": 3.0, "min_shot_s": 1.3, "at_sentence": True,
                        "zooms": [1.0, 1.12, 1.0, 1.24], "max_face_area": 0.17}},
    # sound effects (sfx.py): a whoosh on zoom cuts (sentence ends first, at most one per whoosh_gap_s), a pop
    # when a key word lands (not within 0.45 s of a whoosh), a hit when the hook lands (+ a riser while a
    # depth hook rises). *_db = loudest 30 ms of the effect vs the voice's average level.
    "sfx": {"enabled": False, "whoosh": True, "whoosh_db": -8, "whoosh_gap_s": 3.0, "pop": True, "pop_db": -12,
            "pop_gap_s": 1.2, "hit": True, "hit_db": -3, "riser": True, "riser_db": -10},
    "qa": {"min_voice_over_music_db": 10},
    "compliance": {"profile": "none", "extra_terms": []},
}
CUTOUT_MODEL = Path.home() / ".cache" / "hyperframes" / "background-removal" / "models" / "u2net_human_seg.onnx"
# Profile keys that are identity (apply whatever style is chosen); everything else is look.
IDENTITY = {"language", "logo", "contact", "audio", "length", "compliance"}
MUSIC_IDENTITY = {"enabled", "folder", "track"}


def merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def available_styles() -> list[str]:
    return sorted(p.stem for p in STYLES_DIR.glob("*.json"))


def load_style(name: str, root: Path) -> dict:
    p = Path(name)
    for c in ([p if p.is_absolute() else root / p] if p.suffix == ".json" else []) + [STYLES_DIR / f"{name}.json"]:
        if c.exists():
            return json.loads(c.read_text(encoding="utf-8"))
    raise SystemExit(f"style '{name}' not found. Available: {', '.join(available_styles())}")


def load_brand(path: Path, style: str | None = None) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    root = path.parent
    own = raw.get("style") or "karaoke"
    own = STYLE_ALIASES.get(own, own)
    name = style or own
    name = STYLE_ALIASES.get(name, name)
    st = load_style(name, root)
    b = merge(DEFAULTS, {k: v for k, v in st.items() if k not in ("name", "description")})
    if name == own:  # the profile's own look settings tune its default style
        b = merge(b, {k: v for k, v in raw.items() if k not in ("style", "styles")})
    else:            # another style: take only the identity from the profile
        ident = {k: raw[k] for k in IDENTITY if k in raw}
        if isinstance(raw.get("music"), dict):
            ident["music"] = {k: v for k, v in raw["music"].items() if k in MUSIC_IDENTITY}
        b = merge(b, ident)
    per_style = raw.get("styles") or {}
    for old in [k for k, v in STYLE_ALIASES.items() if v == name]:
        b = merge(b, per_style.get(old, {}))
    b = merge(b, per_style.get(name, {}))
    b["style"] = name
    rel = lambda v: str((root / v).resolve()) if v and not Path(v).is_absolute() else v  # noqa: E731
    for sect, key in [("logo", "path"), ("music", "folder"), ("music", "track"), ("contact", "logo")]:
        b[sect][key] = rel(b[sect].get(key))
    b["contact"]["lines"] = [dict(ln, icon=rel(ln.get("icon"))) if ln.get("icon") else ln
                             for ln in b["contact"].get("lines", [])]
    cap = b["caption"]
    cap["font_file"] = resolve_font(cap["font_file"], root)
    em = cap["emphasis"]
    em["font_file"] = resolve_font(em["font_file"], root) if em.get("font_file") else cap["font_file"]
    hk = b["hook_title"]
    hk["font_file"] = resolve_font(hk["font_file"], root) if hk.get("font_file") else cap["font_file"]
    hk["small_font_file"] = resolve_font(hk["small_font_file"], root) if hk.get("small_font_file") \
        else hk["font_file"]
    ec = b["end_card"]
    ec["text_font"] = resolve_font(ec["text_font"], root) if ec.get("text_font") else cap["font_file"]
    return b


# ---------------------------------------------------------------- cutting ----
def plan_pieces(words: list[dict], segments: list[dict], ed: dict) -> list[dict]:
    """Segments -> contiguous source pieces snapped to word edges."""
    pieces = []
    for seg_no, seg in enumerate(segments):
        if "words" in seg:
            a, b = seg["words"]
            sw = [w for w in words if a <= w["i"] <= b]
        else:
            sw = [w for w in words if w["end"] > seg["start"] + 0.02 and w["start"] < seg["end"] - 0.02]
        kept = [w for w in sw if not (ed["drop_fillers"] and (w["filler"] or w["repeat"]))]
        if not kept:
            continue
        groups, cur = [], [kept[0]]
        for w in kept[1:]:
            if w["start"] - cur[-1]["end"] > ed["max_pause"] or w["i"] != cur[-1]["i"] + 1:
                groups.append(cur)
                cur = [w]
            else:
                cur.append(w)
        groups.append(cur)
        for g in groups:
            a = g[0]["start"] - ed["pad_in"]
            b = g[-1]["end"] + ed["pad_out"]
            if g[0]["i"] > 0:
                a = max(a, words[g[0]["i"] - 1]["end"] + 0.02)
            if g[-1]["i"] + 1 < len(words):
                b = min(b, words[g[-1]["i"] + 1]["start"] - 0.02)
            pieces.append({"seg": seg_no, "src_start": round(max(0.0, a), 3), "src_end": round(b, 3),
                           "words": [w["i"] for w in g]})
    return pieces


# ---------------------------------------------------------------- framing ----
_CASCADE = None


def detect_face(src: Path, t: float) -> tuple[float, float, float] | None:
    """(cx, cy, area) of the largest face as fractions of the display frame, or None."""
    global _CASCADE
    if _CASCADE is None:
        _CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1",
                        "-vf", "scale=-2:640", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                       capture_output=True)
    if not r.stdout:
        return None
    h = 640
    w = len(r.stdout) // (h * 3)
    img = np.frombuffer(r.stdout[: w * h * 3], np.uint8).reshape(h, w, 3)
    gray = cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    faces = _CASCADE.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(48, 48))
    if len(faces) == 0:
        return None
    x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
    return ((x + fw / 2) / w, (y + fh / 2) / h, (fw * fh) / (w * h))


def segment_faces(src: Path, pieces: list[dict]) -> dict[int, dict]:
    """One locked framing per planned segment (no in-shot panning)."""
    out = {}
    for seg in sorted({p["seg"] for p in pieces}):
        ps = [p for p in pieces if p["seg"] == seg]
        a, b = ps[0]["src_start"], ps[-1]["src_end"]
        times = [a + (b - a) * f for f in (0.15, 0.5, 0.85)] if b - a > 1 else [(a + b) / 2]
        hits = [f for f in (detect_face(src, t) for t in times) if f]
        if hits:
            out[seg] = {"cx": statistics.median(h[0] for h in hits), "cy": statistics.median(h[1] for h in hits),
                        "area": statistics.median(h[2] for h in hits), "found": len(hits) / len(times)}
        else:
            out[seg] = {"cx": 0.5, "cy": 0.4, "area": 0.0, "found": 0.0}
    return out


def face_marks(W: int, H: int, face: dict, rect: tuple[int, int, int, int]) -> dict:
    """Where the head sits in the output frame, in px: top of the hair (estimated: Haar boxes run roughly
    brow to chin, hair adds ~30% of the box above), brow, mouth, chin."""
    if not face.get("area"):
        return {}
    side = (face["area"] * W * H) ** 0.5
    top, bottom = face["cy"] * H - side / 2, face["cy"] * H + side / 2
    out = lambda v: round((v - rect[1]) * OUT_H / rect[3])  # noqa: E731
    return {"head_top_y": out(top - 0.3 * side), "face_top_y": out(top), "mouth_y": out(bottom - 0.27 * side),
            "chin_y": out(bottom)}


def reveal_half(cap: dict) -> float:
    """Half the height of the tallest reveal caption block (small line + key-word line + small line)."""
    em = cap["emphasis"]
    return (2 * cap["size"] * 1.08 + (em["size"] * em["line_scale"] if em["enabled"] else 0)) / 2


def crop_filter(W: int, H: int, face: dict, zoom: float, anchor: str = "face") -> tuple[str, tuple[int, int, int, int]]:
    """Face-centred 9:16 crop. A punch-in normally grows around the face centre; anchor="head_top" grows
    around the top of the head instead, so the head never rises into captions placed above it."""
    if W / H > OUT_W / OUT_H:  # wider than 9:16 -> crop width
        cw, ch = H * OUT_W / OUT_H, H
    else:
        cw, ch = W, W * OUT_H / OUT_W
    fx, fy = face["cx"] * W, face["cy"] * H
    ay = fy
    if anchor == "head_top" and face.get("area"):
        ay = max(fy - 0.8 * (face["area"] * W * H) ** 0.5, 0)
    x0 = min(max(fx - cw / 2, 0), W - cw)
    y0 = min(max(fy - ch * 0.4, 0), H - ch)
    zw, zh = cw / zoom, ch / zoom
    x = x0 + (fx - x0) * (1 - 1 / zoom)
    y = y0 + (ay - y0) * (1 - 1 / zoom)
    x = min(max(x, x0), x0 + cw - zw)
    y = min(max(y, y0), y0 + ch - zh)
    ev = lambda v: int(v) // 2 * 2  # noqa: E731
    rect = (ev(x), ev(y), ev(zw), ev(zh))
    return f"crop={rect[2]}:{rect[3]}:{rect[0]}:{rect[1]},scale={OUT_W}:{OUT_H}:flags=lanczos,setsar=1", rect


# ------------------------------------------------------------------ grade ----
def measure_luma(src: Path, pieces: list[dict]) -> float | None:
    """Median mean-Y (0-255, video range) of up to 6 frames across the planned pieces."""
    mids = [(p["src_start"] + p["src_end"]) / 2 for p in pieces]
    picks = [mids[round(k * (len(mids) - 1) / 5)] for k in range(6)] if len(mids) > 6 else mids
    vals = []
    for t in picks:
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1",
                            "-vf", "scale=160:-2,format=gray", "-f", "rawvideo", "-"], capture_output=True)
        if r.stdout:
            vals.append(float(np.frombuffer(r.stdout, np.uint8).mean()))
    return statistics.median(vals) if vals else None


def grade_filter(gr: dict, src: Path, pieces: list[dict]) -> tuple[str, dict]:
    """Style grade as an ffmpeg filter chain. target_luma pulls the clip's average brightness toward the
    style's (measured on the reference reels) with a gamma move, so dark and bright sources both land."""
    if not gr.get("enabled"):
        return "", {}
    g, lum = 1.0, None
    if gr.get("target_luma"):
        lum = measure_luma(src, pieces)
        if lum and 10 < lum < 245:
            g = min(max(math.log(lum / 255) / math.log(gr["target_luma"] / 255), 0.85), 1.35)
    parts = [f"eq=gamma={g:.3f}:contrast={gr['contrast']}:saturation={gr['saturation']}"]
    if gr.get("black_lift"):
        parts.append(f"curves=m='0/{gr['black_lift']} 1/1'")
    if gr.get("temperature"):
        parts.append(f"colortemperature=temperature={gr['temperature']}:pl=1")
    return ",".join(parts), {"source_luma": round(lum, 1) if lum else None, "gamma": round(g, 3)}


# --------------------------------------------------------------- captions ----
PUNCT = re.compile(r"[^\w\s$%'’\-áéíóúüñÁÉÍÓÚÜÑ]")
STOP = {"a", "al", "algo", "ante", "aquí", "aqui", "así", "asi", "cada", "como", "con", "cual", "cuando", "de",
        "del", "desde", "donde", "el", "ella", "ellas", "ellos", "en", "entre", "era", "eres", "es", "esa", "esas",
        "ese", "eso", "esos", "esta", "está", "estas", "están", "estar", "este", "esto", "estos", "fue", "ha",
        "han", "has", "hay", "hace", "hacer", "la", "las", "le", "les", "lo", "los", "más", "mas", "me", "mi",
        "mis", "muy", "nada", "ni", "no", "nos", "nuestro", "nuestra", "nuestros", "nuestras", "o", "otra",
        "otro", "para", "pero", "poco", "por", "porque", "puede", "pueden", "que", "qué", "se", "sea", "ser",
        "si", "sí", "sin", "sobre", "son", "su", "sus", "también", "tambien", "tanto", "te", "tener", "tiene",
        "tienen", "tienes", "todo", "toda", "todos", "todas", "tu", "tú", "tus", "un", "una", "uno", "unos",
        "unas", "usted", "va", "vamos", "veces", "y", "ya", "yo", "estamos", "estoy", "tengo", "entonces",
        "después", "despues", "antes", "mucho", "mucha", "muchos", "muchas", "cosas", "cosa", "siempre",
        "the", "and", "that", "this", "with", "your", "you", "they", "there", "their", "what", "when", "which",
        "about", "from", "have", "just", "like", "really", "because", "would", "could", "should", "these"}


def clean_word(t: str, cap: dict) -> str:
    if cap["strip_punctuation"] == "light":  # keep ¿ ¡ ? ! inside, drop trailing , . ; : and quotes
        t = re.sub(r"[.,;:\"“”«»]+$", "", t).lstrip("\"“”«»")
    elif cap["strip_punctuation"]:
        t = PUNCT.sub("", t)
    return t.upper() if cap["uppercase"] else t


def ass_escape(t: str) -> str:
    return t.replace("\\", "").replace("{", "(").replace("}", ")")


def font_face(path: Path) -> tuple[str, bool, bool]:
    """(legacy family name, bold, italic). libass matches the legacy family (name ID 1, e.g. 'Arial Black',
    'Bodoni MT') plus the bold/italic flags; FreeType/PIL report the typographic family ('Arial') and libass
    then falls back to the regular face. Use static TTF/OTF files; variable fonts select their default."""
    from fontTools.ttLib import TTFont
    names = TTFont(str(path), fontNumber=0, lazy=True)["name"]
    get = lambda nid: (names.getName(nid, 3, 1, 0x409) or names.getName(nid, 1, 0, 0))  # noqa: E731
    fam = get(1) or get(4)
    family = fam.toUnicode() if fam else ImageFont.truetype(str(path), 10).getname()[0]
    sub = (get(2).toUnicode() if get(2) else "").lower()
    return family, "bold" in sub, ("italic" in sub or "oblique" in sub)


def font_family(path: Path) -> str:
    return font_face(path)[0]


def ass_pil_font(path, size: float) -> ImageFont.FreeTypeFont:
    """A PIL font that measures text the way libass draws it. An ASS font size is the font's full height
    (winAscent + winDescent), not its em, so e.g. Arial Black at size 100 draws a ~71 px em and Arial Bold
    ~90 px. Measuring with ImageFont.truetype(path, size) overestimates widths by that ratio."""
    from fontTools.ttLib import TTFont
    t = TTFont(str(path), fontNumber=0, lazy=True)
    upm = t["head"].unitsPerEm
    os2 = t["OS/2"] if "OS/2" in t else None
    full = (os2.usWinAscent + os2.usWinDescent) if os2 and os2.usWinAscent + os2.usWinDescent > 0 \
        else t["hhea"].ascent - t["hhea"].descent
    return ImageFont.truetype(str(path), max(1, round(size * upm / full)))


def prep_items(out_words: list[dict], cap: dict, lang: str) -> list[dict]:
    items = []
    for w in out_words:
        txt = clean_word(w["text"], cap)
        if not txt:
            continue
        if txt == "%" and items:  # transcripts split "78 %": show "78%"
            items[-1].update(show=items[-1]["show"] + "%", end=w["end"], text=items[-1]["text"] + w["text"])
            continue
        items.append(dict(w, show=txt))
    if cap.get("numbers_as_digits", True):  # Scribe spells numbers out: "ocho de diez" -> "8 de 10"
        for it, shown in zip(items, digits_for([it["show"] for it in items], lang)):
            it["show"] = shown
    merged = []  # "8 de 10" / "1 in 5" stay together as one caption word (and one key word)
    for it in items:
        if (len(merged) >= 2 and is_number(it["show"]) and emph_core(merged[-1]["show"]) in ("de", "of", "en", "in")
                and is_number(merged[-2]["show"]) and it["start"] - merged[-2]["end"] < 1.2):
            joiner = merged.pop()
            merged[-1] = dict(merged[-1], show=f"{merged[-1]['show']} {joiner['show']} {it['show']}", end=it["end"],
                              text=f"{merged[-1]['text']} {joiner['text']} {it['text']}")
            continue
        merged.append(it)
    return merged


def chunk_items(items: list[dict], cap: dict, font: ImageFont.FreeTypeFont, limit: float) -> list[list[dict]]:
    chunks, cur = [], []
    for item in items:
        if cur:
            joined = " ".join(c["show"] for c in cur + [item])
            if (len(cur) >= cap["words_per_chunk"] or font.getlength(joined) > limit
                    or item["start"] - cur[-1]["end"] > 0.45 or cur[-1]["text"].rstrip()[-1:] in ".?!…,"):
                chunks.append(cur)
                cur = []
        cur.append(item)
    if cur:
        chunks.append(cur)
    return chunks


def chunk_end(chunks: list[list[dict]], k: int) -> float:
    nxt = chunks[k + 1][0]["start"] if k + 1 < len(chunks) else None
    last = chunks[k][-1]["end"]
    return nxt if nxt is not None and nxt - last < 0.6 else last + 0.25


def emph_core(text: str) -> str:
    return re.sub(r"[^\wáéíóúüñ]", "", text.lower())


def is_number(text: str) -> bool:
    return any(c.isdigit() for c in emph_core(text))


def word_stress(src: Path, ids: list[int], words: list[dict]) -> dict[int, float]:
    """How hard each kept word is stressed when spoken: loudness, pitch and stretch (seconds per vowel group),
    each as a robust z-score against the ~12 words around it, so a naturally loud speaker or a loud room
    doesn't make everything 'stressed'. Weighted sum; > ~1.2 is a word the speaker leaned on."""
    sr, n, hop = 16000, 640, 160
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le",
                          "-"], capture_output=True).stdout
    x = np.frombuffer(raw, np.float32)
    win, lo, hi = np.hanning(n), sr // 400, sr // 75
    feats = []
    for i in ids:
        w = words[i]
        a, b = int(w["start"] * sr), int(w["end"] * sr)
        if b - a < n:
            a = max(0, (a + b) // 2 - n // 2)
            b = a + n
        seg = x[a:b]
        if len(seg) < n:
            continue
        fr = np.lib.stride_tricks.sliding_window_view(seg, n)[::hop]
        fr = fr - fr.mean(axis=1, keepdims=True)
        en = (fr ** 2).mean(axis=1)
        loud = 10 * np.log10(np.percentile(en, 75) + 1e-10)
        v = fr[en >= np.median(en)] * win
        ac = np.fft.irfft(np.abs(np.fft.rfft(v, 2 * n, axis=1)) ** 2, axis=1)[:, :n]
        ac = ac / (ac[:, :1] + 1e-12)
        lag = lo + ac[:, lo:hi].argmax(axis=1)
        f0 = sr / lag[ac[np.arange(len(ac)), lag] > 0.4]
        semis = 12 * math.log2(float(np.median(f0)) / 100) if len(f0) >= 2 else None
        groups = max(1, len(re.findall(r"[aeiouáéíóúü]+", w["text"].lower())))
        feats.append((i, float(loud), semis, (w["end"] - w["start"]) / groups))

    def z(vals: list, k: int) -> float:
        near = [v for v in vals[max(0, k - 6):k + 7] if v is not None]
        if vals[k] is None or len(near) < 4:
            return 0.0
        med = statistics.median(near)
        mad = statistics.median(abs(v - med) for v in near) * 1.4826 or 1e-6
        return max(-3.0, min(3.0, (vals[k] - med) / mad))

    cols = [[f[c] for f in feats] for c in (1, 2, 3)]
    return {f[0]: round(float(z(cols[0], k) + 0.8 * z(cols[1], k) + 0.5 * z(cols[2], k)), 2) for k, f in enumerate(feats)}


def choose_emphasis(chunks: list[list[dict]], em: dict, cap: dict, f_emph: ImageFont.FreeTypeFont, limit: float,
                    forced, auto: bool = True) -> dict[int, int]:
    """{phrase index: key-word index}. Plan word ids and (if the style marks them) numbers always get the big
    line. Then, unless the plan turned auto off, the style's pick rule:
      "longest" - walking forward, the longest content word once every_s has passed since the last key word;
      "stress"  - the most strongly spoken words first (score >= stress_min), never closer than every_s to
                  another key word; then any stretch longer than max_gap_s without one gets its best-spoken
                  word, so the screen never goes too long without an accent.
    Words too long to show at >= 1.15x the caption size inside the safe width are never picked."""
    def fits(w: dict) -> bool:
        width = f_emph.getlength(w["show"].upper() if em["uppercase"] else w["show"])
        return em["size"] * min(1.0, limit / width if width else 1.0) >= cap["size"] * 1.15

    times = [ch[0]["start"] for ch in chunks]
    pick: dict[int, int] = {}
    for k, ch in enumerate(chunks):
        j = next((j for j, w in enumerate(ch) if isinstance(forced, set) and w["i"] in forced and fits(w)), None)
        if j is None and em.get("numbers"):
            j = next((j for j, w in enumerate(ch) if is_number(w["show"]) and fits(w)), None)
        if j is not None:
            pick[k] = j
    if not auto:
        return pick
    content = {k: [j for j, w in enumerate(ch) if len(emph_core(w["show"])) >= em["min_len"] and fits(w)
                   and emph_core(w["show"]) not in STOP and not is_number(w["show"])]
               for k, ch in enumerate(chunks)}
    if em.get("pick") != "stress":
        last = -99.0
        for k, ch in enumerate(chunks):
            if k not in pick and times[k] - last >= em["every_s"] and content[k]:
                pick[k] = max(content[k], key=lambda j: (len(emph_core(ch[j]["show"])), j))
            if k in pick:
                last = times[k]
        return pick
    stress = lambda k, j: chunks[k][j].get("stress", 0.0)  # noqa: E731
    best = {k: max(js, key=lambda j: stress(k, j)) for k, js in content.items() if js and k not in pick}
    clear = lambda k: all(abs(times[k] - times[q]) >= em["every_s"] for q in pick)  # noqa: E731
    for k in sorted(best, key=lambda k: -stress(k, best[k])):
        if stress(k, best[k]) >= em["stress_min"] and clear(k):
            pick[k] = best[k]
    if em.get("max_gap_s"):
        end = chunks[-1][-1]["end"] if chunks else 0.0

        def gap(k: int) -> float:
            prev = max((times[q] for q in pick if times[q] < times[k]), default=0.0)
            nxt = min((times[q] for q in pick if times[q] > times[k]), default=end)
            return nxt - prev
        while True:
            fill = [k for k in best if k not in pick and gap(k) > em["max_gap_s"] and clear(k)]
            if not fill:
                break
            k = max(fill, key=lambda k: stress(k, best[k]))
            pick[k] = best[k]
    return pick


def build_reveal(out_words: list[dict], cap: dict, f_small: ImageFont.FreeTypeFont,
                 f_emph: ImageFont.FreeTypeFont, lang: str, forced, auto: bool = True) -> list[dict]:
    """Editorial captions: phrases of up to words_per_chunk words that appear word by word; one key word per
    phrase (the plan's "emphasis" word ids, numbers, or the style's auto pick) gets its own big line in the
    emphasis font."""
    em = cap["emphasis"]
    limit = cap["max_line_px"] - 2 * cap["outline_px"]
    chunks = chunk_items(prep_items(out_words, cap, lang), cap, f_small, limit)
    keys = choose_emphasis(chunks, em, cap, f_emph, limit, forced, auto) \
        if em["enabled"] and forced != "none" else {}
    out = []
    for k, ch in enumerate(chunks):
        e = keys.get(k)
        etext = lambda w: w["show"].upper() if em["uppercase"] else w["show"]  # noqa: E731
        es = em["size"]
        if e is not None:  # a long key word shrinks to fit the safe width; below ~1.15x the small size, skip it
            w = f_emph.getlength(etext(ch[e]))
            if w > limit:
                es = int(em["size"] * limit / w)
            if es < cap["size"] * 1.15:
                e, es = None, em["size"]
        if e is not None:
            groups =([("small", ch[:e])] if e else []) + [("emph", [ch[e]])] + \
                ([("small", ch[e + 1:])] if e + 1 < len(ch) else [])
        else:
            groups = [("small", ch)]
        hs, he = cap["size"] * 1.08, es * em["line_scale"]
        heights = [he if kind == "emph" else hs for kind, _ in groups]
        y = cap["y"] - sum(heights) / 2
        lines = []
        for (kind, ws), h in zip(groups, heights):
            shown = [etext(w) if kind == "emph" else w["show"] for w in ws]
            text = " ".join(shown)
            width = f_emph.getlength(text) * es / em["size"] if kind == "emph" else f_small.getlength(text)
            lines.append({"kind": kind, "words": [dict(w, show=s) for w, s in zip(ws, shown)], "text": text,
                          "y": round(y + h / 2), "size": es if kind == "emph" else cap["size"],
                          "width_px": round(width + 2 * cap["outline_px"])})
            y += h
        out.append({"start": ch[0]["start"], "end": chunk_end(chunks, k), "words": ch,
                    "text": " ".join(w["show"] for w in ch), "lines": lines,
                    "width_px": max(ln["width_px"] for ln in lines)})
    return out


def build_captions(out_words: list[dict], cap: dict, font: ImageFont.FreeTypeFont,
                   lang: str = "es") -> list[dict]:
    pop = 1.08 if cap["pop"] else 1.0
    limit = cap["max_line_px"] / pop - 2 * cap["outline_px"]
    items = prep_items(out_words, cap, lang)
    chunks, cur = [], []
    for item in items:
        if cur:
            joined = " ".join(c["show"] for c in cur + [item])
            if (len(cur) >= cap["words_per_chunk"] or font.getlength(joined) > limit
                    or item["start"] - cur[-1]["end"] > 0.45 or cur[-1]["text"].rstrip()[-1:] in ".?!…,"):
                chunks.append(cur)
                cur = []
        cur.append(item)
    if cur:
        chunks.append(cur)
    out = []
    for k, ch in enumerate(chunks):
        nxt = chunks[k + 1][0]["start"] if k + 1 < len(chunks) else None
        end = nxt if nxt is not None and nxt - ch[-1]["end"] < 0.6 else ch[-1]["end"] + 0.25
        text = " ".join(c["show"] for c in ch)
        width = round(font.getlength(text) * pop + 2 * cap["outline_px"])
        out.append({"start": ch[0]["start"], "end": end, "words": ch, "text": text, "width_px": width,
                    "lines": [{"kind": "small", "text": text, "y": cap["y"], "size": cap["size"],
                               "width_px": width}]})
    return out


def wrap_title(text: str, font: ImageFont.FreeTypeFont, max_px: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if cur and font.getlength(trial) > max_px:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + ([cur] if cur else [])


# ------------------------------------------------------------------- hook ----
def ink_box(path, size: float, text: str, y: float = 0) -> tuple[int, int, int]:
    """(top, bottom, width) of `text` as libass draws it at \\pos(540, y), alignment 5. The line box is the
    font's full height (= the ASS size) centred on y, with the baseline winAscent below its top. Matches
    libass to the pixel vertically; the width is the advance (a few % wider than the ink, so fits are safe)."""
    from fontTools.ttLib import TTFont
    os2 = TTFont(str(path), fontNumber=0, lazy=True)["OS/2"]
    base = y - size / 2 + size * os2.usWinAscent / (os2.usWinAscent + os2.usWinDescent)
    f = ass_pil_font(path, size)
    _, t, _, b = f.getbbox(text, anchor="ls")
    return round(base + t), round(base + b), round(f.getlength(text))


def hook_parts(title: str, upper: bool) -> list[str]:
    parts = [p.strip() for p in title.split("|")]
    return [p.upper() if upper else p for p in parts]


def two_tier_hook(small: str, big: str, hk: dict, hf: Path) -> dict:
    size = hk["size"]
    bfont = ass_pil_font(hf, size)
    widest = max(bfont.getlength(w) for w in big.split())
    if widest > hk["big_max_px"]:
        size = int(size * hk["big_max_px"] / widest)
        bfont = ass_pil_font(hf, size)
    hook = {"kind": "two-tier", "small": small, "big": wrap_title(big, bfont, hk["big_max_px"]), "big_size": size}
    hook["lines"] = ([small] if small else []) + hook["big"]
    sfont = ass_pil_font(hk["small_font_file"], hk["small_size"])
    hook["boxes"] = ([{"text": small, "y": hk["small_y"], "size": hk["small_size"],
                       "width_px": round(sfont.getlength(small))}] if small else []) + \
        [{"text": ln, "y": hk["big_y"] + n * round(size * 0.95), "size": size,
          "width_px": round(bfont.getlength(ln))} for n, ln in enumerate(hook["big"])]
    hook["land"] = 0.1
    return hook


def cutout_person(work: Path, seconds: float) -> tuple[Path | None, str]:
    """Cut the speaker out of the first `seconds` of base.mov with HyperFrames' remove-background
    (u2net_human_seg, MIT; ~3.5 frames/s on a CPU). Returns (ProRes 4444 .mov with alpha, "") or (None, why).
    Never downloads the model itself: that's a one-time 176 MB download the user OKs (doctor.py says how)."""
    npx = shutil.which("npx")
    if not npx:
        return None, "npx (Node.js) is not installed"
    if not CUTOUT_MODEL.exists():
        return None, f"the cut-out model isn't downloaded yet ({CUTOUT_MODEL.name}, 176 MB; see doctor.py)"
    run(["ffmpeg", "-v", "error", "-y", "-i", "base.mov", "-t", f"{seconds:.3f}", "-an", "-c:v", "libx264",
         "-crf", "10", "-pix_fmt", "yuv420p", "hook-src.mp4"], cwd=work)
    r = subprocess.run([npx, "--yes", "hyperframes", "remove-background", "hook-src.mp4", "-o", "cutout.mov"],
                       cwd=work, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not (work / "cutout.mov").exists():
        return None, f"remove-background failed: {(r.stderr or r.stdout)[-300:]}"
    return work / "cutout.mov", ""


def head_tops(cutout: Path) -> list[int]:
    """Top of the person in each frame of the cut-out (output px), from its alpha. A row counts once it is
    ~24 px wide, so stray specks above the hair are ignored."""
    w, h = 270, 480
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(cutout), "-vf", f"alphaextract,scale={w}:{h}",
                          "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
    tops = []
    for fr in np.frombuffer(raw, np.uint8)[: len(raw) // (w * h) * w * h].reshape(-1, h, w):
        rows = np.where((fr > 128).sum(1) >= 6)[0]
        if len(rows):
            tops.append(int(rows[0] * OUT_H / h))
    return tops


def layout_depth(top: str, big: str, label: str, hk: dict, head_top: int, zone: dict) -> dict | None:
    """Place the depth hook around the measured head top: BIG's bottom `overlap` of its height below the head
    top, the top line above it, the label across BIG's middle (but never on the head). None = doesn't fit."""
    d = hk["depth"]
    max_w = OUT_W - 2 * max(zone.get("side") or 0, 40) - 10
    bf, sf = hk["font_file"], hk["small_font_file"]
    t, b, w = ink_box(bf, 1000, big)
    size = 1000 * min(max_w / w, d["max_glyph_px"] / (b - t))
    t, b, w = ink_box(bf, size, big)
    gh = b - t
    ts = d["top_size"]
    if top:
        tt, tb, tw = ink_box(sf, ts, top)
        ts = ts * min(1.0, max_w / tw)
        tt, tb, tw = ink_box(sf, ts, top)
    top_block = (tb - tt + d["gap_px"]) if top else 0
    # BIG may not rise above the zone with the top line on it; if needed, shrink BIG to fit
    room = head_top + d["overlap"] * gh - gh - top_block - zone["top"]
    if room < 0:
        gh_fit = (head_top - top_block - zone["top"]) / (1 - d["overlap"])
        if gh_fit < d["min_glyph_px"]:
            return None
        size *= gh_fit / gh
        t, b, w = ink_box(bf, size, big)
        gh = b - t
    if gh < d["min_glyph_px"]:
        return None
    bottom = round(head_top + d["overlap"] * gh)
    if bottom > zone["bottom"]:
        return None
    big_y = bottom - b
    big_top = bottom - gh
    out = {"head_top": head_top, "overlap_px": bottom - head_top,
           "big": {"text": big, "size": round(size), "y": big_y, "y_from": big_y + d["rise_px"],
                   "ink": [big_top, bottom], "width_px": w}}
    if top:
        ty = big_top - d["gap_px"] - tb
        out["top"] = {"text": top, "size": round(ts), "y": ty, "ink": [ty + tt, ty + tb], "width_px": tw}
    else:
        out["top"] = None
    if label:
        ls = d["label_size"]
        lt, lb, lw = ink_box(sf, ls, label)
        ls *= min(1.0, 0.9 * w / lw)
        lt, lb, lw = ink_box(sf, ls, label)
        centre = min(big_top + d["label_at"] * gh, head_top - 8 - (lb - lt) / 2)
        ly = round(centre - (lt + lb) / 2)
        out["label"] = {"text": label, "size": round(ls), "y": ly, "ink": [ly + lt, ly + lb], "width_px": lw}
    else:
        out["label"] = None
    return out


def opacity_alpha(opacity: float) -> int:
    return max(0, min(255, round((1 - opacity) * 255)))


def ass_style(name: str, face: tuple[str, bool, bool], size: int, color: str, cap: dict, border: int = 1,
              outline_px: int | None = None, shadow_px: int | None = None, box: str | None = None) -> str:
    fam, bold, italic = face
    oc = ass_color(box or cap["outline"], 0 if box else opacity_alpha(cap.get("outline_opacity", 1.0)))
    bc = ass_color(box or cap.get("shadow_color", "#000000"),
                   0 if box else opacity_alpha(cap.get("shadow_opacity", 0.608)))
    op = cap["outline_px"] if outline_px is None else outline_px
    sp = cap["shadow_px"] if shadow_px is None else shadow_px
    return (f"Style: {name},{fam},{size},{ass_color(color)},{ass_color(color)},{oc},{bc},{-1 if bold else 0},"
            f"{-1 if italic else 0},0,0,100,100,0,0,{border},{op},{sp},5,60,60,0,1")


def write_ass(path: Path, chunks: list[dict], brand: dict, faces: dict, hook: dict | None) -> None:
    """faces: {'cap': (family, bold, italic), 'emph': ..., 'hook': ..., 'hook_small': ...}."""
    cap = brand["caption"]
    hk = brand["hook_title"]
    styles = [ass_style("Cap", faces["cap"], cap["size"], cap["color"], cap)]
    ev = []
    if cap["mode"] == "reveal":
        em = cap["emphasis"]
        styles.append(ass_style("Emph", faces["emph"], em["size"], em["color"], cap))
        a1 = lambda o: f"&H{o:02X}&"  # noqa: E731
        oa, sa = opacity_alpha(cap.get("outline_opacity", 1.0)), opacity_alpha(cap.get("shadow_opacity", 0.608))
        fade = cap["fade_ms"]
        blur = f"\\blur{cap['blur']}" if cap.get("blur") else ""
        pop = round(em.get("pop", 1.0) * 100)
        if em.get("glow"):  # a soft halo behind each key word: transparent fill, wide blurred outline
            styles.append(ass_style("Glow", faces["emph"], em["size"], em["glow"], cap,
                                    outline_px=em["glow_px"], shadow_px=0, box=em["glow"]))
        for ch in chunks:
            for ln in ch["lines"]:
                emph = ln["kind"] == "emph"
                parts, glow = [], []
                for w in ln["words"]:
                    t0 = max(0, round((w["start"] - ch["start"]) * 1000))
                    grow = f"\\fscx{pop}\\fscy{pop}" if emph and pop != 100 else ""
                    settle = f"\\t({t0},{t0 + 160},\\fscx100\\fscy100)" if grow else ""
                    parts.append(f"{{\\1a&HFF&\\3a&HFF&\\4a&HFF&{grow}\\t({t0},{t0 + fade},"
                                 f"\\1a&H00&\\3a{a1(oa)}\\4a{a1(sa)}){settle}}}{ass_escape(w['show'])}")
                    glow.append(f"{{\\1a&HFF&\\3a&HFF&\\4a&HFF&{grow}\\t({t0},{t0 + fade},"
                                f"\\3a{a1(opacity_alpha(em['glow_opacity']))}){settle}}}{ass_escape(w['show'])}")
                st = "Emph" if emph else "Cap"
                fs = f"\\fs{ln['size']}" if emph and ln["size"] != em["size"] else ""
                t = f"{fmt_ass_time(ch['start'])},{fmt_ass_time(ch['end'])}"
                if emph and em.get("glow"):
                    ev.append(f"Dialogue: 0,{t},Glow,,0,0,0,,{{\\pos(540,{ln['y']}){fs}\\blur{em['glow_blur']}"
                              f"\\fad(0,90)}}{' '.join(glow)}")
                ev.append(f"Dialogue: 1,{t},{st},,0,0,0,,{{\\pos(540,{ln['y']}){fs}{blur}\\fad(0,90)}}{' '.join(parts)}")
    else:
        hi = ass_color(cap["highlight"])
        base = ass_color(cap["color"])
        pos = f"\\pos(540,{cap['y']})"
        for ch in chunks:
            ws = ch["words"]
            for j, w in enumerate(ws):
                s = w["start"] if j else ch["start"]
                e = ws[j + 1]["start"] if j + 1 < len(ws) else ch["end"]
                parts = []
                for m, o in enumerate(ws):
                    t = ass_escape(o["show"])
                    if m == j:
                        sc = "\\fscx108\\fscy108" if cap["pop"] else ""
                        parts.append(f"{{\\c{hi}{sc}}}{t}{{\\c{base}\\fscx100\\fscy100}}")
                    else:
                        parts.append(t)
                ev.append(f"Dialogue: 0,{fmt_ass_time(s)},{fmt_ass_time(e)},Cap,,0,0,0,,{{{pos}}}{' '.join(parts)}")
    kind = hook.get("kind", hk["kind"]) if hook else None
    if hook and kind == "depth":  # front layer only: the top line + the label (BIG is in behind.ass)
        d = hook["depth"]
        if d["top"]:
            soft = dict(cap, outline_px=2, shadow_px=2)
            styles.append(ass_style("HookS", faces["hook_small"], d["top"]["size"], hk["small_color"], soft))
            ev.append(f"Dialogue: 3,{fmt_ass_time(0)},{fmt_ass_time(hk['seconds'])},HookS,,0,0,0,,"
                      f"{{\\pos(540,{d['top']['y']})\\blur4\\fad(150,250)}}{ass_escape(d['top']['text'])}")
        if d["label"]:
            styles.append(ass_style("HookL", faces["hook_small"], d["label"]["size"], hk["depth"]["label_color"],
                                    dict(cap, outline_px=6, shadow_px=4)))
            ev.append(f"Dialogue: 3,{fmt_ass_time(hk['depth']['label_delay'])},{fmt_ass_time(hk['seconds'])},"
                      f"HookL,,0,0,0,,{{\\pos(540,{d['label']['y']})\\blur2\\fscx130\\fscy130"
                      f"\\t(0,160,\\fscx100\\fscy100)\\fad(80,250)}}{ass_escape(d['label']['text'])}")
    elif hook and kind == "two-tier":
        soft = dict(cap, outline_px=2, shadow_px=2)
        styles.append(ass_style("HookS", faces["hook_small"], hk["small_size"], hk["small_color"], soft))
        styles.append(ass_style("HookB", faces["hook"], hook["big_size"], hk["big_color"], soft))
        blur = "\\blur4"
        if hook["small"]:
            ev.append(f"Dialogue: 3,{fmt_ass_time(0)},{fmt_ass_time(hk['seconds'])},HookS,,0,0,0,,"
                      f"{{\\pos(540,{hk['small_y']}){blur}\\fad(150,250)}}{ass_escape(hook['small'])}")
        if hk.get("glow"):
            em = cap["emphasis"]
            styles.append(ass_style("HookG", faces["hook"], hook["big_size"], hk["glow"], cap,
                                    outline_px=em["glow_px"] + 4, shadow_px=0, box=hk["glow"]))
        for n, line in enumerate(hook["big"]):
            y = hk["big_y"] + n * round(hook["big_size"] * 0.95)
            t = f"{fmt_ass_time(0.1)},{fmt_ass_time(hk['seconds'])}"
            if hk.get("glow"):
                ga = f"&H{opacity_alpha(cap['emphasis']['glow_opacity']):02X}&"
                ev.append(f"Dialogue: 2,{t},HookG,,0,0,0,,{{\\pos(540,{y})\\blur{cap['emphasis']['glow_blur'] + 4}"
                          f"\\1a&HFF&\\3a{ga}\\fad(200,250)}}{ass_escape(line)}")
            ev.append(f"Dialogue: 3,{t},HookB,,0,0,0,,{{\\pos(540,{y}){blur}\\fad(200,250)}}{ass_escape(line)}")
    elif hook:
        styles.append(ass_style("Hook", faces["hook"], hk["size"], hk["color"], cap, border=3, outline_px=18,
                                shadow_px=0, box=hk["box"]))
        txt = "\\N".join(ass_escape(l) for l in hook["lines"])
        ev.append(f"Dialogue: 3,{fmt_ass_time(0)},{fmt_ass_time(hk['seconds'])},Hook,,0,0,0,,"
                  f"{{\\pos(540,{hk['y']})\\fad(0,250)}}{txt}")
    write_ass_doc(path, styles, ev)


def write_ass_doc(path: Path, styles: list[str], ev: list[str]) -> None:
    path.write_text(
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n" + "\n".join(styles) +
        "\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n" +
        "\n".join(ev) + "\n", encoding="utf-8")


def write_depth_behind(path: Path, hook: dict, brand: dict, faces: dict) -> None:
    """The depth hook's BIG word (and its glow), rising from behind the head. Burned BEFORE the cut-out of
    the speaker is laid on top, so the head covers it."""
    cap, hk = brand["caption"], brand["hook_title"]
    d, bg = hook["depth"], hook["depth"]["big"]
    styles = [ass_style("HookB", faces["hook"], bg["size"], hk["big_color"], dict(cap, outline_px=3, shadow_px=0))]
    t = f"{fmt_ass_time(0.05)},{fmt_ass_time(hk['seconds'])}"
    mv = f"\\move(540,{bg['y_from']},540,{bg['y']},0,{hk['depth']['rise_ms']})"
    ev = []
    if hk.get("glow"):
        em = cap["emphasis"]
        bord = max(em["glow_px"] + 4, round(bg["size"] * 0.042))
        styles.append(ass_style("HookG", faces["hook"], bg["size"], hk["glow"], cap, outline_px=bord, shadow_px=0,
                                box=hk["glow"]))
        ga = f"&H{opacity_alpha(em['glow_opacity']):02X}&"
        ev.append(f"Dialogue: 0,{t},HookG,,0,0,0,,{{{mv}\\blur{round(bord * 0.85)}\\1a&HFF&\\3a{ga}"
                  f"\\fad(150,250)}}{ass_escape(bg['text'])}")
    ev.append(f"Dialogue: 1,{t},HookB,,0,0,0,,{{{mv}\\blur4\\fad(150,250)}}{ass_escape(bg['text'])}")
    write_ass_doc(path, styles, ev)


# --------------------------------------------------------------- end card ----
def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def render_end_card(ec: dict, contact: dict, out: Path) -> None:
    """Style layout + brand identity -> a 1080x1920 PNG: background (solid or radial gradient), logo, then
    contact lines, each = optional icon image or label (accent colour) + text, centred as a group."""
    bg = ec["background"]
    if isinstance(bg, list):
        c0, c1 = np.array(hex_rgb(bg[0]), float), np.array(hex_rgb(bg[1]), float)
        yy, xx = np.mgrid[0:OUT_H, 0:OUT_W]
        d = np.clip(np.sqrt(((xx - OUT_W / 2) / (OUT_W * 0.8)) ** 2 + ((yy - OUT_H * 0.47) / (OUT_H * 0.62)) ** 2),
                    0, 1) ** 1.3
        img = Image.fromarray((c0 * (1 - d[..., None]) + c1 * d[..., None]).astype(np.uint8), "RGB").convert("RGBA")
    else:
        img = Image.new("RGBA", (OUT_W, OUT_H), hex_rgb(bg) + (255,))
    if contact.get("logo") and Path(contact["logo"]).exists():
        lg = Image.open(contact["logo"]).convert("RGBA")
        s = ec["logo_width"] / lg.width
        lg = lg.resize((round(lg.width * s), round(lg.height * s)), Image.LANCZOS)
        img.alpha_composite(lg, (round(OUT_W / 2 - lg.width / 2), round(ec["logo_y"] - lg.height / 2)))
    text_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    shadow = Image.new("L", img.size, 0)
    td, sd = ImageDraw.Draw(text_layer), ImageDraw.Draw(shadow)
    dx, dy = ec.get("shadow_offset", [5, 8])
    y = ec["lines_y"]
    for ln in contact.get("lines", []):
        small = bool(ln.get("small"))
        size = ec["small_size"] if small else ec["text_size"]
        font = ImageFont.truetype(ec["text_font"], size)
        items, gap = [], round(size * 0.28)
        if ln.get("icon") and Path(ln["icon"]).exists():
            ic = Image.open(ln["icon"]).convert("RGBA")
            h = round(ec["icon_height"] * (0.5 if small else 1))
            ic = ic.resize((round(ic.width * h / ic.height), h), Image.LANCZOS)
            items.append(("img", ic, ic.width, None))
        if ln.get("label"):
            items.append(("text", ln["label"], font.getlength(ln["label"]), ec["label_color"]))
        items.append(("text", ln["text"], font.getlength(ln["text"]), ec["text_color"]))
        x = OUT_W / 2 - (sum(it[2] for it in items) + gap * (len(items) - 1)) / 2
        for kind, val, w, color in items:
            if kind == "img":
                pos = (round(x), round(y - val.height / 2))
                text_layer.alpha_composite(val, pos)
                shadow.paste(255, (pos[0] + dx, pos[1] + dy), val.getchannel("A"))
            else:
                td.text((x, y), val, font=font, fill=hex_rgb(color) + (255,), anchor="lm")
                sd.text((x + dx, y + dy), val, font=font, fill=255, anchor="lm")
            x += w + gap
        y += round(ec["line_gap"] * (0.65 if small else 1))
    if ec.get("shadow"):
        sh = shadow.filter(ImageFilter.GaussianBlur(ec.get("shadow_blur", 6)))
        sh = sh.point(lambda v: round(v * ec.get("shadow_opacity", 0.6)))
        img.alpha_composite(Image.merge("RGBA", (*[Image.new("L", img.size, 20)] * 3, sh)))
    img.alpha_composite(text_layer)
    img.convert("RGB").save(out)


def end_card_piece(ec: dict, contact: dict, work: Path, name: str) -> float:
    png = work / "endcard.png"
    render_end_card(ec, contact, png)
    frames = max(1, round(ec["seconds"] * FPS))
    dur = frames / FPS
    fade = f"fade=t=in:st=0:d={ec['fade_in']}:color={ec['fade_color']}," if ec.get("fade_in") else ""
    # format=yuv420p LAST: fade negotiates 4:4:4 from the PNG, and a 4:4:4 piece makes the final
    # render reconfigure (and stall) at the join
    run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", str(FPS), "-i", str(png),
         "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-frames:v", str(frames), "-t", f"{dur:.4f}",
         "-vf", f"{fade}format=yuv420p", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "17", "-c:a", "pcm_s16le", "-ac", "2", str(work / "pieces" / name)])
    return dur


# ------------------------------------------------------------------ audio ----
def pick_music(clip: dict, brand: dict, slug: str) -> Path | None:
    choice = clip.get("music", "auto")
    if choice == "none" or not brand["music"]["enabled"]:
        return None
    if choice not in (None, "auto"):
        return Path(choice)
    if brand["music"]["track"]:
        return Path(brand["music"]["track"])
    folder = brand["music"]["folder"]
    if not folder or not Path(folder).is_dir():
        return None
    tracks = sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".aac", ".flac"})
    if not tracks:
        return None
    return tracks[int(hashlib.md5(slug.encode()).hexdigest(), 16) % len(tracks)]


def loudnorm_stats(wav: Path, lufs: float, tp: float) -> dict:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(wav), "-af",
                        f"loudnorm=I={lufs}:TP={tp}:LRA=11:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    return json.loads(m.group(0))


def plan_sfx(sx: dict, shots: list[dict], out_words: list[dict], chunks: list[dict], hook: dict | None,
             hook_s: float, content_end: float, broll: list[dict]) -> list[dict]:
    """Where the sound effects go ("at" = the moment each one peaks or lands)."""
    ev = []
    if hook and sx["hit"]:
        land = hook.get("land", 0.1)
        if hook.get("kind") == "depth" and sx["riser"]:
            ev.append({"kind": "riser", "at": land, "db": sx["riser_db"], "why": "hook rises"})
        ev.append({"kind": "hit", "at": land, "db": sx["hit_db"], "why": "hook lands"})
    calm = hook_s + 0.3 if hook else 0.3  # the hook has its own sounds
    ends = [(w["end"], w["text"]) for w in out_words]

    def after_sentence(t: float) -> bool:
        prev = [txt for e, txt in ends if e <= t + 0.05]
        return bool(prev) and prev[-1].rstrip()[-1:] in ".?!…"

    cands = [(b["out_start"], after_sentence(b["out_start"])) for a, b in zip(shots, shots[1:])
             if b["zoom"] != a["zoom"]]
    cands += [(br["start"], True) for br in broll]  # a B-roll cutaway is a cut too
    cands = [c for c in cands if calm <= c[0] <= content_end - 0.4]
    whooshes = []
    if sx["whoosh"]:
        for t, _ in sorted(cands, key=lambda c: (not c[1], c[0])):  # sentence ends first, then the rest
            if all(abs(t - u) >= sx["whoosh_gap_s"] for u in whooshes):
                whooshes.append(t)
        for n, t in enumerate(sorted(whooshes)):  # peak 1 frame before the cut: the sound leads the picture
            ev.append({"kind": "whoosh", "at": round(t - 1 / FPS, 3), "db": sx["whoosh_db"], "variant": n % 3,
                       "why": f"cut at {t:.2f}s"})
    if sx["pop"]:
        last = -9.0
        for c in chunks:
            for ln in c.get("lines", []):
                if ln["kind"] != "emph":
                    continue
                t = max(min(w["start"] for w in ln["words"]), c["start"])
                if t < calm or t - last < sx["pop_gap_s"] or any(abs(t - u) < 0.45 for u in whooshes):
                    continue
                ev.append({"kind": "pop", "at": round(t, 3), "db": sx["pop_db"], "why": ln["text"]})
                last = t
    return sorted(ev, key=lambda e: e["at"])


# ------------------------------------------------------------------- main ----
def build(plan: dict, clip: dict, brand: dict, words: list[dict]) -> None:
    src = Path(plan["source"])
    slug = clip["slug"]
    work = Path(plan["work"]) / slug
    deliver = Path(plan["deliver"])
    if work.exists():
        shutil.rmtree(work)
    (work / "pieces").mkdir(parents=True)
    (work / "fonts").mkdir()
    deliver.mkdir(parents=True, exist_ok=True)

    ed = brand["edit"]
    pieces = plan_pieces(words, clip["segments"], ed)
    if not pieces:
        raise SystemExit(f"{slug}: no words inside the planned segments")
    W, H = display_size(video_stream(probe(src)))
    faces = segment_faces(src, pieces)
    grade, grade_info = grade_filter(brand["grade"], src, pieces)
    gchain = f",{grade}" if grade else ""

    # punch-in alternates per piece; very short pieces keep the previous zoom (no flicker). With edit.rhythm,
    # zoom levels cycle through rhythm.zooms and long takes get extra zoom cuts (video only; the audio of a
    # piece stays one continuous stream)
    rh = ed.get("rhythm") or {}
    rhythm = bool(rh.get("enabled"))
    zoom, flip, z_idx = 1.0, False, 0
    base_frac = ((H * OUT_W / OUT_H) * H) / (W * H) if W / H > OUT_W / OUT_H else (W * W * OUT_H / OUT_W) / (W * H)
    # Safe zone (caption.safe_zone, e.g. Meta's ad zone): if the caption block can't fit between the lowest
    # chin and the zone's bottom on the tightest shot, the captions go ABOVE the head instead, and every
    # punch-in grows around the top of the head so the head never rises into them.
    capc = brand["caption"]
    zone = capc.get("safe_zone")
    anchor = "face"
    if zone and capc["y"] == "auto" and capc["mode"] == "reveal":
        zmax = max(rh["zooms"]) if rhythm else max(1.0, ed["punch_in"] or 1.0)
        for f in faces.values():
            zc = (rh.get("max_face_area", 1.0) / (f["area"] / base_frac)) ** 0.5 if rhythm and f.get("area") else 9.0
            m = face_marks(W, H, f, crop_filter(W, H, f, max(1.0, min(zmax, zc)))[1])
            if m and m["chin_y"] + 20 + 2 * reveal_half(capc) > zone["bottom"] - 4:
                anchor = "head_top"
    offset = 0.0
    out_words, seams, zoom_cuts, shots = [], [], [], []
    for k, p in enumerate(pieces):
        # whole frames only: 1 frame = 1600 audio samples at 48k, so A/V stay locked across the concat
        frames = max(1, round((p["src_end"] - p["src_start"]) * FPS))
        dur = frames / FPS
        p["src_end"] = round(p["src_start"] + dur, 4)
        face = faces[p["seg"]]
        cap_z = (rh.get("max_face_area", 1.0) / (face["area"] / base_frac)) ** 0.5 if face.get("area") else 9.0
        level = lambda n: max(1.0, min(rh["zooms"][n % len(rh["zooms"])], cap_z))  # noqa: E731
        if k and ed["punch_in"] and dur >= ed["min_piece_for_punch"]:
            if rhythm:
                z_idx += 1
                zoom = level(z_idx)
            else:
                flip = not flip
                zoom = ed["punch_in"] if flip else 1.0
        starts = [0]  # sub-shot starts, in frames from the piece start
        if rhythm:
            last = 0.0
            pw = p["words"]
            for a, b in zip(pw, pw[1:]):
                g = (words[a]["end"] + words[b]["start"]) / 2 - p["src_start"]
                if dur - g < rh["min_shot_s"]:
                    break
                sentence = words[a]["text"].rstrip()[-1:] in ".?!…"
                if (rh.get("at_sentence") and sentence and g - last >= rh["min_shot_s"]) or g - last >= rh["every_s"]:
                    starts.append(round(g * FPS))
                    last = g
        subs = []
        for j, f0 in enumerate(starts):
            if j:
                z_idx += 1
                zoom = level(z_idx)
            f1 = starts[j + 1] if j + 1 < len(starts) else frames
            vf, rect = crop_filter(W, H, face, zoom, anchor)
            m = face_marks(W, H, face, rect)
            subs.append({"f0": f0, "f1": f1, "zoom": round(zoom, 3), "vf": vf, "crop": list(rect),
                         "chin_y": m.get("chin_y"), "mouth_y": m.get("mouth_y"), "face_top_y": m.get("face_top_y"),
                         "head_top_y": m.get("head_top_y")})
        p.update(zoom=subs[0]["zoom"], out_start=round(offset, 3), out_end=round(offset + dur, 3),
                 crop=subs[0]["crop"], chin_y=max((s["chin_y"] for s in subs if s["chin_y"]), default=None))
        for s in subs:
            shots.append({"seg": p["seg"], "out_start": round(offset + s["f0"] / FPS, 3),
                          "out_end": round(offset + s["f1"] / FPS, 3), "zoom": s["zoom"], "crop": s["crop"],
                          "chin_y": s["chin_y"], "mouth_y": s["mouth_y"], "face_top_y": s["face_top_y"],
                          "head_top_y": s["head_top_y"]})
            if s["f0"]:
                zoom_cuts.append(round(offset + s["f0"] / FPS, 3))
        fade = f"afade=t=in:st=0:d=0.03,afade=t=out:st={max(dur - 0.03, 0):.3f}:d=0.03"
        out_piece = str(work / "pieces" / f"p{k:03d}.mov")
        if len(subs) == 1:
            run(["ffmpeg", "-v", "error", "-y", "-ss", f"{p['src_start']:.3f}", "-i", str(src), "-t", f"{dur:.3f}",
                 "-vf", subs[0]["vf"] + f"{gchain},fps={FPS},format=yuv420p",
                 "-af", f"aresample=48000,{fade}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
                 "-c:a", "pcm_s16le", "-ac", "2", out_piece])
        else:
            fc = [f"[0:v]fps={FPS},split={len(subs)}" + "".join(f"[s{j}]" for j in range(len(subs)))]
            for j, s in enumerate(subs):
                end = f":end_frame={s['f1']}" if j + 1 < len(subs) else ""
                fc.append(f"[s{j}]trim=start_frame={s['f0']}{end},setpts=PTS-STARTPTS,{s['vf']}{gchain},"
                          f"format=yuv420p[v{j}]")
            fc.append("".join(f"[v{j}]" for j in range(len(subs))) + f"concat=n={len(subs)}:v=1:a=0[v]")
            fc.append(f"[0:a]aresample=48000,{fade}[a]")
            run(["ffmpeg", "-v", "error", "-y", "-ss", f"{p['src_start']:.3f}", "-i", str(src), "-t", f"{dur:.3f}",
                 "-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]", "-frames:v", str(frames),
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
                 "-c:a", "pcm_s16le", "-ac", "2", out_piece])
        for i in p["words"]:
            w = words[i]
            out_words.append({"i": i, "text": w["text"], "start": round(w["start"] - p["src_start"] + offset, 3),
                              "end": round(min(w["end"], p["src_end"]) - p["src_start"] + offset, 3)})
        if k:
            seams.append(round(offset, 3))
        offset += dur
    content_end = offset
    names = [f"p{k:03d}.mov" for k in range(len(pieces))]
    ec, contact = brand["end_card"], brand["contact"]
    card_s = 0.0
    if ec["enabled"]:
        if not (contact.get("logo") or contact.get("lines")) and brand["logo"].get("path"):
            contact = dict(contact, logo=brand["logo"]["path"])
        if contact.get("logo") or contact.get("lines"):
            card_s = end_card_piece(ec, contact, work, "zz_endcard.mov")
            names.append("zz_endcard.mov")
            seams.append(round(content_end, 3))
        else:
            print(f"{slug}: style '{brand['style']}' has an end card but the brand profile has no contact "
                  f"logo/lines; skipped it")
    # exact durations come from the encoded pieces (frame rounding), so re-measure
    (work / "pieces.txt").write_text("".join(f"file 'pieces/{n}'\n" for n in names))
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", "pieces.txt", "-c", "copy",
         "base.mov"], cwd=work)
    total = float(probe(work / "base.mov")["format"]["duration"])

    # ---- audio: voice chain + ducked music bed -> mix_base.wav (sound effects + loudnorm come after captions)
    au = brand["audio"]
    music = pick_music(clip, brand, slug)
    voice = "highpass=f=80,acompressor=threshold=-20dB:ratio=3:attack=5:release=150:makeup=2" \
        if au["voice_cleanup"] else "anull"
    if music:
        mv = brand["music"]["volume_db"]
        bed = (f"[1:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total:.3f},asetpts=N/SR/TB,"
               f"volume={mv}dB,afade=t=in:d=0.6,afade=t=out:st={max(total - 1.5, 0):.3f}:d=1.5[bed]")
        if brand["music"]["duck"]:
            fg = (f"[0:a]{voice},asplit=2[v][key];{bed};"
                  "[bed][key]sidechaincompress=threshold=0.03:ratio=6:attack=10:release=350[duck];"
                  "[v][duck]amix=inputs=2:normalize=0:duration=first[a]")
        else:
            fg = f"[0:a]{voice}[v];{bed};[v][bed]amix=inputs=2:normalize=0:duration=first[a]"
        run(["ffmpeg", "-v", "error", "-y", "-i", "base.mov", "-stream_loop", "-1", "-i", str(music),
             "-filter_complex", fg, "-map", "[a]", "-c:a", "pcm_s16le", "-ar", "48000", "mix_base.wav"], cwd=work)
    else:
        run(["ffmpeg", "-v", "error", "-y", "-i", "base.mov", "-af", voice, "-c:a", "pcm_s16le", "-ar", "48000",
             "mix_base.wav"], cwd=work)

    # ---- captions + hook title
    cap = dict(brand["caption"])
    band = cap.get("safe_zone") or {"top": 220, "bottom": 1500, "side": 0}
    chins = [p["chin_y"] for p in pieces if p.get("chin_y")]
    place = "below"
    if cap["mode"] == "reveal" and cap["y"] == "auto":
        # the style's preferred height (chest level on a medium shot), pushed down to clear the lowest chin
        # on tighter shots; half = worst-case block (small + emphasis + small line). With a safe zone that
        # can't hold the block under the chin, the block sits above the head (see anchor above).
        half, margin = reveal_half(cap), 0.06 * cap["size"] + 2
        if anchor == "head_top":
            place = "above"
            tops = [s["head_top_y"] for s in shots if s.get("head_top_y") is not None]
            cap["y"] = round(max(min(tops) - half - 20 if tops else 0, band["top"] + half + margin))
        else:
            lo, hi = cap.get("y_pref", 1110), band["bottom"] - half - margin  # bottom line inside the band
            cap["y"] = round(min(max(max(chins) + half + 20 if chins else lo, lo), hi))
    elif cap["y"] == "auto":  # just under the lowest chin of any shot, inside the safe band
        lo, hi = 1100, band["bottom"] - cap["size"] * 0.6
        cap["y"] = round(min(max(max(chins) + cap["size"] * 0.8, lo), hi)) if chins else 1300
    brand = dict(brand, caption=cap)
    fonts_used = {}

    def use_font(key: str, file: str) -> Path:
        f = Path(file)
        if not (work / "fonts" / f.name).exists():
            shutil.copy(f, work / "fonts" / f.name)
        fonts_used[key] = font_face(f)
        return f

    cap_font = ass_pil_font(use_font("cap", cap["font_file"]), cap["size"])
    if cap["mode"] == "reveal":
        em = cap["emphasis"]
        emph_font = ass_pil_font(use_font("emph", em["font_file"]), em["size"])
        forced = clip.get("emphasis", "auto")
        forced = set(forced) if isinstance(forced, list) else forced
        auto = forced != "none" and clip.get("emphasis_auto", True)
        if em["enabled"] and em.get("pick") == "stress" and auto:
            stress = word_stress(src, [w["i"] for w in out_words], words)
            for w in out_words:
                w["stress"] = stress.get(w["i"], 0.0)
        chunks = build_reveal(out_words, cap, cap_font, emph_font, brand["language"], forced, auto)
    else:
        chunks = build_captions(out_words, cap, cap_font, brand["language"])
    hook = None
    hk = brand["hook_title"]
    hook_note = None
    if clip.get("hook_title") and hk["enabled"]:
        hf = use_font("hook", hk["font_file"])
        kind = clip.get("hook_kind") or hk["kind"]
        if kind == "depth":  # "top line | BIG | label"; "top | BIG label" and "BIG label" work too
            use_font("hook_small", hk["small_font_file"])
            parts = hook_parts(clip["hook_title"], hk["uppercase"])
            if len(parts) >= 3:
                top, big, label = parts[0], parts[1], " ".join(parts[2:])
            else:
                top = parts[0] if len(parts) == 2 else ""
                big, _, label = parts[-1].partition(" ")
            cut, why = cutout_person(work, hk["seconds"] + 0.1)
            tops = head_tops(cut) if cut else []
            lay = layout_depth(top, big, label.strip(), hk, int(statistics.median(tops)), band) if tops else None
            if lay:
                hook = {"kind": "depth", "depth": lay, "land": 0.05 + hk["depth"]["rise_ms"] / 1000,
                        "lines": [x["text"] for x in (lay["top"], lay["big"], lay["label"]) if x],
                        "boxes": [{"text": x["text"], "y": x["y"], "size": x["size"], "width_px": x["width_px"],
                                   "top": x["ink"][0], "bottom": x["ink"][1], **({"behind": True} if x is lay["big"]
                                                                                 else {})}
                                  for x in (lay["top"], lay["big"], lay["label"]) if x]}
                hook_note = (f"depth hook: '{big}' behind the head (head top y={lay['head_top']}, "
                             f"{lay['overlap_px']}px hidden)")
            else:
                why = why or ("no person found in the cut-out" if not tops else
                              f"'{big}' can't be big enough behind the head (head top y={statistics.median(tops):.0f})")
                hook_note = f"depth hook fell back to two-tier: {why}"
                kind = "two-tier"
        if kind == "two-tier":  # "small part | BIG WORD(S)"; a depth title "a | B | c" reads "a" / "B c"
            use_font("hook_small", hk["small_font_file"])
            parts = hook_parts(clip["hook_title"], hk["uppercase"])
            small, big = (parts[0], " ".join(parts[1:])) if len(parts) > 1 else ("", parts[0])
            hook = two_tier_hook(small, big, hk, hf)
        elif kind != "depth":
            hfont = ass_pil_font(hf, hk["size"])
            title = " ".join(hook_parts(clip["hook_title"], hk["uppercase"]))
            hook = {"kind": "box", "land": 0.1, "lines": wrap_title(title, hfont, hk["max_line_px"] - 36)}
            n = len(hook["lines"])
            hook["boxes"] = [{"text": ln, "y": round(hk["y"] + (j - (n - 1) / 2) * hk["size"]), "size": hk["size"],
                              "width_px": round(hfont.getlength(ln)) + 36} for j, ln in enumerate(hook["lines"])]
    srt_chunks = chunks
    if place == "above" and hook:
        # captions above the head share the top of the frame with the hook: the hook has it to itself, and
        # captions start when it clears (the .srt keeps every word)
        hold, kept = hk["seconds"], []
        for c in chunks:
            if c["end"] > hold + 0.05:
                kept.append(dict(c, start=max(c["start"], hold)))
        chunks = kept
    write_ass(work / "captions.ass", chunks, brand, fonts_used, hook)

    # ---- final: depth hook (BIG behind the head), B-roll cutaways, logo overlay, captions LAST, audio
    inputs = ["-i", "base.mov", "-i", "mix.wav"]
    graph, v, n_in = [], "[0:v]", 2
    if hook and hook.get("kind") == "depth":
        write_depth_behind(work / "behind.ass", hook, brand, fonts_used)
        inputs += ["-i", "cutout.mov"]
        graph.append("[0:v]subtitles=behind.ass:fontsdir=fonts[vd]")
        graph.append("[vd][2:v]overlay=0:0:format=yuv444:eof_action=pass[vc]")
        v, n_in = "[vc]", 3
    broll = []
    by_word = {w["i"]: w["start"] for w in out_words}
    for k, b in enumerate(clip.get("broll", [])):
        t0 = by_word.get(b["at_word"]) if "at_word" in b else b.get("at")
        if t0 is None or not Path(b["file"]).exists():
            print(f"{slug}: skipped B-roll {b.get('file')} (word {b.get('at_word')} not in the cut, or no file)")
            continue
        t1 = min(t0 + b.get("seconds", 2.0), content_end)
        if t1 - t0 < 0.4:
            continue
        inputs += ["-ss", f"{b.get('from', 0):.3f}", "-t", f"{t1 - t0 + 0.2:.3f}", "-i", str(Path(b["file"]))]
        graph.append(f"[{n_in}:v]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},"
                     f"setsar=1,fps={FPS}{gchain},format=yuv420p,setpts=PTS-STARTPTS+{t0:.3f}/TB[b{k}]")
        graph.append(f"{v}[b{k}]overlay=0:0:enable='between(t,{t0:.3f},{t1:.3f})':eof_action=pass[vb{k}]")
        v, n_in = f"[vb{k}]", n_in + 1
        broll.append({"file": b["file"], "start": round(t0, 3), "end": round(t1, 3)})
    lg = brand["logo"]
    if lg["enabled"] and lg["path"] and Path(lg["path"]).exists():
        inputs += ["-i", str(lg["path"])]
        lx = "60" if "left" in lg["corner"] else "W-w-60"
        ly = "230" if "top" in lg["corner"] else "H-h-420"
        graph.append(f"[{n_in}:v]scale={lg['width']}:-1,format=rgba,colorchannelmixer=aa={lg['opacity']}[lg]")
        graph.append(f"{v}[lg]overlay={lx}:{ly}:enable='lt(t,{content_end:.3f})'[vl]")
        v = "[vl]"
    graph.append(f"{v}subtitles=captions.ass:fontsdir=fonts[v]")
    vf = ";".join(graph)

    # ---- sound effects on top of voice + music, then 2-pass loudnorm of the whole mix
    sx = brand["sfx"]
    sfx_events = []
    if sx["enabled"] and clip.get("sfx", "auto") != "none":
        sfx_events = plan_sfx(sx, shots, out_words, chunks, hook, hk["seconds"], content_end, broll)
    if sfx_events:
        vdb = sfxlib.voice_level_db(work / "mix_base.wav", [(w["start"], w["end"]) for w in out_words])
        sfxlib.write_wav(work / "sfx.wav", sfxlib.render(sfx_events, total, vdb))
        run(["ffmpeg", "-v", "error", "-y", "-i", "mix_base.wav", "-i", "sfx.wav", "-filter_complex",
             "[0:a][1:a]amix=inputs=2:normalize=0:duration=first[a]", "-map", "[a]", "-c:a", "pcm_s16le",
             "mix.wav"], cwd=work)
    else:
        shutil.copy(work / "mix_base.wav", work / "mix.wav")
    ln = loudnorm_stats(work / "mix.wav", au["lufs"], au["true_peak"])
    loud = (f"loudnorm=I={au['lufs']}:TP={au['true_peak']}:LRA=11:measured_I={ln['input_i']}:"
            f"measured_TP={ln['input_tp']}:measured_LRA={ln['input_lra']}:measured_thresh={ln['input_thresh']}:"
            f"offset={ln['target_offset']}:linear=true,aresample=48000")
    final = deliver / f"{slug}.mp4"
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", f"{vf};[1:a]{loud}[a]",
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
         str(final.resolve())], cwd=work)

    # ---- side outputs
    srt = []
    for n, ch in enumerate(srt_chunks, 1):
        srt.append(f"{n}\n{fmt_srt_time(ch['start'])} --> {fmt_srt_time(ch['end'])}\n{ch['text']}\n")
    (deliver / f"{slug}.srt").write_text("\n".join(srt), encoding="utf-8")
    cover_t = min(1.0, total / 2)
    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{cover_t}", "-i", str(final), "-frames:v", "1", "-q:v", "2",
         str(deliver / f"{slug}-cover.jpg")])
    script = " ".join(w["text"] for w in out_words)
    (work / "script.txt").write_text(script + "\n", encoding="utf-8")
    manifest = {
        "slug": slug, "source": str(src), "final": str(final), "duration": round(total, 3),
        "purpose": clip.get("purpose", "organic"), "hook_title": clip.get("hook_title"),
        "brand": plan["brand"], "source_size": [W, H], "music": str(music) if music else None,
        "seams": seams, "pieces": pieces, "faces": {str(k): v for k, v in faces.items()},
        "shots": shots, "zoom_cuts": zoom_cuts,
        "emphasis_words": [dict(text=ln["text"], start=c["start"], **({"stress": ln["words"][0]["stress"]}
                                                                      if "stress" in ln["words"][0] else {}))
                           for c in chunks for ln in c["lines"] if ln["kind"] == "emph"],
        "first_word_at": out_words[0]["start"], "last_word_end": out_words[-1]["end"],
        # a sentence end = terminal punctuation, the end of the recording, or a real pause before the next word
        "ends_on_sentence": (out_words[-1]["text"].rstrip()[-1:] in ".?!…" or out_words[-1]["i"] + 1 >= len(words)
                             or words[out_words[-1]["i"] + 1]["start"] - words[out_words[-1]["i"]]["end"] >= 0.6),
        "words": out_words,
        "captions": [{k: v for k, v in c.items() if k not in ("words", "lines")} for c in chunks],
        "caption_lines": [dict({k: v for k, v in ln.items() if k != "words"}, start=c["start"], end=c["end"])
                          for c in chunks for ln in c["lines"]],
        "caption_mode": cap["mode"], "caption_y": cap["y"], "caption_size": cap["size"],
        "max_line_px": cap["max_line_px"],
        "hook_lines": hook["lines"] if hook else None,
        "hook_kind": hook.get("kind", hk["kind"]) if hook else None,
        "hook_boxes": hook.get("boxes") if hook else None, "hook_seconds": hk["seconds"] if hook else None,
        "hook_depth": ({k: hook["depth"][k] for k in ("head_top", "overlap_px")} | {"cutout": "cutout.mov"})
        if hook and hook.get("kind") == "depth" else None,
        "hook_note": hook_note,
        "sfx": sfx_events, "mix_base": "mix_base.wav" if sfx_events else None,
        "safe_zone": cap.get("safe_zone"), "caption_place": place, "zoom_anchor": anchor,
        "style": brand["style"], "grade": dict(grade_info, filter=grade) if grade else None,
        "content_end": round(content_end, 3), "end_card_seconds": round(card_s, 3), "broll": broll,
        "lufs": brand["audio"]["lufs"], "length": brand["length"],
        "qa_min_voice_over_music_db": brand["qa"]["min_voice_over_music_db"],
        "loudnorm_input": {"I": ln["input_i"], "TP": ln["input_tp"]},
    }
    (work / "build.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    for f in (work / "pieces").iterdir():
        f.unlink()
    print(f"{slug} [{brand['style']}]: {total:.1f}s, {len(pieces)} pieces, {len(seams)} cuts"
          f"{f' + {len(zoom_cuts)} zoom cuts' if zoom_cuts else ''}, "
          f"music={music.name if music else 'none'}"
          f"{f', end card {card_s:.1f}s' if card_s else ''}{f', {len(broll)} B-roll' if broll else ''}"
          f"{f', {len(sfx_events)} sound effects' if sfx_events else ''}"
          f"{f'; {hook_note}' if hook_note else ''}\n  -> {final}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("plan", type=Path)
    ap.add_argument("--only", default=None, help="build just this slug")
    ap.add_argument("--style", default=None, help=f"override the style for every clip ({', '.join(available_styles())})")
    a = ap.parse_args()
    plan = json.loads(a.plan.read_text(encoding="utf-8"))
    words = load_words(Path(plan["transcript"]))
    for clip in plan["clips"]:
        if a.only and clip["slug"] != a.only:
            continue
        brand = load_brand(Path(plan["brand"]), a.style or clip.get("style") or plan.get("style"))
        build(plan, clip, brand, words)


if __name__ == "__main__":
    main()
