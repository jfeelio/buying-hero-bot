"""Premium style: mixed-typography kinetic captions + big words BEHIND the speaker + light grade.

  python premium.py <reel_dir> <clean.mp4> <out.mp4>

<clean.mp4> is render.py's output with no captions/lists (render.build(..., premium=True)) — it already has
B-roll, cards, zooms, music and SFX. This pass cuts the speaker out of every frame (Robust Video Matting,
ONNX on CPU, ~9 fps, cached in build/matte.mp4), draws hero words between background and speaker, then
draws captions in front. Audio is copied from the clean render.

edit.json "premium" block (word indices from `reel.py words`):
  key:     [i, ...]   bold brand-blue UPPERCASE word (default: edit.json "emphasis")
  serif:   [i, ...]   elegant white serif italic word        serif_blue: [i, ...] same, brand blue
  big:     [i, ...]   oversized serif word (shown alone, e.g. "meditation.")
  breaks:  [i, ...]   force a new caption chunk to start at word i
  lists:   [{"words": [i, ...]}]    each word whips in big, one at a time, alternating Anton / serif
  heroes:  [{"lines": [{"text": "HOARDER", "word": 21}, ...], "x_at"?: 6.85, "glitch"?: true,
             "end"?: secs, "color"?: "white"|"blue" per line}]
           big Anton words BEHIND the speaker; stacked lines; each line enters at its word.
           Stays up >= HOLD s after the last line (Jorge 11/17: "doesn't stay long enough").
           x_at draws a red X (also behind him). Keep heroes white — blue vanishes on sky/water.
  grade:   "light" (default) | "none"
Words used by heroes/lists are not repeated as captions.
"""
import json, math, os, subprocess, sys, urllib.request
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from captions import tokens
from render import ffmpeg_bin

W, H, FPS = 1080, 1920, 30
BLUE = (0, 131, 202)
BLUE_HI = (38, 163, 240)   # brighter brand blue for small text over dark clothing/grass
WHITE = (255, 255, 255)
RED = (229, 57, 53)
FONTS = os.path.join(HERE, "fonts")
CAP_Y = 1300               # caption top; Jorge-approved height (don't move up for IG overlay)
LIST_Y = 1290
HOLD = 1.9
GRADES = {
    "light": ("eq=contrast=1.04:saturation=1.12:brightness=0.015,"
              "colorbalance=rs=0.02:bs=-0.03:rh=0.02:bh=-0.02,vignette=angle=PI/9"),
    "none": "null",
}
RVM_URL = "https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3_fp32.onnx"
RVM = os.path.join(HERE, ".cache", "rvm_mobilenetv3_fp32.onnx")

# ------------------------------------------------------------------ type
_fc = {}
def font(name, size):
    k = (name, size)
    if k not in _fc:
        if name == "serif":
            f = ImageFont.truetype(os.path.join(FONTS, "PlayfairItalic.ttf"), size); f.set_variation_by_name("Black Italic")
        elif name == "anton":
            f = ImageFont.truetype(os.path.join(FONTS, "Anton.ttf"), size)
        elif name == "black":
            f = ImageFont.truetype(os.path.join(FONTS, "Montserrat-Black.ttf"), size)
        else:
            f = ImageFont.truetype(os.path.join(FONTS, "Montserrat-ExtraBold.ttf"), size)
        _fc[k] = f
    return _fc[k]

STY = {  # font, size, color, uppercase
    "base": ("bold", 84, WHITE, False),
    "key": ("black", 92, BLUE_HI, True),
    "serif": ("serif", 114, WHITE, False),
    "serif_blue": ("serif", 114, BLUE_HI, False),
    "big": ("serif", 170, WHITE, False),
}

def text_img(text, fnt, color, shadow=170, blur=9, sy=6):
    """RGBA text with a soft drop shadow -> (img, baseline_y, pad)."""
    pad = blur * 3 + 10
    x0, y0, x1, y1 = fnt.getbbox(text, anchor="ls")
    w, h = (x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad
    base = pad - y0
    def draw(fill):
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((pad - x0, base), text, font=fnt, fill=fill, anchor="ls")
        return im
    txt = draw(color + (255,))
    if not shadow:
        return txt, base, pad
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.alpha_composite(draw((0, 0, 0, shadow)).filter(ImageFilter.GaussianBlur(blur)), (0, sy))
    out.alpha_composite(txt)
    return out, base, pad

def fit_size(text, name, width, start=420):
    s = start
    while s > 20:
        x0, _, x1, _ = font(name, s).getbbox(text, anchor="ls")
        if x1 - x0 <= width: return s
        s -= 4
    return s

def paste(layer, im, x, y, alpha=1.0):
    x, y = int(round(x)), int(round(y))
    if alpha <= 0: return
    if alpha < 1:
        im = im.copy(); im.putalpha(im.getchannel("A").point(lambda v: int(v * alpha)))
    sx, sy = max(0, -x), max(0, -y)
    if sx >= im.width or sy >= im.height: return
    im = im.crop((sx, sy, im.width, im.height)); x, y = max(x, 0), max(y, 0)
    if x >= layer.width or y >= layer.height: return
    layer.alpha_composite(im.crop((0, 0, min(im.width, layer.width - x), min(im.height, layer.height - y))), (x, y))

def ease_out(p): p = min(max(p, 0), 1); return 1 - (1 - p) ** 3
def spring(t, k=14, w=20): return 1 - math.exp(-t * k) * math.cos(t * w) if t > 0 else 0

def xform(im, scale=1.0, blur=0.0):
    if abs(scale - 1) > 0.005:
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.BICUBIC)
    return im.filter(ImageFilter.GaussianBlur(blur)) if blur > 0.4 else im

