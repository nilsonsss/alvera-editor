#!/usr/bin/env python3
"""Per-frame person matte for a job, so graphics can sit BEHIND the speaker (and the background can be replaced).

  matte.py picture <job> --timeline T     render a PICTURE-ONLY pass (V2+ disabled) -> graphics/matte/picture.mp4
  matte.py compute <job> [--short 720]    DeepLabV3-ResNet101 person matte -> graphics/matte/alpha.mp4 (gray)
  matte.py check   <job> [--frames ...]   contact sheet of frame / matte / punched text

The matte MUST be computed on the picture-only pass: run it on a finished render and the model segments the
people inside your own caption text and screenshot cards as "person" (measured.
`picture` runs on the MCP venv python (Resolve API); `compute`/`check` run on the whisperx venv (torch).
"""
import os as _os; _os.environ["PATH"] = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "tools", "bin") + _os.pathsep + _os.environ.get("PATH", "")
import argparse, json, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FF, FP = "ffmpeg", "ffprobe"


def cmd_picture(a):
    """The picture-only pass of V1, built by render_edit.py (ffmpeg; no Resolve): framed by default, --sub neutral = no zoom."""
    args = [sys.executable, str(ROOT / "scripts" / "render_edit.py"), "picture", a.job] + (["--neutral"] if getattr(a, "sub", None) == "neutral" else [])
    subprocess.run([sys.executable, str(ROOT / "scripts" / "render_edit.py"), "timeline", a.job], check=True, capture_output=True)
    r = subprocess.run(args, capture_output=True, text=True)
    print((r.stdout + r.stderr).strip().splitlines()[-1])
    if r.returncode != 0: raise SystemExit(r.stderr[-1200:])


