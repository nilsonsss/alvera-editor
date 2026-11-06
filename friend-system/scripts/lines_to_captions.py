#!/usr/bin/env python3
"""words_aligned.json (source seconds, from align_words.py) -> captions_corrected.json (timeline frames), the input of
caption_swap.py plan. Source seconds are mapped to timeline frames through clip_infos.json (record_frame + source
frame - start_frame). Accent = every token that contains a digit (the numbers are the point of a cost video);
change `accent` in the output file by hand for any other emphasis.
Usage: lines_to_captions.py <job> [--timeline NAME]"""
import os as _os; _os.environ["PATH"] = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "tools", "bin") + _os.pathsep + _os.environ.get("PATH", "")
import argparse, json, re
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser(); ap.add_argument("job"); ap.add_argument("--timeline"); a = ap.parse_args()
P = ROOT / "projects" / a.job / "transcript"
A = json.loads((P / "words_aligned.json").read_text()); CI = json.loads((P / "clip_infos.json").read_text())
L = json.loads((P / "lines.json").read_text())

def tl(clip, t):
    """source seconds -> timeline frame. Source frames are counted at the clip's own rate (29.97 for the Canon files), the timeline at 30; a
    conformed span (conform_sources.py) starts `src_offset` seconds into the original clip."""
    best = None
    for c in CI:
        if c["source"] != clip: continue
        fps = float(c.get("clip_fps", 30.0)); f = (t - float(c.get("src_offset", 0.0))) * fps
        if c["start_frame"] <= f < c["end_frame"]:
            return c["record_frame"] + (f - c["start_frame"]) * 30.0 / fps
        d = min(abs(f - c["start_frame"]), abs(f - c["end_frame"]))
        if best is None or d < best[0]: best = (d, c, f, fps)
    _, c, f, fps = best
    n = round((c["end_frame"] - c["start_frame"]) * 30.0 / fps)
    return c["record_frame"] if f < c["start_frame"] else c["record_frame"] + n

words = []
for l in L:
    for w in A[l["id"]]["words"]:
        s = int(round(tl(l["clip"], w["s"]))); e = s + max(2, round((w["e"] - w["s"]) * 30))
        words.append({"w": w["w"], "s": s, "e": e, "accent": bool(re.search(r"\d", w["w"]))})
# optional transcript/caption_edits.json: {"accent_first": [tokens], "accent_all": [tokens], "accent_none": true, "display": {"twenties,": "20s,"}}
ed = P / "caption_edits.json"
if ed.exists():
    E = json.loads(ed.read_text())
    if E.get("accent_none"):
        for w in words: w["accent"] = False
    seen = set()
    for w in words:
        if w["w"] in E.get("accent_all", []): w["accent"] = True
        if w["w"] in E.get("accent_first", []) and w["w"] not in seen: w["accent"] = True; seen.add(w["w"])
    for w in words: w["w"] = E.get("display", {}).get(w["w"], w["w"])
words.sort(key=lambda x: x["s"])                 # a line whose shots were reordered (lines.json "order") is read in TIMELINE order
assert all(b["s"] >= x["s"] for x, b in zip(words, words[1:])), "words out of order"
total = sum(c["end_frame"] - c["start_frame"] for c in CI)
out = {"timeline": a.timeline or a.job, "fps": 30, "source": "align_words.py + lines_to_captions.py",
       "captions": [{"index": 0, "text": a.job, "start_frame": 0, "duration": total, "words": words}]}
(P / "captions_corrected.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
print(len(words), "words;", sum(w["accent"] for w in words), "accent; last word ends", words[-1]["e"], "of", total)
