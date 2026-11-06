# What the eye sees as shake: frame-to-frame jumps that differ from the neighbouring frames' motion.
import cv2, numpy as np, subprocess, sys, os, json
FF = os.path.expanduser('~/.local/bin/ffmpeg')
for f in sys.argv[1:]:
    w, h = 540, 960
    raw = subprocess.run([FF, '-nostdin', '-v', 'error', '-i', f, '-vf', f'scale={w}:{h},format=gray', '-f', 'rawvideo', '-'], capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, h, w); v = []
    for a, b in zip(fr[:-1], fr[1:]):
        p = cv2.goodFeaturesToTrack(a, 600, 0.01, 6); M = None
        if p is not None and len(p) > 8:
            n, st, _ = cv2.calcOpticalFlowPyrLK(a, b, p, None); ok = st.ravel() == 1
            if ok.sum() > 8: M, _ = cv2.estimateAffinePartial2D(p[ok], n[ok], ransacReprojThreshold=1.0)
        v.append((M[0, 2], M[1, 2]) if M is not None and np.isfinite(M).all() else (0, 0))
    v = np.array(v) * 1080 / w
    jerk = np.hypot(*np.diff(v, axis=0).T)            # change of per-frame motion
    print(json.dumps({'clip': os.path.basename(f), 'jerk_mean': round(float(jerk.mean()), 2), 'jerk_p90': round(float(np.percentile(jerk, 90)), 2),
                      'speed_mean': round(float(np.hypot(*v.T).mean()), 2)}))