def cmd_compute(a):
    import numpy as np, torch
    import torchvision.transforms.functional as TF
    from torchvision.models.segmentation import deeplabv3_resnet101, DeepLabV3_ResNet101_Weights
    P = ROOT / "projects" / a.job / "graphics" / "matte"
    if getattr(a, "sub", None):
        P = P / a.sub
    src = P / "picture.mp4"
    if not src.exists():
        raise SystemExit(f"{src} missing — run `matte.py picture` first (the matte must NOT be computed on a "
                         f"finished render; the model reads people inside captions and screenshot cards as persons)")
    w, h = 1080, 1920
    out_ = subprocess.run([FP, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=nb_frames",
                           "-of", "csv=p=0", str(src)], capture_output=True, text=True).stdout
    nb = int(next(x for x in out_.split() if x.isdigit()))   # ffprobe can print one line per stream copy
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    net = deeplabv3_resnet101(weights=DeepLabV3_ResNet101_Weights.COCO_WITH_VOC_LABELS_V1).eval().to(dev)
    MEAN, STD, PERSON = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225], 15
    if dev != "cpu" and not a.fp32:
        net = net.half()                                    # half precision costs nothing measurable here same IoU as fp32 at the same size)
    dec = subprocess.Popen([FF, "-v", "error", "-i", str(src), "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
                           stdout=subprocess.PIPE)
    enc = subprocess.Popen([FF, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{w}x{h}",
                            "-framerate", "30", "-i", "-", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "gray",
                            str(P / "alpha.mp4")], stdin=subprocess.PIPE)
    prev = None
    done = 0
    while True:
        bufs = []
        for _ in range(a.batch):
            buf = dec.stdout.read(w * h * 3)
            if len(buf) < w * h * 3:
                break
            bufs.append(np.frombuffer(buf, np.uint8).reshape(h, w, 3))
        if not bufs:
            break
        t = torch.from_numpy(np.stack(bufs)).permute(0, 3, 1, 2).float() / 255
        s = a.short / min(h, w)
        t = TF.resize(t, [int(h * s), int(w * s)], antialias=True)
        t = TF.normalize(t, MEAN, STD).to(dev)
        if dev != "cpu" and not a.fp32:
            t = t.half()
        with torch.no_grad():
            o = net(t)["out"].float().softmax(1)[:, PERSON]
        ps = TF.resize(o, [h, w], antialias=True).cpu().numpy()
        for p in ps:
            soft = np.clip((p - 0.35) / 0.30, 0, 1)                 # feathered edge, not a hard cut
            prev = soft if prev is None else 0.65 * soft + 0.35 * prev   # temporal smoothing kills edge flicker
            enc.stdin.write((prev * 255).astype(np.uint8).tobytes())
            done += 1
        if done % 60 < a.batch:
            print(f"  {done}/{nb}", flush=True)
    enc.stdin.close(); enc.wait(); dec.wait()
    print(f"alpha.mp4: {done} frames (picture has {nb}) on {dev} -> {P/'alpha.mp4'}")


def cmd_check(a):
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
    P = ROOT / "projects" / a.job / "graphics" / "matte"
    fs = [int(x) for x in a.frames.split(",")]
    cells = []
    for f in fs:
        pic = _one(P / "picture.mp4", f)
        al = _one(P / "alpha.mp4", f, gray=True)
        txt = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        fo = ImageFont.truetype(str(ROOT / "assets/fonts/InstrumentSerif-Italic.ttf"), 300)
        ImageDraw.Draw(txt).text((540, 820), a.text, font=fo, fill=(108, 123, 255, 255), anchor="mm")
        a2 = np.clip(np.array(txt.split()[3]).astype(np.int32) - al, 0, 255).astype(np.uint8)
        txt.putalpha(Image.fromarray(a2))
        comp = Image.fromarray(pic).convert("RGBA"); comp.alpha_composite(txt)
        cells += [Image.fromarray(pic), Image.fromarray(al).convert("RGB"), comp.convert("RGB")]
    cw = 210; ch = int(cw * 16 / 9)
    sh = Image.new("RGB", (3 * cw, len(fs) * ch), "black")
    for k, im in enumerate(cells):
        sh.paste(im.resize((cw, ch)), ((k % 3) * cw, (k // 3) * ch))
    out = ROOT / "analysis" / f"matte_check_{a.job}.png"
    sh.save(out); print(out)


def cmd_warp(a):
    """Build graphics/matte/alpha.mp4 for the CURRENT framing by transforming the NEUTRAL matte
    (graphics/matte/neutral/alpha.mp4, computed once on an unzoomed picture-only pass) with each shot's
    scale + pivot from effects.json. A Fusion Transform of size s about pivot p maps x -> p + (x-p)*s, so the
    output pixel x reads the neutral matte at p + (x-p)/s. Re-framing therefore costs seconds, not a 13-minute
    segmentation pass. `matte.py verify` spot-checks the result against a direct segmentation."""
    import numpy as np
    from PIL import Image
    P = ROOT / "projects" / a.job / "graphics" / "matte"
    W_, H_ = 1080, 1920
    raw = subprocess.run([FF, "-v", "error", "-i", str(P / "neutral" / "alpha.mp4"), "-pix_fmt", "gray",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    n = len(raw) // (W_ * H_)
    N = np.frombuffer(raw[:n * W_ * H_], np.uint8).reshape(n, H_, W_)
    eff = json.loads((ROOT / "projects" / a.job / "transcript" / "effects.json").read_text())["zooms"]
    clips = json.loads((ROOT / "projects" / a.job / "transcript" / "clip_infos.json").read_text())
    enc = subprocess.Popen([FF, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{W_}x{H_}",
                            "-framerate", "30", "-i", "-", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "gray",
                            str(P / "alpha.mp4")], stdin=subprocess.PIPE)
    t = 0
    zmap = {z["clip"]: z for z in eff}
    for ci, c in enumerate(clips, 1):
        d = c["end_frame"] - c["start_frame"]; z = zmap.get(ci)
        for k in range(d):
            f = t + k
            if z is None:
                enc.stdin.write(N[f].tobytes()); continue
            keys = z["keys"]; px, py = z["anchor"]
            sc = keys[-1][1]
            for (f0, s0), (f1, s1) in zip(keys, keys[1:]):
                if f0 <= k <= f1:
                    sc = s0 + (s1 - s0) * ((k - f0) / max(1, f1 - f0)); break
            if abs(sc - 1.0) < 1e-4:
                enc.stdin.write(N[f].tobytes()); continue
            pxp, pyp = px * W_, (1 - py) * H_                     # Fusion y runs from the BOTTOM
            im = Image.fromarray(N[f]).transform((W_, H_), Image.AFFINE,
                    (1 / sc, 0, pxp * (1 - 1 / sc), 0, 1 / sc, pyp * (1 - 1 / sc)), resample=Image.BILINEAR)
            enc.stdin.write(im.tobytes())
        t += d
    enc.stdin.close(); enc.wait()
    print(f"alpha.mp4 rebuilt for the current framing from the neutral matte: {t} frames")


def cmd_verify(a):
    """Spot-check alpha.mp4 against a direct segmentation of picture.mp4 at a few frames (IoU)."""
    import numpy as np, torch
    import torchvision.transforms.functional as TF
    from torchvision.models.segmentation import deeplabv3_resnet101, DeepLabV3_ResNet101_Weights
    P = ROOT / "projects" / a.job / "graphics" / "matte"
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    net = deeplabv3_resnet101(weights=DeepLabV3_ResNet101_Weights.COCO_WITH_VOC_LABELS_V1).eval().to(dev)
    worst, ious = 1.0, []
    for f in [int(x) for x in a.frames.split(",")]:
        pic = _one(P / "picture.mp4", f); al = _one(P / "alpha.mp4", f, gray=True) > 127
        t = torch.from_numpy(pic.copy()).permute(2, 0, 1).float() / 255
        t = TF.resize(t, [1024, 576], antialias=True)          # the same size `compute` uses by default, so the comparison is like for like
        t = TF.normalize(t, [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]).unsqueeze(0).to(dev)
        with torch.no_grad():
            pr = net(t)["out"][0].softmax(0)[15]
        pr = TF.resize(pr.unsqueeze(0), [1920, 1080], antialias=True)[0].cpu().numpy() > 0.5
        iou = 1.0 if not (pr | al).any() else (pr & al).sum() / (pr | al).sum()
        worst = min(worst, iou); ious.append(float(iou))
        print(f"  frame {f:4d}: IoU {iou:.3f}")
    mean = sum(ious) / max(1, len(ious))
    # a single moving-hand frame can sit at 0.9; the matte is wrong when the MEAN is low or a frame is far off (a black picture = offline media gives 0.000)
    print(f"warped matte matches a direct segmentation (mean IoU {mean:.3f}, worst {worst:.3f})" if mean > 0.95 and worst > 0.8 else f"MISMATCH (mean IoU {mean:.3f}, worst {worst:.3f}) - recompute with `matte.py compute`, or the picture is black (offline media)")


def _one(src, f, gray=False):
    import numpy as np
    pix = "gray" if gray else "rgb24"
    raw = subprocess.run([FF, "-v", "error", "-i", str(src), "-vf",
                          f"trim=start_frame={f}:end_frame={f+1},setpts=PTS-STARTPTS",
                          "-frames:v", "1", "-pix_fmt", pix, "-f", "rawvideo", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape((1920, 1080) if gray else (1920, 1080, 3))


ap = argparse.ArgumentParser()
sub = ap.add_subparsers(dest="cmd", required=True)
p = sub.add_parser("picture"); p.add_argument("job"); p.add_argument("--timeline")
p.add_argument("--sub", help="subfolder of graphics/matte to render into, e.g. neutral"); p.set_defaults(fn=cmd_picture)
p = sub.add_parser("compute"); p.add_argument("job"); p.add_argument("--short", type=int, default=576, help="short side the model sees (720 was 4.7x slower for IoU 0.96 vs 576)")
p.add_argument("--batch", type=int, default=4); p.add_argument("--fp32", action="store_true")
p.add_argument("--sub", help="subfolder of graphics/matte, e.g. neutral (the unzoomed pass)"); p.set_defaults(fn=cmd_compute)
p = sub.add_parser("check"); p.add_argument("job"); p.add_argument("--frames", default="60,300,700,900")
p.add_argument("--text", default="text"); p.set_defaults(fn=cmd_check)
def cmd_trim(a):
    """A cut change that only REMOVES frames does not need a 17-minute segmentation: drop the same frames from the neutral matte.
    --remove 1443-1449,1500-1500   (inclusive timeline frames of the OLD timeline). Re-render the neutral picture afterwards
    (matte.py picture --sub neutral) so picture.mp4 and alpha.mp4 agree, then `verify` checks the warped result against a direct pass."""
    P = ROOT / "projects" / a.job / "graphics" / "matte" / (a.sub or "")
    src = P / "alpha.mp4"
    spans = [tuple(int(x) for x in r.split("-")) for r in a.remove.split(",")]
    n0 = int(subprocess.run([FP, "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(src)],
                            capture_output=True, text=True).stdout.split()[0].strip(","))
    bak = P / "alpha_before_trim.mp4"
    if not bak.exists():
        shutil.copy(src, bak)
    expr = "*".join(f"not(between(n\\,{x}\\,{y}))" for x, y in spans)
    subprocess.run([FF, "-v", "error", "-y", "-i", str(bak), "-vf", f"select='{expr}',setpts=N/30/TB", "-r", "30", "-c:v", "libx264", "-crf", "12",
                    "-pix_fmt", "gray", str(src)], check=True)
    n1 = int(subprocess.run([FP, "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(src)],
                            capture_output=True, text=True).stdout.split()[0].strip(","))
    removed = sum(y - x + 1 for x, y in spans)
    print(f"alpha.mp4: {n0} -> {n1} frames (removed {removed}); original kept as {bak.name}")
    if n0 - n1 != removed:
        raise SystemExit("frame count does not match the removed span: do not use this matte")


p = sub.add_parser("trim"); p.add_argument("job"); p.add_argument("--remove", required=True); p.add_argument("--sub"); p.set_defaults(fn=cmd_trim)
p = sub.add_parser("warp"); p.add_argument("job"); p.set_defaults(fn=cmd_warp)
p = sub.add_parser("verify"); p.add_argument("job"); p.add_argument("--frames", default="46,130,272,600,863"); p.set_defaults(fn=cmd_verify)
a = ap.parse_args(); a.fn(a)
