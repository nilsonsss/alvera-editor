#!/usr/bin/env python3
"""Export -> one-channel fix -> loudness -> a NEW numbered version -> QA. One command for what used to be four, and it never
overwrites a delivered file.

  finish.py <job> [--timeline NAME] [--note "what changed"] [--no-export]

Writes   projects/<job>/outputs/<job>_v<N>.mp4     the deliverable (N = next free number)
         projects/<job>/outputs/<job>.mp4          the latest (a hard link to the same file)
         projects/<job>/outputs/work/<job>_v<N>_raw.mp4, _chfix.mp4   intermediates, kept
Before exporting, the current <job>.mp4 is registered as a version of its own if it is not one yet, because Resolve's export
replaces <job>.mp4. Nothing is ever deleted.
--no-export reuses the newest outputs/<job>.mp4 render in outputs/work/ (post-processing only).
Run with the whisperx venv python (numpy/PIL). The export is `render_edit.py` (ffmpeg, no Resolve)."""
import os as _os; _os.environ["PATH"] = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "tools", "bin") + _os.pathsep + _os.environ.get("PATH", "")
import argparse, json, os, re, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def versions(out, job):
    vs = {}
    for p in out.glob(f"{job}_v*.mp4"):
        m = re.fullmatch(rf"{re.escape(job)}_v(\d+)\.mp4", p.name)
        if m: vs[int(m.group(1))] = p
    return vs


def same_file(a, b):
    try: return os.path.samefile(a, b)
    except OSError: return False


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("job"); ap.add_argument("--timeline"); ap.add_argument("--note", default="")
    ap.add_argument("--no-export", action="store_true")
    a = ap.parse_args()
    P = ROOT / "projects" / a.job
    out = P / "outputs"; work = out / "work"; work.mkdir(parents=True, exist_ok=True)
    vs = versions(out, a.job)
    latest = out / f"{a.job}.mp4"
    if latest.exists() and not any(same_file(latest, v) for v in vs.values()):
        n0 = max(vs, default=0) + 1
        v = out / f"{a.job}_v{n0}.mp4"
        os.link(latest, v)                                 # hard link: same bytes, no copy, survives the export replacing the name
        print(f"registered the existing {latest.name} as {v.name}")
        vs[n0] = v
    n = max(vs, default=0) + 1
    raw = work / f"{a.job}_v{n}_raw.mp4"
    if not a.no_export:
        # the Resolve-free render (render_edit.py): plan check, then picture + B-roll + graphics + captions + voice + sound effects in one ffmpeg pass
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "render_edit.py"), "check", a.job], capture_output=True, text=True)
        print(r.stdout[-900:])
        if r.returncode != 0: sys.exit("final check failed: " + r.stdout[-600:] + r.stderr[-600:])
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "render_edit.py"), "final", a.job, "--out", str(raw)], capture_output=True, text=True)
        print(r.stdout[-300:])
        if r.returncode != 0 or not raw.exists(): sys.exit("render failed: " + r.stdout[-600:] + r.stderr[-900:])
    else:
        cands = sorted(work.glob(f"{a.job}_v*_raw.mp4"), key=lambda p: p.stat().st_mtime)
        if not cands: sys.exit("--no-export: nothing in outputs/work")
        raw = cands[-1]; print("reusing", raw.name)
    # one-channel voice, on the finished file
    cf = work / f"{a.job}_v{n}_chfix.mp4"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "channel_fix.py"), "fix", a.job, str(raw), str(cf)], capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip())
    if r.returncode != 0: sys.exit("channel_fix failed")
    final = out / f"{a.job}_v{n}.mp4"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "loudness.py"), str(cf), str(final)], capture_output=True, text=True)
    print([l for l in r.stdout.splitlines() if l.strip()][-1] if r.stdout.strip() else r.stderr[-400:])
    if r.returncode != 0 or not final.exists(): sys.exit("loudness failed")
    if latest.exists() or latest.is_symlink(): latest.unlink()
    os.link(final, latest)
    (out / "versions.json").write_text(json.dumps({**(json.loads((out / "versions.json").read_text()) if (out / "versions.json").exists() else {}),
                                                   str(n): {"file": final.name, "note": a.note}}, indent=1))
    print(f"\nDELIVERABLE  {final.relative_to(ROOT)}   (latest: {latest.name})")
    q = subprocess.run([sys.executable, str(ROOT / "scripts" / "qa_final.py"), a.job, "--file", str(final)], capture_output=True, text=True)
    print(q.stdout)
    sys.exit(0)


main()
