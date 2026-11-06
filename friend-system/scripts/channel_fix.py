#!/usr/bin/env python3
"""One-channel voice: find it, fix it on the FINISHED file.

Some of the speaker's clips are recorded with the voice in the LEFT channel only (the right is silent, about -91 dB) and ~5 dB quieter than
the speaker's stereo clips. On a laptop or phone speaker that plays as one-sided and quiet.

  channel_fix.py check <job>                       level of each picked take, left / right, and which are one-channel
  channel_fix.py fix   <job> <in.mp4> <out.mp4> [--gain dB]
        for every stretch of the timeline whose source take is one-channel: the live channel is copied to both channels, and
        a gain brings EACH of those takes to the mean loudness of the speaker's stereo takes (per take, clamped to +-9 dB, because the
        one-channel takes were also recorded at different levels: 2.5 dB apart on. --gain forces one value instead.
        Everything else is untouched. The picture is stream-copied. Run it BEFORE loudness.py.

It works on the finished file, never on the timeline: the voice track in Resolve stays exactly as recorded.
Usage (any python, needs ffmpeg)."""
import os as _os; _os.environ["PATH"] = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "tools", "bin") + _os.pathsep + _os.environ.get("PATH", "")
import argparse, json, re, subprocess, sys
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent.parent
FF = "ffmpeg"
FPS = 30.0


def mean_db(path, ss, to, ch):
    t = subprocess.run([FF, "-hide_banner", "-nostats", "-ss", str(ss), "-to", str(to), "-i", str(path), "-af",
                        f"pan=mono|c0=c{ch},volumedetect", "-f", "null", "-"], capture_output=True, text=True).stderr
    m = re.search(r"mean_volume: (-?[\d.]+) dB", t)
    return float(m.group(1)) if m else -91.0


def lufs(path, ss, to):
    t = subprocess.run([FF, "-hide_banner", "-nostats", "-ss", str(ss), "-to", str(to), "-i", str(path), "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", t)
    return float(m[-1]) if m else None


def survey(job):
    P = ROOT / "projects" / job
    rows = []
    for l in json.loads((P / "transcript" / "lines.json").read_text()):
        src = P / "raw" / l["clip"]
        L, R = mean_db(src, l["start"], l["end"], 0), mean_db(src, l["start"], l["end"], 1)
        dead = "R" if L - R > 20 else "L" if R - L > 20 else None   # the channel that is DEAD
        rows.append({"id": l["id"], "clip": l["clip"], "start": l["start"], "end": l["end"], "L": L, "R": R, "dead": dead,
                     "lufs": lufs(src, l["start"], l["end"])})
    return rows


def cmd_check(a):
    rows = survey(a.job)
    for r in rows:
        flag = f"  <-- {r['dead']} channel is silent: voice in {'L' if r['dead'] == 'R' else 'R'} only" if r["dead"] else ""
        print(f"{r['id']:6s} {r['clip']}  L {r['L']:6.1f}  R {r['R']:6.1f} dB   {r['lufs']} LUFS{flag}")
    bad = [r for r in rows if r["dead"]]
    print(f"\n{len(bad)} one-channel take(s) of {len(rows)}")
    return rows


def cmd_fix(a):
    P = ROOT / "projects" / a.job
    rows = survey(a.job)
    dead_clip = {r["clip"]: r["dead"] for r in rows if r["dead"]}
    if not dead_clip:
        print("no one-channel clips: copying unchanged")
        subprocess.run([FF, "-v", "error", "-y", "-i", a.src, "-c", "copy", a.dst], check=True); return
    one = [r["lufs"] for r in rows if r["dead"] and r["lufs"] is not None]
    two = [r["lufs"] for r in rows if not r["dead"] and r["lufs"] is not None]
    mean_two = statistics.mean(two) if two else None
    if mean_two is None and one:          # a batch with NO stereo take (all ten iPhone clips of: level the takes to each other
        mean_two = statistics.median(x + 3.01 for x in one)
    per = {}
    for r in rows:
        if r["dead"] and r["lufs"] is not None and mean_two is not None:
            per.setdefault(r["clip"], []).append(max(-9.0, min(9.0, mean_two - (r["lufs"] + 3.01))))
    gain_of = {c: (a.gain if a.gain is not None else statistics.mean(g)) for c, g in per.items()}
    infos = json.loads((P / "transcript" / "clip_infos.json").read_text())
    total = sum(c["end_frame"] - c["start_frame"] for c in infos)
    pieces = []   # (t0, t1, dead channel or None, gain)
    for c in infos:
        d = dead_clip.get(c["source"]); g = round(gain_of.get(c["source"], 0.0), 2) if d else 0.0
        t0 = c["record_frame"] / FPS; t1 = (c["record_frame"] + c["end_frame"] - c["start_frame"]) / FPS
        if pieces and pieces[-1][2] == d and pieces[-1][3] == g and abs(pieces[-1][1] - t0) < 1e-6:
            pieces[-1] = (pieces[-1][0], t1, d, g)
        else:
            pieces.append((t0, t1, d, g))
    # the render may be longer than V1 (graphics past the last shot): keep the remainder untouched
    pieces.append((total / FPS, 1e6, None, 0.0))
    fc, outs = [], []
    for i, (t0, t1, d, g) in enumerate(pieces):
        end = f":end={t1:.5f}" if t1 < 1e5 else ""
        f = f"[0:a]atrim=start={t0:.5f}{end},asetpts=PTS-STARTPTS"
        if d:
            live = 0 if d == "R" else 1
            f += f",pan=stereo|c0=c{live}|c1=c{live},volume={g:.2f}dB"
        fc.append(f + f"[a{i}]"); outs.append(f"[a{i}]")
    fc.append("".join(outs) + f"concat=n={len(outs)}:v=0:a=1[a]")
    cmd = [FF, "-v", "error", "-y", "-i", a.src, "-filter_complex", ";".join(fc), "-map", "0:v", "-map", "[a]", "-c:v", "copy",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", a.dst]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("ffmpeg failed: " + r.stderr[-1500:])
    fixed = [(round(t0, 2), round(min(t1, total / FPS), 2), d, g) for t0, t1, d, g in pieces if d]
    print(f"fixed {len(fixed)} stretch(es) (start, end, dead channel, gain dB): {fixed}\n  live channel -> both; each take matched to the stereo "
          f"takes' mean {mean_two:.1f} LUFS (one-channel takes were {statistics.mean(one):.1f} LUFS, +3.0 as dual mono)")


ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
p = sub.add_parser("check"); p.add_argument("job"); p.set_defaults(fn=cmd_check)
p = sub.add_parser("fix"); p.add_argument("job"); p.add_argument("src"); p.add_argument("dst"); p.add_argument("--gain", type=float); p.set_defaults(fn=cmd_fix)
a = ap.parse_args(); a.fn(a)
