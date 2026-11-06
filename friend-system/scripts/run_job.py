#!/usr/bin/env python3
"""ONE command from the authored plan to a finished, checked, versioned preview. No questions, no waiting for the speaker.

  run_job.py <job> [--auto | --from STAGE | --only STAGE] [--to STAGE] [--clips FILE ...] [--dry-run] [--note "what changed"]

The speaker gives a prompt, the footage lands, and the only creative work left is writing the plan files (Claude does that in one pass from the transcripts):
  transcript/lines.json        which take of which line, in order (+ "order", "override")           REQUIRED (stage `author`)
  transcript/splits.json       where a line is cut into shots                                       optional: autoplanned (phrase boundaries, 1.2-3 s shots)
  transcript/caption_edits.json  accents                                                            optional
  transcript/frame.json        {"scales": "...", "pattern": "..."}                                  optional: autoplanned (two centred sizes, a push every ~9 shots)
  graphics/build_scenes.py     writes graphics/remotion/scenes.json                                 REQUIRED for graphics (none = captions only)
  transcript/broll.json        cutaways                                                             optional
  transcript/sfx_manual.json   [{"name","at","gain_db"}]                                            optional: otherwise sound effects are derived from the scenes

Stages, in order (each one is idempotent; `--auto` re-runs only what an edited input made stale, plus everything after it). NO Resolve: everything is ffmpeg + Remotion.
  intake      --clips: clone the files into raw/ (APFS clone, zero disk), transcribe, split into takes, judge the attempts   (stops at `author`)
  author      lines.json must exist
  align       forced alignment of the verified wording                              align_words.py
  cuts        tight cut list from the audio                                         lines_to_cuts.py --tight, take_pick.py check
  timeline    record frames / source frames from the cut list                       render_edit.py timeline
  matte       neutral picture-only pass + person matte + head boxes                 render_edit.py picture --neutral, matte.py compute (~14 frames/s)
  frame       framing solved from the head boxes, framed picture pass, matte warped + verified   frame_solver.py, render_edit.py picture, matte.py
  captions    two-size captions, one height, ending at every cut                    caption_swap.py
  graphics    scenes rendered in parallel (cached)                                  build_scenes.py, remotion_gfx.py
  sfx         sound effects derived from the scenes                                 plan_sfx
  finish      plan check, ONE ffmpeg render (picture + B-roll + graphics + captions + voice + effects), one-channel fix, loudness, new numbered version, QA, final-audio read-back, design lint, report
Exit codes: 0 done; 3 the plan is missing (`author`); 1 a stage failed twice (the message says which and why). Run with any python 3.
"""
import os as _os; _os.environ["PATH"] = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "tools", "bin") + _os.pathsep + _os.environ.get("PATH", "")
import argparse, difflib, hashlib, json, math, os, re, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SC = ROOT / "scripts"
PYW = str(Path.home() / ".cache" / "video-editor" / "whisperx-venv" / "bin" / "python")    # torch / PIL / whisperx
NOISE = re.compile(r"warn|torchcodec|Reason|libav|compat|table|exception|Another|FFmpeg|PyTorch|use audio|traceback|^\s*$|\*|versions 4", re.I)
STAGES = ["intake", "author", "align", "cuts", "timeline", "matte", "frame", "captions", "graphics", "sfx", "finish"]


class StageError(Exception):
    pass


def log(msg): print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def sh(cmd, py=PYW, tolerate=False, tail=6, timeout=3600):
    """Run a script of this repo; filter the library noise; raise StageError (or return False) when it fails."""
    full = [py] + [str(c) for c in cmd] if py else [str(c) for c in cmd]
    if DRY[0]:
        log("DRY  " + " ".join(os.path.basename(x) if i < 2 else x for i, x in enumerate(full))); return True
    r = subprocess.run(full, capture_output=True, text=True, timeout=timeout)
    out = "\n".join(l for l in (r.stdout + "\n" + r.stderr).splitlines() if not NOISE.search(l))
    if r.returncode != 0:
        if tolerate: return False
        raise StageError(f"{' '.join(os.path.basename(str(x)) for x in full[:3])} failed ({r.returncode}):\n" + "\n".join(out.splitlines()[-12:]))
    for l in out.splitlines()[-tail:]: print("   " + l)
    return out or "ok"


