"""Automatic QA for a built reel: catches the mistakes Jorge kept catching by eye (Cost per deal, 11-22).

  python reel.py qa <reel> [output/hook_B.mp4]      (also runs at the end of every premium `reel.py build`)

Checks (premium style): edges vs HIS jump cuts, slides that flash by, slide gaps, orphan / duplicate captions,
graphics over his face, unreadable behind-the-head text, too many behind-texts, sound-alike typos.
Writes build/qa.txt and output/qa/sheet_NN.jpg (a frame every 0.5s, timestamped). Claude must LOOK at every
sheet before delivering -- the checks catch the known mistake types, the sheets catch the rest.
"""
import glob, json, os, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from render import ffmpeg_bin

W, H = 1080, 1920
EDGE_TOL, EDGE_NEAR = 0.04, 0.6        # within 0.04s = on the cut; 0.04-0.6s off = flashes the wrong clip
MIN_SLIDE, MIN_CAPTION = 2.5, 0.5
SUSPECT = {"guests": "guess", "loose": "lose"}   # Whisper sound-alikes seen in Jorge's reels


def cuts(reel):
    cj = os.path.join(reel, "build", "cuts.json")
    raw = os.path.join(reel, "raw.mov")
    if os.path.exists(cj) and json.load(open(cj)).get("size") == os.path.getsize(raw):
        return json.load(open(cj))["cuts"]
    r = subprocess.run([ffmpeg_bin(), "-i", raw, "-vf", "select='gt(scene,0.08)',showinfo", "-an", "-f", "null", "-"],
                       capture_output=True, text=True, errors="ignore")
    cs = sorted({round(float(x.split("pts_time:")[1].split()[0]), 3) for x in r.stderr.splitlines() if "pts_time:" in x})
    json.dump({"size": os.path.getsize(raw), "cuts": cs}, open(cj, "w"))
    return cs


def frame(path, t, gray=False):
    b = subprocess.run([ffmpeg_bin(), "-v", "error", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1", "-f", "rawvideo",
                        "-pix_fmt", "gray" if gray else "rgb24", "-"], capture_output=True).stdout
    if not b: return None
    return np.frombuffer(b, np.uint8).reshape(H, W) if gray else np.frombuffer(b, np.uint8).reshape(H, W, 3)


def face_box(m):
    """face from the matte: head width just under the crown, face = crown .. ~1.35 head-widths down (chin).
    (OpenCV 5 dropped Haar cascades; the matte is already there and follows him exactly.)"""
    rows = np.where((m > 128).sum(axis=1) > 6)[0]
    if not len(rows): return None
    top = int(rows[0])
    ws, cs = [], []
    for y in range(top + 60, min(top + 260, H)):
        xs = np.where(m[y] > 128)[0]
        if len(xs): ws.append(xs[-1] - xs[0]); cs.append((xs[-1] + xs[0]) / 2)
    if not ws: return None
    w0, cx = float(np.median(ws)), float(np.median(cs))
    return (cx - w0 / 2, top + 0.2 * w0, cx + w0 / 2, top + 1.35 * w0)


