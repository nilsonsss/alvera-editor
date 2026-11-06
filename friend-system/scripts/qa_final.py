#!/usr/bin/env python3
"""The listen-and-look QA that an export must pass before the speaker sees it (added after the speaker found, by playing the file, a
one-sided start, a blue line painted before its highlight, a CTA that started late and a video that outlived its last word).

  qa_final.py <job> [--file outputs/<job>.mp4]

PACING / AUDIO (printed, with flags)
  - left / right level and loudness per 5 s block        -> flags a dead or one-sided channel, a block >2 LU off the median
  - first-sound offset, last-sound offset and the tail   -> flags a start later than 0.15 s and a tail longer than 0.25 s
  - every silence inside the file                        -> flags any pause longer than 0.45 s
CUTS (from the final render only; a snapshot or preview proves nothing about a cut)
  - outputs/qa/<name>_cuts.png: the frame before and the first frame after every cut, as pairs. The "after" frame must be the new
    shot with the right framing and no leftover (a caption, a graphic or a person from the previous shot).
  - a one-frame blip detector over the whole file (a frame that differs from both neighbours while they match each other)
LOOK
  - writes outputs/qa/<name>_qa.png: frames 2 before and 3 after the start of every graphic, the first frames and the last frames.
    Open it and look: a line already drawn before its highlight, a label popping in late, a graphic over the face.

Exit code 1 when anything is flagged, so `finish.py` can say so. Flags are information: the speaker decides.
Usage (whisperx venv: needs PIL)."""
import os as _os; _os.environ["PATH"] = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "tools", "bin") + _os.pathsep + _os.environ.get("PATH", "")
import argparse, json, re, subprocess, sys
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent.parent
FF = "ffmpeg"


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def duration(f):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)]).stdout.strip())


def block(f, a, b):
    out = {}
    for ch in (0, 1):
        t = run([FF, "-hide_banner", "-nostats", "-ss", f"{a}", "-to", f"{b}", "-i", str(f), "-af", f"pan=mono|c0=c{ch},volumedetect", "-f", "null", "-"]).stderr
        m = re.search(r"mean_volume: (-?[\d.]+) dB", t)
        out["LR"[ch]] = float(m.group(1)) if m else -91.0
    t = run([FF, "-hide_banner", "-nostats", "-ss", f"{a}", "-to", f"{b}", "-i", str(f), "-af", "ebur128", "-f", "null", "-"]).stderr
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", t)
    out["lufs"] = float(m[-1]) if m else None
    return out


def pacing(f, flags):
    dur = duration(f)
    print(f"\nPACING / AUDIO  ({f.name}, {dur:.2f} s)")
    print("  block        L dB    R dB   LUFS")
    lufs = []
    a = 0.0
    rows = []
    while a < dur - 0.4:
        b = min(a + 5.0, dur)
        r = block(f, a, b); rows.append((a, b, r)); a = b
        if r["lufs"] is not None and r["lufs"] > -70 and b - a >= 0:
            lufs.append(r["lufs"])
    med = statistics.median(lufs) if lufs else 0
    for a, b, r in rows:
        note = ""
        if abs(r["L"] - r["R"]) > 3.0:
            note = "  <-- one-sided"; flags.append(f"{a:.0f}-{b:.0f} s: L/R differ by {abs(r['L'] - r['R']):.1f} dB")
        if r["lufs"] is not None and abs(r["lufs"] - med) > 2.0 and (b - a) > 2.0:
            note += f"  <-- {r['lufs'] - med:+.1f} LU vs median"; flags.append(f"{a:.0f}-{b:.0f} s: {r['lufs'] - med:+.1f} LU off the median")
        print(f"  {a:5.1f}-{b:5.1f}  {r['L']:6.1f}  {r['R']:6.1f}  {r['lufs']}{note}")
    # level per 50 ms window (RMS, mono down-mix). Peak-based silencedetect never sees silence in a room whose noise peaks near -35 dB.
    t = run([FF, "-v", "error", "-i", str(f), "-af", "pan=mono|c0=0.5*c0+0.5*c1,asetnsamples=2400,astats=metadata=1:reset=1,"
             "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-", "-f", "null", "-"]).stdout
    lv = [float(x) if x not in ("-inf", "inf") else -120.0 for x in re.findall(r"RMS_level=(-?[\d.]+|-inf|inf)", t)]
    W = 0.05
    loud = [i for i, v in enumerate(lv) if v > -32.0]
    first = loud[0] * W if loud else 0.0
    last_end = (loud[-1] + 1) * W if loud else dur
    tail = dur - last_end
    print(f"\n  first sound at {first:.2f} s | last sound at {last_end:.2f} s | tail after it {tail:.2f} s   (windows of 50 ms above -32 dB)")
    if first > 0.15: flags.append(f"starts {first:.2f} s late")
    if tail > 0.25: flags.append(f"ends {tail:.2f} s after the last sound")
    run_start = None
    for i in range(loud[0] if loud else 0, (loud[-1] if loud else 0) + 1):
        quiet = lv[i] <= -32.0
        if quiet and run_start is None: run_start = i
        if (not quiet or i == (loud[-1] if loud else 0)) and run_start is not None:
            n = i - run_start
            if n * W > 0.45:
                print(f"  pause {run_start * W:6.2f}-{i * W:6.2f} s ({n * W:.2f} s)")
                flags.append(f"pause of {n * W:.2f} s at {run_start * W:.1f} s")
            run_start = None


