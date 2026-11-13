---
name: vibe-edit
description: Edit talking-head videos into finished, on-brand vertical reels (9:16) by conversation. It transcribes, picks the strongest moments, cuts pauses, fillers and dead air, frames the face, punches in on cuts, burns word-by-word captions in the brand's font and colours, adds a hook title, mixes ducked music to -14 LUFS, then runs 6 quality gates before showing anything. Use it whenever the user wants a video edited, cut, captioned or turned into reels, shorts or TikToks: "edit this video", "make clips from this", "turn this into reels", "add subtitles", "cut the pauses", "polish this reel", "edita este video", "hazme reels de esto", "ponle subtítulos". Covers the agency's own content and client footage (med spas, salons). Also use it for changes to a clip already made ("captions bigger", "different song", "cut that line").
---

# Vibe Edit

Raw talking-head footage in, finished vertical reels out, in the brand's look, checked before
anyone sees them. This is a Windows + macOS take on the "Vibe Editing" playbook (Acquisition.com's
Mac kit). It keeps that kit's best ideas (an editorial rubric, a brand profile, self-auditing gates)
and builds on ffmpeg, uv, and ElevenLabs Scribe or faster-whisper.

Everything runs through the scripts in `scripts/`. Run them with `uv run` (it installs their Python
deps on first use). Never touch the user's source files; all output goes in a project folder.
Human-facing docs (how-to, rules, brand profiles) are in the business vault: "Vibe Edit - Video Editing System".

## Where things live

| What | Where |
|---|---|
| Brand profile (own agency) | the vault's `machine/vibe-edit/video-style.json`, with `music/` and the logo beside it. The vault is `~/Claude/Vault` on the Windows PC and `~/Documents/Business` on the Mac, synced by git, so every computer gets the same profile. |
| Brand profile (a client) | `~/Claude/Clients/<client>/video-style.json` (+ `music/`, `fonts/` beside it) |
| Project (own content) | `~/Claude/Videos/<YYYY-MM-DD>-<slug>/work/` and `/deliver/` |
| Project (client) | `~/Claude/Clients/<client>/videos/<YYYY-MM-DD>-<slug>/work/` and `/deliver/` |
| ElevenLabs key (optional) | `~/.config/vibe-edit/keys.env`, line `ELEVENLABS_API_KEY=sk_...` (per computer, never in git) |

`~/Claude` is the Claude workspace folder in the user's home directory. Content for the agency's own channels is
always for the Maria avatar (vault: Customer Avatar - Maria), in Spanish unless told otherwise.

## First run on a computer
Run `uv run scripts/doctor.py`. It checks ffmpeg (with libass), the ElevenLabs key, the agency brand
profile, its fonts and its music, and prints the fix for anything missing.
- **Mac:** `brew install uv ffmpeg`.
- **Windows:** `winget install astral-sh.uv Gyan.FFmpeg`.

`git pull` the vault first so the profile is there. The ElevenLabs key is the one thing to re-enter by
hand on each computer. Fix the MISS lines before the first edit. An optional MISS (the key) still lets
you edit: without a key, transcription runs locally for free (faster-whisper, model downloads once).

## The flow

### 1. Intake
Work out three things, asking only what you can't tell:
- **Whose brand**: the agency's own, or which client. If it's unclear, ask.
- **The job**:
  - **Polish**: one short raw video becomes one finished reel. Cut the dead air, caption it, add music.
  - **Clips**: a long recording becomes the N best standalone reels.
- **Purpose**: `organic` (default) or `ad`. Ads get the strict compliance gate.

A URL works as a source too: download it with `yt-dlp` into `work/source/`, only if the user owns the content.

### 2. Brand profile
Load the brand's `video-style.json`. If it's missing, make one: read
[references/brand-profile.md](references/brand-profile.md), prefill it from what already exists
(`brand-context.md`, logo, colours, fonts), and ask only the gaps, **one question at a time**.
The user's taste lives in this file. That's why their clips look like theirs and not a template.

### 3. Transcribe (cached)
```
uv run scripts/transcribe.py "<video>" --work "<project>/work" --language es
uv run scripts/pack.py "<project>/work/transcripts/<stem>.json"
```
With an `sk_` ElevenLabs key saved it uses Scribe, which is verbatim: it keeps "eh"/"um" so the
builder can cut them, and it labels speakers. Without a key it runs faster-whisper locally, for free.
Read `<stem>.transcript.md`: each line is `[w12-w31 | 3.20-8.90] text`, with fillers in `{braces}`.
Exact word times are in `<stem>.words.tsv`.

