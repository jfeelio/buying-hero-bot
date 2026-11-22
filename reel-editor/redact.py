"""Find a private object (e.g. a family photo on the shelf) in every frame and write blur boxes.

  python redact.py <reel_dir> [template.png ...]      (default: every *.png in D:/Reels/_redact/)

Templates live OUTSIDE the repo (D:/Reels/_redact/) -- this repo is public, never commit them.
Matching: multiscale normalised cross-correlation at 1/4 res on output/_clean.mp4 (the exact frames premium.py
draws on, zooms included). A frame counts when score >= THRESH; short dropouts (motion blur) are bridged
by holding the last box; boxes are smoothed and padded generously (the template is the lower part of the
photo, so the box grows UP more). premium.py reads build/redact.json and blurs those boxes on background
pixels only (the matte keeps Jorge sharp if he passes in front).
"""
import glob, json, os, subprocess, sys
import numpy as np, cv2
from render import ffmpeg_bin

W, H, D = 1080, 1920, 4
THRESH = 0.70          # Cost per deal reel: real 0.74-0.99, false 0.59-0.66
HOLD = 12              # frames to keep a box through a dropout
PAD_X, PAD_UP, PAD_DOWN = 0.45, 0.9, 0.3

def detect(clean, tpl_paths):
    tpls = []
    for tp in tpl_paths:
        t0 = cv2.cvtColor(cv2.imread(tp), cv2.COLOR_BGR2GRAY)
        for s in np.arange(0.5, 2.01, 0.1):
            t = cv2.resize(t0, None, fx=s / D, fy=s / D, interpolation=cv2.INTER_AREA)
            if t.shape[0] >= 8 and t.shape[1] >= 8: tpls.append(t)
    p = subprocess.Popen([ffmpeg_bin(), "-v", "error", "-i", clean, "-vf", f"scale={W // D}:{H // D}",
                          "-f", "rawvideo", "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE)
    fs = (W // D) * (H // D); raw = []
    while True:
        b = p.stdout.read(fs)
        if len(b) < fs: break
        g = np.frombuffer(b, np.uint8).reshape(H // D, W // D)
        best = (-1.0, None)
        for t in tpls:
            if t.shape[0] > g.shape[0] or t.shape[1] > g.shape[1]: continue
            _, mx, _, loc = cv2.minMaxLoc(cv2.matchTemplate(g, t, cv2.TM_CCOEFF_NORMED))
            if mx > best[0]: best = (mx, (loc[0] * D, loc[1] * D, t.shape[1] * D, t.shape[0] * D))
        raw.append(best)
    return raw

def boxes(raw):
    out, last, gap = [], None, 99
    for sc, bx in raw:
        if sc >= THRESH: last, gap = bx, 0
        else:
            gap += 1
            # a jump cut moves the best (false) match far away -> stop holding the box
            if last and bx and abs(bx[0] - last[0]) + abs(bx[1] - last[1]) > 80: gap = 99
        out.append(last if last and gap <= HOLD else None)
    sm = []
    for i, b in enumerate(out):                        # median-smooth positions over +-3 frames
        if b is None: sm.append(None); continue
        win = [x for x in out[max(0, i - 3):i + 4] if x]
        x, y, w, h = (int(np.median([v[k] for v in win])) for k in range(4))
        x0, x1 = max(0, int(x - w * PAD_X)), min(W, int(x + w * (1 + PAD_X)))
        y0, y1 = max(0, int(y - h * PAD_UP)), min(H, int(y + h * (1 + PAD_DOWN)))
        sm.append([x0, y0, x1, y1])
    return sm

if __name__ == "__main__":
    reel = sys.argv[1]
    tpls = sys.argv[2:] or sorted(glob.glob("D:/Reels/_redact/*.png"))
    raw = detect(os.path.join(reel, "output", "_clean.mp4"), tpls)
    bx = boxes(raw)
    os.makedirs(os.path.join(reel, "build"), exist_ok=True)
    json.dump({"boxes": bx, "scores": [round(r[0], 3) for r in raw]}, open(os.path.join(reel, "build", "redact.json"), "w"))
    on = sum(1 for b in bx if b); print(f"redact: {on}/{len(bx)} frames get a blur box")
