#!/usr/bin/env python3
"""The Resolve-free render: cuts, framing, B-roll, graphics, captions, voice and sound effects -> one H.264 file, in ffmpeg. No GUI, no scripting port, no ProRes conform, no ProRes master.

  render_edit.py timeline <job>                       transcript/cuts.json -> transcript/clip_infos.json (record frames, source frames)
  render_edit.py picture  <job> [--neutral] [--out F]  the picture-only pass of V1: framed (effects.json zooms) -> graphics/matte/picture.mp4, --neutral (no zoom) -> graphics/matte/neutral/picture.mp4
  render_edit.py final    <job> [--out F]              picture + B-roll + graphics + captions + voice + sound effects -> outputs/work/<job>_render.mp4  (then finish.py: channel fix, loudness, version, QA)

What replaces what:  build_timeline.py -> `timeline` (plain arithmetic on cuts.json);  matte.py picture / apply_effects zooms -> `picture`;
captions.py place-gfx, overlays_resolve.py, broll_insert.py, apply_effects sfx, deliver.py export -> `final`.
Geometry (identical to matte.py warp, which warps the matte the same way): a shot of scale s about pivot p (x from the left, y from the BOTTOM, as in effects.json "anchor")
maps x -> p + (x - p) * s, so the picture is the source scaled by s and cropped at p * (s - 1). Keys are linear in the shot's own frame numbers.
Every shot plays in REAL time from its source time (start_frame / 29.97), so 24 / 25 / 29.97 / variable-frame-rate clips all land right and the voice stays in sync; each shot is exactly
end_frame - start_frame timeline frames at 30 fps. Source colour range is normalised to limited, rotation is applied by ffmpeg.
Run with any python 3 (stdlib only).
"""
import os as _os; _os.environ["PATH"] = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "tools", "bin") + _os.pathsep + _os.environ.get("PATH", "")
import argparse, json, math, os, subprocess, sys, wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FF = "ffmpeg"
FPS_SRC = 30000 / 1001
W, H = 1080, 1920


def sh(cmd, quiet=True):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("ffmpeg failed:\n" + (r.stderr or r.stdout)[-2500:])
    return r


def load(job):
    P = ROOT / "projects" / job
    return P, json.loads((P / "transcript" / "clip_infos.json").read_text()) if (P / "transcript" / "clip_infos.json").exists() else None


def cmd_timeline(a):
    P = ROOT / "projects" / a.job
    cuts = json.loads((P / "transcript" / "cuts.json").read_text())["cuts"]
    infos, rec = [], 0
    for c in cuts:
        sf = int(math.floor(c["start"] * FPS_SRC + 1e-6)); ef = int(math.ceil(c["end"] * FPS_SRC - 1e-6))
        infos.append({"source": c["source"], "file": None, "src_offset": 0.0, "start_frame": sf, "end_frame": ef, "record_frame": rec, "clip_fps": FPS_SRC, "text": c.get("note", "")})
        rec += ef - sf
    (P / "transcript" / "clip_infos.json").write_text(json.dumps(infos, indent=1, ensure_ascii=False))
    print(f"timeline: {len(infos)} shots, {rec} frames ({rec / 30:.2f} s)")


def zexpr(keys):
    """scale(n) for keys [[frame, scale], ...] as an ffmpeg expression of the shot's frame number n (linear between keys, held after the last)."""
    keys = [(float(f), float(s)) for f, s in keys]
    e = f"{keys[-1][1]:.5f}"
    for (f0, s0), (f1, s1) in reversed(list(zip(keys, keys[1:]))):
        e = f"if(lt(n,{f1:g}),{s0:.5f}+({s1 - s0:.5f})*(n-{f0:g})/{max(1.0, f1 - f0):g},{e})"
    return f"if(lt(n,{keys[0][0]:g}),{keys[0][1]:.5f},{e})"


