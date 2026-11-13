# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Turn a Scribe transcript into the editor's reading view.

Writes next to the transcript:
  <stem>.transcript.md  phrase lines: [w12-w31 | 3.20-8.90] text   (fillers shown as {eh})
  <stem>.words.tsv      one word per line: index, start, end, text (for exact cut points)

A new line starts on a pause >= 0.5s, a speaker change, or a sentence end once
the line has 6+ words. Gaps >= 1.0s are printed as (pause 1.4s).

Usage: uv run pack.py <work>/transcripts/<stem>.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import load_words  # noqa: E402


def main() -> None:
    tp = Path(sys.argv[1])
    words = load_words(tp)
    meta = json.loads(tp.read_text(encoding="utf-8"))
    stem = tp.stem
    lines, cur = [], []

    def flush():
        if cur:
            txt = " ".join("{" + w["text"] + "}" if w["filler"] else "~" + w["text"] + "~" if w["repeat"] else w["text"]
                           for w in cur)
            spk = f" S{cur[0]['speaker'].split('_')[-1]}" if cur[0].get("speaker") else ""
            lines.append(f"[w{cur[0]['i']}-w{cur[-1]['i']} | {cur[0]['start']:.2f}-{cur[-1]['end']:.2f}]{spk} {txt}")
            cur.clear()

    for k, w in enumerate(words):
        if cur:
            gap = w["start"] - cur[-1]["end"]
            ends = cur[-1]["text"].rstrip()[-1:] in ".?!…"
            if gap >= 0.5 or w["speaker"] != cur[-1]["speaker"] or (ends and len(cur) >= 6) or len(cur) >= 24:
                flush()
                if gap >= 1.0:
                    lines.append(f"  (pause {gap:.1f}s)")
        cur.append(w)
    flush()

    dur = words[-1]["end"] if words else 0
    nfill = sum(w["filler"] for w in words)
    nrep = sum(w["repeat"] for w in words)
    head = (f"# {stem}\n\nlanguage: {meta.get('language_code')} | spoken: {dur:.1f}s | words: {len(words)} | "
            f"fillers: {nfill} {{in braces}} | stutters: {nrep} ~like this~ (both auto-dropped by the builder)\n"
            f"Engine: {meta.get('engine', 'elevenlabs-scribe_v1')}. Cut by word index (`\"words\": [a, b]`) or by time; "
            f"exact word times are in {stem}.words.tsv.\n\n")
    md = tp.with_name(f"{stem}.transcript.md")
    md.write_text(head + "\n".join(lines) + "\n", encoding="utf-8")
    tsv = tp.with_name(f"{stem}.words.tsv")
    tsv.write_text("i\tstart\tend\ttext\n" + "\n".join(
        f"{w['i']}\t{w['start']:.3f}\t{w['end']:.3f}\t{w['text']}" for w in words) + "\n", encoding="utf-8")
    print(f"wrote {md}\nwrote {tsv}")


if __name__ == "__main__":
    main()
