# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "opencv-python-headless<5", "pillow", "fonttools"]
# ///
"""Build finished vertical clips from a cut plan.

  uv run build_clip.py <plan.json> [--only <slug>]

plan.json:
{
  "source": "C:/.../raw.mp4",
  "transcript": "<work>/transcripts/raw.json",
  "brand": "C:/.../video-style.json",
  "work": "<project>/work",
  "deliver": "<project>/deliver",
  "clips": [
    {"slug": "3-sistemas", "hook_title": "3 sistemas que ...", "purpose": "organic",
     "segments": [{"words": [0, 41]}, {"start": 20.5, "end": 31.0}],
     "music": "auto"}            # "auto" | "none" | "<file path>"
  ]
}

Per clip, in this order (order is load-bearing):
  1. snap every segment to word boundaries, drop hesitation fillers, close pauses
     longer than edit.max_pause (jump cuts), pad each piece edge
  2. per piece: face-centred 9:16 crop (+ alternating punch-in), 30ms audio fades
  3. lossless concat -> base.mp4
  4. voice clean-up + music bed ducked under the voice -> two-pass loudnorm
  5. logo overlay, then branded word-by-word captions burned LAST
Outputs: <deliver>/<slug>.mp4, <slug>.srt, <slug>-cover.jpg; <work>/<slug>/build.json
(seams, pieces, face boxes, caption chunks) which qa.py reads.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from common import (ass_color, digits_for, display_size, fmt_ass_time, fmt_srt_time, load_words, resolve_font,  # noqa: E402
                    probe, run, video_stream)

OUT_W, OUT_H, FPS = 1080, 1920, 30
DEFAULTS = {
    "language": "es",
    "caption": {"font_file": "C:/Windows/Fonts/ariblk.ttf", "size": 78, "uppercase": False,
                "words_per_chunk": 3, "max_line_px": 800, "color": "#FFFFFF", "highlight": "#FFD400",
                "outline": "#000000", "outline_px": 7, "shadow_px": 0, "y": "auto",
                "strip_punctuation": True, "pop": True},
    "hook_title": {"enabled": True, "font_file": None, "size": 62, "color": "#FFFFFF", "box": "#000000",
                   "y": 430, "seconds": 3.0, "uppercase": False, "max_line_px": 860},
    "logo": {"enabled": False, "path": None, "width": 130, "corner": "top-left", "opacity": 0.9},
    "music": {"enabled": True, "folder": None, "track": None, "volume_db": -22, "duck": True},
    "audio": {"lufs": -14, "true_peak": -1.5, "voice_cleanup": True},
    "length": {"min": 15, "max": 60},
    "edit": {"pad_in": 0.06, "pad_out": 0.12, "max_pause": 0.4, "drop_fillers": True,
             "punch_in": 1.12, "min_piece_for_punch": 0.8},
    "compliance": {"profile": "none", "extra_terms": []},
}


def merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def load_brand(path: Path) -> dict:
    b = merge(DEFAULTS, json.loads(path.read_text(encoding="utf-8")))
    root = path.parent
    for sect, key in [("logo", "path"), ("music", "folder"), ("music", "track")]:
        v = b[sect].get(key)
        if v and not Path(v).is_absolute():
            b[sect][key] = str((root / v).resolve())
    b["caption"]["font_file"] = resolve_font(b["caption"]["font_file"], root)
    hf = b["hook_title"]["font_file"]
    b["hook_title"]["font_file"] = resolve_font(hf, root) if hf else b["caption"]["font_file"]
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


def chin_out_y(W: int, H: int, face: dict, rect: tuple[int, int, int, int]) -> float | None:
    """Bottom of the face box in output pixels (Haar boxes run brow to chin)."""
    if not face.get("area"):
        return None
    side = (face["area"] * W * H) ** 0.5
    x, y, w, h = rect
    return (face["cy"] * H + side / 2 - y) * OUT_H / h


def crop_filter(W: int, H: int, face: dict, zoom: float) -> tuple[str, tuple[int, int, int, int]]:
    if W / H > OUT_W / OUT_H:  # wider than 9:16 -> crop width
        cw, ch = H * OUT_W / OUT_H, H
    else:
        cw, ch = W, W * OUT_H / OUT_W
    fx, fy = face["cx"] * W, face["cy"] * H
    x0 = min(max(fx - cw / 2, 0), W - cw)
    y0 = min(max(fy - ch * 0.4, 0), H - ch)
    zw, zh = cw / zoom, ch / zoom
    x = x0 + (fx - x0) * (1 - 1 / zoom)
    y = y0 + (fy - y0) * (1 - 1 / zoom)
    x = min(max(x, x0), x0 + cw - zw)
    y = min(max(y, y0), y0 + ch - zh)
    ev = lambda v: int(v) // 2 * 2  # noqa: E731
    rect = (ev(x), ev(y), ev(zw), ev(zh))
    return f"crop={rect[2]}:{rect[3]}:{rect[0]}:{rect[1]},scale={OUT_W}:{OUT_H}:flags=lanczos,setsar=1", rect


# --------------------------------------------------------------- captions ----
PUNCT = re.compile(r"[^\w\s$%'’\-áéíóúüñÁÉÍÓÚÜÑ]")


def clean_word(t: str, cap: dict) -> str:
    if cap["strip_punctuation"]:
        t = PUNCT.sub("", t)
    return t.upper() if cap["uppercase"] else t


def ass_escape(t: str) -> str:
    return t.replace("\\", "").replace("{", "(").replace("}", ")")


def font_family(path: Path) -> str:
    """Legacy family name (name ID 1), e.g. 'Arial Black', which is what libass matches.
    FreeType/PIL report the typographic family ('Arial'), and libass then falls back to regular Arial.
    Use static TTF/OTF files; variable fonts select their default weight."""
    from fontTools.ttLib import TTFont
    names = TTFont(str(path), fontNumber=0, lazy=True)["name"]
    for nid in (1, 4):
        rec = names.getName(nid, 3, 1, 0x409) or names.getName(nid, 1, 0, 0)
        if rec:
            return rec.toUnicode()
    return ImageFont.truetype(str(path), 10).getname()[0]


def build_captions(out_words: list[dict], cap: dict, font: ImageFont.FreeTypeFont,
                   lang: str = "es") -> list[dict]:
    pop = 1.08 if cap["pop"] else 1.0
    limit = cap["max_line_px"] / pop - 2 * cap["outline_px"]
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
        out.append({"start": ch[0]["start"], "end": end, "words": ch, "text": text,
                    "width_px": round(font.getlength(text) * pop + 2 * cap["outline_px"])})
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


def write_ass(path: Path, chunks: list[dict], brand: dict, cap_family: str, hook: dict | None) -> None:
    cap = brand["caption"]
    hk = brand["hook_title"]
    hi = ass_color(cap["highlight"])
    base = ass_color(cap["color"])
    styles = [
        f"Style: Cap,{cap_family},{cap['size']},{base},{base},{ass_color(cap['outline'])},&H64000000,"
        f"0,0,0,0,100,100,0,0,1,{cap['outline_px']},{cap['shadow_px']},5,60,60,0,1",
    ]
    if hook:
        styles.append(
            f"Style: Hook,{hook['family']},{hk['size']},{ass_color(hk['color'])},{ass_color(hk['color'])},"
            f"{ass_color(hk['box'])},{ass_color(hk['box'])},0,0,0,0,100,100,0,0,3,18,0,5,60,60,0,1")
    ev = []
    if hook:
        txt = "\\N".join(ass_escape(l) for l in hook["lines"])
        ev.append(f"Dialogue: 1,{fmt_ass_time(0)},{fmt_ass_time(hk['seconds'])},Hook,,0,0,0,,"
                  f"{{\\pos(540,{hk['y']})\\fad(0,250)}}{txt}")
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
    path.write_text(
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n" + "\n".join(styles) +
        "\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n" +
        "\n".join(ev) + "\n", encoding="utf-8")


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

    # punch-in alternates per piece; very short pieces keep the previous zoom (no flicker)
    zoom, flip = 1.0, False
    offset = 0.0
    out_words, seams = [], []
    for k, p in enumerate(pieces):
        # whole frames only: 1 frame = 1600 audio samples at 48k, so A/V stay locked across the concat
        dur = max(1, round((p["src_end"] - p["src_start"]) * FPS)) / FPS
        p["src_end"] = round(p["src_start"] + dur, 4)
        if k and ed["punch_in"] and dur >= ed["min_piece_for_punch"]:
            flip = not flip
            zoom = ed["punch_in"] if flip else 1.0
        p.update(zoom=zoom, out_start=round(offset, 3), out_end=round(offset + dur, 3))
        fade = f"afade=t=in:st=0:d=0.03,afade=t=out:st={max(dur - 0.03, 0):.3f}:d=0.03"
        vfilter, rect = crop_filter(W, H, faces[p["seg"]], zoom)
        chin = chin_out_y(W, H, faces[p["seg"]], rect)
        p.update(crop=list(rect), chin_y=round(chin) if chin else None)
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{p['src_start']:.3f}", "-i", str(src), "-t", f"{dur:.3f}",
             "-vf", vfilter + f",fps={FPS},format=yuv420p",
             "-af", f"aresample=48000,{fade}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
             "-c:a", "pcm_s16le", "-ac", "2", str(work / "pieces" / f"p{k:03d}.mov")])
        for i in p["words"]:
            w = words[i]
            out_words.append({"i": i, "text": w["text"], "start": round(w["start"] - p["src_start"] + offset, 3),
                              "end": round(min(w["end"], p["src_end"]) - p["src_start"] + offset, 3)})
        if k:
            seams.append(round(offset, 3))
        offset += dur
    # exact durations come from the encoded pieces (frame rounding), so re-measure
    (work / "pieces.txt").write_text("".join(f"file 'pieces/p{k:03d}.mov'\n" for k in range(len(pieces))))
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", "pieces.txt", "-c", "copy",
         "base.mov"], cwd=work)
    total = float(probe(work / "base.mov")["format"]["duration"])

    # ---- audio: voice chain + ducked music bed -> wav, then 2-pass loudnorm
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
             "-filter_complex", fg, "-map", "[a]", "-c:a", "pcm_s16le", "mix.wav"], cwd=work)
    else:
        run(["ffmpeg", "-v", "error", "-y", "-i", "base.mov", "-af", voice, "-c:a", "pcm_s16le", "mix.wav"],
            cwd=work)
    ln = loudnorm_stats(work / "mix.wav", au["lufs"], au["true_peak"])
    loud = (f"loudnorm=I={au['lufs']}:TP={au['true_peak']}:LRA=11:measured_I={ln['input_i']}:"
            f"measured_TP={ln['input_tp']}:measured_LRA={ln['input_lra']}:measured_thresh={ln['input_thresh']}:"
            f"offset={ln['target_offset']}:linear=true,aresample=48000")

    # ---- captions + hook title
    cap = dict(brand["caption"])
    if cap["y"] == "auto":  # just under the lowest chin of any shot, inside the 220-1500 safe band
        chins = [p["chin_y"] for p in pieces if p.get("chin_y")]
        lo, hi = 1100, 1500 - cap["size"] * 0.6
        cap["y"] = round(min(max(max(chins) + cap["size"] * 0.8, lo), hi)) if chins else 1300
    brand = dict(brand, caption=cap)
    cap_font_file = Path(cap["font_file"])
    shutil.copy(cap_font_file, work / "fonts" / cap_font_file.name)
    cap_font = ImageFont.truetype(str(cap_font_file), cap["size"])
    cap_family = font_family(cap_font_file)
    chunks = build_captions(out_words, cap, cap_font, brand["language"])
    hook = None
    if clip.get("hook_title") and brand["hook_title"]["enabled"]:
        hk = brand["hook_title"]
        hf = Path(hk["font_file"])
        if not (work / "fonts" / hf.name).exists():
            shutil.copy(hf, work / "fonts" / hf.name)
        hfont = ImageFont.truetype(str(hf), hk["size"])
        title = clip["hook_title"].upper() if hk["uppercase"] else clip["hook_title"]
        hook = {"family": font_family(hf), "lines": wrap_title(title, hfont, hk["max_line_px"] - 36)}
    write_ass(work / "captions.ass", chunks, brand, cap_family, hook)

    # ---- final: logo overlay, captions LAST, normalized audio
    inputs = ["-i", "base.mov", "-i", "mix.wav"]
    lg = brand["logo"]
    if lg["enabled"] and lg["path"] and Path(lg["path"]).exists():
        inputs += ["-i", str(lg["path"])]
        lx = "60" if "left" in lg["corner"] else f"W-w-60"
        ly = "230" if "top" in lg["corner"] else "H-h-420"
        vf = (f"[2:v]scale={lg['width']}:-1,format=rgba,colorchannelmixer=aa={lg['opacity']}[lg];"
              f"[0:v][lg]overlay={lx}:{ly}[v0];[v0]subtitles=captions.ass:fontsdir=fonts[v]")
    else:
        vf = "[0:v]subtitles=captions.ass:fontsdir=fonts[v]"
    final = deliver / f"{slug}.mp4"
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", f"{vf};[1:a]{loud}[a]",
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
         str(final.resolve())], cwd=work)

    # ---- side outputs
    srt = []
    for n, ch in enumerate(chunks, 1):
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
        "first_word_at": out_words[0]["start"], "last_word_end": out_words[-1]["end"],
        # a sentence end = terminal punctuation, the end of the recording, or a real pause before the next word
        "ends_on_sentence": (out_words[-1]["text"].rstrip()[-1:] in ".?!…" or out_words[-1]["i"] + 1 >= len(words)
                             or words[out_words[-1]["i"] + 1]["start"] - words[out_words[-1]["i"]]["end"] >= 0.6),
        "words": out_words,
        "captions": [{k: v for k, v in c.items() if k != "words"} for c in chunks],
        "caption_y": cap["y"], "caption_size": cap["size"], "max_line_px": cap["max_line_px"],
        "hook_lines": hook["lines"] if hook else None,
        "loudnorm_input": {"I": ln["input_i"], "TP": ln["input_tp"]},
    }
    (work / "build.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    for f in (work / "pieces").iterdir():
        f.unlink()
    print(f"{slug}: {total:.1f}s, {len(pieces)} pieces, {len(seams)} cuts, music={music.name if music else 'none'}"
          f"\n  -> {final}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("plan", type=Path)
    ap.add_argument("--only", default=None, help="build just this slug")
    a = ap.parse_args()
    plan = json.loads(a.plan.read_text(encoding="utf-8"))
    brand = load_brand(Path(plan["brand"]))
    words = load_words(Path(plan["transcript"]))
    for clip in plan["clips"]:
        if a.only and clip["slug"] != a.only:
            continue
        build(plan, clip, brand, words)


if __name__ == "__main__":
    main()
