# Price counter overlay: fast count $0 -> $5,000 ("five") -> $10,000 ("ten grand"), hold, crack, shatter.
# Writes elements/overlays/counter.mov (RGBA, starts at T0 on the timeline) + counter_ticks.wav (one tick per digit change).
import os, math, random, subprocess
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "overlays"); os.makedirs(OUT + "/frames", exist_ok=True)
FONT = os.path.expanduser("~/Documents/claude-alvera/video-editor/assets/fonts/Geist/Geist-Black.ttf")
TICK_SRC = os.path.expanduser("~/Documents/claude-alvera/video-editor/assets/sfx/Display Digits 2.wav")
W, H, FPS = 1080, 1920, 24
CX, CY = 540, 1180
T0, T5, T10, TB, TEND = 4.26, 4.70, 5.10, 5.75, 6.35   # start, $5,000 on "ten", land, break, end
COLORS = [(214, 255, 226), (60, 240, 120), (16, 168, 78)]  # money green: light top -> vivid -> deep
SIZE = 205
random.seed(4)

def ease(x): return 1 - (1 - x) ** 3

def value(t):
    if t < T5: return 5000 * ease((t - T0) / (T5 - T0))
    if t < T10: return 5000 + 5000 * ease((t - T5) / (T10 - T5))
    return 10000

def gradient(h):
    ys = np.linspace(0, 1, h)[:, None]
    c = np.array(COLORS, float); k = ys * (len(c) - 1); i = np.clip(k.astype(int), 0, len(c) - 2); f = k - i
    return (c[i[:, 0]] * (1 - f) + c[i[:, 0] + 1] * f).astype(np.uint8)  # h x 3

def number(text, scale=1.0):
    """RGBA full-frame image of the price: shadow, dark edge, green gradient fill."""
    font = ImageFont.truetype(FONT, int(SIZE * scale))
    l, t, r, b = font.getbbox(text, stroke_width=8)
    tw, th = r - l, b - t; x0, y0 = CX - tw // 2 - l, CY - th // 2 - t
    m = Image.new("L", (W, H)); ImageDraw.Draw(m).text((x0, y0), text, font=font, fill=255)
    edge = Image.new("L", (W, H)); ImageDraw.Draw(edge).text((x0, y0), text, font=font, fill=255, stroke_width=8, stroke_fill=255)
    shadow = edge.filter(ImageFilter.GaussianBlur(14)).point(lambda v: int(v * 0.75))
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh = Image.new("RGBA", (W, H), (0, 6, 2, 255)); sh.putalpha(shadow)
    img = Image.alpha_composite(img, sh.transform((W, H), Image.AFFINE, (1, 0, 0, 0, 1, -10)))
    ed = Image.new("RGBA", (W, H), (3, 22, 10, 255)); ed.putalpha(edge); img = Image.alpha_composite(img, ed)
    g = np.zeros((H, W, 3), np.uint8); top, bot = CY - th // 2, CY + th // 2
    g[max(0, top):bot] = gradient(bot - max(0, top))[:, None, :]
    g[:max(0, top)] = COLORS[0]; g[bot:] = COLORS[-1]
    fill = Image.fromarray(g).convert("RGBA"); fill.putalpha(m); return Image.alpha_composite(img, fill)

def fmt(v): return "$" + f"{int(round(v / 10) * 10):,}"

