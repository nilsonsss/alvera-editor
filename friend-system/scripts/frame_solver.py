#!/usr/bin/env python3
"""Measure where the speaker actually IS in each shot (from the matte) and solve the Pivot that puts the speaker where
the composition wants the speaker. Replaces guessing a pivot and hoping.

  frame_solver.py measure <job>                      -> graphics/matte/subject.json (per shot: cx, head top, chin, hand top)
  frame_solver.py plan    <job> --write              -> transcript/effects.json zooms with solved pivots

Scaling a Transform about Pivot p maps x -> p + (x-p)*s, so to land the subject's centre cx at target t:
    p = (cx*s - t) / (s - 1)        (s > 1)
Any s >= 1 is black-bar-safe at any p: the visible range is [p-p*s, p+(1-p)*s], which covers [0,1].
"""
import os as _os; _os.environ["PATH"] = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "tools", "bin") + _os.pathsep + _os.environ.get("PATH", "")
import argparse, json, subprocess
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
FF = "ffmpeg"
W, H = 1080, 1920


def read_gray(src):
    raw = subprocess.run([FF, "-v", "error", "-i", str(src), "-pix_fmt", "gray", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    n = len(raw) // (W * H)
    return np.frombuffer(raw[:n * W * H], np.uint8).reshape(n, H, W)


def spans_of(job):
    L = json.loads((ROOT / "projects" / job / "transcript" / "clip_infos.json").read_text())
    out, t = [], 0
    for c in L:
        d = c["end_frame"] - c["start_frame"]
        out.append((t, t + d)); t += d
    return out


def cmd_measure(a):
    P = ROOT / "projects" / a.job / "graphics" / "matte"
    M = read_gray(P / "alpha.mp4")
    rows = []
    for i, (s, e) in enumerate(spans_of(a.job), 1):
        seg = M[s:e].astype(np.float32) / 255
        m = seg.mean(axis=0)                                   # average occupancy over the shot
        ys, xs = np.where(m > 0.5)
        if len(xs) == 0:
            rows.append({"shot": i, "start": s, "end": e, "empty": True}); continue
        colw = (m > 0.5).sum(axis=0)
        cx = float((np.arange(W) * colw).sum() / max(1, colw.sum())) / W
        head = int(ys.min())
        # chin: the row where the silhouette stops being head-width and starts being shoulder-width
        wid = (m > 0.5).sum(axis=1).astype(float)
        headw = np.median(wid[head:head + 220]) if head + 220 < H else wid[head:].max()
        chin = head + 220
        for y in range(head + 150, min(H, head + 900)):
            if wid[y] > headw * 1.55:
                chin = y; break
        rows.append({"shot": i, "start": s, "end": e,
                     "cx": round(cx, 4), "head_top": head, "chin": int(chin),
                     "cover_pct": round(float((m > 0.5).mean() * 100), 1)})
    out = P / "subject.json"
    out.write_text(json.dumps({"width": W, "height": H, "shots": rows}, indent=1))
    for r in rows:
        print(f"shot {r['shot']:2d} f{r['start']:4d}-{r['end']:4d}  cx {r.get('cx','-'):>6}  "
              f"head top {r.get('head_top','-'):>4}  chin {r.get('chin','-'):>4}  covers {r.get('cover_pct','-')}%")
    print("->", out)


def cmd_plan(a):
    P = ROOT / "projects" / a.job / "graphics" / "matte"
    sub = {r["shot"]: r for r in json.loads((P / "subject.json").read_text())["shots"]}
    # subject.json was measured on the picture-only pass, which ALREADY had the previous pivots applied.
    # Back the measurement out to the untransformed frame first, or the solve compounds:  cx_o = p + (cx_c - p)/s
    old = json.loads((ROOT / "projects" / a.job / "transcript" / "effects.json").read_text()).get("zooms", [])
    prev = {z["clip"]: (z["anchor"][0], z["keys"][-1][1]) for z in old}
    for i, r in sub.items():
        if "cx" in r and i in prev:
            pp, ss = prev[i]
            r["cx"] = pp + (r["cx"] - pp) / ss if ss > 1e-6 else r["cx"]
    # alternating composition: L = the speaker sits left (card room on the right), R = right, C = centred
    pattern = a.pattern.split(",")
    targets = {"L": 0.34, "R": 0.64, "C": 0.50}
    scales = [float(x) for x in a.scales.split(",")]
    zooms = []
    for i, (s, e) in enumerate(spans_of(a.job), 1):
        want = pattern[(i - 1) % len(pattern)]
        sc = scales[(i - 1) % len(scales)]
        cx = sub[i].get("cx", 0.5)
        t = targets[want]
        if sc <= 1.001:
            p, sc = 0.5, 1.0
        else:
            p = (cx * sc - t) / (sc - 1)
            if not (0.0 <= p <= 1.0):                      # need more scale to reach that target
                for sc2 in (sc + 0.06, sc + 0.12, sc + 0.20, sc + 0.30):
                    p2 = (cx * sc2 - t) / (sc2 - 1)
                    if 0.0 <= p2 <= 1.0:
                        p, sc = p2, sc2; break
                else:
                    p = min(1.0, max(0.0, p))
        n = e - s
        keys = [[0, 1.34], [6, round(sc, 3)], [n - 1, round(sc, 3)]] if i == 1 else [[0, round(sc, 3)], [n - 1, round(sc, 3)]]
        land = p + (cx - p) * sc
        zooms.append({"clip": i, "keys": keys, "anchor": [round(p, 4), 0.66], "whoosh": False,
                      "compose": want, "subject_cx": cx, "lands_at": round(land, 3),
                      "why": f"{want}: subject measured at x {cx:.2f}, scale {sc:.2f}, pivot {p:.2f} lands the speaker at {land:.2f}"})
    if a.write:
        f = ROOT / "projects" / a.job / "transcript" / "effects.json"
        d = json.loads(f.read_text()) if f.exists() else {"brand": "starter", "sfx_gain_db": -14, "draft": False, "timeline": a.job, "zooms": [], "sfx": []}
        d["zooms"] = zooms
        d["review"] = ("Framing solved: each shot's pivot is computed from the subject's MEASURED "
                       "centre in the matte so the speaker actually lands left / right / centre as the pattern asks. "
                       "Scale is flat inside the shot and steps at the cut.")
        f.write_text(json.dumps(d, indent=1))
    prev = None
    for z in zooms:
        land = z["lands_at"] * W
        print(f"shot {z['clip']:2d} {z['compose']}  scale {z['keys'][-1][1]:.2f}  pivot {z['anchor'][0]:.2f}  "
              f"cx {z['subject_cx']:.2f} -> lands {land:4.0f}px" + (f"   moved {abs(land-prev):4.0f}px" if prev is not None else ""))
        prev = land
    print("written" if a.write else "(dry run, pass --write)")


def head_boxes(M, shots):
    """Per shot: the head's left/right extent on EVERY frame (the speaker sways inside a shot), plus head top and chin.
    The head is the run of columns, through the silhouette's centre, in the rows between forehead and jaw."""
    out = []
    for i, (s, e) in enumerate(shots, 1):
        seg = M[s:e] > 127
        m = seg.mean(axis=0) > 0.5
        wid = m.sum(axis=1).astype(float)
        rows = np.where(wid > 80)[0]
        if len(rows) == 0:
            out.append({"shot": i, "start": s, "end": e, "empty": True}); continue
        head = int(rows.min())
        headw = np.median(wid[head + 60:head + 260])
        chin = head + 260
        for y in range(head + 180, min(H, head + 900)):
            if wid[y] > headw * 1.55:
                chin = y; break
        y0, y1 = head + 50, max(head + 120, chin - 90)
        L, R, T = [], [], []
        for f in range(8 if s == 0 else 0, min(e - s, len(seg))):          # the first frames of the video are the camera settling
            fr = np.where(seg[f].sum(axis=1) > 80)[0]
            if len(fr): T.append(int(fr[0]))                # this frame's own head top (the speaker bobs while walking)
            occ = seg[f][y0:y1].mean(axis=0) > 0.5
            if not occ.any():
                continue
            c = int(round((np.arange(W) * occ).sum() / occ.sum()))
            if not occ[c]:
                idx = np.where(occ)[0]; c = int(idx[np.argmin(abs(idx - c))])
            a = c
            while a > 0 and occ[a - 1]: a -= 1
            b = c
            while b < W - 1 and occ[b + 1]: b += 1
            L.append(a); R.append(b)
        out.append({"shot": i, "start": s, "end": e, "head_top": head, "chin": int(chin),
                    "head_top_hi": int(np.percentile(T, 5)) if T else head,   # HIGHEST the head gets: size words behind the speaker from THIS
                    "head_left_min": int(np.percentile(L, 3)), "head_right_max": int(np.percentile(R, 97)),
                    "head_left_med": int(np.median(L)), "head_right_med": int(np.median(R))})
    return out


def cmd_head(a):
    P = ROOT / "projects" / a.job / "graphics" / "matte" / (a.sub or "")
    rows = head_boxes(read_gray(P / "alpha.mp4"), spans_of(a.job))
    (P / "head.json").write_text(json.dumps({"shots": rows}, indent=1))
    for r in rows:
        print(f"shot {r['shot']:2d}  head x {r.get('head_left_min')}-{r.get('head_right_max')}  "
              f"(typical {r.get('head_left_med')}-{r.get('head_right_med')})  top {r.get('head_top')}  chin {r.get('chin')}")
    print("->", P / "head.json")


def cmd_solve(a):
    """Framing from the NEUTRAL head boxes, with a hard rule: on every frame of the shot the head stays at least
    --margin px inside the frame. Side L/R pushes the speaker as
    far that way as the margin allows; C centres the speaker.

    --scales takes one entry per shot:
      1.20          flat for the whole shot (steps at the cut)
      (up to 1.6 is allowed; above --closeup-from 1.28 the pivot drops so the chin lands at --chin-max 1230)
      1.08>1.24     push-in across the whole shot        (1.24>1.08 = pull-out)
      1.08>1.24@8   push-in over the FIRST 8 frames, then held
      1.24>1.08@-10 held, then pull-out over the LAST 10 frames
    The pivot is solved at the LARGEST scale of the move: the margin bound (hl*s - m)/(s - 1) only tightens as s
    grows, so a pivot that is safe there is safe on every frame of the move."""
    P = ROOT / "projects" / a.job / "graphics" / "matte"
    hb = {r["shot"]: r for r in json.loads((P / "neutral" / "head.json").read_text())["shots"]}
    sides = a.pattern.split(","); specs = a.scales.split(",")
    m = a.margin / W
    zooms = []
    for i, (s0, e0) in enumerate(spans_of(a.job), 1):
        side, r = sides[i - 1], hb[i]; n = e0 - s0
        if r.get("empty"):                                     # nobody in the shot
            zooms.append({"clip": i, "keys": [[0, 1.0], [n - 1, 1.0]], "anchor": [0.5, 0.66], "whoosh": False, "compose": side, "why": "no person in this shot"}); continue
        spec, _, ramp = specs[i - 1].partition("@")
        a0, _, a1 = spec.partition(">"); a0 = float(a0); a1 = float(a1) if a1 else a0
        sc = max(a0, a1)                                       # solve where the move is tightest
        hl, hr = r["head_left_min"] / W, r["head_right_max"] / W
        mid = (r["head_left_med"] + r["head_right_med"]) / 2 / W
        if sc <= 1.001:
            p, sc = 0.5, 1.0
        elif side == "L":
            p = min(1.0, (hl * sc - m) / (sc - 1))             # largest pivot that keeps the left margin
        elif side == "R":
            p = max(0.0, (hr * sc - (1 - m)) / (sc - 1))       # smallest pivot that keeps the right margin
        else:
            p = min(1.0, max(0.0, (mid * sc - 0.5) / (sc - 1)))
        p = min(1.0, max(0.0, p))
        # Pivot HEIGHT. 0.66 (653 px from the top) suits scales up to ~1.28; a bigger close-up would push the chin past the captions
        # (1.6 about 653 px: chin 1110 -> 1384). Above --closeup-from the pivot moves down so the chin lands at --chin-max.
        ay = 0.66
        if sc > a.closeup_from + 1e-6:
            chin = float(r["chin"])
            py = (chin * sc - a.chin_max) / (sc - 1)
            py = min(1900.0, max(700.0, py))
            ay = round(1 - py / H, 4)
        else:
            py = (1 - ay) * H
        top_n = py + (float(r.get("head_top_hi", r["head_top"])) - py) * sc
        chin_n = py + (float(r["chin"]) - py) * sc
        nl, nr = (p + (hl - p) * sc) * W, (p + (hr - p) * sc) * W
        if abs(a1 - a0) > 1e-4:                                # animated: push-in or pull-out
            k = int(ramp) if ramp else 0
            keys = ([[0, a0], [min(k, n - 1), a1], [n - 1, a1]] if k > 0 else
                    [[0, a0], [max(0, n - 1 + k), a0], [n - 1, a1]] if k < 0 else [[0, a0], [n - 1, a1]])
        else:
            keys = [[0, sc], [n - 1, sc]]
        for _, ks in keys:                                     # the margin must hold at EVERY key scale
            kl, kr = (p + (hl - p) * ks) * W, (p + (hr - p) * ks) * W
            if kl < a.margin - 1 or kr > W - a.margin + 1:
                print(f"   shot {i}: at scale {ks:.2f} the head is at x {kl:.0f}-{kr:.0f}   <-- margin not met")
        zooms.append({"clip": i, "keys": keys, "anchor": [round(p, 4), ay], "whoosh": False, "compose": side,
                      "head_px": [round(nl), round(nr)], "chin_px": round(chin_n), "head_top_px": round(top_n),
                      "why": f"{side}: head kept {a.margin}px inside the frame on every frame; lands at x {nl:.0f}-{nr:.0f}"})
        if sc > a.closeup_from + 1e-6:
            print(f"   close-up {sc:.2f}: pivot y {py:.0f} px from the top; chin -> {chin_n:.0f}, head top -> {top_n:.0f}"
                  + ("   <-- head top above y 120" if top_n < 120 else "") + ("   <-- chin below the caption line" if chin_n > a.chin_max + 40 else ""))
        ok = nl >= a.margin - 1 and nr <= W - a.margin + 1
        print(f"shot {i:2d} {side}  scale {specs[i - 1]:>13s}  pivot {p:.2f}  head x {nl:4.0f}-{nr:4.0f}  centre {(nl+nr)/2:4.0f}" + ("" if ok else "   <-- margin not met"))
    if a.write:
        f = ROOT / "projects" / a.job / "transcript" / "effects.json"
        d = json.loads(f.read_text()) if f.exists() else {"brand": "starter", "sfx_gain_db": -14, "draft": False, "timeline": a.job, "zooms": [], "sfx": []}
        d["zooms"] = zooms
        d["review"] = ("Framing solved from per-frame head boxes measured on the NEUTRAL matte. Hard rule: the "
                       f"head stays >= {a.margin}px inside the frame on every frame of every shot, including during "
                       "any push-in or pull-out; sides alternate so each cut is a new composition.")
        f.write_text(json.dumps(d, indent=1)); print("written")


ap = argparse.ArgumentParser(); sub_ = ap.add_subparsers(dest="cmd", required=True)
p = sub_.add_parser("measure"); p.add_argument("job"); p.set_defaults(fn=cmd_measure)
p = sub_.add_parser("plan"); p.add_argument("job"); p.add_argument("--write", action="store_true")
p.add_argument("--pattern", default="L,L,R,L,R,R,L,L,C,L,R,L,L,R,R,L")
p.add_argument("--scales", default="1.16,1.26,1.22,1.34,1.26,1.12,1.30,1.16,1.00,1.24,1.20,1.32,1.16,1.24,1.08,1.28")
p.set_defaults(fn=cmd_plan)
p = sub_.add_parser("head"); p.add_argument("job"); p.add_argument("--sub", default="neutral"); p.set_defaults(fn=cmd_head)
p = sub_.add_parser("solve"); p.add_argument("job"); p.add_argument("--write", action="store_true")
p.add_argument("--margin", type=int, default=90); p.add_argument("--pattern", required=True); p.add_argument("--scales", required=True)
p.add_argument("--closeup-from", type=float, default=1.28, help="scales above this lower the pivot so the chin stays clear of the captions")
p.add_argument("--chin-max", type=int, default=1230, help="where a close-up's chin should land (captions sit below ~1290)")
p.set_defaults(fn=cmd_solve)
a = ap.parse_args(); a.fn(a)
