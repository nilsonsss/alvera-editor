# Graphics

`projects/<job>/graphics/build_scenes.py` writes `graphics/remotion/scenes.json`; the `graphics` stage renders it. `examples/build_scenes.py` is a working starting point.

```json
{"composition": "SceneFlat", "scenes": [{"id": "hook", "at": 1, "frames": 60, "why": "...", "elements": [{"type": "banner", "at": 1, "out": 58}]}]}
```
All frames are absolute timeline frames. Take them from `transcript/captions_corrected.json` (the frame each word starts). Scenes must not overlap in time; one scene can hold several elements. A scene must end inside the video. `"captions": "off"` on a scene allows it over the caption band (use with `caption_skip.json`).

Pictures and clips go in `projects/_remotion/public/`, referenced by file name.

## Elements (besides `type`, `at`, `out`; most take `x`, `y`)
| type | fields | what |
|---|---|---|
| hookstack | y, size, gap, words[{t, at, bg, fg, rot, dx}] (bg / fg: accent, paper, ink, haze) | headline blocks that land on their words |
| banner | text, sub, w, size, strikeAt, swapAt, text2 | wipe-in bar; strike through; swap text |
| plate | glyph, label, size, shape, fill, tilt | an icon on a plate |
| pairicons | size, gap, items[{g, at, ink}] | two or more icons, each on its word |
| tiles | cols, rows, glyphs, size, gap, step, crossFrom, crossStep, label | a grid of icons, optionally crossed out |
| counter | countFrom, countTo, max, label, badges | a number counting |
| clock | dur, label, size | a clock running |
| stamp | text, size, rotate | a round sticker (a price) |
| steps | climbFrom, climbDur, flagAt, label | stairs climbed to a flag |
| chips | items[{t, at, x, y, glyph}] | ticked chips |
| toggle | l1, l2, flipAt | a switch flipping |
| follow | text, done, tapAt | a button that gets tapped |
| bubble | text, msgAt, w, size, scale | a message bubble |
| photocard | src, w, h, tilt, label, pos | a picture card |
| bgvideo | src, skip, brightness, splitY, splitFade, pos, h | a clip behind the speaker with `"layer": "behind"`; split = down to the chest, fading into the room |
| behindword | text, size, color, opacity, rotate | a giant word behind the head, `"layer": "behind"` |

Glyphs: fish heart bell clock ban book person people flag camera check bread wrench bulb star spark smile bottle hammer phone chat route.
Field names ending in `At`, `From`, `To`, `Frame` (and `to`, `from`) hold absolute frames and are converted for you; do not use such names for anything else.

## A new element
Add a component to `SceneFlat.tsx` (`const XEl: React.FC<P> = ({e, lf, brand, ex}) => ...`; `lf` = frames since `at`, `ex` = exit fade, colours from `brand`, font family `BrandFont`) and a `case` in the switch at the bottom. Check a frame: `~/.cache/video-editor/whisperx-venv/bin/python scripts/remotion_gfx.py preview <job> <scene> --frames a,b --safe`.