# shards of the final number
final = number("$10,000"); A = np.array(final)[:, :, 3]
ys, xs = np.where(A > 10); bx0, by0, bx1, by1 = xs.min(), ys.min(), xs.max(), ys.max()
sub = cv2.Subdiv2D((int(bx0) - 2, int(by0) - 2, int(bx1 - bx0) + 6, int(by1 - by0) + 6))
pts = [(bx0, by0), (bx1, by0), (bx0, by1), (bx1, by1)] + [(random.uniform(bx0, bx1), random.uniform(by0, by1)) for _ in range(34)]
for p in pts: sub.insert((float(min(p[0], bx1)), float(min(p[1], by1))))
tris = [t.reshape(3, 2) for t in sub.getTriangleList() if all(bx0 - 3 <= v <= bx1 + 3 for v in t[0::2]) and all(by0 - 3 <= v <= by1 + 3 for v in t[1::2])]
FA = np.array(final); shards = []
for tri in tris:
    mask = np.zeros((H, W), np.uint8); cv2.fillConvexPoly(mask, tri.astype(np.int32), 255)
    x, y, w, h = cv2.boundingRect(tri.astype(np.int32)); x, y = max(x - 2, 0), max(y - 2, 0); w, h = w + 4, h + 4
    piece = FA[y:y + h, x:x + w].copy(); piece[:, :, 3] = np.minimum(piece[:, :, 3], mask[y:y + h, x:x + w])
    if piece[:, :, 3].max() < 20: continue
    c = tri.mean(0); d = c - (CX + random.uniform(-40, 40), CY + 30); n = np.hypot(*d) + 1e-6
    v = d / n * random.uniform(700, 1500) + (random.uniform(-150, 150), random.uniform(-650, -250))
    shards.append(dict(img=Image.fromarray(piece), c=c, v=v, w=random.uniform(-520, 520)))

frames = int(round((TEND - T0) * FPS)); ticks = []; last = None
for f in range(frames):
    t = T0 + f / FPS
    if t < TB:
        s = 1.0 + 0.35 * max(0, 1 - (t - T0) / 0.15)                       # punch in
        if t >= T10: s += 0.12 * max(0, 1 - (t - T10) / 0.18)             # landing bump
        txt = fmt(value(t)); img = number(txt, s)
        if txt != last: ticks.append(t - T0); last = txt
    else:
        tau = t - TB; img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); a = max(0.0, 1 - tau / 0.55)
        for sd in shards:
            p = sd["c"] + sd["v"] * tau + np.array([0, 2600]) * tau * tau / 2
            pc = sd["img"].rotate(sd["w"] * tau, resample=Image.BICUBIC, expand=True)
            if a < 1: pc.putalpha(pc.getchannel("A").point(lambda v: int(v * a)))
            img.alpha_composite(pc, (int(p[0] - pc.width / 2), int(p[1] - pc.height / 2))) if -400 < p[0] < W + 400 and -400 < p[1] < H + 400 else None
    img.save(f"{OUT}/frames/{f:03d}.png")

subprocess.run([os.path.expanduser("~/.local/bin/ffmpeg"), "-nostdin", "-v", "error", "-y", "-framerate", str(FPS),
                "-i", f"{OUT}/frames/%03d.png", "-c:v", "png", "-pix_fmt", "rgba", f"{OUT}/counter.mov"], check=True)
# one tick per digit change, slightly brighter as it climbs
raw = subprocess.run([os.path.expanduser("~/.local/bin/ffmpeg"), "-nostdin", "-v", "error", "-ss", "0.15", "-t", "0.05", "-i", TICK_SRC,
                      "-ac", "2", "-ar", "48000", "-f", "f32le", "-"], capture_output=True).stdout
tick = np.frombuffer(raw, np.float32).reshape(-1, 2) * np.hanning(len(raw) // 8)[:, None]
outw = np.zeros((int((TB - T0 + 0.2) * 48000), 2), np.float32)
for k, at in enumerate(ticks):
    i = int(at * 48000); g = 0.55 + 0.45 * k / max(1, len(ticks) - 1)
    outw[i:i + len(tick)] += tick[:len(outw) - i] * g
subprocess.run([os.path.expanduser("~/.local/bin/ffmpeg"), "-nostdin", "-v", "error", "-y", "-f", "f32le", "-ar", "48000", "-ac", "2",
                "-i", "-", "-c:a", "pcm_s16le", f"{OUT}/counter_ticks.wav"], input=outw.tobytes(), check=True)
print("frames", frames, "shards", len(shards), "digit ticks", len(ticks))
