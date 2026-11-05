"""Trim padding bands Gemini sometimes adds above/below a scene (it pads to reach 4:5).

A padding band ends in a perfectly straight seam: nearly EVERY column changes between two rows.
Natural edges (roof lines, horizons) never do that across the full width, so we look for a row
pair whose MEDIAN per-column difference spikes (real seams measured 30-37; normal photos ~3).
Flat sky is untouched (an earlier flat-row heuristic wrongly ate real sky).

Usage: python trim.py <img> [<img> ...]   (in place; prints what it cut). Also used by gen_scene.py.
"""
import sys
import numpy as np
from PIL import Image

SEAM = 15          # median |row diff| above this = straight padding seam
ZONE = 0.45        # only look in the top/bottom 45% of the image
PAD = 8            # extra px removed past the seam to drop the soft edge


def trim(path):
    im = Image.open(path).convert("RGB")
    g = np.asarray(im.convert("L")).astype(np.float32)
    h = g.shape[0]
    d = np.median(np.abs(np.diff(g, axis=0)), axis=1)          # d[y] = change between row y and y+1
    z = int(h * ZONE)
    top = bot = 0
    yt = int(np.argmax(d[:z]))
    if d[yt] > SEAM:
        top = yt + 1 + PAD
    yb = h - 1 - z + int(np.argmax(d[h - 1 - z:]))
    if d[yb] > SEAM:
        bot = h - (yb + 1) + PAD
    if top or bot:
        im.crop((0, top, im.width, h - bot)).save(path)
    return top, bot


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(p, "cut top/bottom px:", trim(p))