DRY = [False]


def fhash(paths):
    h = hashlib.sha256()
    for p in paths:
        p = Path(p)
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file(): h.update(f.name.encode()); h.update(str(f.stat().st_size).encode())
        elif p.exists(): h.update(p.read_bytes())
        else: h.update(b"-")
    return h.hexdigest()[:16]


# ---------------------------------------------------------------- autoplan: everything a plan file would otherwise need from the speaker
def plan_splits(P):
    A = json.loads((P / "transcript" / "words_aligned.json").read_text())
    S = {}
    for lid, v in A.items():
        ws = v["words"]; cuts = []; seg0 = ws[0]["s"]
        for i, w in enumerate(ws[:-1]):
            seg = w["e"] - seg0; rest = ws[-1]["e"] - w["e"]
            punct = w["w"][-1] in ",.?!;:"
            if (punct and seg >= 1.2 and rest >= 0.9) or seg >= 3.2:
                if not punct and seg >= 3.2:                       # no punctuation: cut at the widest gap around 2 s instead
                    k = max(range(max(0, i - 3), i + 1), key=lambda j: ws[j + 1]["s"] - ws[j]["e"]); w = ws[k]; i = k
                cuts.append(w["w"]); seg0 = ws[i + 1]["s"]
        if cuts: S[lid] = cuts
    if not DRY[0]: (P / "transcript" / "splits.json").write_text(json.dumps(S, indent=1, ensure_ascii=False))
    log(f"autoplan: splits for {len(S)} lines")


