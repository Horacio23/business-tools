# Quality gates

A clip that fails a gate doesn't ship. `scripts/qa.py` runs the measurable parts. You run the two
that need judgment (the contact sheet and the script audit). The gates and thresholds are adapted from
the Vibe Editing kit's audit skills (audio, captions, script, visual) and its V1 delivery checklist.

| # | Gate | What it catches | Thresholds |
|---|---|---|---|
| 1 | FILE | wrong size or codec, A/V drift from the plan, off-brand length | 1080×1920, h264 yuv420p, AAC, 30 fps; duration within 0.15s of plan; WARN outside `length` |
| 2 | AUDIO | loudness off-platform, dead air before the hook, clipped last word, pops at cuts, music fighting the voice | -14 LUFS ±1.5, true peak ≤ -1 dBTP; first word ≤ 0.35s; tail 0.03–0.9s after the last word (an end card after that is fine); seam spike > 1.6× neighbours = FAIL; voice over the bed in pauses ≥ the style's `qa.min_voice_over_music_db` (10 karaoke, 6 serenity; WARN within 4 dB below, FAIL under that). With sound effects, the cut and music checks run on `mix_base.wav` (before the effects), and a "sound effects" line checks each effect's loudest 30 ms against the voice's average level: ≤ 0 dB PASS, up to +3 WARN, above FAIL; more than 0.8 effects per second = WARN (busy). Numbers can't judge taste: have the user listen to the first clip with effects |
| 3 | VISUAL | black frames, frozen picture, lost face, over-zoom | any black ≥ 0.07s = FAIL; freeze ≥ 1.5s = WARN (the end card is a still on purpose and is skipped); face found < 60% of samples = WARN; face > 22% of frame = FAIL (16–22% WARN), checked on every shot including rhythm zoom cuts; the contact sheet shows the open, every cut and zoom cut (up to 16), and the close |
| 4 | CAPTIONS | text clipped by the platform UI, covering the face, flicker | every line (key-word lines too) ≤ 800px wide and inside y 220–1500, or inside the style's `safe_zone` (e.g. Meta's ad zone 269–1248, 65px sides; hook lines included) = FAIL if outside; captions placed above the head must stay clear of the brow (WARN); top of the caption block clear of the mouth in every shot, except during B-roll (WARN if it covers the mouth; touching the chin on a punched-in shot is only noted, since close-up reels do that); no line < 0.15s; hook title ≤ 2 lines (3 for a two-tier or depth hook). A depth hook is checked by its exact ink edges, and the line says where the head is and how much of BIG it hides, or why it fell back to two-tier |
| 5 | SCRIPT | clips that don't make sense to a stranger | quick: no continuation-word opener, ends on a full sentence; full audit: fresh subagent (below) |
| 6 | COMPLIANCE | Meta ad-policy trouble for med spas | `compliance.profile: "medspa"` scans for before/after, "look younger", guarantees, weight-loss numbers, Rx drug names (Botox, Ozempic…), "your wrinkles/fat" personal attributes. WARN for organic, FAIL for `purpose: "ad"` |

Why these and not more: each one is a defect a viewer notices (or that gets an ad rejected), and each
is cheap to measure. The kit has heavier versions (phase-correlation crop checks, OCR on burned
captions). Add those only if a defect actually slips through.

## Contact sheet (your eyes)

`work/<slug>/contact.jpg` shows frames at the open, just after every cut, and at the close. Check:
- the face is fully in frame, with headroom and no forehead cut, in both the normal and punched-in shots,
- captions are readable, don't cover the mouth, and stay clear of the right-side action buttons,
- the hook title box isn't covering the face,
- nothing odd: a wrong person, a blurry frame, a cut that lands mid-gesture in a jarring way.

## Script audit: fresh-subagent prompt

Spawn a subagent (the Agent tool, general-purpose) with only this. Don't send the transcript of the full
recording or your reasoning: the auditor must be a cold viewer.

```
You are auditing the script of a short vertical video (Reel/TikTok) before it is published.
You have NOT seen the source footage. Judge only the words below, as a stranger scrolling.

Audience: <brand profile "audience">
Purpose: <organic | ad>
On-screen hook title (first 3s): "<hook_title>"
Spoken script:
<contents of work/<slug>/script.txt>

Check each and answer PASS / WARN / FAIL with a short quote as evidence:
1. HOOK: would the first sentence stop a stranger in this audience from scrolling? Which hook type is it?
2. COLD VIEWER: does every line make sense with no prior context? Flag dangling "eso/esto/él/like I said",
   undefined jargon, mid-conversation starts.
3. ONE ARC: one topic and one payoff? Flag topic jumps or two stitched stories.
4. PAYOFF: does the last sentence land a clear takeaway (not trail off, not open a new idea)?
5. FLOW: any jump in logic where a cut removed something the next line needs?
6. LANGUAGE: natural for a native speaker? Flag transcription errors that would show in captions.
7. POLICY (if purpose is ad, or the audience is med spa patients): medical claims, guarantees,
   before/after, "you/your" + a body flaw, prescription drug names.
The spoken words are fixed: they are what the speaker said and cannot be rewritten. Possible fixes are
only: cut a line, restore a line that was cut, reorder lines, or change the on-screen hook title.
Do not suggest rewording what is spoken (note it under LANGUAGE only if captions would show a
transcription error).
End with: VERDICT: SHIP | FIX (list the fixes, most important first).
```

A FAIL on 2–5 sends you back to the segments. A FAIL on 6 means the captions show wrong words: fix the
word in the transcript JSON (`text` field), re-run `pack.py`, and rebuild. Then re-audit once.
