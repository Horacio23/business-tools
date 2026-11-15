# Styles: `styles/<name>.json`

A **style** is a look: how captions are set and animated, the hook, the end card layout, the grade, how
loud the music sits, and the QA targets that go with it. A **brand profile** is an identity: logo,
contact lines, music folder, language, compliance. Any brand can wear any style. The end card fills
the style's layout with the brand's logo and contact lines.

## The styles

| Style | Looks like | Use for |
|---|---|---|
| `punch` | White heavy-sans captions (navy edge) that appear word by word, 3 at a time; **numbers and the words the speaker stresses** jump out on their own line, bigger, in **cyan with an electric-blue glow** and a small pop; a **depth hook** (a giant cyan word rising from behind the speaker's head, a small line above, a white label across it; two-tier when it can't fit); a **zoom cut every ~3 s or at each new sentence** on top of the jump cuts; **sound effects** (whoosh on zoom cuts, soft pop on key words, riser + hit on the hook); everything inside **Meta's ad safe zone** (above the head on close-ups); **no end card** (ends on the last word) | **Cyber Popular's default** (Horacio's pick, Nov 2026). Fast, attention-holding talking heads. Colours are the Cyber Popular Design System's; a client profile can wear it in its own colours |
| `karaoke` | Big heavy captions, 3 words at a time, the spoken word lights up in the brand colour, boxed hook title for 3 s, tight punch-ins, quiet music | The original look. Punchy talking heads (agency content) |
| `serenity` | Small white sentence-case captions at chest height that appear word by word, one key word per phrase set big in an **italic serif** (Bodoni), soft shadow, no hook box, bright soft grade, present music, B-roll cutaways, 2 s end card (logo + WhatsApp/SMS lines on light grey, flashes in from white) | Editorial med-spa reels. Measured from the Serenity (Miami) editor's Oct 2026 reels |
| `serenity-bold` | Same as `serenity`, but the key word is a **big bold sans** (up to 150 px, shrinks to fit) | Cleaner on busy backgrounds. The Oct 17 re-delivery the client picked |
| `serenity-naples` | Small **ALL-CAPS** white captions low on the frame, key words in big **gold** caps, a two-tier hook ("SI TE HAS PUESTO" small serif over "BOTOX" big gold), 3 s cream end card with gold logo, phone and address | The Serenity Naples reels (Nov 2026) |

Pick the style by, in order: `--style` on the command line, the clip's `"style"`, the plan's `"style"`,
the brand profile's `"style"`, else `karaoke`. One plan can render the same cut in several styles
(one clip per style, same segments) so the user can compare.

## What the styles need from the footage and the plan

- **Shot size.** The serenity styles were measured on **medium shots** (waist or knees up), where
  chest height is clear of the face. On a tight close-up, `"y": "auto"` pushes the captions down to
  clear the chin. If even 1500 px can't clear it, QA warns that the captions touch the chin.
- **Safe zone** (`caption.safe_zone`, on in `punch`). Every caption line and hook line stays inside
  `{"top", "bottom", "side"}`; Meta's ad zone is `{"top": 269, "bottom": 1248, "side": 65}` (14% top,
  35% bottom, 6% sides of 1080×1920). It's an ads rule: the Sponsored label, CTA button and ad text cover
  the bottom third. Organic Reels only lose the bottom ~20% and the right-hand buttons. Cyber Popular keeps
  every video inside it, so any post can be boosted or run as an ad without re-editing.
  - **Medium shot** (chest up, eyes about a third down the frame): the captions fit under the chin,
    above y 1248.
  - **Tight close-up** (the 300-segundos footage): they can't. The builder places the caption block
    **above the head** instead, and every punch-in grows downward from the top of the head
    (`zoom_anchor: head_top` in `build.json`) so the head never rises into them.
  - While the hook is on screen it has the top to itself, and captions start when it clears. The `.srt`
    keeps every word.
  - QA FAILs any caption or hook line outside the zone, and WARNs if captions above the head reach the
    brow.
