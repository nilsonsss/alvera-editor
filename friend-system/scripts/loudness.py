#!/usr/bin/env python3
"""Bring a FINISHED export to the social loudness target. The picture is copied, never re-encoded.

  loudness.py <render.mp4> <out.mp4> [--target -14] [--tp -1.0]

1. Measure. If a plain volume lift reaches the target without pushing the true peak past --tp, do only that.
2. Otherwise lift and pass the result through a peak LIMITER, then re-measure and trim the lift until the file
   lands on target. Only the loudest peaks are rounded; nothing else
   about the voice changes. This happens on the finished file ONLY - the voice is still never processed in the
   timeline.
Prints what it did, including how many dB of peak had to be held back, so the report can say it plainly.
"""
import os as _os; _os.environ["PATH"] = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "tools", "bin") + _os.pathsep + _os.environ.get("PATH", "")
import argparse, json, subprocess, sys

FF = "ffmpeg"


def measure(path, af=None):
    chain = (af + "," if af else "") + "loudnorm=print_format=json"
    e = subprocess.run([FF, "-hide_banner", "-i", path, "-af", chain, "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    m = json.loads(e[e.rindex("{"):e.rindex("}") + 1])
    return float(m["input_i"]), float(m["input_tp"])


def encode(src, out, af):
    p = subprocess.run([FF, "-v", "error", "-y", "-i", src, "-c:v", "copy", "-af", af, "-c:a", "aac", "-b:a", "192k",
                        "-ar", "48000", "-movflags", "+faststart", out], capture_output=True, text=True)
    if p.returncode:
        sys.exit(p.stderr[-400:])


def engagement(src, gain_db, limit_db):
    """How hard the limiter works: % of 10 ms windows it acts in, and the median / max reduction there.
    Report THIS, not a worst-case guess - it is what tells you whether the voice is being squeezed."""
    import numpy as np, wave, tempfile, os
    tmp = os.path.join(tempfile.gettempdir(), "_loud.wav")
    subprocess.run([FF, "-v", "error", "-y", "-i", src, "-vn", "-ac", "1", "-ar", "48000", tmp], check=True)
    with wave.open(tmp) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(float) / 32768
    hop = 480; e = np.array([np.abs(x[i:i + hop]).max() for i in range(0, len(x) - hop, hop)]) * 10 ** (gain_db / 20)
    lim = 10 ** (limit_db / 20); over = e > lim
    if not over.any():
        return (0.0, 0.0, 0.0)
    gr = 20 * np.log10(e[over] / lim)
    return (over.mean() * 100, float(np.median(gr)), float(gr.max()))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("src"); ap.add_argument("out")
    ap.add_argument("--target", type=float, default=-14.0); ap.add_argument("--tp", type=float, default=-1.0)
    a = ap.parse_args()
    i0, tp0 = measure(a.src)
    gain = a.target - i0
    if tp0 + gain <= a.tp:
        af = f"volume={gain:.2f}dB"; mode = "plain lift"; held = None
    else:
        limit_db = a.tp - 0.9                               # sample-peak ceiling; leaves room for inter-sample peaks after AAC
        lim = f"alimiter=limit={10 ** (limit_db / 20):.4f}:attack=5:release=60:level=false"
        for _ in range(5):                                  # the limiter gives a little loudness back: trim the lift
            af = f"volume={gain:.2f}dB,{lim}"
            i1, _ = measure(a.src, af)
            if abs(i1 - a.target) <= 0.15:
                break
            gain += (a.target - i1)
        mode = "lift + limiter"; held = engagement(a.src, gain, limit_db)
    encode(a.src, a.out, af)
    i2, tp2 = measure(a.out)
    print(f"loudness: {i0:.1f} -> {i2:.1f} LUFS (target {a.target:.0f}) | true peak {tp0:.1f} -> {tp2:.1f} dBTP | {mode}, "
          f"lift {gain:+.1f} dB" + (f" | limiter active {held[0]:.0f}% of the time, median {held[1]:.1f} dB, max {held[2]:.1f} dB" if held else ""))
    if abs(i2 - a.target) > 0.5 or tp2 > a.tp + 0.6:
        sys.exit(f"MISSED: {i2:.1f} LUFS / {tp2:.1f} dBTP")


main()
