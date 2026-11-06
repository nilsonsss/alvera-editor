#!/usr/bin/env python3
"""Caption renderer .

Three modes, all measured off the reference reel:
  word   ONE WORD per cue, big, swapped not animated — the word is up exactly as long as it is spoken.
  stack  2-4 lines accumulate one at a time, alternating the plain sans and the accent italic serif, then hold.
  line   a short full line in the small sans, STATIC for its whole cue. Words marked "accent" are in the accent
         italic serif from the first frame. (The reference's travelling accent was built and REJECTED.)

Plain words: Instrument Sans Bold, white, tight tracking, soft dark shadow, no outline.
Accent words: Instrument Serif Italic in the brand accent colour. Nothing else changes between the two.

Usage (whisperx venv):
  caption_swap.py plan  <job> [--captions captions_corrected.json]   -> transcript/captions_swap.json
  caption_swap.py render <job> [--mov] [--only 3,7]                  -> graphics/captions/*.mov + captions_gfx.json
"""
import os as _os; _os.environ["PATH"] = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "tools", "bin") + _os.pathsep + _os.environ.get("PATH", "")
import argparse, json, subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
W, H = 1080, 1920
SIDE = 120                 # safe-zone rule for graphics
CAP_SIDE = 56              # default only; the brand file sets `side_margin` (Instagram / TikTok keep buttons and captions at the edges)
BOTTOM_CLEAR = 480         # text bottom <= y 1440
MIN_STATE = 2              # Resolve silently drops 1-frame clips

FONT_DIR = ROOT / "assets/fonts"

DEFAULTS = {
    "font": "InstrumentSans[wdth,wght].ttf", "weight": 700, "accent_weight": 700, "accent_font": None,
    # EXACTLY two caption sizes in a video. size_big = a single word on its own; size_small = a grouped line. Nothing is ever shrunk to
    # fit: `plan` lowers size_big ONCE, for the whole video, until the longest single word fits.
    "size_big": 132, "size_small": 76,
    "gap_under_chin": 130, "y_min": 1240, "y_max": 1345, "side_margin": 56,
    "tracking_em": -0.02,
    "shadow": {"dy": 4, "blur": 9, "alpha": 165},
    "stack_pitch": 1.06,
}


def hex_rgb(h):
    h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def brand(job):
    jf = ROOT / "projects" / job / "job.json"
    j = json.loads(jf.read_text()) if jf.exists() else {}
    b = json.loads((ROOT / "assets" / "brands" / f"{j.get('brand','starter')}.json").read_text())
    pal = b.get("palette", {})
    sw = {**DEFAULTS, **b.get("captions", {}).get("swap", {}), **j.get("swap_overrides", {})}
    sw = {k: v for k, v in sw.items() if not k.startswith("_")}
    global CAP_SIDE
    CAP_SIDE = int(sw.get("side_margin", CAP_SIDE))
    sw["fill"] = hex_rgb(sw.get("fill") or pal.get("paper") or "#FFFFFF")
    sw["accent"] = hex_rgb(sw.get("accent") or pal.get("accent") or b.get("accent") or "#FFFFFF")
    return b.get("name", "default"), j.get("brand", "default"), sw


class F:
    """The brand's typeface(s). `font` is the one family every word is set in; `accent_font` is optional and is
    ONLY used when a brand explicitly has a second face."""
    _c = {}
    @classmethod
    def get(cls, name, px, wght):
        k = (name, px, wght)
        if k not in cls._c:
            f = ImageFont.truetype(str(FONT_DIR / name), px)
            try:
                axes = f.get_variation_axes()
                f.set_variation_by_axes([wght if (a.get("name") in (b"Weight", "Weight") or i == len(axes) - 1) else a["default"]
                                         for i, a in enumerate(axes)])
            except Exception:
                pass
            cls._c[k] = f
        return cls._c[k]


def font_for(accent, px, S):
    if accent and S.get("accent_font"):
        return F.get(S["accent_font"], px, S.get("accent_weight", S.get("weight", 700)))
    return F.get(S["font"], px, S.get("accent_weight", S.get("weight", 700)) if accent else S.get("weight", 700))


def _plain(px, S):
    return F.get(S["font"], px, S.get("weight", 700))


def runs_width(runs, px, S, draw):
    """runs = [(text, accent)]; width with tracking, plus the per-run metrics."""
    tr = S["tracking_em"] * px
    out, total = [], 0.0
    for t, acc in runs:
        f = font_for(acc, px, S)
        w = draw.textlength(t, font=f) + tr * max(0, len(t) - 1)
        out.append((t, acc, f, w))
        total += w
    total += draw.textlength(" ", font=_plain(px, S)) * max(0, len(runs) - 1)
    return total, out


