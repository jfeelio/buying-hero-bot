"""Render an Instagram carousel (1080x1350 slides) from <carousel_dir>/slides.json.

Usage: python render.py <carousel_dir>      -> <carousel_dir>/output/slide_01.png ... + contact.jpg

slides.json: {"slides": [ {type, ...}, ... ]}. Text supports *blue highlight* markup and \\n line breaks.
Types:
  photo      bg (path rel. to dir), title, body?, kicker?, pos: top|bottom (text placement), swipe?: true
  text       num?, kicker?, title, body?, inset? (image path)
  stats      kicker?, title, rows: [[label, value], ...]  (last row = hero, blue)
  checklist  kicker?, title, items: [...]
  cta        title, body?
"""
import json, os, sys
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from PIL import ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "..", "reel-editor", "fonts")
HEADSHOT = "D:/Brand/jorge_headshot.png"
HANDLE = "@jorgesiverio.rei"
BRAND = "BH PROPERTIES"

W, H = 1080, 1350
M = 84                                   # side margin
NAVY = (11, 18, 34)
NAVY2 = (20, 32, 56)
BLUE = (0, 131, 202)
WHITE = (255, 255, 255)
SOFT = (196, 205, 220)
DIM = (120, 134, 158)


def F(size, w="Black"):
    if w in ("Black", "ExtraBold"):
        return ImageFont.truetype(os.path.join(FONTS, f"Montserrat-{w}.ttf"), size)
    return ImageFont.truetype({"Body": "C:/Windows/Fonts/segoeui.ttf",
                               "BodyBold": "C:/Windows/Fonts/segoeuib.ttf"}[w], size)


# ---------- rich text: *highlight* -> blue ----------
def tokens(text):
    out, hi = [], False
    for line_i, line in enumerate(text.split("\n")):
        if line_i:
            out.append(("\n", hi))
        for word in line.split(" "):
            if not word:
                continue
            if word.startswith("*"):
                hi = True
            end = "*" in word.lstrip("*")
            out.append((word.replace("*", ""), hi))
            if end:
                hi = False
    return out


def layout(text, font, width):
    lines, cur, cur_w = [], [], 0
    space = font.getlength(" ")
    for w, hi in tokens(text):
        if w == "\n":
            lines.append(cur); cur, cur_w = [], 0; continue
        lw = font.getlength(w)
        if cur and cur_w + space + lw > width:
            lines.append(cur); cur, cur_w = [], 0
        cur_w += (space if cur else 0) + lw
        cur.append((w, hi))
    if cur:
        lines.append(cur)
    return lines


def fit(text, width, max_h, start, minimum, w="Black", lh=1.08):
    size = start
    while size > minimum:
        f = F(size, w)
        if len(layout(text, f, width)) * size * lh <= max_h:
            return f, size
        size -= 2
    return F(minimum, w), minimum


def draw_rich(d, text, x, y, font, size, width, color=WHITE, hi=BLUE, lh=1.08, align="left", shadow=False, pill=False):
    lines = layout(text, font, width)
    space = font.getlength(" ")
    for ln in lines:
        lw = sum(font.getlength(w) for w, _ in ln) + space * (len(ln) - 1)
        cx = x + (width - lw) / 2 if align == "center" else x
        if pill:   # one blue box behind each run of highlighted words
            runs, k = [], 0
            px = cx
            for w, h in ln:
                ww = font.getlength(w)
                if h:
                    if runs and runs[-1][2]:
                        runs[-1][1] = px + ww
                    else:
                        runs.append([px, px + ww, True])
                elif runs:
                    runs[-1][2] = False
                px += ww + space
            for x0, x1, _ in runs:
                d.rounded_rectangle((x0 - 14, y + size * 0.06, x1 + 14, y + size * 1.06), int(size * 0.16), fill=BLUE)
        for w, h in ln:
            if pill and h:
                d.text((cx, y), w, font=font, fill=WHITE)
                cx += font.getlength(w) + space
                continue
            if shadow:
                d.text((cx + 3, y + 3), w, font=font, fill=(0, 0, 0, 160))
            d.text((cx, y), w, font=font, fill=hi if h else color)
            cx += font.getlength(w) + space
        y += size * lh
    return y


# ---------- helpers ----------
def cover(path, w=W, h=H):
    return ImageOps.fit(Image.open(path).convert("RGB"), (w, h), Image.LANCZOS, centering=(0.5, 0.4))


def gradient(img, pos, strength=235, reach=0.62):
    g = Image.new("L", (1, H))
    for yy in range(H):
        t = (yy / H) if pos == "bottom" else (1 - yy / H)
        a = max(0.0, (t - (1 - reach)) / reach)
        g.putpixel((0, yy), int(strength * a ** 1.3))
    shade = Image.new("RGB", (W, H), (5, 9, 18))
    return Image.composite(shade, img, g.resize((W, H)))