def probe_sheet(job, f, flags):
    from PIL import Image, ImageDraw
    P = ROOT / "projects" / job
    mf = P / "graphics" / "overlays" / "overlays_gfx.json"
    ov = json.loads(mf.read_text())["overlays"] if mf.exists() else []
    n = int(run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(f)]).stdout.split()[0].strip(","))
    pts = [(0, "first"), (3, "f3")]
    for o in ov:
        s = o["start_frame"]
        pts += [(max(0, s - 2), f"{o['id']} -2"), (min(n - 1, s + 3), f"{o['id']} +3")]
    pts += [(n - 7, "end -6"), (n - 1, "last")]
    seen, uniq = set(), []
    for fr, lab in pts:
        if fr not in seen: seen.add(fr); uniq.append((fr, lab))
    TW, TH, cols = 216, 384, 8
    rows = (len(uniq) + cols - 1) // cols
    sheet = Image.new("RGB", (TW * cols, TH * rows), (0, 0, 0))
    out_dir = P / "outputs" / "qa"; out_dir.mkdir(parents=True, exist_ok=True)
    for i, (fr, lab) in enumerate(uniq):
        raw = subprocess.run([FF, "-v", "error", "-i", str(f), "-vf", f"select=eq(n\\,{fr}),scale={TW}:{TH}", "-vframes", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout
        if len(raw) == TW * TH * 3:
            im = Image.frombytes("RGB", (TW, TH), raw)
            ImageDraw.Draw(im).rectangle([0, 0, TW, 14], fill=(0, 0, 0)); ImageDraw.Draw(im).text((3, 1), f"f{fr} {lab}", fill=(255, 255, 0))
            sheet.paste(im, ((i % cols) * TW, (i // cols) * TH))
    out = out_dir / f"{f.stem}_qa.png"; sheet.save(out)
    print(f"\nLOOK  {len(uniq)} frames around graphics + first/last -> {out}")
    print("      open it: anything already drawn before its moment, anything popping in late, anything over the face?")


def cut_checks(job, f, flags):
    import numpy as np
    from PIL import Image, ImageDraw
    P = ROOT / "projects" / job
    infos = json.loads((P / "transcript" / "clip_infos.json").read_text()) if (P / "transcript" / "clip_infos.json").exists() else []
    cuts = [c["record_frame"] for c in infos[1:]]
    # whole file, grey, small: 135x240
    w, h = 135, 240
    raw = subprocess.run([FF, "-v", "error", "-i", str(f), "-vf", f"scale={w}:{h}:flags=area,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    n = len(raw) // (w * h)
    V = np.frombuffer(raw[:n * w * h], np.uint8).reshape(n, h, w).astype(np.int16)
    d = np.abs(np.diff(V, axis=0)).mean(axis=(1, 2))          # d[i] = change from frame i to i+1
    base = float(np.median(d)) + 1.0
    blips = [i + 1 for i in range(1, len(d) - 1) if d[i - 1] > 6 * base and d[i] > 6 * base and abs(V[i + 1] - V[i - 1]).mean() < 2 * base]
    # a cut is allowed to be big; a blip is big on BOTH sides of a frame whose neighbours agree
    for b in blips:
        flags.append(f"one-frame blip at frame {b} ({b / 30:.2f} s)")
    # soft / motion-blurred frames (the speaker swings the phone while a take starts or stops: the CTA take of began and ended in a smear). Measured on the PICTURE-ONLY pass
    # (captions and graphics add edges of their own): Laplacian variance of the centre of each frame against the median of the file; the first 10 frames, the last 10 and the
    # first 8 after every cut are inspected, 4 soft frames in a row-ish is a flag.
    pic = P / "graphics" / "matte" / "picture.mp4"
    if pic.exists():
        pw, ph = 270, 480
        rawp = subprocess.run([FF, "-v", "error", "-i", str(pic), "-vf", f"scale={pw}:{ph}:flags=area,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
        npf = len(rawp) // (pw * ph)
        if npf > 20:
            VP = np.frombuffer(rawp[:npf * pw * ph], np.uint8).reshape(npf, ph, pw).astype(np.float32)[:, 100:380, 40:230]
            lap = lambda a: float((a[1:-1, 1:-1] * 4 - a[:-2, 1:-1] - a[2:, 1:-1] - a[1:-1, :-2] - a[1:-1, 2:]).var())
            lv = np.array([lap(x) for x in VP]); med = float(np.median(lv))
            soft = lambda lo, hi: [i for i in range(max(0, lo), min(npf, hi)) if lv[i] < 0.45 * med]
            for lo, hi, what in [(0, 10, "the first frames"), (npf - 10, npf, "the last frames")] + [(c, c + 8, f"the shot starting at frame {c}") for c in cuts]:
                bad = soft(lo, hi)
                if len(bad) >= 6: flags.append(f"{len(bad)} soft / motion-blurred frames in {what} (frames {bad[0]}-{bad[-1]}): a take problem, re-film or cut it")
    if not cuts:
        return
    TW, TH = 144, 256
    cols = 8
    pairs = len(cuts)
    rows = (pairs * 2 + cols - 1) // cols
    sheet = Image.new("RGB", (TW * cols, TH * rows), (0, 0, 0))
    k = 0
    for c in cuts:
        for fr, lab in ((c - 1, "before"), (c, "after")):
            raw = subprocess.run([FF, "-v", "error", "-i", str(f), "-vf", f"select=eq(n\\,{fr}),scale={TW}:{TH}", "-vframes", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
            if len(raw) == TW * TH * 3:
                im = Image.frombytes("RGB", (TW, TH), raw)
                ImageDraw.Draw(im).rectangle([0, 0, TW, 13], fill=(0, 0, 0)); ImageDraw.Draw(im).text((3, 1), f"f{fr} {lab}", fill=(255, 255, 0) if lab == "after" else (180, 180, 180))
                sheet.paste(im, ((k % cols) * TW, (k // cols) * TH))
            k += 1
    out_dir = P / "outputs" / "qa"; out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{f.stem}_cuts.png"; sheet.save(out)
    print(f"\nCUTS  {pairs} cuts as before|after pairs -> {out}   ({len(blips)} one-frame blip(s) found)")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("job"); ap.add_argument("--file"); ap.add_argument("--no-look", action="store_true", help="audio/pacing only, no frame sheet")
    a = ap.parse_args()
    P = ROOT / "projects" / a.job
    f = Path(a.file) if a.file else P / "outputs" / f"{a.job}.mp4"
    if not f.is_absolute(): f = ROOT / f
    if not f.exists(): sys.exit(f"no such file: {f}")
    flags = []
    pacing(f, flags)
    try:
        if not a.no_look:
            cut_checks(a.job, f, flags)
            probe_sheet(a.job, f, flags)
    except ImportError:
        print("\nLOOK  skipped (PIL not available in this python: use the whisperx venv)")
    print("\nFLAGS" if flags else "\nno flags")
    for x in flags: print("  -", x)
    sys.exit(1 if flags else 0)


main()