def fit_px(runs, px, S, draw, usable=None):
    usable = W - 2 * CAP_SIDE if usable is None else usable
    """No shrink-to-fit any more: a cue is set at its size or it FAILS. (Shrinking long words gave the video a
    third, fourth and fifth text size; the user asked for exactly two.) Returns (px, fits)."""
    tot, _ = runs_width(runs, px, S, draw)
    return px, tot <= usable


def draw_runs(img, runs, px, S, cy, draw_shadow=True, left=None):
    """Draw one line of [(text, accent)] with its vertical centre at cy: centred on x=540, or starting at `left`."""
    d = ImageDraw.Draw(img)
    tot, metrics = runs_width(runs, px, S, d)
    space = d.textlength(" ", font=_plain(px, S))
    tr = S["tracking_em"] * px
    x = (W - tot) / 2 if left is None else left
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0)); ds = ImageDraw.Draw(sh)
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0)); dl = ImageDraw.Draw(lay)
    boxes = []
    pill = S.get("accent_style") == "pill"
    for i, (t, acc, f, w) in enumerate(metrics):
        col = S["fill"] if (acc and pill) else (S["accent"] if acc else S["fill"])
        cx = x
        if acc and pill:                                   # optional: emphasis as a coloured box behind the word
            pad = S.get("pill_pad_em", 0.16) * px; bb = d.textbbox((x, cy), t, font=f, anchor="lm")
            box = (x - pad, bb[1] - pad * 0.8, x + w + pad, bb[3] + pad * 0.8)
            ds.rounded_rectangle(box, radius=pad * 1.2, fill=(0, 0, 0, 255)); dl.rounded_rectangle(box, radius=pad * 1.2, fill=S["accent"] + (255,))
        for ch in t:                                       # per character so the tracking applies
            ds.text((cx, cy), ch, font=f, fill=(0, 0, 0, 255), anchor="lm")
            dl.text((cx, cy), ch, font=f, fill=col + (255,), anchor="lm")
            boxes.append(dl.textbbox((cx, cy), ch, font=f, anchor="lm"))
            cx += d.textlength(ch, font=f) + tr
        x += w + (space if i < len(metrics) - 1 else 0)
    if draw_shadow:
        s = S["shadow"]
        sh = sh.filter(ImageFilter.GaussianBlur(s["blur"]))
        a = sh.split()[3].point(lambda v: int(v * s["alpha"] / 255))
        sh.putalpha(a)
        img.alpha_composite(sh, (0, s["dy"]))
    img.alpha_composite(lay)
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def render_state(lines, px_list, S, block_centre, align="center", all_lines=None):
    """lines = [[(text, accent), ...], ...] stacked; returns (image, bbox).
    align="left" shares ONE left edge across the lines, set by the WIDEST line of the finished stack (all_lines),
    so the block does not slide sideways as it builds. That is what the reference does."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pitch = [int(p * S["stack_pitch"]) for p in px_list]
    total_h = sum(pitch)
    y = block_centre - total_h / 2
    left = None
    if align == "left":
        d0 = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
        widest = max(runs_width(L, px_list[0], S, d0)[0] for L in (all_lines or lines))
        left = (W - widest) / 2
    bb = None
    for runs, px, p in zip(lines, px_list, pitch):
        if runs:
            b = draw_runs(img, runs, px, S, y + p / 2, left=left)
            if b:
                bb = b if bb is None else (min(bb[0], b[0]), min(bb[1], b[1]), max(bb[2], b[2]), max(bb[3], b[3]))
        y += p
    return img, bb


def encode_mov(png, frames, out):
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-framerate", "30", "-i", str(png),
                        "-frames:v", str(frames), "-c:v", "prores_ks", "-profile:v", "4444",
                        "-pix_fmt", "yuva444p10le", str(out)], capture_output=True, text=True)
    if p.returncode:
        raise SystemExit(p.stderr[-400:])
    pix = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=pix_fmt,nb_frames", "-of", "csv=p=0", str(out)],
                         capture_output=True, text=True).stdout.strip().split(",")
    if not pix[0].startswith("yuva"):
        raise SystemExit(f"{out.name}: no alpha ({pix})")
    return int(pix[1])


# ---------------------------------------------------------------- plan
SENT_END = (".", "?", "!")


def cmd_plan(a):
    """Words -> cues. One word per cue at the BIG size; runs of very short words are grouped into one static line
    at the SMALL size. Every cue carries its sentence number so `place-y` can hold one height per sentence.
    A word is accented (brand accent colour) for its whole cue when its entry has "accent": true."""
    P = ROOT / "projects" / a.job
    _, _, S = brand(a.job)
    src = json.loads((P / "transcript" / a.captions).read_text())
    words, sent = [], 0
    for c in src["captions"]:
        for w in c["words"]:
            t = w["w"].strip().replace("[[", "").replace("]]", "")
            if not t:
                continue
            words.append({"text": t, "start": int(w["s"]), "end": int(w["e"]), "accent": bool(w.get("accent")), "sentence": sent})
            if t.endswith(SENT_END):
                sent += 1
    skip_f = P / "transcript" / "caption_skip.json"        # {"frames": [[0, 61]]}: stretches whose words are shown by a designed graphic instead of captions
    if skip_f.exists():
        spans = json.loads(skip_f.read_text())["frames"]
        words = [w for w in words if not any(a <= w["start"] < b for a, b in spans)]
    spans = json.loads(skip_f.read_text())["frames"] if skip_f.exists() else []
    for i in range(len(words) - 1):                      # a word is up until the next one starts, but never into a skipped stretch
        nxt = words[i + 1]["start"]; nxt = min([nxt] + [a for a, b in spans if words[i]["start"] < a < nxt])
        words[i]["end"] = max(words[i]["start"] + MIN_STATE, nxt)
    words[-1]["end"] = max(words[-1]["end"], words[-1]["start"] + MIN_STATE)

    cues, buf = [], []
    def flush():
        nonlocal buf
        if len(buf) == 1:
            cues.append({"kind": "word", **buf[0]})
        elif buf:
            cues.append({"kind": "line", "start": buf[0]["start"], "end": buf[-1]["end"], "sentence": buf[0]["sentence"],
                         "words": [{"w": x["text"], "s": x["start"], "accent": x["accent"]} for x in buf]})
        buf = []
    for w in words:
        short = (w["end"] - w["start"]) < a.short_frames and not w["accent"]
        if short:
            cand = buf + [w]
            ok = (len(cand) <= 5 and len(" ".join(x["text"] for x in cand)) <= a.line_chars
                  and cand[-1]["end"] - cand[0]["start"] <= 28 and cand[0]["sentence"] == w["sentence"])
            if ok:
                buf = cand; continue
            flush(); buf = [w]
        else:
            flush(); cues.append({"kind": "word", **w})
    flush()

    # a cue never runs into the next one (a grouped line used to end 1 frame after the next word began; Resolve then moves the next clip)
    for a_, b_ in zip(cues, cues[1:]):
        if a_["end"] > b_["start"]: a_["end"] = max(a_["start"] + MIN_STATE, b_["start"])
        if a_["end"] > b_["start"]: b_["start"] = a_["end"]

    # no cue runs across a cut:
    # a cue ends on the last frame before the cut; the first cue of the new shot starts on the cut when its word is up within 4 frames of it
    cut_file = P / "transcript" / "clip_infos.json"
    if cut_file.exists():
        cuts = [int(c["record_frame"]) for c in json.loads(cut_file.read_text())[1:]]
        for c_ in cues:
            for cut in cuts:
                if c_["start"] < cut < c_["end"]:
                    if cut - c_["start"] < MIN_STATE: c_["start"] = cut
                    else: c_["end"] = cut
                elif cut < c_["start"] <= cut + 4:
                    c_["start"] = cut
        for a_, b_ in zip(cues, cues[1:]):
            if a_["end"] > b_["start"]: a_["end"] = max(a_["start"] + MIN_STATE, b_["start"])
            if a_["end"] > b_["start"]: b_["start"] = a_["end"]

    # a lone short word ("a", "I") is up for at least 5 frames.
    # The frames come from the cue before it, then from the one after, and never across a cut.
    cut_set = set(int(c["record_frame"]) for c in json.loads((P / "transcript" / "clip_infos.json").read_text())[1:]) if (P / "transcript" / "clip_infos.json").exists() else set()
    for i, c_ in enumerate(cues):
        if c_["kind"] != "word" or c_["accent"] or c_["end"] - c_["start"] >= 5: continue
        need = 5 - (c_["end"] - c_["start"])
        if i > 0 and not any(c_["start"] - need <= k <= c_["start"] for k in cut_set):
            prev = cues[i - 1]; take = min(need, max(0, prev["end"] - prev["start"] - 3))
            c_["start"] -= take; prev["end"] -= take; need -= take
        if need > 0 and i + 1 < len(cues) and not any(c_["end"] <= k <= c_["end"] + need for k in cut_set):
            nxt = cues[i + 1]; give = min(need, max(0, nxt["end"] - nxt["start"] - 3))
            c_["end"] += give; nxt["start"] += give

    # ONE big size for the whole video: lower it until the longest single word fits, then never touch it again
    d = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    big = int(S["size_big"]); usable = W - 2 * CAP_SIDE
    singles = [(c["text"], c["accent"]) for c in cues if c["kind"] == "word"]
    while big > 60 and any(runs_width([r], big, S, d)[0] > usable for r in singles):
        big -= 2
    small = int(S["size_small"])
    lines = [[(x["w"], x["accent"]) for x in c["words"]] for c in cues if c["kind"] == "line"]
    while small > 48 and any(runs_width(L, small, S, d)[0] > usable for L in lines):
        small -= 2
    out = {"fps": 30, "width": W, "height": H, "sizes": {"big": big, "small": small},
           "note": "kind: word (BIG size) | line (SMALL size, static). Exactly two sizes. block_centre is set per "
                   "SENTENCE by `place-y`. Edit freely; `render` is the only consumer.",
           "cues": cues}
    f = P / "transcript" / "captions_swap.json"
    f.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    dur = sorted(c["end"] - c["start"] for c in cues)
    print(f"{f.name}: {len(cues)} cues ({sum(c['kind']=='word' for c in cues)} words, {sum(c['kind']=='line' for c in cues)} lines), "
          f"{sent + (0 if words[-1]['text'].endswith(SENT_END) else 1)} sentences, median {dur[len(dur)//2]} frames")
    print(f"sizes: BIG {big}px (asked {S['size_big']}), SMALL {small}px (asked {S['size_small']}) - the only two in the video")


def cmd_place_y(a):
    """One caption height per SENTENCE. The height comes from the LOWEST chin among the shots the sentence
    runs across, so the block clears the speaker's jaw in every one of them, clamped into the safe band."""
    P = ROOT / "projects" / a.job
    _, _, S = brand(a.job)
    hb = json.loads((P / "graphics" / "matte" / "head.json").read_text())["shots"]
    f = P / "transcript" / "captions_swap.json"; d = json.loads(f.read_text())
    span = {}
    for c in d["cues"]:
        s0, e0 = span.get(c["sentence"], (c["start"], c["end"]))
        span[c["sentence"]] = (min(s0, c["start"]), max(e0, c["end"]))
    ys = {}
    for k, (s0, e0) in span.items():
        chins = [r["chin"] for r in hb if r["start"] < e0 and r["end"] > s0 and "chin" in r]
        if chins: ys[k] = int(max(S["y_min"], min(S["y_max"], max(chins) + S["gap_under_chin"])))
    for k in span:
        if k not in ys: ys[k] = max(ys.values()) if ys else int(S["y_max"])
    if max(ys.values()) - min(ys.values()) <= a.hold_within:
        # the sentences ask for nearly the same height: do not move at all - one line for the whole video
        ys = {k: max(ys.values()) for k in ys}
        print(f"  all sentences within {a.hold_within}px of each other -> ONE height for the whole video")
    for c in d["cues"]:
        c["block_centre"] = ys[c["sentence"]]
    f.write_text(json.dumps(d, indent=1, ensure_ascii=False))
    for k in sorted(ys):
        txt = " ".join(c.get("text") or " ".join(w["w"] for w in c["words"]) for c in d["cues"] if c["sentence"] == k)
        print(f"  sentence {k}: frames {span[k][0]:4d}-{span[k][1]:4d}  y {ys[k]}  | {txt[:70]}")