def plan_frame(P):
    H = json.loads((P / "graphics" / "matte" / "neutral" / "head.json").read_text())["shots"]
    n = len(H); scales = []
    push_at = set(range(2, n, max(4, n // 3)))                       # a push every ~9 shots, starting at shot 3
    for i, s in enumerate(H):
        if s.get("empty"): scales.append("1.00"); continue
        wd = max(60, s.get("head_right_med", s["head_right_max"]) - s.get("head_left_med", s["head_left_min"]))
        sc = max(1.0, min(1.6, (340 if i % 2 else 290) / wd))
        if i == 0: sc = max(1.0, min(1.6, 290 / wd))
        scales.append(f"{sc * 0.97:.2f}>{min(1.6, sc * 1.12):.2f}" if i in push_at else f"{sc:.2f}")
    plan = {"auto": True, "pattern": ",".join(["C"] * n), "scales": ",".join(scales), "closeup_from": 1.0, "chin_max": 1150}
    if not DRY[0]: (P / "transcript" / "frame.json").write_text(json.dumps(plan, indent=1))
    log(f"autoplan: framing for {n} shots")


def plan_sfx(P):
    """Quiet sound effects from what the scenes contain: a pop where a card / plate / counter lands, a click on a tick / click / snap, a ding on the follow tap."""
    man = P / "transcript" / "sfx_manual.json"
    eff = json.loads((P / "transcript" / "effects.json").read_text())
    if eff.get("sfx_source") == "manual" and not man.exists():
        log("sfx: kept as written in effects.json (sfx_source: manual)"); return
    if man.exists():
        eff["sfx"] = json.loads(man.read_text())
    else:
        sf = P / "graphics" / "remotion" / "scenes.json"; sfx = []
        for sc in (json.loads(sf.read_text())["scenes"] if sf.exists() else []):
            for e in sc["elements"]:
                t = e["type"]; at = int(e["at"])
                if t in ("follow", "followtag"): sfx.append({"name": "ding", "at": int(e.get("tapAt", at + 10)), "why": t})
                elif t == "chain": sfx.append({"name": "click", "at": int(e.get("breakAt", at + 20)), "why": t})
                elif t == "confirm": sfx.append({"name": "click", "at": int(e.get("clickAt", at + 14)), "why": t})
                elif t == "renttoggle": sfx.append({"name": "click", "at": int(e.get("flipAt", at + 14)), "why": t})
                elif t == "chips":
                    for it in e["items"]: sfx.append({"name": "click", "at": int(it["at"]), "why": "tick"})
                elif t == "photocard": sfx.append({"name": "pop", "at": at + 2, "why": t})
                elif t == "pairicons":
                    for it in e["items"]: sfx.append({"name": "pop", "at": int(it["at"]), "gain_db": -18, "why": "icon"})
                elif t in ("counter", "tiles", "daycounter", "appicons", "stamp", "plate", "book", "versus", "bubble", "bgimage", "bgvideo", "hookstack"):
                    if t == "bgvideo" and sc["id"] == "follow": continue
                    sfx.append({"name": "pop", "at": at + 2, "why": t})
        sfx.sort(key=lambda x: x["at"]); keep, last = [], -999
        for x in sfx:
            if x["name"] == "pop" and x["at"] - last < 18: continue          # never a pile of pops
            keep.append({**x, "align": "start"}); last = x["at"] if x["name"] == "pop" else last
        eff["sfx"] = keep
    eff["sfx_source"] = "auto"
    if not DRY[0]: (P / "transcript" / "effects.json").write_text(json.dumps(eff, indent=1))
    log(f"sfx: {len(eff['sfx'])} effects")


# ---------------------------------------------------------------- stages
def stage_intake(c):
    if not c.clips: return
    names = []
    for f in c.clips:
        sh([SC / "intake.sh", f, c.job], py="bash", tail=1); names.append(Path(f).name)
    raw = [c.P / "raw" / n for n in names]
    sh([SC / "transcribe_batch.py", "--language", c.lang] + raw, tail=1)
    kw = json.loads((c.P / "job.json").read_text()).get("keywords", "") if (c.P / "job.json").exists() else ""
    sh([SC / "takes.py", c.job, "--language", c.lang] + (["--prompt", kw] if kw else []), tail=2)
    sh([SC / "take_pick.py", "pick", c.job], tail=0)
    log("intake done: read analysis/takes.json + take_pick output, then write transcript/lines.json")


def stage_author(c):
    if not (c.P / "transcript" / "lines.json").exists():
        print("AUTHORING NEEDED: write projects/%s/transcript/lines.json (and graphics/build_scenes.py), then run again" % c.job); sys.exit(3)


def stage_align(c): sh([SC / "align_words.py", c.job], tail=0)


def stage_cuts(c):
    if not (c.P / "transcript" / "splits.json").exists(): plan_splits(c.P)
    sh([SC / "lines_to_cuts.py", c.job, "--tight"], tail=3); sh([SC / "take_pick.py", "check", c.job], tail=1)


def stage_timeline(c): sh([SC / "render_edit.py", "timeline", c.job], tail=1)


def stage_matte(c):
    sh([SC / "render_edit.py", "picture", c.job, "--neutral"], tail=1)
    sh([SC / "matte.py", "compute", c.job, "--sub", "neutral"], tail=1)
    sh([SC / "frame_solver.py", "head", c.job, "--sub", "neutral"], tail=0)


def stage_frame(c):
    ff = c.P / "transcript" / "frame.json"
    if not ff.exists() or json.loads(ff.read_text()).get("auto"): plan_frame(c.P)
    fp = json.loads(ff.read_text()) if ff.exists() else {"pattern": "C", "scales": "1.0"}
    sh([SC / "frame_solver.py", "solve", c.job, "--write", "--pattern", fp["pattern"], "--scales", fp["scales"], "--closeup-from", str(fp.get("closeup_from", 1.0)),
        "--chin-max", str(fp.get("chin_max", 1150))], tail=2)
    sh([SC / "render_edit.py", "picture", c.job], tail=1)
    sh([SC / "matte.py", "warp", c.job], tail=1)
    n = int(sum(x["end_frame"] - x["start_frame"] for x in json.loads((c.P / "transcript" / "clip_infos.json").read_text()))) if not DRY[0] else 1000
    v = sh([SC / "matte.py", "verify", c.job, "--frames", ",".join(str(int(n * k / 9)) for k in range(1, 9))], tail=10)
    if not DRY[0] and "MISMATCH" in v: raise StageError("the matte does not match the picture: " + v.splitlines()[-1])
    sh([SC / "frame_solver.py", "head", c.job, "--sub", "."], tail=0)


def stage_captions(c):
    sh([SC / "lines_to_captions.py", c.job, "--timeline", c.job], tail=1)
    sh([SC / "caption_swap.py", "plan", c.job], tail=1); sh([SC / "caption_swap.py", "place-y", c.job], tail=1)
    sh([SC / "caption_swap.py", "render", c.job], tail=1)


def stage_graphics(c):
    bs = c.P / "graphics" / "build_scenes.py"
    if not bs.exists():
        log("no graphics/build_scenes.py: captions only"); return
    (c.P / "graphics" / "overlays").mkdir(parents=True, exist_ok=True); (c.P / "graphics" / "remotion").mkdir(parents=True, exist_ok=True)
    sh([bs], tail=2); sh([SC / "remotion_gfx.py", "render", c.job], tail=12)


def stage_sfx(c): plan_sfx(c.P)


def stage_finish(c):
    sh([SC / "finish.py", c.job, "--note", c.note or "run_job"], tail=40)
    out = c.P / "outputs"; vs = sorted(out.glob(f"{c.job}_v*.mp4"), key=lambda p: int(re.search(r"_v(\d+)", p.name).group(1)))
    final = vs[-1] if vs else None
    if final is None or DRY[0]: return
    report = readback(c, final) + design_lint(c)
    jc = c.P / "transcript" / "judgement.json"                       # the judgement calls the speaker must be told about (Claude writes them while authoring the plan)
    calls = json.loads(jc.read_text()) if jc.exists() else []
    (out / f"{c.job}_report.md").write_text("# %s %s\n\n## Automatic checks\n%s\n\n## Judgement calls\n%s\n" % (
        c.job, final.name, "\n".join("- " + r for r in report) if report else "- all clean", "\n".join("- " + r for r in calls) or "- none"))
    print("\nREPORT FLAGS:" if report else "\nREPORT: all automatic checks clean")
    for r in report: print("  - " + r)
    print(f"\nDELIVERABLE: {final}")


def readback(c, final):
    """The finished file's own audio, transcribed and read against the script: catches clipped / swallowed words (CLAUDE.md, before anything is sent)."""
    flags = []
    wav = c.P / "outputs" / "work" / "_readback.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(final), "-vn", "-ac", "1", "-ar", "16000", str(wav)], check=True)
    code = ("import whisperx,sys,json\nm=whisperx.load_model(%r,'cpu',compute_type='int8',language=%r)\na=whisperx.load_audio(%r)\n"
            "r=m.transcribe(a,batch_size=4)\nprint('TXT '+' '.join(s['text'].strip() for s in r['segments']))" % ("medium.en" if c.lang == "en" else "large-v3", c.lang, str(wav)))
    r = subprocess.run([PYW, "-c", code], capture_output=True, text=True)
    heard = next((l[4:] for l in r.stdout.splitlines() if l.startswith("TXT ")), "")
    L = json.loads((c.P / "transcript" / "lines.json").read_text())
    norm = lambda t: re.sub(r"[^\w' ]", "", t.lower().replace("-", " ")).split()
    cc = c.P / "transcript" / "captions_corrected.json"                  # TIMELINE order (a line whose shots were reordered is read as it plays)
    if cc.exists(): want = [w for x in sorted(json.loads(cc.read_text())["captions"][0]["words"], key=lambda x: x["s"]) for w in norm(x["w"])]
    else: want = [w for l in L for w in norm(l["text"])]
    got = norm(heard)
    sm = difflib.SequenceMatcher(None, want, got, autojunk=False)
    ratio = sm.ratio()
    (c.P / "outputs" / "qa").mkdir(exist_ok=True, parents=True)
    (c.P / "outputs" / "qa" / f"{final.stem}_readback.txt").write_text(heard)
    if ratio < 0.93: flags.append(f"final audio read-back matches the script only {ratio:.0%}: read outputs/qa/{final.stem}_readback.txt (a clipped or swallowed word?)")
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("delete", "replace") and i2 - i1 >= 2:
            flags.append(f"script words not heard: '{' '.join(want[i1:i2])}' (heard '{' '.join(got[j1:j2])}')")
    return flags[:6]


def design_lint(c):
    """The design gate as code: common design mistakes."""
    flags = []
    sf = c.P / "graphics" / "remotion" / "scenes.json"; ci = json.loads((c.P / "transcript" / "clip_infos.json").read_text())
    total = sum(x["end_frame"] - x["start_frame"] for x in ci)
    if sf.exists():
        S = json.loads(sf.read_text())["scenes"]
        per = len(S) / max(1, total / 30)
        if per > 1 / 5.5: flags.append(f"{len(S)} graphics in {total / 30:.0f} s: denser than one per 5.5 s")
        if S and min(int(s["at"]) for s in S) > 3 and not any(int(e["at"]) <= 3 for s in S for e in s["elements"]): flags.append("no designed visual by frame 3")
        if not S: flags.append("no graphics at all (captions only): a designed visual from the first frame is a rule")
    cs = c.P / "transcript" / "captions_swap.json"
    if cs.exists():
        cues = json.loads(cs.read_text())["cues"]
        short = [x for x in cues if x["end"] - x["start"] < 3 and x["kind"] == "word"]
        if short: flags.append(f"{len(short)} caption cue(s) shorter than 3 frames (unreadable)")
    return flags


STAGE_INPUTS = {
    "align": lambda P: [P / "transcript" / "lines.json"],
    "cuts": lambda P: [P / "transcript" / "lines.json", P / "transcript" / "splits.json"],
    "timeline": lambda P: [P / "transcript" / "cuts.json"],
    "matte": lambda P: [P / "transcript" / "cuts.json"],
    "frame": lambda P: [P / "transcript" / "cuts.json", P / "transcript" / "frame.json"],
    "captions": lambda P: [P / "transcript" / "lines.json", P / "transcript" / "caption_edits.json", P / "transcript" / "caption_skip.json", P / "transcript" / "cuts.json", P / "transcript" / "frame.json"],
    "graphics": lambda P: [P / "graphics" / "build_scenes.py", P / "transcript" / "cuts.json", P / "transcript" / "frame.json", P / "transcript" / "caption_edits.json"],
    "sfx": lambda P: [P / "graphics" / "remotion" / "scenes.json", P / "transcript" / "sfx_manual.json", P / "transcript" / "cuts.json"],
}
FUNCS = {k[6:]: v for k, v in globals().items() if k.startswith("stage_")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job"); ap.add_argument("--auto", action="store_true"); ap.add_argument("--from", dest="frm"); ap.add_argument("--only"); ap.add_argument("--to")
    ap.add_argument("--clips", nargs="*"); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--note"); ap.add_argument("--project", default="unused")
    a = ap.parse_args(); DRY[0] = a.dry_run
    a.P = ROOT / "projects" / a.job; a.lang = "en"
    if (a.P / "job.json").exists(): a.lang = json.loads((a.P / "job.json").read_text()).get("language", "en")
    a.P.mkdir(parents=True, exist_ok=True)
    state_f = a.P / "transcript" / ".run_state.json"; (a.P / "transcript").mkdir(exist_ok=True)
    state = json.loads(state_f.read_text()) if state_f.exists() else {}
    names = STAGES
    if a.only: run_list = [a.only]
    else:
        i0 = names.index(a.frm) if a.frm else 0; i1 = names.index(a.to) + 1 if a.to else len(names); run_list = names[i0:i1]
        if a.auto and not a.frm:
            dirty = False; sel = []
            for s in names[:i1]:
                if s in ("intake", "author", "finish"): sel.append(s) if s == "author" else None; continue
                h = fhash(STAGE_INPUTS[s](a.P)); dirty = dirty or state.get(s) != h
                if dirty: sel.append(s)
            if sel and sel != ["author"]: sel.append("finish")
            run_list = sel
    run_list = [s for s in run_list if s != "intake" or a.clips]
    log(f"{a.job}: stages {run_list}")
    for s in run_list:
        for attempt in (1, 2):
            try:
                log(f"== {s}" + (" (retry)" if attempt == 2 else "")); t0 = time.time()
                FUNCS[s](a)
                if s in STAGE_INPUTS and not DRY[0]: state[s] = fhash(STAGE_INPUTS[s](a.P)); state_f.write_text(json.dumps(state, indent=1))
                log(f"== {s} ok in {time.time() - t0:.0f} s"); break
            except StageError as e:
                if attempt == 2:
                    print(f"\nSTAGE FAILED TWICE: {s}\n{e}\nFix the cause (read the message above), then: run_job.py {a.job} --from {s}"); sys.exit(1)
                log(f"{s} failed, one repair + retry:\n{e}")


main()
