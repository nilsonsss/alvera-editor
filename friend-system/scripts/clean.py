#!/usr/bin/env python3
"""Disk hygiene for projects/: delete what the pipeline can REGENERATE, never what it cannot.

  clean.py [--apply] [--keep-recent 4] [--job NAME]
  (dry run by default: prints what it would delete and how much space it frees)

Deleted, for EVERY job (all of it is rebuilt by `run_job.py <job> --from conform`):
  raw_conform/                          ProRes spans of the raw clips (conform_sources.py)
  outputs/work/                         ProRes masters of every export (deliver.py)
  graphics/matte/**/work/               ProRes picture-only passes (matte.py picture)
  graphics/matte/**/alpha_before_trim*, alpha_v*, picture_prev*   superseded mattes
  graphics/remotion/preview/            composite stills
Deleted additionally for jobs OLDER than the newest --keep-recent (by their newest export): the whole matte folder and the rendered overlay / caption /
hook / behind clips (graphics/{matte,remotion,captions,overlays,behind,hook}); a Resolve timeline that still points at them shows offline media.
NEVER touched: raw/ (copies of the speaker's clips), outputs/*.mp4 (every delivered version), transcript/, analysis/, graphics/shots/, job.json, any *.py / *.json plan, the brand files.
"""
import os as _os; _os.environ["PATH"] = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "tools", "bin") + _os.pathsep + _os.environ.get("PATH", "")
import argparse, shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
P = ROOT / "projects"


def size(p):
    if p.is_file(): return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--keep-recent", type=int, default=4); ap.add_argument("--job")
    a = ap.parse_args()
    jobs = [d for d in P.iterdir() if d.is_dir() and not d.name.startswith("_") and (d / "job.json").exists() or (d.is_dir() and d.name == "effects-gallery")]
    def newest(d):
        mp4 = list((d / "outputs").glob("*.mp4")) if (d / "outputs").exists() else []
        return max((f.stat().st_mtime for f in mp4), default=0)
    ordered = sorted([j for j in jobs if j.name != "effects-gallery"], key=newest, reverse=True)
    recent = {j.name for j in ordered[:a.keep_recent]}
    targets = []
    for j in jobs:
        if a.job and j.name != a.job: continue
        if j.name == "effects-gallery":
            targets.append(j / "work"); continue
        targets += [j / "raw_conform", j / "outputs" / "work", j / "graphics" / "remotion" / "preview"]
        m = j / "graphics" / "matte"
        if m.exists():
            targets += list(m.rglob("work")) + list(m.rglob("alpha_before_trim*")) + list(m.rglob("alpha_v*")) + list(m.rglob("picture_prev*"))
            if j.name not in recent: targets.append(m)
        if j.name not in recent:
            g = j / "graphics"
            for sub in ("remotion", "captions", "overlays", "behind", "hook"):
                if (g / sub).exists(): targets.append(g / sub)
    seen, total = set(), 0
    for t in targets:
        if not t.exists() or any(str(t).startswith(str(s) + "/") for s in seen) or t in seen: continue
        seen.add(t); s = size(t); total += s
        print(f"  {s / 1e6:9.0f} MB  {t.relative_to(ROOT)}")
        if a.apply:
            shutil.rmtree(t) if t.is_dir() else t.unlink()
    print(f"\n{'deleted' if a.apply else 'would delete'}: {total / 1e9:.1f} GB   (kept recent jobs: {sorted(recent)})")


main()
