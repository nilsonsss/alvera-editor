#!/usr/bin/env python3
"""Copy to projects/<job>/graphics/build_scenes.py and adapt. Frames come from the spoken words."""
import json
from pathlib import Path
P = Path(__file__).resolve().parents[1]
W = json.loads((P / "transcript/captions_corrected.json").read_text())["captions"][0]["words"]
CI = json.loads((P / "transcript/clip_infos.json").read_text())
TOTAL = CI[-1]["record_frame"] + CI[-1]["end_frame"] - CI[-1]["start_frame"]
w = lambda token, nth=0: [x["s"] for x in W if x["w"].lower().strip(".,?!:") == token.lower()][nth]
S = []
def sc(id, at, end, why, els, **x): S.append({"id": id, "at": at, "frames": end - at, "why": why, "elements": els, **x})
sc("hook", 1, 60, "headline on frame 2", [{"type": "hookstack", "at": 1, "out": 58, "y": 250, "size": 96, "words": [
    {"t": "Your headline", "at": 2, "bg": "accent", "fg": "paper", "rot": -2}, {"t": "goes here", "at": 14, "bg": "paper", "fg": "ink", "rot": 1.5}]}])
json.dump({"composition": "SceneFlat", "scenes": S}, open(P / "graphics/remotion/scenes.json", "w"), indent=1, ensure_ascii=False)
