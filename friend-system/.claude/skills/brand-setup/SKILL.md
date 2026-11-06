---
name: brand-setup
description: Set up a brand's visual identity (colours, typeface, caption sizes, sound level). Use when the user wants to set their own look or names a new brand.
---
1. Ask for: brand name, accent colour, a second lighter colour, text colours, the typeface file (.ttf/.otf), the language. Never invent these.
2. Copy the font into `assets/fonts/`. Copy `assets/brands/_template.json` to `assets/brands/<brand>.json` and fill it in. `captions.swap.font` is the font's file name and is used by both the captions and the graphics. Set `accent` in `captions.swap` to the accent colour. `"accent_style": "pill"` in `captions.swap` makes emphasised words a coloured box instead of coloured text. Graphics take `accent`, `accent_2`, `ink`, `paper` from `palette`.
3. Use `"brand": "<brand>"` in each job's `job.json`.
4. Check it: on a finished job run `~/.cache/video-editor/whisperx-venv/bin/python scripts/run_job.py <job> --from captions` and look at the frames.