- **Key words** (`caption.mode: "reveal"`). At most one per phrase, chosen in this order:
  1. word ids listed in the clip's `"emphasis": [12, 27, ...]` (always shown),
  2. numbers, if the style sets `emphasis.numbers` (`punch` does). "8 de 10" stays together as one key word,
  3. the style's `pick` rule, unless the clip sets `"emphasis_auto": false`:
     - `"longest"` (serenity): the longest content word, at most one every `every_s` seconds;
     - `"stress"` (punch): the words the speaker leans on. Each kept word gets a score from its loudness,
       pitch and stretch against the ~12 words around it. Words scoring ≥ `stress_min` (1.2) win, strongest
       first, never closer than `every_s` (2.2 s) to another key word. Any stretch longer than
       `max_gap_s` (4 s) without one gets its best-spoken content word.

  `"emphasis": "none"` turns key words off. The audio can't tell meaning: when planning, add the payoff
  word of a sentence if the speaker didn't stress it (on the 300-segundos test the stress pass found
  DEMORAN and RESPONDE; VELOCIDAD was added by hand). Serenity's good picks are the treatment, the body
  area, the benefit, or the emotional word ("papada", "naturales", "equilibrio", "dolió"). The Serenity
  editor uses about one every 2 seconds. `build.json` lists the picks in `emphasis_words`.
- **Rhythm** (`edit.rhythm`, `punch`). Jump cuts already change the zoom. Inside a continuous take the
  builder adds a zoom cut at each sentence end (once the shot is ≥ `min_shot_s`, 1.3 s), or at the first
  word gap after `every_s` (3 s). Levels cycle through `zooms` ([1.0, 1.12, 1.0, 1.24]), centred on the
  face. The tightest is capped so the face fills at most `max_face_area` (15.5%) of the frame, which
  keeps the QA framing gate at PASS. Only the picture is cut; the audio of a take stays continuous. On
  the 300-segundos test: 11 jump cuts + 3 zoom cuts in 25 s, no shot over 3 s. `build.json` has `shots`
  and `zoom_cuts`.
- **B-roll** (`"broll"` in the clip). The serenity reels cut away to treatment footage, product
  close-ups or stock for 1.5–3 s while the voice continues. Each item is
  `{"file", "at_word" (source word id), "seconds", "from"}`. The clip is scaled to fill 9:16 and graded
  like the rest. Look at the clip before placing it, and match it to the words it covers.
