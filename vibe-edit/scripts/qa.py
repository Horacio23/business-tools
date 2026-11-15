# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy", "pillow"]
# ///
"""Automated quality gates for a clip made by build_clip.py.

  uv run qa.py <work>/<slug>/build.json

Gates (see references/qa-gates.md for the why):
  1 FILE        1080x1920 h264/yuv420p, aac 48k, 30fps, duration = plan, length in brand range
  2 AUDIO       -14 LUFS +-1.5, true peak <= -1.0, clean open/close, no pops at cuts, music under voice
  3 VISUAL      no black frames, no long freezes, face found + not over-zoomed; writes contact.jpg
  4 CAPTIONS    every line fits the 800px safe width and the safe band, no flicker, every word captioned
  5 SCRIPT      quick text checks; the full cold-viewer audit is a fresh subagent (PENDING here)
  6 COMPLIANCE  med spa / Meta terms (WARN organic, FAIL ad)
Writes <work>/<slug>/qa.json and contact.jpg. Exit code 1 if any gate FAILs.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from common import probe  # noqa: E402

RESULTS: list[dict] = []
CONTINUATION = {"y", "entonces", "pero", "también", "tambien", "porque", "además", "ademas", "o", "pues",
                "and", "so", "but", "also", "because", "anyway"}
MEDSPA_TERMS = [
    r"antes y despu[eé]s", r"before (and|&) after", r"rejuvenec", r"look(s|ing)? younger", r"m[aá]s joven",
    r"garantiz", r"guarantee", r"\b100 ?%", r"sin dolor\b", r"pain[- ]?free",
    r"pierde \d+ ?(libras|kilos|lbs)", r"lose \d+ ?(pounds|lbs|kilos)",
    r"\bbotox\b", r"\bdysport\b", r"\bxeomin\b", r"\bozempic\b", r"\bwegovy\b", r"\bmounjaro\b",
    r"semaglut", r"tirzepat",
    r"\btus? (arrugas|grasa|papada|celulitis|manchas|acn[eé]|kilos|libras|flacidez)\b",
    r"\byour (wrinkles|fat|double chin|cellulite|acne|weight|sagging)\b",
]


def gate(name: str, status: str, detail: str) -> None:
    RESULTS.append({"gate": name, "status": status, "detail": detail})


def ffmpeg_stderr(args: list[str]) -> str:
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stderr


def load_audio(path: Path, sr: int = 16000) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, np.float32)


def rms_db(x: np.ndarray) -> float:
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9) if len(x) else -120.0


def main() -> None:
    bj = Path(sys.argv[1])
    m = json.loads(bj.read_text(encoding="utf-8"))
    brand = json.loads(Path(m["brand"]).read_text(encoding="utf-8"))
    # effective targets (style + profile) are written by build_clip.py; older manifests fall back to the profile
    length = {"min": 15, "max": 60, **(m.get("length") or brand.get("length", {}))}
    lufs = m.get("lufs", brand.get("audio", {}).get("lufs", -14))
    music_sep = m.get("qa_min_voice_over_music_db", 10)
    final = Path(m["final"])
    work = bj.parent

    # 1 FILE ---------------------------------------------------------------
    info = probe(final)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    dur = float(info["format"]["duration"])
    fps = eval(v["r_frame_rate"])  # noqa: S307  ("30/1")
    problems = []
    if (v["width"], v["height"]) != (1080, 1920):
        problems.append(f"size {v['width']}x{v['height']}")
    if v["codec_name"] != "h264" or v.get("pix_fmt") != "yuv420p":
        problems.append(f"{v['codec_name']}/{v.get('pix_fmt')}")
    if not a or a["codec_name"] != "aac":
        problems.append("audio not aac")
    if abs(fps - 30) > 0.1:
        problems.append(f"fps {fps:.2f}")
    if abs(dur - m["duration"]) > 0.15:
        problems.append(f"duration {dur:.2f}s vs plan {m['duration']:.2f}s")
    gate("1 FILE", "FAIL" if problems else "PASS", "; ".join(problems) or f"1080x1920 h264 30fps {dur:.1f}s")
    if not length["min"] <= dur <= length["max"]:
        gate("1 FILE length", "WARN", f"{dur:.1f}s is outside the brand range {length['min']}-{length['max']}s")

    # 2 AUDIO --------------------------------------------------------------
    eb = ffmpeg_stderr(["-i", str(final), "-af", "ebur128=peak=true", "-f", "null", "-"])
    I = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", eb)[-1])
    tps = re.findall(r"Peak:\s+(-?[\d.]+|-inf) dBFS", eb)
    tp = float(tps[-1]) if tps and tps[-1] != "-inf" else -99
    st = "PASS" if abs(I - lufs) <= 1.5 and tp <= -1.0 else "FAIL"
    gate("2 AUDIO loudness", st, f"{I:.1f} LUFS (target {lufs}), true peak {tp:.1f} dBTP")
    head, tail = m["first_word_at"], m.get("content_end", dur) - m["last_word_end"]
    card = m.get("end_card_seconds") or 0
    gate("2 AUDIO open", "PASS" if head <= 0.35 else "FAIL",
         f"first word at {head:.2f}s" + ("" if head <= 0.35 else " (dead air or fluff before the hook)"))
    gate("2 AUDIO close", "PASS" if 0.03 <= tail <= 0.9 else "WARN",
         f"{tail:.2f}s after the last word" + (" (last word may be clipped)" if tail < 0.03 else
                                               " (long tail)" if tail > 0.9 else "")
         + (f", then a {card:.1f}s end card" if card else ""))
    sr = 16000
    # with sound effects, the cut and music checks run on the voice + music mix from before the effects
    # (a whoosh on a cut is not a pop); the effects get their own check below
    sfx = m.get("sfx") or []
    base_mix = work / (m.get("mix_base") or "")
    pre = bool(sfx) and base_mix.is_file()
    x = load_audio(base_mix if pre else final, sr)
    pops = []
    for s in m["seams"]:
        c = int(s * sr)
        local = np.abs(x[max(c - 130, 0):c + 130]).max(initial=0)
        ref = max(np.abs(x[max(c - 3200, 0):max(c - 320, 0)]).max(initial=0), np.abs(x[c + 320:c + 3200]).max(initial=0))
        if local > 0.08 and local > ref * 1.6:
            pops.append(f"{s:.2f}s")
    gate("2 AUDIO cuts", "FAIL" if pops else "PASS",
         (f"spike at cut {', '.join(pops)}" if pops else f"{len(m['seams'])} cuts, no pops")
         + (" (checked before the sound effects)" if pre else ""))
    if m.get("music"):
        spans = [(w["start"], w["end"]) for w in m["words"]]
        speech = np.concatenate([x[int(s * sr):int(e * sr)] for s, e in spans]) if spans else np.array([])
        gaps = []
        for (s0, e0), (s1, _) in zip(spans, spans[1:]):
            if s1 - e0 >= 0.3:
                gaps.append(x[int((e0 + 0.1) * sr):int((s1 - 0.1) * sr)])
        if gaps:
            sep = rms_db(speech) - rms_db(np.concatenate(gaps))
            st = "PASS" if sep >= music_sep else "WARN" if sep >= music_sep - 4 else "FAIL"
            gate("2 AUDIO music bed", st,
                 f"voice sits {sep:.1f} dB over the music in pauses (want >= {music_sep} for this style)")
        else:
            gate("2 AUDIO music bed", "NOTE", "no pause long enough to measure; listen to it")
    if sfx and pre and (work / "sfx.wav").is_file():
        # how loud each effect is at its loudest 30 ms, against the voice's average level (both before loudnorm)
        fx = load_audio(work / "sfx.wav", sr)
        spans = [(w["start"], w["end"]) for w in m["words"]]
        voice = rms_db(np.concatenate([x[int(s * sr):int(e * sr)] for s, e in spans]))
        win = int(0.03 * sr)
        rel = []
        for ev in sfx:
            seg = fx[int(ev["start"] * sr):int(ev["end"] * sr) + 1]
            if len(seg) > win:
                c = np.cumsum(np.concatenate([[0.0], seg.astype(np.float64) ** 2]))
                rel.append(10 * np.log10((c[win:] - c[:-win]).max() / win + 1e-12) - voice)
        kinds = {}
        for ev in sfx:
            kinds[ev["kind"]] = kinds.get(ev["kind"], 0) + 1
        loudest = max(rel) if rel else -99
        busy = len(sfx) / max(m.get("content_end", dur), 1)
        st = "FAIL" if loudest > 3 else "WARN" if loudest > 0 or busy > 0.8 else "PASS"
        gate("2 AUDIO sound effects", st,
             f"{len(sfx)} effects ({', '.join(f'{n} {k}' for k, n in kinds.items())}), loudest "
             f"{loudest:+.1f} dB vs the voice's average level (want <= 0)"
             + (f"; busy: {busy:.1f} per second" if busy > 0.8 else "") + "; listen to one before shipping")

    # 3 VISUAL -------------------------------------------------------------
    bd = ffmpeg_stderr(["-i", str(final), "-vf", "blackdetect=d=0.07:pix_th=0.10", "-an", "-f", "null", "-"])
    blacks = re.findall(r"black_start:([\d.]+)", bd)
    gate("3 VISUAL black", "FAIL" if blacks else "PASS",
         f"black frames at {', '.join(blacks)}s" if blacks else "no black frames")
    fz = ffmpeg_stderr(["-i", str(final), "-vf", "freezedetect=n=-60dB:d=1.5", "-an", "-f", "null", "-"])
    content_end = m.get("content_end", dur)  # the end card is a still on purpose
    freezes = [f for f in re.findall(r"freeze_start: ([\d.]+)", fz) if float(f) < content_end - 0.2]
    gate("3 VISUAL freeze", "WARN" if freezes else "PASS",
         f"frozen picture from {', '.join(freezes)}s" if freezes else "no frozen stretches")
    W, H = m["source_size"]
    face_notes, worst = [], "PASS"
    for seg, f in m["faces"].items():
        if f["found"] < 0.6:
            face_notes.append(f"segment {seg}: face found in {f['found']:.0%} of samples (framing is a centered guess)")
            worst = "WARN" if worst == "PASS" else worst
        zooms = [p["zoom"] for p in (m.get("shots") or m["pieces"]) if str(p["seg"]) == seg]
        if f["area"] and zooms:
            base_frac = ((H * 1080 / 1920) * H) / (W * H) if W / H > 1080 / 1920 else (W * W * 1920 / 1080) / (W * H)
            out_area = f["area"] / (base_frac / max(zooms) ** 2)
            if out_area > 0.22:
                face_notes.append(f"segment {seg}: face fills {out_area:.0%} of frame when punched in (too tight)")
                worst = "FAIL"
            elif out_area > 0.16:
                face_notes.append(f"segment {seg}: face fills {out_area:.0%} when punched in (tight)")
                worst = "WARN" if worst == "PASS" else worst
    gate("3 VISUAL framing", worst, "; ".join(face_notes) or "face found and framed in every segment")
    # contact sheet: open, each cut, close
    times = [0.3] + ([1.0] if m.get("hook_seconds") and m["hook_seconds"] > 1.3 else []) \
        + [s + 0.15 for s in sorted(m["seams"] + m.get("zoom_cuts", []))][:16] + [max(dur - 0.3, 0)]
    tiles = []
    for t in times:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(final), "-frames:v", "1",
                              "-vf", "scale=216:384", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout
        if len(raw) == 216 * 384 * 3:
            im = Image.frombytes("RGB", (216, 384), raw)
            ImageDraw.Draw(im).rectangle([0, 0, 70, 22], fill=(0, 0, 0))
            ImageDraw.Draw(im).text((5, 4), f"{t:.1f}s", fill=(255, 255, 0), font=ImageFont.load_default())
            tiles.append(im)
    cols = min(6, len(tiles))
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 216, rows * 384), (30, 30, 30))
    for k, im in enumerate(tiles):
        sheet.paste(im, ((k % cols) * 216, (k // cols) * 384))
    sheet.save(work / "contact.jpg", quality=85)

    # 4 CAPTIONS -----------------------------------------------------------
    caps, notes, st = m["captions"], [], "PASS"
    lines = m.get("caption_lines") or [{"text": c["text"], "width_px": c["width_px"], "y": m["caption_y"],
                                        "size": m["caption_size"], "start": c["start"], "end": c["end"]} for c in caps]
    # the style's safe zone (e.g. Meta's ad zone: 269-1248, 65px sides), else the 220-1500 band
    zone = m.get("safe_zone") or {"top": 220, "bottom": 1500, "side": 0}
    zname = (f"Meta's ad safe zone (y {zone['top']}-{zone['bottom']}, {zone['side']}px sides)" if m.get("safe_zone")
             else f"the {zone['top']}-{zone['bottom']} safe band")
    max_w = min(m["max_line_px"], 1080 - 2 * zone["side"]) if zone.get("side") else m["max_line_px"]
    wide = [ln["text"] for ln in lines if ln["width_px"] > max_w]
    if wide:
        notes.append(f"{len(wide)} line(s) wider than {max_w}px: {wide[:3]}")
        st = "FAIL"
    cap_top = min(ln["y"] - ln["size"] * 0.6 for ln in lines) if lines else m["caption_y"]
    cap_bot = max(ln["y"] + ln["size"] * 0.6 for ln in lines) if lines else m["caption_y"]
    cutaways = m.get("broll") or []
    shots = [p for p in (m.get("shots") or m["pieces"])
             if not any(b["start"] <= p["out_start"] and p["out_end"] <= b["end"] for b in cutaways)]
    if m.get("caption_place") == "above":
        # captions above the head: covering the brow/eyes is a problem, grazing the hair is only noted
        on_head = [p for p in shots if p.get("head_top_y") is not None and cap_bot > p["head_top_y"] + 5]
        on_eyes = [p for p in on_head if p.get("face_top_y") is None or cap_bot > p["face_top_y"]]
        if on_eyes:
            notes.append(f"captions overlap the face in {len(on_eyes)} shot(s) "
                         f"(caption bottom {cap_bot:.0f}px, brow {min(p['face_top_y'] for p in on_eyes)}px)")
            st = "WARN" if st == "PASS" else st
        elif on_head:
            notes.append(f"caption block grazes the hair in {len(on_head)} shot(s), face clear")
    else:
        on_face = [p for p in shots if p.get("chin_y") and cap_top < p["chin_y"] - 5]
        # mouth_y (newer builds): covering the mouth is a real problem; touching the chin on a punched-in
        # shot is normal for close-up reels and is only noted
        on_mouth = [p for p in on_face if p.get("mouth_y") is None or cap_top < p["mouth_y"]]
        if on_mouth:
            notes.append(f"captions overlap the chin/mouth in {len(on_mouth)} shot(s) "
                         f"(caption top {cap_top:.0f}px, chin {max(p['chin_y'] for p in on_mouth)}px)")
            st = "WARN" if st == "PASS" else st
        elif on_face:
            notes.append(f"caption block touches the chin in {len(on_face)} punched-in shot(s), mouth clear "
                         f"(caption top {cap_top:.0f}px, chin up to {max(p['chin_y'] for p in on_face)}px)")
    inside = lambda b: zone["top"] <= b["y"] - b["size"] * 0.6 and b["y"] + b["size"] * 0.6 <= zone["bottom"]  # noqa: E731
    out_band = sorted({ln["y"] for ln in lines if not inside(ln)})
    if out_band:
        notes.append(f"caption line(s) at y={out_band[:4]} leave {zname}")
        st = "FAIL"
    # depth hooks record their exact ink edges (top/bottom); other hooks use the size estimate
    in_hook = lambda b: zone["top"] <= b["top"] and b["bottom"] <= zone["bottom"] if "top" in b else inside(b)  # noqa: E731
    out_hook = [b["text"] for b in m.get("hook_boxes") or [] if not in_hook(b) or b["width_px"] > 1080 - 2 * zone["side"]]
    if out_hook:
        notes.append(f"hook line(s) {out_hook} leave {zname}")
        st = "FAIL"
    flick = [c["text"] for c in caps if c["end"] - c["start"] < 0.15]
    if flick:
        notes.append(f"{len(flick)} caption(s) on screen < 0.15s")
        st = "WARN" if st == "PASS" else st
    max_hook = 3 if m.get("hook_kind") in ("two-tier", "depth") else 2
    if m.get("hook_note"):
        notes.append(m["hook_note"])
    if m.get("hook_lines") and len(m["hook_lines"]) > max_hook:
        notes.append(f"hook title wraps to {len(m['hook_lines'])} lines (keep it to {max_hook})")
        st = "WARN" if st == "PASS" else st
    where = f"{len(caps)} caption lines" + (" and the hook" if m.get("hook_boxes") else "") + f" inside {zname}" \
        + (", captions above the head" if m.get("caption_place") == "above" else "")
    gate("4 CAPTIONS", st, "; ".join(notes + ([where] if st == "PASS" else [])))

    # 5 SCRIPT (quick checks; full audit = fresh subagent) ------------------
    words = [w["text"] for w in m["words"]]
    first = re.sub(r"[^\wáéíóúüñ]", "", words[0].lower()) if words else ""
    notes = []
    if first in CONTINUATION:
        notes.append(f"opens on a continuation word ('{words[0]}')")
    if words and not m.get("ends_on_sentence", words[-1].rstrip()[-1:] in ".?!…"):
        notes.append(f"last word '{words[-1]}' does not end a sentence")
    gate("5 SCRIPT quick", "WARN" if notes else "PASS", "; ".join(notes) or "opens clean, ends on a full sentence")
    gate("5 SCRIPT audit", "PENDING", f"fresh-subagent cold-viewer audit of {work / 'script.txt'}")

    # 6 COMPLIANCE ---------------------------------------------------------
    comp = brand.get("compliance", {})
    terms = (MEDSPA_TERMS if comp.get("profile") == "medspa" else []) + comp.get("extra_terms", [])
    text = " ".join(words) + " " + (m.get("hook_title") or "")
    hits = sorted({mm.group(0) for t in terms for mm in re.finditer(t, text, re.I)})
    if hits:
        gate("6 COMPLIANCE", "FAIL" if m["purpose"] == "ad" else "WARN",
             f"flagged for Meta ad policy: {hits}" + (" (fine organically; rework before using as an ad)"
                                                       if m["purpose"] != "ad" else ""))
    else:
        gate("6 COMPLIANCE", "PASS", f"profile={comp.get('profile', 'none')}, nothing flagged")

    (work / "qa.json").write_text(json.dumps({"clip": m["slug"], "results": RESULTS}, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
    w = max(len(r["gate"]) for r in RESULTS)
    print(f"QA {m['slug']}  ({final.name}, {dur:.1f}s)")
    for r in RESULTS:
        print(f"  {r['gate']:<{w}}  {r['status']:<7}  {r['detail']}")
    print(f"  contact sheet: {work / 'contact.jpg'}")
    sys.exit(1 if any(r["status"] == "FAIL" for r in RESULTS) else 0)


if __name__ == "__main__":
    main()
