#!/usr/bin/env python3
"""Animated graphics from Remotion -> transparent ProRes 4444 -> the same overlay manifest everything else uses.

  remotion_gfx.py render  <job> [--only id1,id2]      render scenes from graphics/remotion/scenes.json
  remotion_gfx.py preview <job> <scene> [--frames a,b] stills of a scene composited on the framed picture (+ matte) for a look

scenes.json
  {"scenes": [{"id", "at", "frames", "why", "elements": [ {type, at, out, x, y, layer: "front"|"behind", ...} ]}]}
Every frame number in a scene file is an ABSOLUTE timeline frame; this script makes them relative to the scene start.
Element types: projects/_remotion/src/SceneFlat.tsx. Colours and typeface come from assets/brands/<brand>.json.

Layers: "front" is drawn as is. "behind" is punched by the person matte (graphics/matte/alpha.mp4) so it passes behind the speaker, then
the front layer is laid over it: one MOV per scene. Scenes must not overlap in time (one graphics track), so a beat that needs
both layers is ONE scene.

Checks before a scene is allowed on the timeline (verdict PASS): the FRONT layer must not touch the head box of the shot it is
in, and must stay inside the platform safe zone: y 220-1440, 60 px from the sides, and out of the right-hand button column
(x > 980 below y 1155). `preview --safe` draws the unsafe area in red.
Usage (whisperx venv; needs numpy + PIL).  Setup: projects/_remotion (npm install done once, see README.md)."""
import os as _os; _os.environ["PATH"] = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "tools", "bin") + _os.pathsep + _os.environ.get("PATH", "")
import argparse, json, os, re, shutil, subprocess, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RM = ROOT / "projects" / "_remotion"
FF = "ffmpeg"
COMP = ["SceneFlat"]          # composition id; a scenes file may set {"composition": "SceneFlat"}
FRAME_KEYS = {"at", "out", "ulAt", "strikeAt", "climbFrom", "climbTo", "flagAt", "labelAt", "limitAt", "label2At", "routeFrom",
              "routeTo", "ringsAt", "from", "to", "arrowAt", "tapAt", "typeFrom", "sendAt"}
W, H = 1080, 1920


def brand_colors(job):
    P = ROOT / "projects" / job
    brand = json.loads((P / "job.json").read_text())["brand"]
    b = json.loads((ROOT / "assets" / "brands" / f"{brand}.json").read_text()); p = b["palette"]
    font = ROOT / "assets" / "fonts" / b.get("captions", {}).get("swap", {}).get("font", "InstrumentSans[wdth,wght].ttf")
    (RM / "public").mkdir(exist_ok=True); shutil.copyfile(font, RM / "public" / "brand-font.ttf")          # the graphics use the brand's typeface
    return {"accent": p["accent"], "accent2": p.get("accent_2") or p["accent"], "ink": p["ink"], "paper": p["paper"]}


FRAME_RE = re.compile(r"^(from|to|.*(At|From|To|Frame))$")


def relative(el, at0):
    """`at`/`out` become scene-relative; every other frame key (anything named from, to, or ending in At / From / To / Frame, e.g. strikeAt,
    countFrom, flipAt) becomes ELEMENT-relative, because the components read them against the element's own clock."""
    o = dict(el)
    at_abs = int(el["at"])
    o["at"] = at_abs - at0
    if "out" in o and isinstance(o["out"], (int, float)):
        o["out"] = int(o["out"]) - at0
    for k in list(o):
        if k not in ("at", "out") and (k in FRAME_KEYS or FRAME_RE.match(k)) and isinstance(o[k], (int, float)) and not isinstance(o[k], bool):
            o[k] = int(o[k]) - at_abs
    # lists of dicts (items, badges, words, notes, lines): their `at` and every frame-named key are element-relative too
    for k, v in list(o.items()):
        if isinstance(v, list) and v and all(isinstance(it, dict) for it in v):
            o[k] = [{**it, **{kk: int(vv) - at_abs for kk, vv in it.items()
                              if (kk in ("at", "underline") or FRAME_RE.match(kk) or kk in FRAME_KEYS) and isinstance(vv, (int, float)) and not isinstance(vv, bool)}} for it in v]
    return o