# ---------------------------------------------------------------- render
def states_for(cue, S, sizes):
    """Expand a cue into [(frame_start, frame_end, lines, px_list, block_centre, align, full_lines)]."""
    bc = cue.get("block_centre", S["y_max"])
    if cue["kind"] == "word":
        return [(cue["start"], cue["end"], [[(cue["text"], cue.get("accent", False))]], [sizes["big"]], bc, "center", None)]
    if cue["kind"] == "line":
        # STATIC: an accented word is accented from the first frame of the cue to the last. It never switches on
        # as it is spoken and never switches back.
        runs = [(x["w"], bool(x.get("accent"))) for x in cue["words"]]
        if cue["end"] - cue["start"] < MIN_STATE:
            return []
        return [(cue["start"], cue["end"], [runs], [sizes["small"]], bc, "center", None)]
    if cue["kind"] == "stack":                              # kept for brands that want it; small size only
        ls = cue["lines"]; marks = [l.get("at", cue["start"]) for l in ls] + [cue["end"]]; out = []
        full = [[(l["text"], l.get("accent", False))] for l in ls]
        for i in range(len(ls)):
            if marks[i + 1] - marks[i] >= MIN_STATE:
                out.append((marks[i], marks[i + 1], full[:i + 1], [sizes["small"]] * (i + 1), bc, cue.get("align", "left"), full))
        return out
    raise SystemExit(f"unknown cue kind {cue['kind']}")