def circle(path, d):
    im = ImageOps.fit(Image.open(path).convert("RGB"), (d, d), Image.LANCZOS, centering=(0.5, 0.35))
    mask = Image.new("L", (d * 4, d * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, d * 4, d * 4), fill=255)
    out = Image.new("RGBA", (d, d)); out.paste(im, (0, 0), mask.resize((d, d), Image.LANCZOS))
    return out


def chrome(img, i, n, dark=True, swipe=False):
    d = ImageDraw.Draw(img, "RGBA")
    # top: brand + page counter
    d.text((M, 64), BRAND, font=F(24, "ExtraBold"), fill=(*WHITE, 230), anchor="lm")
    d.rectangle((M, 84, M + 46, 89), fill=BLUE)
    d.text((W - M, 64), f"{i}/{n}", font=F(24, "ExtraBold"), fill=(*WHITE, 200), anchor="rm")
    # bottom: mini headshot + handle, swipe hint
    av = circle(HEADSHOT, 56)
    img.paste(av, (M, H - 96), av)
    d.text((M + 72, H - 68), HANDLE, font=F(26, "BodyBold"), fill=(*WHITE, 235), anchor="lm")
    if swipe:
        d.rounded_rectangle((W - M - 190, H - 96, W - M, H - 40), 28, fill=BLUE)
        d.text((W - M - 95, H - 68), "SWIPE  →", font=F(24, "ExtraBold"), fill=WHITE, anchor="mm")
    elif i < n:
        d.text((W - M, H - 68), "→", font=F(40, "Black"), fill=(*BLUE, 255), anchor="rm")


def navy_bg():
    img = Image.new("RGB", (W, H), NAVY)
    glow = Image.new("RGB", (W, H), NAVY)
    ImageDraw.Draw(glow).ellipse((W - 520, -380, W + 380, 420), fill=NAVY2)
    return Image.blend(img, glow.filter(ImageFilter.GaussianBlur(160)), 1.0)


# ---------- slide types ----------
def s_photo(s, base):
    pos = s.get("pos", "top")
    img = gradient(cover(os.path.join(base, s["bg"])), pos, reach=s.get("reach", 0.6))
    img = gradient(img, "bottom" if pos == "top" else "top", strength=170, reach=0.16)
    d = ImageDraw.Draw(img, "RGBA")
    tw = W - 2 * M
    f, size = fit(s["title"], tw, s.get("max_h", 430), s.get("size", 96), 52)
    kf = F(34, "Black")
    bf = F(38, "BodyBold")
    body_h = len(layout(s.get("body", ""), bf, tw)) * 38 * 1.3 if s.get("body") else 0
    title_h = len(layout(s["title"], f, tw)) * size * 1.08
    k_h = 70 if s.get("kicker") else 0
    y = 150 if pos == "top" else H - 150 - title_h - body_h - k_h - (24 if body_h else 0)
    if s.get("kicker"):
        kt = s["kicker"].upper()
        d.rounded_rectangle((M, y, M + kf.getlength(kt) + 36, y + 56), 12, fill=BLUE)
        d.text((M + 18, y + 28), kt, font=kf, fill=WHITE, anchor="lm"); y += k_h
    y = draw_rich(d, s["title"], M, y, f, size, tw, shadow=True, pill=True)
    if s.get("body"):
        draw_rich(d, s["body"], M, y + 24, bf, 38, tw, color=SOFT, lh=1.3, shadow=True)
    return img


def block_h(text, font, size, width, lh):
    return len(layout(text, font, width)) * size * lh


def s_text(s, base):
    img = navy_bg()
    d = ImageDraw.Draw(img, "RGBA")
    tw = W - 2 * M
    inset_h = 430 if s.get("inset") else 0
    top, bottom = 150, H - 160 - (inset_h + 40 if inset_h else 0)
    num_h = 230 if s.get("num") else 0
    k_h = 64 if s.get("kicker") else 0
    room = bottom - top - num_h - k_h
    has_body = bool(s.get("body"))
    f, size = fit(s["title"], tw, room * (0.5 if has_body else 0.9), s.get("size", 112), 56)
    th = block_h(s["title"], f, size, tw, 1.08)
    bh, bf, bsize = 0, None, 0
    if has_body:
        bf, bsize = fit(s["body"], tw, room - th - 40, 46, 30, "Body", 1.32)
        bh = block_h(s["body"], bf, bsize, tw, 1.32) + 40
    total = num_h + k_h + th + bh
    y = top + max(0, (bottom - top - total) / 2 - 30)
    if s.get("num"):
        d.text((M - 6, y - 40), f"{int(s['num']):02d}", font=F(210, "Black"), fill=BLUE)
        y += num_h
    if s.get("kicker"):
        d.text((M, y), s["kicker"].upper(), font=F(32, "ExtraBold"), fill=BLUE); y += k_h
    y = draw_rich(d, s["title"], M, y, f, size, tw)
    if has_body:
        draw_rich(d, s["body"], M, y + 40, bf, bsize, tw, color=SOFT, lh=1.32)
    if s.get("inset"):
        im = cover(os.path.join(base, s["inset"]), tw, inset_h)
        mask = Image.new("L", (tw, inset_h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, tw, inset_h), 28, fill=255)
        img.paste(im, (M, H - 150 - inset_h), mask)
    return img