def render_layer(job, sc, layer, brand, outdir):
    els = [relative(e, sc["at"]) for e in sc["elements"] if (e.get("layer") or "front") == layer]
    if not els:
        return None
    props = outdir / f"props_{sc['id']}_{layer}.json"
    props.write_text(json.dumps({"frames": sc["frames"], "layer": layer, "elements": els, "brand": brand}))
    out = outdir / f"{sc['id']}_{layer}.mov"
    cmd = ["npx", "remotion", "render", "src/index.ts", COMP[0], str(out), f"--props={props}", "--codec=prores", "--prores-profile=4444",
           "--pixel-format=yuva444p10le", "--image-format=png", "--overwrite", "--log=error"]
    r = subprocess.run(cmd, cwd=RM, capture_output=True, text=True)
    if r.returncode != 0 or not out.exists():
        sys.exit(f"remotion render failed for {sc['id']} ({layer}):\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
    return out


def combine(sc, behind, front, matte, out):
    """behind punched by the person matte (alpha *= 1 - matte), front laid over it -> one yuva444p10le ProRes 4444 file."""
    if behind is None:
        shutil.copy(front, out); return
    start, dur = sc["at"] / 30.0, sc["frames"] / 30.0
    fc = ("[2:v]format=gray,negate,format=gray[inv];[0:v]format=yuva444p,split[c][aa];[aa]alphaextract,format=gray[ag];"
          "[ag][inv]blend=all_mode=multiply[na];[c]format=yuv444p[crgb];[crgb][na]alphamerge[bp];")
    if front is None:
        fc += "[bp]format=yuva444p10le[o]"
        inputs = ["-i", str(behind), "-i", str(behind), "-ss", f"{start:.4f}", "-t", f"{dur:.4f}", "-i", str(matte)]
    else:
        fc += "[bp][1:v]overlay=format=auto,format=yuva444p10le[o]"
        inputs = ["-i", str(behind), "-i", str(front), "-ss", f"{start:.4f}", "-t", f"{dur:.4f}", "-i", str(matte)]
    r = subprocess.run([FF, "-v", "error", "-y", *inputs, "-filter_complex", fc, "-map", "[o]", "-frames:v", str(sc["frames"]),
                        "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-vendor", "apl0", str(out)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("ffmpeg combine failed: " + r.stderr[-1500:])


def alpha_frames(mov, w=270, h=480):
    raw = subprocess.run([FF, "-v", "error", "-i", str(mov), "-vf", f"alphaextract,scale={w}:{h}:flags=area", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         capture_output=True).stdout
    n = len(raw) // (w * h)
    return np.frombuffer(raw[:n * w * h], np.uint8).reshape(n, h, w)


def overlap_note(sc, behind, front):
    """A number behind the speaker must not be covered by the graphics in front of it."""
    if behind is None or front is None:
        return []
    B, Fr = alpha_frames(behind), alpha_frames(front)
    n = min(len(B), len(Fr)); worst = 0.0; at = 0
    for i in range(0, n, 3):
        b = B[i] > 40; fr = Fr[i] > 40
        if b.sum() < 50: continue
        cov = float((b & fr).sum()) / float(b.sum())
        if cov > worst: worst, at = cov, i
    return [f"behind layer {worst * 100:.0f}% covered by the front layer at f{sc['at'] + at}"] if worst > 0.06 else []


def verdict(job, sc, front):
    """front layer vs the head box of the shot each frame sits in, and vs the bottom UI zone."""
    P = ROOT / "projects" / job
    notes = []
    if front is None:
        return "PASS", notes
    A = alpha_frames(front)
    hj = P / "graphics" / "matte" / "head.json"
    infos = json.loads((P / "transcript" / "clip_infos.json").read_text())
    shots = json.loads(hj.read_text())["shots"] if hj.exists() else []
    spans = []
    for c in infos:
        spans.append((c["record_frame"], c["record_frame"] + c["end_frame"] - c["start_frame"]))
    s = 270 / W
    bad = 0
    cs = P / "transcript" / "captions_swap.json"                  # captions occupy block_centre +- 78 px: graphics keep out of it
    cap_band = None
    if cs.exists():
        bc = [c.get("block_centre") for c in json.loads(cs.read_text())["cues"] if c.get("block_centre")]
        if bc and sc.get("captions") != "off": cap_band = (int(min(bc)) - 78, int(max(bc)) + 78)   # a scene that REPLACES the captions (a hook text) may use the band
    for i in range(0, len(A), 3):
        t = sc["at"] + i
        a = A[i] > 40
        if a[int(1440 * s):].any():
            notes.append(f"f{t}: below y 1440"); bad += 1; continue
        if a[:int(220 * s)].any():
            notes.append(f"f{t}: above y 220 (Instagram / TikTok header)"); bad += 1; continue
        if cap_band and a[int(cap_band[0] * s):int(cap_band[1] * s)].any():
            notes.append(f"f{t}: over the caption band y {cap_band[0]}-{cap_band[1]}"); bad += 1; continue
        if a[int(1155 * s):, int((W - 100) * s):].any():
            notes.append(f"f{t}: in the right-hand button column (x > 980, y > 1155)"); bad += 1; continue
        if a[:, :int(60 * s)].any() or a[:, int((W - 60) * s):].any():
            notes.append(f"f{t}: within 60 px of a side"); bad += 1; continue
        k = next((j for j, (a0, a1) in enumerate(spans) if a0 <= t < a1), None)
        if k is None or k >= len(shots) or shots[k].get("empty"):
            continue
        sh = shots[k]
        x0, x1 = int((sh["head_left_min"] + 30) * s), int((sh["head_right_max"] - 30) * s)
        y0, y1 = int((sh["head_top"] + 20) * s), int(sh["chin"] * s)
        if a[y0:y1, x0:x1].sum() > 6:
            notes.append(f"f{t}: touches the face (shot {k + 1})"); bad += 1
    return ("PASS" if bad == 0 else "FAIL"), notes[:6]


def scenes_file(a, P):
    return Path(a.scenes) if getattr(a, "scenes", None) else P / "graphics" / "remotion" / "scenes.json"


def scene_key(sc, P, brand, matte):
    """Everything a scene's render AND its verdict depend on. Unchanged key + the rendered file still there = skip the render a one-graphic change re-rendered
    every scene, 20-40 s each)."""
    import hashlib
    h = hashlib.sha256()
    h.update(json.dumps(sc, sort_keys=True).encode()); h.update(json.dumps(brand, sort_keys=True).encode()); h.update(COMP[0].encode())
    for f in sorted((RM / "src").glob("*.tsx")): h.update(f.read_bytes())
    for name in ("graphics/matte/head.json", "transcript/captions_swap.json", "transcript/clip_infos.json"):
        q = P / name
        if q.exists(): h.update(q.read_bytes())
    if any((e.get("layer") or "front") == "behind" for e in sc["elements"]) and matte.exists():
        h.update(f"{matte.stat().st_size}:{matte.stat().st_mtime_ns}".encode())
    for e in sc["elements"]:
        src = e.get("src")
        if src and (RM / "public" / src).exists(): h.update(f"{src}:{(RM / 'public' / src).stat().st_size}".encode())
    return h.hexdigest()


def cmd_render(a):
    import concurrent.futures as cf
    P = ROOT / "projects" / a.job
    sf = json.loads(scenes_file(a, P).read_text()); COMP[0] = sf.get("composition", "SceneFlat"); spec = sf["scenes"]
    only = set(a.only.split(",")) if a.only else None
    brand = brand_colors(a.job)
    out_dir = P / "graphics" / "remotion"
    matte = P / "graphics" / "matte" / "alpha.mp4"
    cache_f = out_dir / "cache.json"
    cache = json.loads(cache_f.read_text()) if cache_f.exists() and not a.force else {}
    todo = [sc for sc in spec if not (only and sc["id"] not in only)]

    def one(sc):
        key = scene_key(sc, P, brand, matte)
        final = out_dir / f"{sc['id']}.mov"
        c = cache.get(sc["id"])
        if c and c["key"] == key and final.exists():
            return sc, {**c["entry"], "start_frame": sc["at"], "duration": sc["frames"]}, "cached", key
        behind = render_layer(a.job, sc, "behind", brand, out_dir)
        front = render_layer(a.job, sc, "front", brand, out_dir)
        if behind is not None and not matte.exists():
            sys.exit("a scene has a behind layer but graphics/matte/alpha.mp4 does not exist")
        combine(sc, behind, front, matte, final)
        v, notes = verdict(a.job, sc, front)
        ov = overlap_note(sc, behind, front)
        if ov:
            v = "FAIL"; notes = notes + ov
        return sc, {"id": sc["id"], "kind": "remotion", "start_frame": sc["at"], "duration": sc["frames"],
                    "mov": str(final.relative_to(ROOT)), "verdict": v, "why": sc.get("why", ""), "notes": notes}, "rendered", key
    man = []
    with cf.ThreadPoolExecutor(max_workers=a.jobs) as ex:
        for sc, entry, how, key in ex.map(one, todo):
            man.append(entry); cache[sc["id"]] = {"key": key, "entry": entry}
            print(f"{sc['id']:14s} remotion @{sc['at']:5d} {sc['frames']:4d}f  {entry['verdict']}  {how}  {'; '.join(entry['notes'])}")
    cache_f.write_text(json.dumps(cache, indent=1, ensure_ascii=False))
    # scenes are one track: no overlaps between ANY manifest entries
    mf = P / "graphics" / "overlays" / "overlays_gfx.json"
    cur = json.loads(mf.read_text()) if mf.exists() else {"width": W, "height": H, "overlays": []}
    keep = [o for o in cur["overlays"] if o["id"] not in {m["id"] for m in man} and (a.keep_others or o.get("kind") == "behind")]
    allm = sorted(keep + man, key=lambda o: o["start_frame"])
    for x, y in zip(allm, allm[1:]):
        if x["start_frame"] + x["duration"] > y["start_frame"]:
            print(f"WARNING overlap on the graphics track: {x['id']} ({x['start_frame']}+{x['duration']}) runs into {y['id']} @{y['start_frame']}")
    cur["overlays"] = allm
    mf.write_text(json.dumps(cur, indent=1, ensure_ascii=False))
    print("->", mf)


def cmd_preview(a):
    from PIL import Image
    P = ROOT / "projects" / a.job
    _sf = json.loads(scenes_file(a, P).read_text()); COMP[0] = _sf.get("composition", "SceneFlat")
    sc = next(s for s in _sf["scenes"] if s["id"] == a.scene)
    brand = brand_colors(a.job)
    out_dir = P / "graphics" / "remotion" / "preview"; out_dir.mkdir(parents=True, exist_ok=True)
    frames = [int(x) for x in a.frames.split(",")] if a.frames else [sc["at"] + sc["frames"] // 2]
    for t in frames:
        rel = t - sc["at"]
        layers = {}
        for layer in ("behind", "front"):
            els = [relative(e, sc["at"]) for e in sc["elements"] if (e.get("layer") or "front") == layer]
            if not els:
                continue
            props = out_dir / f"props_{layer}.json"
            props.write_text(json.dumps({"frames": sc["frames"], "layer": layer, "elements": els, "brand": brand}))
            png = out_dir / f"{sc['id']}_{layer}_{t}.png"
            r = subprocess.run(["npx", "remotion", "still", "src/index.ts", COMP[0], str(png), f"--props={props}", f"--frame={rel}", "--log=error", "--overwrite"],
                               cwd=RM, capture_output=True, text=True)
            if r.returncode != 0:
                sys.exit(r.stdout[-800:] + r.stderr[-800:])
            layers[layer] = Image.open(png).convert("RGBA")

        def grab(src, gray=False):
            raw = subprocess.run([FF, "-v", "error", "-i", str(src), "-vf", f"select=eq(n\\,{t})", "-vframes", "1", "-f", "rawvideo",
                                  "-pix_fmt", "gray" if gray else "rgb24", "-"], capture_output=True).stdout
            return np.frombuffer(raw, np.uint8).reshape(H, W) if gray else Image.frombytes("RGB", (W, H), raw)
        base = grab(P / "graphics" / "matte" / "picture.mp4").convert("RGBA")
        if "behind" in layers:
            m = grab(P / "graphics" / "matte" / "alpha.mp4", gray=True)
            b = np.array(layers["behind"]); b[..., 3] = (b[..., 3].astype(np.float32) * (1 - m / 255.0)).astype(np.uint8)
            base.alpha_composite(Image.fromarray(b))
        if "front" in layers:
            base.alpha_composite(layers["front"])
        if a.safe:
            from PIL import ImageDraw
            g = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(g); red = (255, 0, 0, 72)
            d.rectangle([0, 0, W, 220], fill=red); d.rectangle([0, 1440, W, H], fill=red)
            d.rectangle([0, 0, 60, H], fill=red); d.rectangle([W - 60, 0, W, H], fill=red); d.rectangle([W - 100, 1155, W, H], fill=red)
            base.alpha_composite(g)
        o = out_dir / f"{sc['id']}_{t}.png"; base.convert("RGB").save(o); print(o)


ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
p = sub.add_parser("render"); p.add_argument("job"); p.add_argument("--only")
p.add_argument("--scenes", help="a scenes file other than the job's own (e.g. projects/_remotion/examples/...)")
p.add_argument("--force", action="store_true", help="ignore the render cache (graphics/remotion/cache.json)"); p.add_argument("--jobs", type=int, default=3, help="scenes rendered at the same time")
p.add_argument("--keep-others", action="store_true", help="keep other manifest entries (default: only 'behind' items from behind_gfx.py)")
p.set_defaults(fn=cmd_render)
p = sub.add_parser("preview"); p.add_argument("job"); p.add_argument("scene"); p.add_argument("--frames")
p.add_argument("--safe", action="store_true", help="draw the platform-unsafe area in red"); p.add_argument("--scenes"); p.set_defaults(fn=cmd_preview)
a = ap.parse_args(); a.fn(a)
