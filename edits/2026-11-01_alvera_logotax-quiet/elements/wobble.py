# Residual camera motion in prepared clips: track features frame to frame, report wobble
# (path minus a 0.4 s smooth: shake/wobble) and drift (slow sway over the shot), in px at 1080 wide.
import cv2, numpy as np, subprocess, sys, json, os
FF = os.path.expanduser('~/.local/bin/ffmpeg')
def path(f, w=360, h=640):
    raw = subprocess.run([FF, '-nostdin', '-v', 'error', '-i', f, '-vf', f'scale={w}:{h},format=gray', '-f', 'rawvideo', '-'], capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, h, w); t = [(0, 0, 0)]
    for a, b in zip(fr[:-1], fr[1:]):
        p = cv2.goodFeaturesToTrack(a, 400, 0.01, 6); M = None
        if p is not None and len(p) > 8:
            n, st, _ = cv2.calcOpticalFlowPyrLK(a, b, p, None); ok = st.ravel() == 1
            if ok.sum() > 8: M, _ = cv2.estimateAffinePartial2D(p[ok], n[ok], ransacReprojThreshold=1.0)
        if M is None or not np.isfinite(M).all(): M = np.eye(2, 3)
        t.append((t[-1][0] + M[0, 2], t[-1][1] + M[1, 2], t[-1][2] + np.degrees(np.arctan2(M[1, 0], M[0, 0]))))
    return np.array(t) * [1080 / w, 1080 / w, 1]
for f in sys.argv[1:]:
    t = path(f)
    if len(t) < 3: print(json.dumps({"clip": os.path.basename(f), "error": "no frames read"})); continue
    r = 5; k = np.exp(-.5 * (np.arange(-r, r + 1) / 2.4) ** 2); k /= k.sum()
    sm = np.stack([np.convolve(np.pad(t[:, c], r, mode='edge'), k, 'valid') for c in range(3)], 1)
    hp = t - sm
    wob = float(np.hypot(hp[:, 0], hp[:, 1]).mean()); rot = float(np.abs(hp[:, 2]).mean())
    lin = np.polyfit(np.arange(len(t)), t[:, :2], 1); drift = float(np.hypot(*(t[:, :2] - np.outer(np.arange(len(t)), lin[0]) - lin[1]).T).max())
    print(json.dumps({'clip': os.path.basename(f), 'wobble_px': round(wob, 2), 'rot_wobble_deg': round(rot, 3), 'sway_px': round(drift, 1)}))