- **Two-tier hook** (`serenity-naples`, and `punch`'s fallback). Write `hook_title` as
  `"small part | BIG WORD"`, e.g. `"Si te has puesto | Botox"`. The big line shrinks to fit 900 px and
  wraps per word if it must (3 lines in all is the most QA allows).
- **Depth hook** (`hook_title.kind: "depth"`, `punch`). This is the trending "text behind the
  subject" look. Write `hook_title` as `"top line | BIG | label"`, e.g. `"Tienes | 300 | segundos"`
  (`"Tienes | 300 segundos"` works too: the first word after the bar becomes BIG).
  1. The builder cuts the speaker out of the hook seconds of `base.mov` with
     `npx hyperframes remove-background` (MIT `u2net_human_seg`, ~3.5 frames/s on a CPU). The output is
     `cutout.mov`, ProRes 4444 with alpha.
  2. It reads the top of the head from the cut-out's alpha: the median over the hook's frames.
  3. It sizes BIG to the safe-zone width, capped at `max_glyph_px` (400 px) tall, and places it so the
     head hides `overlap` (30%) of it.
  4. It places the top line `gap_px` above BIG, and the label in front across BIG's middle (`label_at`
     0.55), never lower than 8 px above the head.
  5. BIG rises `rise_px` from behind the head over `rise_ms`; the label pops in at `label_delay`.

  Render order: base → `behind.ass` (BIG + glow) → the cut-out on top → B-roll/logo → `captions.ass`
  (the top line, the label, captions).
  - **Falls back to two-tier** (with the reason in QA's captions line) when BIG would be under
    `min_glyph_px` (180 px) tall, the head sits too high for BIG plus the top line to fit in the zone, no
    person is found, or npx or the model is missing. The model is a one-time 176 MB download; ask the user
    first, and `doctor.py` prints the command.
  - **What works**: one short word or number for BIG, since a long word loses its middle letters behind
    the head; the label across BIG's middle. A label across BIG's bottom hides exactly where the head
    overlaps, and the depth disappears. Use it once per video.
  - Tested on 300 segundos (2026-11-14): head top y 720, BIG "300" at 662 (348 px tall, 939 px wide),
    104 px hidden, clean hair edge.
- **Sound effects** (`sfx`, on in `punch`). They're synthesized in `scripts/sfx.py` (filtered noise and
  sine sweeps), so there are no sample files to license or ship.
  - **Hook**: a hit when the hook lands, plus a riser while a depth hook's BIG rises.
  - **Whoosh**: on cuts where the zoom changes, and on B-roll starts. Sentence ends go first, at most one
    per `whoosh_gap_s` (3 s), peaking 1 frame before the cut so the sound leads the picture. They
    alternate left→right and right→left.
  - **Soft pop**: when a key word lands. At most one per `pop_gap_s`, none within 0.45 s of a whoosh.
  - Each `*_db` is the effect's loudest 30 ms against the voice's average level, measured on the voice +
    music mix before the effects.
  - The test clip got 14 effects in 25 s: riser + hit, 5 whooshes, 7 pops. The loudest was 2.9 dB under
    the voice.
  - QA runs the cut and music checks on `mix_base.wav` (a whoosh on a cut isn't a pop) and adds a
    "sound effects" line.
  - Phones play little below ~150 Hz, so the hit carries a mid "knock" as well as the boom.
- **End card.** Comes from the brand profile's `contact`: `{"logo", "lines": [{"icon"|"label", "text",
  "small"}]}`. A brand with a different card per style puts it under `"styles": {"<name>": {"contact": ...}}`.
  With no contact and no logo, the end card is skipped and the build prints why.

## Schema (fields a style can set)

```jsonc
{
  "name": "serenity", "description": "...",
  "caption": {
    "mode": "reveal",                 // "karaoke" (word highlight) | "reveal" (word-by-word fade-in + key word)
    "font_file": ["C:/Windows/Fonts/arialbd.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"],
    "size": 68, "uppercase": false, "words_per_chunk": 4, "max_line_px": 800,
    "color": "#FFFFFF", "outline": "#000000", "outline_px": 2, "outline_opacity": 0.45, "blur": 5,
    "shadow_px": 2, "shadow_color": "#000000", "shadow_opacity": 0.45,
    "y": "auto", "y_pref": 1150,     // reveal: preferred block centre, pushed down to clear the chin
    "safe_zone": null,                // or {"top": 269, "bottom": 1248, "side": 65} = Meta's ad zone
    "strip_punctuation": "light",     // true = strip all, "light" = keep ¿ ¡ ? ! inside, drop trailing , .
    "fade_ms": 120,
    "emphasis": {"enabled": true, "font_file": [...], "size": 100, "color": "#FFFFFF", "uppercase": false,
                 "every_s": 1.6, "min_len": 5, "line_scale": 0.8,
                 "numbers": false,            // true = every number gets the big line
                 "pick": "longest",           // or "stress" (+ "stress_min": 1.2, "max_gap_s": 4.0)
                 "pop": 1.0,                  // 1.25 = the key word lands 25% big and settles in 160 ms
                 "glow": null, "glow_px": 16, "glow_blur": 12, "glow_opacity": 0.8}   // "#2563FF" = halo
  },
  "hook_title": {"enabled": true, "kind": "box" | "two-tier" | "depth", ...},  // two-tier: small_font_file,
                                                        // small_size, small_y, big_color, big_y, big_max_px, glow
                 // depth: {"top_size": 110, "label_size": 150, "label_color": "#FFFFFF", "max_glyph_px": 400,
                 //         "min_glyph_px": 180, "overlap": 0.3, "gap_px": 28, "label_at": 0.55,
                 //         "label_delay": 0.35, "rise_px": 140, "rise_ms": 420}  (+ big_color, glow, fonts)
  "sfx": {"enabled": false, "whoosh": true, "whoosh_db": -8, "whoosh_gap_s": 3.0, "pop": true, "pop_db": -12,
          "pop_gap_s": 1.2, "hit": true, "hit_db": -3, "riser": true, "riser_db": -10},  // dB vs the voice
  "end_card": {"enabled": true, "seconds": 2.0, "background": "#FAF7F4" | ["#F4F4F4", "#D9D9D9"],
               "logo_width": 610, "logo_y": 946, "lines_y": 1402, "line_gap": 125, "text_font": [...],
               "text_size": 68, "small_size": 34, "text_color": "#FFFFFF", "label_color": "#C9A54E",
               "icon_height": 98, "shadow": true, "fade_in": 0.35, "fade_color": "white"},
  "grade": {"enabled": true, "target_luma": 145, "contrast": 0.95, "saturation": 0.95,
            "black_lift": 0.035, "temperature": 6200},   // target_luma pulls average brightness toward the reference
  "music": {"volume_db": -17, "duck": true},
  "edit": {"punch_in": 1.08,
           "rhythm": {"enabled": false, "every_s": 3.0, "min_shot_s": 1.3, "at_sentence": true,
                      "zooms": [1.0, 1.12, 1.0, 1.24], "max_face_area": 0.155}},
  "qa": {"min_voice_over_music_db": 6}                   // the serenity reels keep music only ~4-6 dB under the voice
}
```

**Sizes are ASS sizes**: the font's full height (winAscent + winDescent), not its em. Arial Black at 100
draws a ~71 px em, Arial Bold ~90 px, Bodoni MT Italic ~83 px. The builder measures text the same way
(`ass_pil_font`), so wrapping, shrink-to-fit and the QA width check match the render. Before 2026-11-14
it measured at the em and wrapped too early. Since then karaoke fits 3 words per line more often, and
the rendered sizes are unchanged.

Every font is a list: the Windows path, then the Mac fallback. Bodoni MT (Windows, comes with Office)
has no exact Mac twin, so the Mac uses Georgia Italic, and Century Gothic falls back to Arial. For an
identical look on both machines, put an OFL font in the vault (e.g. Playfair Display Italic) and list it
first. Ask before downloading. `scripts/doctor.py` checks every style's fonts.

## Trying a new type of edit (keep the named ones fixed)

`punch` is the user's keeper (named 2026-11-14; its old name `accent` still loads it through
`STYLE_ALIASES` in `build_clip.py`). To try a different type:
1. Copy the closest style to `styles/<new-name>.json`, and set its `name` and `description`.
2. Change only the copy, then render the same cut in both styles so the user can compare them.
3. If the user keeps it, give it a name they'll say out loud. Otherwise delete the file.

Never edit a named style for an experiment. Change it only when the user asks for that style to change.
Renaming a style: rename the file, add the old name to `STYLE_ALIASES`, and update the brand profiles
that name it.

## Making a new style from someone's videos

This is how the serenity styles were made. Repeat it for any editor or account the user wants to match.
1. **Collect** the finished reels (not the raw footage). Group them by batch or editor, because looks
   drift between deliveries.
2. **Contact sheets**: 12 frames per video (`fps=12/duration,scale=270:480,tile=4x3`). Read them to
   find the caption type, case, position, key-word treatment, B-roll habits, transitions and end card.
3. **Measure, don't guess.** Pull full-size frames and measure the white text extents with numpy.
   Convert widths to ASS font sizes with `ass_pil_font(font, 100).getlength(text)` (not plain PIL at
   100, which gives the em). The first guess from a grid was 15% too small. Also take the brightness (`signalstats` YAVG), the loudness (`ebur128`) and the cut
   times (`select='gt(scene,0.28)'`).
4. **Pacing and music level**: transcribe 2–3 reels with `transcribe.py`, then compare speech RMS with
   the RMS between words and after the last word. That gives words per second, the longest pause left
   in, and how far under the voice the music sits.
5. **Brand assets**: cut the logo, icons and end-card colours from an end-card frame (circular or
   rounded alpha mask, or key out a flat background). Save them in the client's `video-brand/`.
6. Write `styles/<name>.json` and a brand profile, build one test in each style from the same cut, and
   compare full-size frames side by side with the reference. Adjust sizes until they match.
