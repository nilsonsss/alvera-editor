#!/usr/bin/env python3
"""lines.json + words_aligned.json + analysis/takes.json -> transcript/cuts.json (one cut per picked line, long lines split
at phrase boundaries, frame-exact).

lines.json entry: {"id","clip","start","end","text","take": <attempt number in takes.json>}
splits.json:      {"<line id>": ["<aligned token to split AFTER, with its punctuation>", ...]}
Cut start = min(take start, first aligned word - 0.10). Cut end = min(take end + 0.05, last aligned word + 0.40), never under
last word + 0.15: the aligner under-reads the LAST word by ~0.3 s (measured, four lines), so word end + 0.15
alone clips the final syllable, and the loud-span end alone can hold a breath.
Seconds are written (f+0.5)/30 and (f-0.5)/30 so build_timeline lands on the exact frame.
Usage: lines_to_cuts.py <job>   then take_pick.py check <job>"""
import os as _os; _os.environ["PATH"] = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "tools", "bin") + _os.pathsep + _os.environ.get("PATH", "")
import json, subprocess, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parent.parent
P = ROOT / "projects" / sys.argv[1]
TIGHT = "--tight" in sys.argv        # cut edges from the AUDIO, not the aligner: first voiced sound - 0.04 s, last voiced sound + 0.07 s
PAD_IN, PAD_OUT = 0.04, 0.07


def voiced_edges(clip, ws):
    """(onset, offset) in source seconds: the first and last sound above (speech level - 18 dB), measured per 10 ms on the raw clip.
    The offset is found by walking on from the last aligned word while the level holds (holes up to 60 ms), so the next attempt's
    breath or noise is never taken for the end of the line."""
    a = max(0.0, ws[0]["s"] - 0.7); b = ws[-1]["e"] + 0.8
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a}", "-t", f"{b - a}", "-i", str(P / "raw" / clip), "-vn", "-ac", "1", "-ar", "16000",
                          "-f", "f32le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, np.float32); n = len(x) // 160
    db = 20 * np.log10(np.sqrt((x[:n * 160].reshape(n, 160) ** 2).mean(1)) + 1e-9)
    thr = np.percentile(db, 92) - 18
    v = db > thr
    i0 = int((ws[0]["s"] - a) * 100)
    k = i0 + 25                                              # walk back from just inside the first word to where the sound starts
    while k > 0 and (v[max(0, k - 6):k + 1].any()): k -= 1
    onset = a + (k + 1) * 0.01
    j = int((ws[-1]["e"] - a) * 100) - 15
    hole = 0
    while j < n - 1 and hole <= 6:
        j += 1
        hole = 0 if v[j] else hole + 1
    offset = a + (j - hole + 1) * 0.01
    # silences of 0.30 s or more between the first and the last sound (the aligner hides them inside word extents)
    sil, i, i_on, i_off = [], int((onset - a) * 100), int((onset - a) * 100), j - hole
    while i < i_off:
        if not v[i]:
            k = i
            while k < i_off and not v[k]: k += 1
            if k - i >= 30: sil.append((a + i * 0.01, a + k * 0.01))
            i = k
        else: i += 1
    return min(onset, ws[0]["s"] - 0.02), max(offset, ws[-1]["e"] + 0.03), sil