def s_stats(s, base):
    img = navy_bg()
    d = ImageDraw.Draw(img, "RGBA")
    tw = W - 2 * M
    rows = s["rows"]
    f, size = fit(s["title"], tw, 220, 96, 48)
    total = (64 if s.get("kicker") else 0) + block_h(s["title"], f, size, tw, 1.08) + 50 + 180 * (len(rows) - 1) + 240
    y = 150 + max(0, (H - 310 - total) / 2)
    if s.get("kicker"):
        d.text((M, y), s["kicker"].upper(), font=F(32, "ExtraBold"), fill=BLUE); y += 64
    y = draw_rich(d, s["title"], M, y, f, size, tw) + 50
    for k, (label, value) in enumerate(rows):
        hero = k == len(rows) - 1
        if hero:
            d.rounded_rectangle((M - 20, y - 10, W - M + 20, y + 230), 30, fill=BLUE)
            d.text((M + 14, y + 24), label.upper(), font=F(30, "ExtraBold"), fill=WHITE)
            d.text((M + 10, y + 70), value, font=F(124, "Black"), fill=WHITE)
            y += 260
        else:
            d.text((M, y), label.upper(), font=F(28, "ExtraBold"), fill=DIM)
            d.text((M, y + 38), value, font=F(84, "Black"), fill=WHITE)
            d.line((M, y + 150, W - M, y + 150), fill=(*WHITE, 40), width=2)
            y += 180
    return img


def s_checklist(s, base):
    img = navy_bg()
    d = ImageDraw.Draw(img, "RGBA")
    tw = W - 2 * M
    items = s["items"]
    f, size = fit(s["title"], tw, 260, 96, 46)
    step = 130
    total = (64 if s.get("kicker") else 0) + block_h(s["title"], f, size, tw, 1.08) + 60 + step * len(items)
    y = 150 + max(0, (H - 310 - total) / 2)
    if s.get("kicker"):
        d.text((M, y), s["kicker"].upper(), font=F(32, "ExtraBold"), fill=BLUE); y += 64
    y = draw_rich(d, s["title"], M, y, f, size, tw) + 60
    itf, isz = fit(max(items, key=len), tw - 110, step - 40, 42, 26, "BodyBold", 1.2)
    for it in items:
        d.rounded_rectangle((M, y + 4, M + 60, y + 64), 14, fill=BLUE)
        d.line([(M + 15, y + 35), (M + 26, y + 47), (M + 46, y + 21)], fill=WHITE, width=7, joint="curve")
        draw_rich(d, it, M + 90, y + 6, itf, isz, tw - 90, lh=1.2)
        y += step
    return img


def s_cta(s, base):
    img = navy_bg()
    d = ImageDraw.Draw(img, "RGBA")
    tw = W - 2 * M
    dia = 300
    ring = Image.new("RGBA", (dia + 24, dia + 24))
    ImageDraw.Draw(ring).ellipse((0, 0, dia + 23, dia + 23), fill=BLUE)
    img.paste(ring, ((W - dia - 24) // 2, 170), ring)
    av = circle(HEADSHOT, dia)
    img.paste(av, ((W - dia) // 2, 182), av)
    y = 170 + dia + 90
    f, size = fit(s["title"], tw, 260, 104, 60)
    y = draw_rich(d, s["title"], M, y, f, size, tw, align="center") + 20
    if s.get("body"):
        bf, bsize = fit(s["body"], tw, 220, 44, 30, "BodyBold", 1.3)
        draw_rich(d, s["body"], M, y, bf, bsize, tw, color=SOFT, lh=1.3, align="center")
    return img


TYPES = {"photo": s_photo, "text": s_text, "stats": s_stats, "checklist": s_checklist, "cta": s_cta}


def render(base):
    spec = json.load(open(os.path.join(base, "slides.json"), encoding="utf-8"))
    slides = spec["slides"]
    out = os.path.join(base, "output")
    os.makedirs(out, exist_ok=True)
    for f in os.listdir(out):
        if f.startswith("slide_"):
            os.remove(os.path.join(out, f))
    paths = []
    for i, s in enumerate(slides, 1):
        img = TYPES[s["type"]](s, base).convert("RGB")
        chrome(img, i, len(slides), swipe=s.get("swipe", i == 1))
        p = os.path.join(out, f"slide_{i:02d}.png")
        img.save(p); paths.append(p)
    # contact sheet for review
    tw, th, cols = 360, 450, 5
    rows = (len(paths) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw + (cols + 1) * 12, rows * th + (rows + 1) * 12), (230, 230, 230))
    for k, p in enumerate(paths):
        sheet.paste(Image.open(p).resize((tw, th)), (12 + (k % cols) * (tw + 12), 12 + (k // cols) * (th + 12)))
    sheet.save(os.path.join(out, "contact.jpg"), quality=88)
    print(f"rendered {len(paths)} slides -> {out}")


if __name__ == "__main__":
    render(sys.argv[1])
