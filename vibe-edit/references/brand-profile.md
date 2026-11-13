# Brand profile: `video-style.json`

One file per brand. It holds the visual taste and edit habits, so every clip comes out in that brand's
look. Relative paths resolve from the file's own folder. Anything left out falls back to the defaults
in `scripts/build_clip.py` (`DEFAULTS`). A working example is the agency's own profile in the vault,
`machine/vibe-edit/video-style.json`. It's kept there so git syncs it to every computer.

```jsonc
{
  "brand": "Example Med Spa",
  "language": "es",
  "audience": "who watches: e.g. Spanish-speaking women 30-60 considering aesthetic treatments",
  "caption": {
    "font_file": "fonts/DMSans-Bold.ttf",   // static TTF/OTF, or a list of paths (first that exists wins)
    "size": 76,                           // px at 1080x1920; 70-84 reads well
    "uppercase": false,
    "words_per_chunk": 3,                 // 2 = punchier, 4 = calmer
    "max_line_px": 800,                   // safe width (clears the right-side action buttons)
    "color": "#FFFFFF", "highlight": "#C9A882", "outline": "#3D2E25",
    "outline_px": 7, "shadow_px": 0,
    "y": "auto",                          // "auto" = just under the lowest chin; or a number 1100-1450
    "strip_punctuation": true,
    "pop": true,                          // active word grows 8%
    "numbers_as_digits": true             // "ocho de diez" -> "8 de 10"
  },
  "hook_title": { "enabled": true, "font_file": null, "size": 60, "color": "#FFFFFF",
                  "box": "#3D2E25", "y": 430, "seconds": 3.0, "uppercase": false },
  "logo": { "enabled": false, "path": "logo.png", "width": 120, "corner": "top-left", "opacity": 0.9 },
  "music": { "enabled": true, "folder": "music", "track": null, "volume_db": -22, "duck": true },
  "audio": { "lufs": -14, "true_peak": -1.5, "voice_cleanup": true },
  "length": { "min": 15, "max": 60 },
  "edit": { "pad_in": 0.06, "pad_out": 0.12, "max_pause": 0.4, "drop_fillers": true,
            "punch_in": 1.12, "min_piece_for_punch": 0.8 },
  "compliance": { "profile": "medspa", "extra_terms": [] },
  "open_rule": "how a clip should open (free text, read when picking)",
  "end_rule": "how a clip should end",
  "notes": ["preferences learned from feedback, newest last"]
}
```

## Making one (interview, one question at a time)

Prefill everything you can find first, and ask only the gaps:
- **Colours and fonts**: a client's `brand-context.md`, the website CSS, the agency's design system
  (`Agency/Brand/Cyber Popular Design System/colors_and_type.css`).
- **Logo**: `logo.png` in the client folder, or the design system's `assets/`.
- **Compliance**: `medspa` for any med spa or aesthetics client, `none` otherwise.

Then ask, one at a time, in plain words (Spanish if the user writes in Spanish):
1. "Here's how captions would look: [colours/font]. Do you want them like this, or do you have a
   screenshot of a style you like?" If they send a screenshot, match the font weight, colours,
   highlight style and case.
2. "Music: use the beds we already have, or do you want a specific vibe?" If they want a vibe and
   have no tracks, offer to resolve one with the `media-use` skill (HeyGen music library, already
   licensed) into the brand's `music/` folder.
3. "How should a clip open and end?" Write the answers into `open_rule` and `end_rule`.
4. "Logo on the video, or keep it clean?" Organic usually looks more native without one.

Show the first test clip and adjust until they like it. Every adjustment goes into this file.

## Fonts

Both Windows and macOS ship Arial Black: `C:/Windows/Fonts/ariblk.ttf` and
`/System/Library/Fonts/Supplemental/Arial Black.ttf`. A profile used on both machines lists both:
`"font_file": ["C:/Windows/Fonts/ariblk.ttf", "/System/Library/Fonts/Supplemental/Arial Black.ttf"]`.
If no listed path exists, the file name is looked up in the usual font folders. The family name libass
needs is read from the font file itself.

For a brand font (Inter Tight, Montserrat, DM Sans…), put the static `.ttf` in a `fonts/` folder next to
the profile, which makes it portable (Google Fonts files are free to use), and point `font_file` at it.
Ask before downloading. libass loads it from there, so nothing has to be installed system-wide.