A = json.loads((P / "transcript" / "words_aligned.json").read_text())
L = json.loads((P / "transcript" / "lines.json").read_text())
T = json.loads((P / "analysis" / "takes.json").read_text())
S = json.loads((P / "transcript" / "splits.json").read_text()) if (P / "transcript" / "splits.json").exists() else {}
shots = []
for l in L:
    ws = A[l["id"]]["words"]; t = T[l["clip"]]["takes"][l["take"] - 1]
    start = min(t["start"], ws[0]["s"] - 0.10)
    end = max(min(t["end"] + 0.05, ws[-1]["e"] + 0.40), ws[-1]["e"] + 0.15)
    if l.get("exact"):                              # an already-cut video: keep the span exactly
        start, end, sil = l["start"], l["end"], []
    elif TIGHT:
        on, off, sil = voiced_edges(l["clip"], ws)
        start = on - PAD_IN; end = off + (0.12 if l is L[-1] else PAD_OUT)
        if "cut_end" in l: end = float(l["cut_end"])               # explicit source second: a quiet last word sits under the speech threshold
        old = (min(t["start"], ws[0]["s"] - 0.10), ws[-1]["e"] + l.get("tail", 0.4))
        print(f"  {l['id']:9s} onset {on:.2f} (aligned {ws[0]['s']:.2f}) offset {off:.2f} (aligned {ws[-1]['e']:.2f}) | start {start:.2f} end {end:.2f} | was {l.get('head', 0.1)} / {l.get('tail', 0.4)} s around the words")
    elif "head" in l: start = ws[0]["s"] - l["head"]        # explicit: seconds before the first aligned word (tighter than the default)
    if "tail" in l and not TIGHT: end = ws[-1]["e"] + l["tail"]         # explicit: seconds after the last aligned word (aligner reads ~0.25 s short)
    fs, fe = round(start * 30), round(end * 30)
    want = S.get(l["id"], [])
    sp_idx = [i for i, w in enumerate(ws[:-1]) if w["w"] in want]
    if len(sp_idx) != len(want):
        sys.exit(f"{l['id']}: split tokens not found: {want} in {[w['w'] for w in ws]}")
    # --tight: every silence of 0.30 s or more inside the line (measured on the audio) becomes a JUMP CUT: last sound + 0.10 s, next onset - 0.04 s
    pairs = []                                   # (last frame of the earlier shot, first frame of the later shot)
    sil = sil if TIGHT and not l.get("keep_pauses") else []      # keep_pauses: a quiet word hides inside the "silence"
    for t0_, t1_ in sil:
        pairs.append((round((t0_ + 0.10) * 30), round((t1_ - 0.04) * 30)))
        print(f"    {l['id']}: silence {t1_ - t0_:.2f} s at {t0_:.2f} s cut out")
    for i in sp_idx:
        m = round((ws[i]["e"] + ws[i + 1]["s"]) / 2 * 30)
        if not any(q[0] <= m <= q[1] for q in pairs): pairs.append((m, m))
    pairs.sort()
    starts = [fs] + [q[1] for q in pairs]; ends = [q[0] for q in pairs] + [fe]
    edges = None
    line_shots = []
    for k in range(len(starts)):
        a, b = starts[k], ends[k]
        txt = " ".join(w["w"] for w in ws if a / 30 - 0.02 <= (w["s"] + w["e"]) / 2 < b / 30 + 0.02)
        cut = {"source": l["clip"], "start": round((a + 0.5) / 30, 4), "end": round((b - 0.5) / 30, 4),
               "src_frames": [a, b], "note": f"{l['id']} | {txt}", "line": l["id"]}
        if l.get("override"): cut["take_override"] = l["override"]      # why this attempt differs from take_pick.py's choice
        line_shots.append(cut)
    if l.get("order"):                              # e.g. [2, 0, 1]: the last phrase of the take plays FIRST (the speaker's "start with what changed",
        line_shots = [line_shots[i] for i in l["order"]]
    shots.extend(line_shots)
(P / "transcript" / "cuts.json").write_text(json.dumps({"cuts": shots, "note": "from lines_to_cuts.py"}, indent=1, ensure_ascii=False))
tot = sum(s["src_frames"][1] - s["src_frames"][0] for s in shots)
for i, s in enumerate(shots, 1):
    n = s["src_frames"][1] - s["src_frames"][0]
    print(f"{i:2d} {s['source'][4:8]} {s['src_frames'][0]:5d}-{s['src_frames'][1]:5d} ({n:3d}f {n/30:4.2f}s) {s['note'][:80]}")
print(len(shots), "shots,", tot, "frames,", round(tot / 30, 1), "s")