def shot_chain(i, n, z):
    """The filter chain of shot i: real-time fps, exactly n frames, range normalised, zoom + crop."""
    head = f"[{i}:v]fps=30,trim=end_frame={n},setpts=PTS-STARTPTS,"
    if z is None or all(abs(s - 1.0) < 1e-4 for _, s in z["keys"]):
        return head + f"scale={W}:{H}:in_range=auto:out_range=tv:flags=bicubic,setsar=1,format=yuv420p[v{i}]"
    ax, ay = z.get("anchor", z.get("center", (0.5, 0.5))); pyt = 1 - ay
    keys = z["keys"]
    if all(abs(s - keys[0][1]) < 1e-4 for _, s in keys):                       # a flat scale
        s = keys[0][1]; sw, sh_ = 2 * round(W * s / 2), 2 * round(H * s / 2)
        sc = f"scale={sw}:{sh_}:in_range=auto:out_range=tv:flags=bicubic"
    else:
        # a PUSH / PULL: zoompan on the full-resolution input (an integer crop in SOURCE pixels, i.e. < 0.25 output px of jitter, then one scale to 1080x1920).
        # `scale eval=frame` + crop was tried first and drifted from the linear curve the matte is warped by (matte IoU 0.65 on push shots).
        zz = zexpr(keys).replace("(n-", "(on-").replace("lt(n,", "lt(on,")
        return (head + "scale=iw:ih:in_range=auto:out_range=tv:flags=bicubic," + f"zoompan=z='{zz}':x='iw*{ax:.5f}*(1-1/zoom)':y='ih*{pyt:.5f}*(1-1/zoom)':d=1:s={W}x{H}:fps=30,setsar=1,format=yuv420p[v{i}]")
    return head + sc + f",crop={W}:{H}:x='(iw-{W})*{ax:.5f}':y='(ih-{H})*{pyt:.5f}',setsar=1,format=yuv420p[v{i}]"


def picture_inputs(P, infos, zooms):
    inputs, chains = [], []
    zmap = {z["clip"]: z for z in zooms}
    for i, c in enumerate(infos):
        n = c["end_frame"] - c["start_frame"]; t0 = c["start_frame"] / c.get("clip_fps", FPS_SRC)
        src = P / "raw" / c["source"]
        inputs += ["-ss", f"{t0:.5f}", "-t", f"{(n + 6) / 30:.4f}", "-i", str(src)]
        chains.append(shot_chain(i, n, zmap.get(i + 1)))
    return inputs, chains


def cmd_picture(a):
    P, infos = load(a.job)
    if infos is None: raise SystemExit("run `render_edit.py timeline <job>` first")
    zooms = [] if a.neutral else json.loads((P / "transcript" / "effects.json").read_text()).get("zooms", [])
    out = Path(a.out) if a.out else P / "graphics" / "matte" / ("neutral" if a.neutral else "") / "picture.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    inputs, chains = picture_inputs(P, infos, zooms)
    graph = ";".join(chains) + ";" + "".join(f"[v{i}]" for i in range(len(infos))) + f"concat=n={len(infos)}:v=1:a=0[vout]"
    gf = out.parent / "_picture_graph.txt"; gf.write_text(graph)
    total = sum(c["end_frame"] - c["start_frame"] for c in infos)
    sh([FF, "-v", "error", "-y"] + inputs + ["-/filter_complex", gf, "-map", "[vout]", "-r", "30", "-frames:v", total, "-an", "-c:v", "libx264", "-crf", "10", "-preset", "veryfast",
        "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", out])
    gf.unlink()
    print(f"picture-only pass ({'neutral' if a.neutral else 'framed'}): {total} frames -> {out}")


# ---------------------------------------------------------------------------------------------------------------------------- final
def wav_seconds(path):
    with wave.open(str(path)) as w: return w.getnframes() / w.getframerate()