def chroma(im, off):
    r, g, b, a = im.split(); z = Image.new("L", im.size, 0)
    out = Image.new("RGBA", (im.width + 2 * off, im.height), (0, 0, 0, 0))
    out.alpha_composite(Image.merge("RGBA", (r, z, z, a)), (0, 0))
    out.alpha_composite(Image.merge("RGBA", (z, z, b, a)), (2 * off, 0))
    out.alpha_composite(im, (off, 0))
    return out

# ------------------------------------------------------------------ matte
def ensure_model():
    if not os.path.exists(RVM):
        os.makedirs(os.path.dirname(RVM), exist_ok=True)
        print("downloading RVM matting model (15 MB)...")
        urllib.request.urlretrieve(RVM_URL, RVM)

def make_matte(src, out):
    import onnxruntime as ort
    ensure_model()
    sess = ort.InferenceSession(RVM, providers=["CPUExecutionProvider"])
    dec = subprocess.Popen([ffmpeg_bin(), "-v", "error", "-i", src, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                           stdout=subprocess.PIPE)
    enc = subprocess.Popen([ffmpeg_bin(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", out],
                           stdin=subprocess.PIPE)
    zero = [np.zeros([1, 1, 1, 1], np.float32)] * 4
    rec, ds, prev, n = zero, np.array([0.25], np.float32), None, 0
    while True:
        buf = dec.stdout.read(W * H * 3)
        if len(buf) < W * H * 3: break
        f = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
        small = f[::8, ::8].astype(np.int16)
        if prev is not None and np.abs(small - prev).mean() > 40:   # hard cut -> reset recurrent state
            rec = zero
        prev = small
        x = (f.astype(np.float32) / 255).transpose(2, 0, 1)[None]
        _, pha, *rec = sess.run([], {"src": x, "r1i": rec[0], "r2i": rec[1], "r3i": rec[2], "r4i": rec[3],
                                     "downsample_ratio": ds})
        enc.stdin.write((pha[0, 0] * 255).clip(0, 255).astype(np.uint8).tobytes())
        n += 1
        if n % 300 == 0: print(f"  matte {n} frames", flush=True)
    enc.stdin.close(); enc.wait(); dec.kill()

# ------------------------------------------------------------------ build spec
def plan(reel):
    edit = json.load(open(os.path.join(reel, "edit.json"), encoding="utf-8"))
    words = json.load(open(os.path.join(reel, "words.json"), encoding="utf-8"))["words"]
    p = edit.get("premium", {})
    toks = tokens(words, edit)
    tok_at = {t["i"]: t for t in toks}
    def ts(i): return tok_at[i]["s"] if i in tok_at else words[i]["s"]
    def te(i): return tok_at[i]["e"] if i in tok_at else words[i]["e"]

    style = {i: "key" for i in p.get("key", edit.get("emphasis", []))}
    for k in ("serif", "serif_blue", "big"):
        for i in p.get(k, []): style[i] = k

    heroes = []
    for h in p.get("heroes", []):
        lines = []
        for ln in h["lines"]:
            col = BLUE if ln.get("color") == "blue" else WHITE
            n = len(h["lines"])
            size = min(fit_size(ln["text"], "anton", 1000 if n == 1 or len(ln["text"]) > 5 else 760), 420)
            im, _, _ = text_img(ln["text"], font("anton", size), col, shadow=110, blur=22, sy=10)
            lines.append(dict(im=im, start=ts(ln["word"]), word=ln["word"]))
        heroes.append(dict(imgs=lines, start=lines[0]["start"], end=h.get("end", te(lines[-1]["word"]) + 0.15),
                           x_at=h.get("x_at"), glitch=h.get("glitch", False), gap=h.get("gap", -16), y=None))
    heroes.sort(key=lambda h: h["start"])
    for k, h in enumerate(heroes):
        nxt = heroes[k + 1]["start"] - 0.25 if k + 1 < len(heroes) else 1e9
        h["end"] = min(max(h["end"], h["imgs"][-1]["start"] + HOLD), nxt)

    lists = []
    for L in p.get("lists", []):
        ws = L["words"]
        for k, i in enumerate(ws):
            t = tok_at.get(i, words[i])["w"].strip(",.")
            if k % 2 == 0: im, _, _ = text_img(t.upper(), font("anton", 150), WHITE, blur=12)
            else: im, _, _ = text_img(t.capitalize(), font("serif", 140), WHITE, shadow=190, blur=12)
            end = ts(ws[k + 1]) if k + 1 < len(ws) else te(i) + 0.05
            lists.append(dict(im=im, start=ts(i), end=end, side=1 if k % 2 else -1))

    hidden = {ln["word"] for h in p.get("heroes", []) for ln in h["lines"]}
    hidden |= {i for L in p.get("lists", []) for i in L["words"]}
    # words between list items ("the") are hidden too, so the list reads clean
    for L in p.get("lists", []):
        hidden |= set(range(min(L["words"]), max(L["words"]) + 1))
    breaks = set(p.get("breaks", []))

    # auto-chunk: break after punctuation, before hidden words, on >0.35s gaps, at 5 words, at forced breaks;
    # "big" words always stand alone
    chunks, cur = [], []
    for t in toks:
        i = t["i"]
        if i in hidden:
            if cur: chunks.append(cur); cur = []
            continue
        if cur and (i in breaks or style.get(i) == "big" or style.get(cur[-1]["i"]) == "big"
                    or len(cur) >= 5 or t["s"] - cur[-1]["e"] > 0.35):
            chunks.append(cur); cur = []
        cur.append(t)
        if t["w"].rstrip()[-1:] in ".,?!":
            chunks.append(cur); cur = []
    if cur: chunks.append(cur)

    beats = sorted([h["start"] for h in heroes] + [L["start"] for L in lists])
    out = []
    for n, ch in enumerate(chunks):
        items = []
        for t in ch:
            fname, size, col, up = STY[style.get(t["i"], "base")]
            txt = t["w"].strip()
            im, base, pad = text_img(txt.upper() if up else txt, font(fname, size), col)
            items.append(dict(im=im, base=base, pad=pad, t=t["s"]))
        start, last_e = ch[0]["s"], ch[-1]["e"]
        stops = [chunks[n + 1][0]["s"]] if n + 1 < len(chunks) else []
        stops += [b for b in beats if b > last_e - 0.01]
        end = min([last_e + 0.45] + [s for s in stops if s > start])
        # greedy wrap at 960px
        lines, row, cw = [], [], 0
        for it in items:
            w = it["im"].width - 2 * it["pad"]
            if row and cw + w > 960: lines.append(row); row, cw = [], 0
            row.append(it); cw += w + 22
        lines.append(row)
        y = CAP_Y
        for ln in lines:
            tot = sum(it["im"].width - 2 * it["pad"] for it in ln) + 22 * (len(ln) - 1)
            x, asc = (W - tot) / 2, max(it["base"] - it["pad"] for it in ln)
            for it in ln:
                it["x"] = x - it["pad"]; it["y"] = y + asc - it["base"] + it["pad"]
                x += it["im"].width - 2 * it["pad"] + 22
            y += max(it["im"].height - 2 * it["pad"] for it in ln) + 6
        out.append(dict(start=start, end=end, items=items))

    full = [(o["start"], o["end"]) for o in edit.get("overlays", []) if o.get("mode", "full") == "full"]
    return dict(chunks=out, heroes=heroes, lists=lists, full=full, grade=GRADES[p.get("grade", "light")])

# ------------------------------------------------------------------ draw
def head_top(m):
    rows = np.where((m > 0.5).sum(axis=1) > 6)[0]
    return int(rows[0]) if len(rows) else 500

def draw_hero(behind, h, t, m):
    if not (h["start"] <= t < h["end"]): return
    if h["y"] is None:
        heights = [d["im"].height - 66 + h["gap"] for d in h["imgs"]]
        # block bottom ~100px below the top of the head, so the head occludes the last line
        y = max(120, head_top(m) + 100 - sum(heights)) - 33
        h["ys"] = []
        for hh in heights: h["ys"].append(y); y += hh
        h["y"] = h["ys"][0]
    fade = 1 - ease_out((t - (h["end"] - 0.14)) / 0.14) if t > h["end"] - 0.14 else 1
    for d, y in zip(h["imgs"], h["ys"]):
        dt = t - d["start"]
        if dt < 0: continue
        p = ease_out(dt / 0.35)
        im = xform(d["im"], 1.22 - 0.22 * p, 14 * (1 - p))
        if h["glitch"] and dt < 0.12: im = chroma(im, 14)
        paste(behind, im, (W - im.width) / 2, y + (d["im"].height - im.height) / 2, min(dt / 0.15, 1) * fade)
    if h["x_at"] and t >= h["x_at"]:
        p = ease_out((t - h["x_at"]) / 0.3)
        y0, y1 = h["ys"][0] + 60, h["ys"][-1] + h["imgs"][-1]["im"].height - 90
        x0, x1 = 170, W - 170
        d = ImageDraw.Draw(behind)
        def seg(a, b, q):
            if q > 0: d.line([a, (a[0] + (b[0] - a[0]) * q, a[1] + (b[1] - a[1]) * q)], fill=RED + (int(255 * fade),), width=22)
        seg((x0, y0), (x1, y1), min(p * 2, 1)); seg((x1, y0), (x0, y1), max(p * 2 - 1, 0))

def draw_chunk(front, c, t):
    if not (c["start"] - 0.01 <= t < c["end"]): return
    fade = 1 - (t - (c["end"] - 0.1)) / 0.1 if t > c["end"] - 0.1 else 1
    for it in c["items"]:
        dt = t - it["t"]
        if dt < -0.02: continue
        dt = max(dt, 0)
        im = xform(it["im"], 0.72 + 0.28 * spring(dt))
        cx = it["x"] + it["im"].width / 2
        cy = it["y"] + it["im"].height / 2 + 18 * (1 - ease_out(dt / 0.2))
        paste(front, im, cx - im.width / 2, cy - im.height / 2, min(dt / 0.07, 1) * fade)

def draw_list(front, L, t):
    if not (L["start"] <= t < L["end"]): return
    dt = t - L["start"]; p = ease_out(dt / 0.2)
    im = xform(L["im"], 1.0, 10 * (1 - p))
    paste(front, im, (W - im.width) / 2 + L["side"] * 260 * (1 - p), LIST_Y - im.height / 2, min(dt / 0.08, 1))

# ------------------------------------------------------------------ render
def render(reel, clean, out):
    pl = plan(reel)
    matte = os.path.join(reel, "build", "matte.mp4")
    stamp = matte + ".src"
    sig = f"{os.path.getsize(clean)}"
    if not (os.path.exists(matte) and os.path.exists(stamp) and open(stamp).read() == sig):
        print("cutting the speaker out of every frame (~3 min/min of video)...")
        make_matte(clean, matte)
        open(stamp, "w").write(sig)
    dec = subprocess.Popen([ffmpeg_bin(), "-v", "error", "-i", clean, "-vf", pl["grade"],
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    mdec = subprocess.Popen([ffmpeg_bin(), "-v", "error", "-i", matte, "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                            stdout=subprocess.PIPE)
    enc = subprocess.Popen([ffmpeg_bin(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-i", clean, "-map", "0:v", "-map", "1:a?",
                            "-c:v", "h264_nvenc", "-preset", "p6", "-cq", "19", "-maxrate", "14M", "-bufsize", "28M",
                            "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", "-shortest", out],
                           stdin=subprocess.PIPE)
    n = 0
    while True:
        b = dec.stdout.read(W * H * 3); mb = mdec.stdout.read(W * H)
        if len(b) < W * H * 3 or len(mb) < W * H: break
        t = n / FPS
        g = np.frombuffer(b, np.uint8).reshape(H, W, 3)
        if any(a <= t < e for a, e in pl["full"]):          # full-screen B-roll: nobody to put text behind
            m = np.zeros((H, W), np.float32)
        else:
            m = np.frombuffer(mb, np.uint8).reshape(H, W).astype(np.float32) / 255
        behind = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for h in pl["heroes"]: draw_hero(behind, h, t, m)
        if behind.getbbox():
            bg = Image.fromarray(g).convert("RGBA"); bg.alpha_composite(behind)
            m3 = m[..., None]
            frame = (np.asarray(bg)[..., :3] * (1 - m3) + g * m3).astype(np.uint8)
        else:
            frame = g
        front = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for c in pl["chunks"]: draw_chunk(front, c, t)
        for L in pl["lists"]: draw_list(front, L, t)
        if front.getbbox():
            img = Image.fromarray(frame).convert("RGBA"); img.alpha_composite(front)
            frame = np.asarray(img)[..., :3]
        enc.stdin.write(np.ascontiguousarray(frame).tobytes())
        n += 1
        if n % 300 == 0: print(f"  premium {n} frames", flush=True)
    enc.stdin.close(); enc.wait()
    print(f"rendered -> {out}")
    return out


if __name__ == "__main__":
    render(*sys.argv[1:4])
