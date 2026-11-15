---
name: vibe-edit
description: Edit talking-head videos into finished, on-brand vertical reels (9:16) by conversation. It transcribes, picks the strongest moments, cuts pauses, fillers and dead air, frames the face, punches in on cuts, burns word-by-word captions, adds a hook title (including big text behind the speaker's head), B-roll cutaways, sound effects and an end card, mixes ducked music to -14 LUFS, then runs 6 quality gates before showing anything. Looks come from named styles (punch, karaoke, serenity, serenity-bold, serenity-naples) worn by any brand profile; punch (big colored key words, zoom cut every few seconds, text-behind-the-head hook, whooshes and pops) is the agency default. Use it whenever the user wants a video edited, cut, captioned or turned into reels, shorts or TikToks: "edit this video", "make clips from this", "turn this into reels", "add subtitles", "cut the pauses", "polish this reel", "do it in the serenity style", "edit this in Punch", "edita este video", "hazme reels de esto", "ponle subtítulos", "con el estilo de Serenity". Covers the agency's own content and client footage (med spas, salons). Also use it for changes to a clip already made ("captions bigger", "different song", "cut that line", "other style"), and for making a new style from someone's finished videos.
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
| Brand profile (a client) | `~/Claude/Clients/<client>/video-style.json` (+ `music/`, `fonts/` beside it). Serenity has two: `video-style.json` (Miami) and `video-style-naples.json`, with assets in `video-brand/` |
| Styles (looks) | `styles/<name>.json` in this skill: [references/styles.md](references/styles.md) |
| Project (own content) | `~/Claude/Videos/<YYYY-MM-DD>-<slug>/work/` and `/deliver/` |
| Project (client) | `~/Claude/Clients/<client>/videos/<YYYY-MM-DD>-<slug>/work/` and `/deliver/` |
| ElevenLabs key (optional) | `~/.config/vibe-edit/keys.env`, line `ELEVENLABS_API_KEY=sk_...` (per computer, never in git) |

`~/Claude` is the Claude workspace folder in the user's home directory. Content for the agency's own channels is
always for the Maria avatar (vault: Customer Avatar - Maria), in Spanish unless told otherwise.

## First run on a computer
Run `uv run scripts/doctor.py`. It checks ffmpeg (with libass), the ElevenLabs key, npx and the person
cut-out model (for the text-behind-the-head hook), the agency brand profile, its fonts and its music, and
prints the fix for anything missing. The cut-out model is a one-time 176 MB download (MIT, rembg's GitHub
releases): ask the user before running the command doctor prints. Until it's there, `depth` hooks fall
back to the two-tier hook on their own.
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

### 2. Brand profile and style
Load the brand's `video-style.json`. If it's missing, make one: read
[references/brand-profile.md](references/brand-profile.md), prefill it from what already exists
(`brand-context.md`, logo, colours, fonts), and ask only the gaps, **one question at a time**.
The user's taste lives in this file. That's why their clips look like theirs and not a template.

The **style** is the look, separate from the brand ([references/styles.md](references/styles.md)):
| Style | In one line |
|---|---|
| `punch` | **Cyber Popular's default**: word-by-word captions, numbers and stressed words big in cyan with a blue glow, a **depth hook** (giant word rising from behind the head), zoom cut every ~3 s or at each new sentence, whooshes on zoom cuts and pops on key words, everything inside Meta's ad safe zone, no end card |
| `karaoke` | big captions, active word in colour, boxed hook (the fallback when a profile names no style) |
| `serenity` | small white captions at chest height + one italic-serif key word, B-roll, gold-logo end card |
| `serenity-bold` | same, key word in big bold sans |
| `serenity-naples` | small ALL-CAPS captions + big gold key words, two-tier hook, cream end card |

Use the profile's `"style"` unless the user names one ("en el estilo Serenity"). When the user isn't
sure, render the same cut in two styles and let them pick. If they want a look none of these covers
("make it like this account's reels"), make a new style from those videos: steps at the end of
styles.md.

**A style the user has named is kept as it is.** Punch ("edit this in Punch") is the user's keeper. To
try a different type of edit, copy the closest style to a new file under a new name and change the
copy. Never edit a named style to run an experiment. Change it only when the user asks for that
style to change ("Punch with softer whooshes"). `accent` is Punch's old name and still loads it.

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
- a **hook title**: on-screen text, at most 2 lines and about 40 characters, Spanish for Maria
  (`serenity` has none; `serenity-naples` wants `"small part | BIG WORD"`). `punch` wants
  `"top line | BIG | label"`, e.g. `"Tienes | 300 | segundos"`:
  - BIG goes **behind the head**. Make it ONE short word or number (≤ ~6 characters) that still reads
    with its lower third hidden: a number is ideal.
  - When BIG would be too long or too small, the builder falls back to the two-tier hook. It also does
    this when the head is too high in the frame or the cut-out model is missing.
  - `"hook_kind": "two-tier"` in the clip forces the plain hook.
  - One behind-the-head moment per video. More than that and it stops working as a pattern interrupt.
- the **segments** as word-index ranges,
- the **length**,
- for the reveal styles (`punch`, serenity): the **key words** (`"emphasis"`, word ids). Numbers are
  automatic in `punch`, and so are the words the speaker leans on (measured from the audio). Add the
  payoff word of a sentence the audio misses, e.g. "velocidad" in "la velocidad es el nuevo servicio al
  cliente". For serenity: the treatment, the body area, the benefit, about one every 2 s.
- any **B-roll** (`"broll"`: treatment, product, screen or stock clips, 1.5–3 s, placed on the words
  they show).

Show the plan to the user in plain words: a short table, one row per clip. **Wait for a yes before
building.** For a simple polish job, one line is enough ("I'll keep everything, cut the pauses, title: …").

### 5. Build
Write `work/plan.json` (format in the header of `scripts/build_clip.py`), then run:
```
uv run scripts/build_clip.py "<project>/work/plan.json"            # all clips
uv run scripts/build_clip.py "<project>/work/plan.json" --only <slug>
uv run scripts/build_clip.py "<project>/work/plan.json" --style serenity   # one style for every clip
```
It does these steps in order, and the order matters:
1. Snap cuts to word edges, drop fillers, and close pauses over `edit.max_pause` (jump cuts).
2. Lock a face-centred 9:16 frame per segment, with no panning inside a shot.
3. Alternate a punch-in on each cut (1.12× karaoke, ~1.07× serenity), so the jump cuts read as intentional.
   Styles with `edit.rhythm` (`punch`) also cut the zoom inside a long take: at each sentence end, or
   at the first word gap after ~3 s, cycling wide → 1.12× → wide → ~1.24×. The tightest level is capped
   so the face never fills more than ~15% of the frame. The audio is untouched.
4. Apply the style's grade, and add 30 ms audio fades at every cut.
5. Append the style's end card, if it has one (brand logo + contact lines). `punch` has none: the
   video ends right after the last word.
6. Clean up the voice and add music ducked under it (`mix_base.wav`).
7. A `depth` hook cuts the speaker out of the hook seconds with HyperFrames (`remove-background`, ~25 s
   on a CPU). The builder measures the top of the head from the cut-out and places BIG so the head hides
   ~30% of it. BIG is drawn first, then the cut-out of the speaker goes over it.
8. Sound effects (`sfx`, synthesized in `scripts/sfx.py`, nothing to license):
   - a riser and hit as the hook lands;
   - a whoosh peaking 1 frame before zoom cuts and B-roll cuts, sentence ends first, at most one per 3 s;
   - a soft pop when a key word lands.

   Levels are set against the voice. Then two-pass loudnorm of the whole mix runs to -14 LUFS.
9. Lay in the B-roll cutaways and the logo, then burn the captions and hook **last** so nothing covers them.

Captions find their height automatically (`caption.y: "auto"`): just under the chin for karaoke, at
chest height for serenity (pushed down on tight shots). `punch` keeps every caption and the hook inside
Meta's ad safe zone (`caption.safe_zone`), so any video can run as an ad. On a medium shot that's under
the chin. On a tight close-up the captions go above the head, and punch-ins grow downward from the top
of the head (details in styles.md). When the user is recording for ads or for us, suggest chest-up
framing with the eyes about a third down the frame.
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
| "captions bigger / another colour / all caps" | `caption.size` / `highlight` / `uppercase` in the brand profile (for a style that isn't the brand's default, under `"styles": {"<name>": {...}}`) |
| "make it look like Serenity's", "other style" | `"style"` in the plan or the profile |
| "that word shouldn't be big", "highlight X" | the clip's `"emphasis"` word ids (adds to the automatic picks); `"emphasis_auto": false` = only the listed words and numbers |
| "fewer / more big words" | `emphasis.stress_min` (higher = fewer), `emphasis.every_s`, `emphasis.max_gap_s` |
| "zoom more / less often" | `edit.rhythm.every_s`, `edit.rhythm.at_sentence`, `edit.rhythm.zooms`; `rhythm.enabled: false` = cut-only punch-ins |
| "sound effects louder / softer", "fewer whooshes", "no pops" | `sfx.whoosh_db` / `pop_db` / `hit_db` (dB vs the voice; -3 = louder), `sfx.whoosh_gap_s`, `sfx.pop: false`; `"sfx": "none"` on a clip; `sfx.enabled: false` for the brand |
| "no text behind my head", "move the big word" | clip `"hook_kind": "two-tier"`; `hook_title.depth.overlap` (more/less hidden), `depth.max_glyph_px` (size) |
| "change the phone on the end" | `contact` in the brand profile |
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
- **Font sizes are ASS sizes**: the font's full height (winAscent + winDescent), not its em. Arial Black
  at 100 draws a ~71 px em, Arial Bold ~90 px. The builder measures widths the same way
  (`ass_pil_font`), so wrapping and shrink-to-fit match what renders.
- **Motion graphics** (animated intros, animated b-roll cards, molecule-style explainers like the
  Serenity editor's) are a HyperFrames job: route to the `hyperframes` skill and drop the result in
  as a B-roll file. The built-in end card is a still that flashes in, not an animation.
- **Not built yet** (the editor does these, the scripts don't): whip and zoom-blur transitions
  between angles, light-leak flashes mid-clip, multi-camera angle switching. Single-camera footage
  gets punch-ins instead (with `edit.rhythm`, every few seconds as well as on cuts). Also not built: a
  "spotlight" moment (background dims and blurs on the punchline, reusing the cut-out) and icon pop-ins.
- **Sound effects can't be judged from numbers alone.** QA checks their levels against the voice, but
  ask the user to listen to the first clip with effects before shipping a batch.
- **iPhone HDR footage** (10-bit, e.g. 1440×2560 60 fps) is converted to 8-bit without tone mapping.
  If colours look washed out, re-export the source as SDR first.