### 4. Pick and propose (don't cut yet)
Read [references/editing-rules.md](references/editing-rules.md) and apply it: payoff first, cold-viewer
context, one arc, finish the point, the brand person carries it. For each clip write:
- the **hook line** (the first words heard),
- a **hook title**: on-screen text, at most 2 lines and about 40 characters, Spanish for Maria,
- the **segments** as word-index ranges,
- the **length**.

Show the plan to the user in plain words: a short table, one row per clip. **Wait for a yes before
building.** For a simple polish job, one line is enough ("I'll keep everything, cut the pauses, title: …").

### 5. Build
Write `work/plan.json` (format in the header of `scripts/build_clip.py`), then run:
```
uv run scripts/build_clip.py "<project>/work/plan.json"            # all clips
uv run scripts/build_clip.py "<project>/work/plan.json" --only <slug>
```
It does these steps in order, and the order matters:
1. Snap cuts to word edges, drop fillers, and close pauses over `edit.max_pause` (jump cuts).
2. Lock a face-centred 9:16 frame per segment, with no panning inside a shot.
3. Alternate a 1.12× punch-in on each cut, so the jump cuts read as intentional.
4. Add 30 ms audio fades at every cut.
5. Clean up the voice, add music ducked under it, and run two-pass loudnorm to -14 LUFS.
6. Overlay the logo, then burn the captions **last** so nothing covers them.

Captions sit just under the lowest chin automatically (`caption.y: "auto"`).
Outputs: `deliver/<slug>.mp4`, `<slug>.srt`, `<slug>-cover.jpg`; plus `work/<slug>/build.json`.

### 6. Quality gates (before the user sees anything)
```
uv run scripts/qa.py "<project>/work/<slug>/build.json"
```
Then do the two checks the script can't do alone. The gates are explained in
[references/qa-gates.md](references/qa-gates.md).
- **Look** at `work/<slug>/contact.jpg`, which shows the open, every cut and the close. Check that the
  face is in frame, the captions are readable and clear of the face, and that no shot looks odd.
- **Script audit**: send `work/<slug>/script.txt` plus the hook title to a **fresh subagent**, using
  the prompt in qa-gates.md. Fresh context matters: a reader who didn't pick the cut is the honest
  cold viewer.

Fix any FAIL by changing the plan or the brand profile, rebuild, and re-run QA, up to 3 passes.
After that, show the clip with the problem named rather than looping. WARNs go to the user in one line each.

### 7. Deliver
Send the finished mp4s with `SendUserFile` (they render inline), the cover, and a one-line QA
summary per clip. Write `deliver/<slug>-post.md`: post caption in Spanish (hook, 2–3 short lines,
CTA, 4–6 hashtags) in the brand's voice. For med spa clients, follow the existing reel logs (e.g.
`Clients/<client>/social/*.md`).

Scheduling is a separate, outward-facing step. Do it only when the user says so, through the GHL Social
Planner (vault: GHL Social Posting System), and follow that client's posting rules.

### 8. Changes and memory
Feedback comes in plain words. Route it to the right place, rebuild, and re-run QA:

| They say | Change |
|---|---|
| "captions bigger / another colour / all caps" | `caption.size` / `highlight` / `uppercase` in the brand profile |
| "different song", "no music", "music lower" | clip `music` in the plan, or `music.volume_db` (-26 is quieter) |
| "cut that line", "keep the part about…" | the clip's `segments` |
| "too many zooms", "faster pace" | `edit.punch_in` (1.0 = off), `edit.max_pause` (0.3 = tighter) |
| "put the logo on" | `logo.enabled: true` |

A preference about the brand ("always…", "never…", or the same fix asked twice) goes into
`video-style.json` (fields or `notes`), so the next clip is right the first time. Don't wait for the
same revision twice.

## Notes
- **Horizontal sources** (Zoom, podcast): the builder crops 9:16 around the detected face per segment.
  With two people on camera, check the contact sheet. The crop follows the largest face only.
- **Patients on camera**: ask whether a signed media release exists before delivering a client clip
  that shows a patient. The vault requires one; the gate can't see it.
- **Fonts**: use static `.ttf`/`.otf` files. A variable font renders at its default weight. A brand
  font that isn't installed goes in the brand's `fonts/` folder, with `font_file` pointing to it.
- **Motion graphics** (animated intros, end cards, b-roll cards) are a HyperFrames job: route to the
  `hyperframes` skill and drop the result in as a segment or overlay.