def overlap(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def minus(iv, muted):
    """visible pieces of interval iv after removing the muted intervals"""
    segs = [iv]
    for a, b in muted:
        nxt = []
        for s, e in segs:
            if b <= s or a >= e: nxt.append((s, e)); continue
            if a > s: nxt.append((s, a))
            if b < e: nxt.append((b, e))
        segs = nxt
    return [(s, e) for s, e in segs if e - s > 0.01]


def run(reel, video=None):
    import premium
    edit = json.load(open(os.path.join(reel, "edit.json"), encoding="utf-8"))
    P = edit.get("premium", {})
    pl = premium.plan(reel)
    cs = cuts(reel)
    issues = []
    def flag(t, kind, msg): issues.append((round(t, 2), kind, msg))
    def near(e):
        if not cs: return None, 99
        c = min(cs, key=lambda c: abs(c - e)); return c, abs(c - e)

    # 1. slide / B-roll edges vs his jump cuts ------------------------------------------------------------
    comps = sorted(P.get("composites", []), key=lambda c: c["start"])
    edges = []
    for k, c in enumerate(comps):
        nm = os.path.basename(c["file"])
        prev_adj = k > 0 and abs(comps[k - 1]["end"] - c["start"]) < 0.05
        next_adj = k + 1 < len(comps) and abs(comps[k + 1]["start"] - c["end"]) < 0.05
        if not prev_adj: edges.append((c["start"], c.get("cut_in", False), f"slide {nm} in"))
        if not next_adj: edges.append((c["end"], c.get("cut_out", False), f"slide {nm} out"))
        if c["end"] - c["start"] < MIN_SLIDE:
            flag(c["start"], "TOO QUICK", f"slide {nm} is up only {c['end'] - c['start']:.1f}s -- keep raw video or lengthen")
        if k + 1 < len(comps) and 0.05 <= comps[k + 1]["start"] - c["end"] < 0.8:
            flag(c["end"], "GAP", f"{comps[k + 1]['start'] - c['end']:.2f}s of his face flashes between two slides")
    for o in edit.get("overlays", []):
        if o.get("mode", "full") != "full":   # cards/stickers/titles float over him; only full-frame B-roll needs cut-snapping
            continue
        hard = o.get("transition", "fade") == "cut"; nm = os.path.basename(o["file"])
        edges += [(o["start"], hard, f"B-roll {nm} in"), (o["end"], hard, f"B-roll {nm} out")]
    for e, hard, what in edges:
        c, d = near(e)
        if EDGE_TOL < d < EDGE_NEAR:
            flag(e, "BAD CUT", f"{what} at {e:.2f}s is {d:.2f}s off his jump cut at {c:.2f}s -- snap it")
        elif d <= EDGE_TOL and not hard:
            flag(e, "BAD CUT", f"{what} lands on his cut at {c:.2f}s but crossfades -- cut_in/cut_out or transition: cut")

    # 2. captions: orphans + duplicates of big text on screen ----------------------------------------------
    hero_txt = [{w.strip(".,!?'").lower() for ln in hs["lines"] for w in ln["text"].split()} for hs in P.get("heroes", [])]
    for c in pl["chunks"]:
        vis = minus((c["start"], c["end"]), pl["mute"])
        txt = " ".join(c["words"])
        for s, e in vis:
            cut_short = (c["end"] - c["start"]) - (e - s) > 0.05
            if e - s < MIN_CAPTION and (cut_short or len(c["words"]) <= 2):
                flag(s, "ORPHAN CAPTION", f"'{txt}' shows only {e - s:.2f}s -- hide it under the graphic or merge it")
        # leftover from the previous sentence: chunk starts with a word that ends a sentence/phrase the viewer
        # mostly didn't see (e.g. "deal okay now keep", "month hey okay") -- flag the leading carry-over word
        if vis and len(c["words"]) > 1 and vis[0][0] - c["start"] > 0.2 and c["start"] - 0.01 <= vis[0][0]:
            flag(vis[0][0], "LEFTOVER?", f"'{txt}' opens on '{c['words'][0]}' said under the graphic -- break before it if it ends the last sentence (judge)")
        cw = {w.strip(".,!?'").lower() for w in c["words"]}
        for h, ht in zip(pl["heroes"], hero_txt):
            dup = (cw & ht) - {"the", "a", "to", "of", "and", "per"}
            if dup and any(min(e, h["end"]) - max(s, h["start"]) > 0.05 for s, e in vis):
                flag(c["start"], "DUPLICATE", f"caption '{txt}' repeats the big text on screen ({', '.join(sorted(dup))})")

    # 3. sound-alike typos ----------------------------------------------------------------------------------
    for c in pl["chunks"]:
        for w in c["words"]:
            k = w.strip(".,!?").lower()
            if k in SUSPECT:
                flag(c["start"], "TYPO?", f"'{w}' in '{' '.join(c['words'])}' -- probably '{SUSPECT[k]}'")

    # 4. graphics over his face + behind-text readability ---------------------------------------------------
    behind = [(h, hs) for h, hs in zip(pl["heroes"], P.get("heroes", [])) if not h["front"]]
    if len(behind) > 1:
        flag(behind[1][0]["start"], "RULE", f"{len(behind)} behind-the-head texts -- Jorge's rule is ONCE per reel")
    clean = next((p for p in (os.path.join(reel, "build", "clean.mp4"), os.path.join(reel, "output", "_clean.mp4"))
                  if os.path.exists(p)), None)
    matte = os.path.join(reel, "build", "matte.mp4")
    if clean:
        checks = []
        for T in P.get("tiles", []):
            y, n = T.get("y", 1290), len(T["items"])
            for k, it in enumerate(T["items"]):
                cx = W / 2 if n == 1 else W / 2 + (k - (n - 1) / 2) * 470
                checks.append((max(it["t"], T["start"]) + 0.4, (cx - 235, y - 170, cx + 235, y + 170), f"'{it['label']}' card"))
        for h, hs in zip(pl["heroes"], P.get("heroes", [])):
            if not h["front"]: continue
            tot = sum(d["im"].height - 66 + h["gap"] for d in h["imgs"])
            y0 = h["top"] if h["top"] is not None else 120
            for t in np.arange(h["start"] + 0.2, h["end"], 1.0):
                checks.append((float(t), (60, y0 + 40, W - 60, y0 + tot), f"big text '{' / '.join(l['text'] for l in hs['lines'])}'"))
        for t, box, what in checks:
            if any(c["start"] <= t < c["end"] for c in comps): continue
            mf = frame(matte, t, gray=True) if os.path.exists(matte) else None
            fb = face_box(mf) if mf is not None else None
            if fb and overlap(fb, box) > 0.12 * (fb[2] - fb[0]) * (fb[3] - fb[1]):
                flag(t, "OVER FACE", f"{what} covers his face at {t:.1f}s -- move it lower")
        if os.path.exists(matte):
            for h, hs in behind:
                m0 = frame(matte, h["start"], gray=True)
                t = min(h["imgs"][-1]["start"] + 0.6, h["end"] - 0.05)
                m = frame(matte, t, gray=True)
                if m0 is None or m is None: continue
                h["y"] = None
                premium.draw_hero(Image.new("RGBA", (W, H)), h, h["start"], m0.astype(np.float32) / 255)
                lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                premium.draw_hero(lay, h, t, m.astype(np.float32) / 255)
                a = np.asarray(lay)[..., 3].astype(np.float32) / 255
                occ = float((a * m / 255).sum() / max(a.sum(), 1))
                if occ > 0.25:
                    flag(h["start"], "UNREADABLE", f"'{' / '.join(l['text'] for l in hs['lines'])}' is {occ:.0%} hidden behind his head")

    # 5. contact sheets: a frame every 0.5s ------------------------------------------------------------------
    video = video or max(glob.glob(os.path.join(reel, "output", "*.mp4")), key=os.path.getmtime)
    qd = os.path.join(reel, "output", "qa"); os.makedirs(qd, exist_ok=True)
    for f in glob.glob(os.path.join(qd, "sheet_*.jpg")): os.remove(f)
    p = subprocess.Popen([ffmpeg_bin(), "-v", "error", "-i", video, "-vf", "fps=2,scale=216:384", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    fr = []
    try: fnt = ImageFont.truetype("arial.ttf", 22)
    except OSError: fnt = ImageFont.load_default()
    while True:
        b = p.stdout.read(216 * 384 * 3)
        if len(b) < 216 * 384 * 3: break
        im = Image.frombytes("RGB", (216, 384), b); d = ImageDraw.Draw(im)
        d.rectangle((0, 0, 70, 28), fill=(0, 0, 0)); d.text((4, 2), f"{len(fr) / 2:.1f}", fill=(255, 255, 0), font=fnt)
        fr.append(im)
    per = 40
    for s in range(0, len(fr), per):
        sh = Image.new("RGB", (216 * 10, 384 * 4))
        for k, im in enumerate(fr[s:s + per]): sh.paste(im, (216 * (k % 10), 384 * (k // 10)))
        sh.save(os.path.join(qd, f"sheet_{s // per + 1:02d}.jpg"), quality=80)

    issues.sort()
    lines = [f"{t:6.2f}s  {k:14s} {m}" for t, k, m in issues] or ["no automatic issues found"]
    lines.append(f"\n{len(fr)} frames in {-(-len(fr) // per)} sheets: {qd}  <- review EVERY sheet before delivering")
    open(os.path.join(reel, "build", "qa.txt"), "w", encoding="utf-8").write("\n".join(lines))
    print("QA:\n" + "\n".join(lines))
    return issues


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