def cmd_render(a):
    P = ROOT / "projects" / a.job
    G = P / "graphics" / "captions"; G.mkdir(parents=True, exist_ok=True)
    name, key, S = brand(a.job)
    spec = json.loads((P / "transcript" / "captions_swap.json").read_text())
    only = {int(x) for x in a.only.split(",")} if a.only else None

    man = []
    idx = 0
    for ci, cue in enumerate(spec["cues"]):
        for si, (s, e, lines, px_list, bc, al, full) in enumerate(states_for(cue, S, spec["sizes"])):
            dur = e - s
            rec = {"index": idx, "cue": ci, "state": si, "kind": cue["kind"],
                   "text": " / ".join(" ".join(t for t, _ in L) for L in lines),
                   "start_frame": int(s), "duration": int(dur), "block_centre": bc, "align": al}
            if only is None or ci in only:
                d = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
                fits = all(fit_px(L, p, S, d)[1] for L, p in zip(lines, px_list))
                img, bb = render_state(lines, px_list, S, bc, align=al, all_lines=full)
                png = G / f"sw_{idx:03d}.png"
                img.save(png)
                rec["font_px"] = px_list
                rec["bbox"] = [int(x) for x in bb] if bb else None
                fails = []
                if bb:
                    if bb[3] > H - BOTTOM_CLEAR: fails.append(f"bottom {int(bb[3])} > {H-BOTTOM_CLEAR}")
                    if bb[0] < CAP_SIDE: fails.append(f"left {int(bb[0])} < {CAP_SIDE}")
                    if bb[2] > W - CAP_SIDE: fails.append(f"right {int(bb[2])} > {W-CAP_SIDE}")
                    if max(px_list) < 48: fails.append(f"font {max(px_list)} < 48")
                if not fits: fails.append("does not fit at its fixed size")
                rec["verdict"] = "FAIL: " + "; ".join(fails) if fails else "PASS"
                rec["png"] = str(png.relative_to(ROOT))
                if a.mov:
                    mov = G / f"sw_{idx:03d}.mov"
                    n = encode_mov(png, int(dur), mov)
                    if n != int(dur):
                        raise SystemExit(f"{mov.name}: {n} frames, wanted {dur}")
                    rec["mov"] = str(mov.relative_to(ROOT))
            idx += 1
            man.append(rec)

    mf = G / "captions_gfx.json"
    if only is not None and mf.exists():                   # --only MERGES, never overwrites
        old = {c["index"]: c for c in json.loads(mf.read_text())["cues"]}
        man = [({**old[c["index"]], **c} if c["index"] in old and "png" not in c else c) for c in man]
    out = {"engine": "caption_swap", "brand": name, "brand_key": key,
           "style": {k: v for k, v in S.items() if k not in ("shadow",)},
           "width": W, "height": H, "cues": man}
    mf.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    bad = [c["index"] for c in man if c.get("verdict", "PASS") != "PASS"]
    end = max(c["start_frame"] + c["duration"] for c in man)
    used = sorted({px for c in man for px in c.get("font_px", [])})
    print(f"{len(man)} states, {end} frames, font {S['font']} (accent face: {S.get('accent_font') or 'same'}), "
          f"accent #{'%02X%02X%02X' % S['accent']}, sizes used: {used}")
    if len(used) > 2:
        raise SystemExit(f"more than two caption sizes in one video: {used}")
    print("FAIL:" if bad else "all states PASS", bad if bad else "")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan"); p.add_argument("job"); p.add_argument("--captions", default="captions_corrected.json")
    p.add_argument("--short-frames", type=int, default=6, help="words shorter than this get grouped into a line")
    p.add_argument("--line-chars", type=int, default=19, help="longest grouped line; keeps every line inside the frame at the small size")
    p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("place-y"); p.add_argument("job")
    p.add_argument("--hold-within", type=int, default=100, help="if every sentence's height is within this many px, use one height for the whole video")
    p.set_defaults(fn=cmd_place_y)
    r = sub.add_parser("render"); r.add_argument("job"); r.add_argument("--mov", action="store_true")
    r.add_argument("--only"); r.set_defaults(fn=cmd_render)
    a = ap.parse_args(); a.fn(a)


main()
