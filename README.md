# Video editor — upgrade workspace

Where we keep improving Claude's video editing (Alvera + personal brand).

## Folders
- `our-editor/` — shortcuts (links) to the editor Claude uses today. The real files live in
  `~/.claude/skills/` and must stay there for Claude to find them; editing through these links
  edits the real thing.
  - `video-core/` shared engine: `scripts/render.py` (edit list → finished MP4), `prep_clip.py`
    (stabilise, LUT, framing), `snap_words.py`; `brands/alvera/` (brand, footage index, learned rules).
  - `edit-paid-ads/`, `edit-short-form/`, `edit-youtube-long/` — one skill per format.
- `friend-system/` — "Video Editing System" a friend sent (moved from Downloads on 2026-10-31,
  unchanged, not installed). Built for talking-head vertical reels: whisperX word alignment, take
  picking, face-based framing, word-by-word captions, Remotion graphics, SFX catalog, loudness, QA
  report. Its `setup.sh` installs ~10 GB (whisperX, Node, Remotion) — not run.

## Where to put things (everything lives here)
- `assets/sfx/` — sound effects. Descriptive names help: `whoosh_soft_airy.wav`, `metal_click_sharp.wav`.
- `assets/music/` — tracks you hold a licence for; put the mood in the name: `code_blue_jazzy_ambient.mp3`.
- `assets/luts/` — colour LUTs (.cube). A graded clip you like works too.
- `assets/fonts/` — fonts (20 free trendy families already here; SPECIMEN.png shows them). Add brand fonts as .otf/.ttf.
- `footage/alvera/`, `footage/personal/` — raw videos and photoshoots, one subfolder per shoot.
- `references/alvera/`, `references/personal/` — ads and videos you like; add a line in a `notes.txt` on what you like about each.
- `brands/alvera/` — copies of the brand guidelines PDF, logos, cards, product pics, ads (voiceover, statics), email images, other (0915 edit, NH36).
  `brand-notes/` links to Claude's live Alvera notes (brand rules, footage index, learned style).
- `edits/` — every finished edit, one folder each: `<date>_<brand>_<name>/final.mp4`.

Still elsewhere until moved here (Claude reads both): music `~/Documents/Nils/music/`, LUTs `~/Documents/Alvera/LUTS/`, Alvera footage `~/Documents/Alvera/SHOOTS/`,
earlier Alvera edits `~/Documents/Alvera/EDITS/`.

## Upgrade ideas from friend-system (to review)
- Word-accurate caption timing (whisperX alignment) and one-word-per-cue caption mode
- Take picking for talking-head footage (personal brand / YouTube)
- Face-measured framing that alternates shot sizes
- Automatic QA: contact sheet of cuts + report next to every render
- SFX catalog file (what each sound is, its peak time) instead of profiling each time
- Remotion animated graphics wired to spoken words
