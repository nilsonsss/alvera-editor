# Video Editing System

The user gives a prompt and footage; Claude edits a finished vertical talking-head video (1080x1920) from it: cuts, framing, captions, animated graphics, sound effects, loudness. Only ffmpeg and Remotion are used; no video editor app is needed.

## First thing, every session
The session starts with a status line from `bash setup.sh --check`. If it is not READY (or you did not see it, run the check yourself): before anything else tell the user in one sentence that you are installing the system (about 15 minutes the first time, mostly downloads), run `bash setup.sh` in the background, and report when it is done. Do not ask them to run it themselves. Then, if `assets/brands/` holds only `starter` and `_template`, offer the `brand-setup` skill; they can also start with `starter`.

All commands below use `PY=~/.cache/video-editor/whisperx-venv/bin/python`.

## Pipeline
`PY scripts/run_job.py <job> --auto` (see its docstring): `intake → author → align → cuts → timeline → matte → frame → captions → graphics → sfx → finish`. `--auto` re-runs only what an edited input made stale.
Claude's creative work is the plan files: `transcript/lines.json` (which take of which line, in order), optional `splits.json`, `caption_edits.json`, `caption_skip.json`, `frame.json`, `broll.json`, `sfx_manual.json`, `judgement.json`, and `graphics/build_scenes.py`. Everything else is automatic.
1. Find the clips, pick a kebab-case job name, write `projects/<job>/job.json`: `{"brand": "<brand>", "language": "en", "format": "1080x1920@30", "keywords": ["names to spell right"]}`.
2. `PY scripts/run_job.py <job> --clips <files...>`: copies the clips to `raw/`, transcribes, splits into takes, judges every attempt, stops at `author`.
3. Write the plan files from `analysis/takes.json` and `analysis/take_pick.json`. Graphics: `docs/graphics.md`.
4. `PY scripts/run_job.py <job> --auto`. Long stages run in the background.
5. Look at `outputs/qa/*_cuts.png` and `*_qa.png`, read `outputs/<job>_report.md`, then report: what was made, what was checked, the judgement calls, what is weak.
An already-cut video: one `lines.json` entry per sentence with `"exact": true`, each ending where the next starts, `frame.json` scales all `1.00`.

## Layout
Chin at y ≈ 1150, captions at one height (y ≈ 1288), front graphics in the top band (y 232 to the head top). Safe zone: y 220-1440, 60 px from the sides, nothing at x > 980 below y 1155. Never over the face. `remotion_gfx.py` fails a scene that breaks this. For ads that also run in a 4:5 feed keep everything inside y 320-1600.

## Cutting
About 0.11 s of silence between takes (`lines_to_cuts.py --tight`); silences of 0.3 s or more inside a take are cut. Never cut into a word. Shots of ~1.2-3 s, cut at phrase boundaries. The video ends ~0.15 s after the last sound. If the read-back flags a quiet word that was lost, set `keep_pauses: true` or `cut_end: <second>` on that line.

## Takes
Default: the LAST complete attempt of each line (reaches the end, no stutter or restart). An earlier one only if the last has a defect. Settle numbers and names with `take_verify.py`. A cut on a non-picked attempt carries `override` in `lines.json`.

## Framing
Two clearly different centred sizes alternating from shot to shot, sized from the measured head; the face is never cut; scale never below 1.0. `frame_solver.py` solves it. Shots of one take that keep the same size should not be split.

## Captions
Brand typeface, two sizes (one word / one grouped line), one height per video, one word per cue at speech pace, no cue across a cut. Accents via `caption_edits.json`: numbers, the key noun of a point, the CTA verb. A stretch carried by a headline can skip captions (`caption_skip.json`).

## Graphics
Remotion, `projects/_remotion/src/SceneFlat.tsx`; how to use and extend them is in `docs/graphics.md`. Colours and typeface come from the brand file. About one graphic per 6-8 s, tied to what is said, landing on the frame the word is spoken. A designed visual by frame 3. When the user wants a look the elements cannot give, add a new element.

## B-roll
`transcript/broll.json`: `{"scrim": true, "inserts": [{"source", "src_start", "at", "frames"}]}` (sources in `raw/`). Covers the picture while the voice runs; not on the hook or the close.

## Sound
Effects at the brand's level (`sfx.gain_db`), derived from the scenes or set in `sfx_manual.json` (`[{"name","at","gain_db"}]`, names in `assets/sfx/catalog.json`). The voice is only processed on the finished file: `channel_fix.py`, then `loudness.py` (-14 LUFS).

## Rules
Never change or delete the user's original files; never post or upload anything. Every delivered version is a new `outputs/<job>_v<N>.mp4`. When a stage fails, read its message, fix the cause, re-run with `--from <stage>`. Numbers are spelled for the aligner in English only: in other languages write numbers as words in `lines.json`.