def captions_track(P, total):
    """One transparent video of every caption state (PNG-in-MOV, lossless, mostly empty so tiny)."""
    man = json.loads((P / "graphics" / "captions" / "captions_gfx.json").read_text())["cues"]
    states = sorted([m for m in man if m.get("png")], key=lambda m: m["start_frame"])
    blank = P / "graphics" / "captions" / "_blank.png"
    if not blank.exists():
        sh([FF, "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=black@0.0:s={W}x{H},format=rgba", "-frames:v", "1", blank])
    lines, t = [], 0
    for m in states:
        if m["start_frame"] > t: lines += [f"file '{blank}'", f"duration {(m['start_frame'] - t) / 30:.6f}"]
        lines += [f"file '{ROOT / m['png']}'", f"duration {m['duration'] / 30:.6f}"]
        t = m["start_frame"] + m["duration"]
    if total > t: lines += [f"file '{blank}'", f"duration {(total - t) / 30:.6f}"]
    lines.append(f"file '{blank}'")
    lst = P / "graphics" / "captions" / "_track.txt"; lst.write_text("\n".join(lines))
    out = P / "graphics" / "captions" / "captions_track.mov"
    sh([FF, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-vf", "fps=30,format=rgba", "-frames:v", total, "-c:v", "png", out])
    return out


def scrim_png(P):
    png = P / "graphics" / "shots" / "scrim.png"
    if not png.exists():
        png.parent.mkdir(parents=True, exist_ok=True)
        sh([FF, "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=black:s={W}x{H},format=rgba", "-vf", "geq=r=0:g=0:b=0:a='255*0.55*pow(clip((Y-1000)/400,0,1),1.3)'", "-frames:v", "1", png])
    return png


def cmd_final(a):
    P, infos = load(a.job)
    total = sum(c["end_frame"] - c["start_frame"] for c in infos)
    pic = P / "graphics" / "matte" / "picture.mp4"
    if not pic.exists(): raise SystemExit("graphics/matte/picture.mp4 missing: run `render_edit.py picture <job>` first")
    out = Path(a.out) if a.out else P / "outputs" / "work" / f"{a.job}_render.mp4"; out.parent.mkdir(parents=True, exist_ok=True)
    eff = json.loads((P / "transcript" / "effects.json").read_text()) if (P / "transcript" / "effects.json").exists() else {}
    sfx_db = eff.get("sfx_gain_db", -14)
    catalog = json.loads((ROOT / "assets" / "sfx" / "catalog.json").read_text()); catalog = catalog.get("sfx", catalog)
    inputs, graph = ["-i", str(pic)], []
    n_in = 1
    v = "[0:v]"
    # --- V2 B-roll (video only, scrimmed copy)
    bj = P / "transcript" / "broll.json"
    plan = json.loads(bj.read_text()) if bj.exists() else {"inserts": []}
    ins = [i for i in plan.get("inserts", []) if not str(i["source"]).startswith("<")]
    for k, i in enumerate(ins):
        p = P / "raw" / i["source"]
        if not p.exists(): p = P / i["source"]
        if not p.exists(): p = Path(i["source"]) if Path(i["source"]).is_absolute() else ROOT / i["source"]
        if not p.exists(): raise SystemExit(f"b-roll source not found: {i['source']}")
        inputs += ["-ss", f"{float(i.get('src_start', 0)):.3f}", "-t", f"{i['frames'] / 30 + 0.5:.3f}", "-i", str(p)]
        bi = n_in; n_in += 1
        t0 = int(i["at"]) / 30
        chain = (f"[{bi}:v]fps=30,trim=end_frame={int(i['frames'])},setpts=PTS-STARTPTS,scale={W}:{H}:force_original_aspect_ratio=increase:in_range=auto:out_range=tv:flags=lanczos,"
                 f"crop={W}:{H},setsar=1,format=rgba")
        if plan.get("scrim"):
            inputs += ["-loop", "1", "-t", f"{i['frames'] / 30 + 1:.3f}", "-i", str(scrim_png(P))]; si = n_in; n_in += 1
            graph.append(chain + f"[b{k}raw];[b{k}raw][{si}:v]overlay=0:0:shortest=1,format=yuv420p,setpts=PTS+{t0:.6f}/TB[b{k}]")
        else:
            graph.append(chain + f",format=yuv420p,setpts=PTS+{t0:.6f}/TB[b{k}]")
        graph.append(f"{v}[b{k}]overlay=eof_action=pass:repeatlast=0:enable='between(t,{t0:.6f},{t0 + i['frames'] / 30 - 1e-4:.6f})'[vb{k}]"); v = f"[vb{k}]"
    # --- V3 graphics (ProRes 4444 with alpha, each starting at its own frame)
    mf = P / "graphics" / "overlays" / "overlays_gfx.json"
    gfx = sorted(json.loads(mf.read_text())["overlays"], key=lambda o: o["start_frame"]) if mf.exists() else []
    for k, o in enumerate(gfx):
        if not o.get("mov"): continue
        inputs += ["-i", str(ROOT / o["mov"])]; gi = n_in; n_in += 1
        graph.append(f"[{gi}:v]format=yuva444p10le,setpts=PTS-STARTPTS+{o['start_frame'] / 30:.6f}/TB[g{k}]")
        graph.append(f"{v}[g{k}]overlay=eof_action=pass:repeatlast=0:format=auto[vg{k}]"); v = f"[vg{k}]"
    # --- V4 captions
    if (P / "graphics" / "captions" / "captions_gfx.json").exists():
        ct = captions_track(P, total)
        inputs += ["-i", str(ct)]; ci = n_in; n_in += 1
        graph.append(f"[{ci}:v]setpts=PTS-STARTPTS[cap]"); graph.append(f"{v}[cap]overlay=eof_action=pass:format=auto,format=yuv420p[vout]"); v = "[vout]"
    else:
        graph.append(f"{v}format=yuv420p[vout]"); v = "[vout]"
    # --- A1 voice: every shot's audio in real time, exactly as long as its picture
    achains = []
    for i, c in enumerate(infos):
        n = c["end_frame"] - c["start_frame"]; t0 = c["start_frame"] / c.get("clip_fps", FPS_SRC)
        inputs += ["-ss", f"{t0:.5f}", "-t", f"{n / 30 + 0.2:.4f}", "-i", str(P / "raw" / c["source"])]
        ai = n_in; n_in += 1
        achains.append(f"[{ai}:a:0]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,atrim=end={n / 30:.6f},asetpts=PTS-STARTPTS,apad=whole_dur={n / 30:.6f}[a{i}]")
    graph += achains
    graph.append("".join(f"[a{i}]" for i in range(len(infos))) + f"concat=n={len(infos)}:v=0:a=1[voice]")
    # --- A2+ sound effects
    amix, k = ["[voice]"], 0
    for s in eff.get("sfx", []):
        ent = catalog[s["name"]]; f = ROOT / ent["file"]; dur = wav_seconds(f)
        at = s["at"] / 30; align = s.get("align", "start")
        t_start = max(0.0, {"start": at, "end": at - dur, "center": at - dur / 2}[align])
        inputs += ["-i", str(f)]; si = n_in; n_in += 1
        graph.append(f"[{si}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume={float(s.get('gain_db', sfx_db)):.2f}dB,adelay={int(t_start * 1000)}|{int(t_start * 1000)}[s{k}]")
        amix.append(f"[s{k}]"); k += 1
    graph.append("".join(amix) + f"amix=inputs={len(amix)}:duration=first:normalize=0,atrim=end={total / 30:.6f}[aout]")
    gf = out.parent / "_final_graph.txt"; gf.write_text(";\n".join(graph))
    sh([FF, "-v", "error", "-y"] + inputs + ["-/filter_complex", gf, "-map", v, "-map", "[aout]", "-r", "30", "-frames:v", total,
        "-c:v", "libx264", "-crf", str(a.crf), "-preset", "medium", "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out])
    gf.unlink()
    got = int(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(out)],
                             capture_output=True, text=True).stdout.split()[0].strip(","))
    print(f"render: {got} frames (plan {total}) -> {out}")
    if got != total: raise SystemExit(f"frame count {got} != plan {total}")


def cmd_check(a):
    """Everything the final file is built from, before it is built (replaces deliver.py check, which read a Resolve timeline)."""
    P, infos = load(a.job); rows = []
    ok = lambda name, good, info="": rows.append(("PASS" if good else "FAIL", name, info))
    if infos is None: raise SystemExit("run `render_edit.py timeline <job>` first")
    total = sum(c["end_frame"] - c["start_frame"] for c in infos)
    cuts = json.loads((P / "transcript" / "cuts.json").read_text())["cuts"]
    ok("shots == cut list", len(cuts) == len(infos), f"{len(infos)} shots, {total} frames ({total / 30:.2f} s)")
    ok("raw clips present", all((P / "raw" / c["source"]).exists() for c in infos))
    pic = P / "graphics" / "matte" / "picture.mp4"
    n = 0
    if pic.exists():
        n = int(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(pic)], capture_output=True, text=True).stdout.split()[0].strip(","))
    ok("picture pass == timeline length", n == total, f"picture {n}, timeline {total}")
    eff = json.loads((P / "transcript" / "effects.json").read_text()) if (P / "transcript" / "effects.json").exists() else {"zooms": [], "sfx": []}
    ok("a zoom entry for every shot", len(eff.get("zooms", [])) == len(infos), f"{len(eff.get('zooms', []))} / {len(infos)}")
    cat = json.loads((ROOT / "assets" / "sfx" / "catalog.json").read_text()); cat = cat.get("sfx", cat)
    ok("sound effects exist and fall inside the video", all(x["name"] in cat and 0 <= x["at"] < total for x in eff.get("sfx", [])), f"{len(eff.get('sfx', []))} effects")
    cm = P / "graphics" / "captions" / "captions_gfx.json"
    if cm.exists():
        cues = json.loads(cm.read_text())["cues"]
        bad = [c for c in cues if not str(c.get("verdict", "")).startswith("PASS") or not (ROOT / c["png"]).exists() or c["start_frame"] + c["duration"] > total + 1]
        ok("captions rendered and PASS", not bad and bool(cues), f"{len(cues)} states" + (f"; first bad: {bad[0].get('text')}" if bad else ""))
    else: ok("captions rendered", False, "graphics/captions/captions_gfx.json missing")
    mf = P / "graphics" / "overlays" / "overlays_gfx.json"
    if mf.exists():
        ov = json.loads(mf.read_text())["overlays"]
        bad = [o["id"] for o in ov if o.get("verdict") != "PASS" or not (ROOT / o["mov"]).exists() or o["start_frame"] + o["duration"] > total + 1]
        ok("graphics rendered and PASS", not bad, f"{len(ov)} scenes" + (f"; bad: {bad}" if bad else ""))
    bj = P / "transcript" / "broll.json"
    if bj.exists():
        for i in json.loads(bj.read_text()).get("inserts", []):
            if str(i["source"]).startswith("<"): continue
            fine = any(q.exists() for q in (P / "raw" / i["source"], P / i["source"], Path(i["source"])))
            ok(f"B-roll {i['source']} at {i['at']}", fine and int(i["at"]) + int(i["frames"]) <= total)
    print(f"FINAL CHECK  {a.job}")
    for st, name, info in rows: print(f"  {st}  {name:46s} {info}")
    if any(r[0] == "FAIL" for r in rows): raise SystemExit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("timeline"); p.add_argument("job"); p.set_defaults(fn=cmd_timeline)
    p = sub.add_parser("picture"); p.add_argument("job"); p.add_argument("--neutral", action="store_true"); p.add_argument("--out"); p.set_defaults(fn=cmd_picture)
    p = sub.add_parser("check"); p.add_argument("job"); p.set_defaults(fn=cmd_check)
    p = sub.add_parser("final"); p.add_argument("job"); p.add_argument("--out"); p.add_argument("--crf", type=int, default=14); p.set_defaults(fn=cmd_final)
    a = ap.parse_args(); a.fn(a)


main()
