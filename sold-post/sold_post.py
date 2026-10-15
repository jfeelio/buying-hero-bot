"""BH Properties "SOLD" social post: property photo + hanging SOLD sign + Jorge headshot + deal numbers.

  python sold_post.py <post_dir> --price 500000 --spread 220000 [--headline auto|"..."] [--area "Miami-Dade"]
                      [--sign left|right] [--photo property.png] [--headshot D:/Brand/jorge_headshot.png]

Writes <post_dir>/sold_post.png (1080x1350, Instagram 4:5) and post.json (settings, used for headline rotation).
"""
import argparse, glob, json, os
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "..", "reel-editor", "fonts")
POSTS = "D:/Posts"
BRAND = "BH PROPERTIES"   # Jorge's DBA for the buyer side + the channel (not "Buying Hero"); logo pending
# Rotated so the feed never shows the same line twice in a row (see `--headline auto`)
HEADLINES = [
    "Another investor just got the keys.",
    "Another BH deal. Closed.",
    "Off-market. Under value. Closed.",
    "Bought right. Closed fast.",
    "Our investors don't chase deals. We bring them.",
    "One more off-market win for our buyers.",
]
BLUE, BLACK, WHITE, GRAY = (0, 131, 202), (8, 10, 12), (255, 255, 255), (150, 156, 162)


def font(size, weight="Black"):
    return ImageFont.truetype(os.path.join(FONTS, f"Montserrat-{weight}.ttf"), size)


def trim_dark_border(im, thresh=45):
    """Screenshots of photos often carry a black frame; cut rows/cols that are mostly near-black."""
    g = ImageOps.grayscale(im)
    w, h = g.size
    px = g.load()

    def dark_row(y): return sum(px[x, y] < thresh for x in range(0, w, 4)) > 0.85 * (w / 4)
    def dark_col(x): return sum(px[x, y] < thresh for y in range(0, h, 4)) > 0.85 * (h / 4)
    t, b, l, r = 0, h - 1, 0, w - 1
    while t < h // 4 and dark_row(t): t += 1
    while b > 3 * h // 4 and dark_row(b): b -= 1
    while l < w // 4 and dark_col(l): l += 1
    while r > 3 * w // 4 and dark_col(r): r -= 1
    pad = 4   # anti-aliased frame edge
    return im.crop((l + pad, t + pad, r - pad, b - pad))


def cover(im, w, h, focus_y=0.5):
    s = max(w / im.width, h / im.height)
    im = im.resize((int(im.width * s + 0.5), int(im.height * s + 0.5)), Image.LANCZOS)
    x = (im.width - w) // 2
    y = int((im.height - h) * focus_y)
    return im.crop((x, y, x + w, y + h))


def hanging_sign(scale=1.0):
    """Classic real-estate post-and-arm sign with a BRAND rider and a big SOLD panel."""
    S = lambda v: int(v * scale)
    W, H = S(420), S(560)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    post_x, arm_y = S(30), S(40)
    # post + arm (white with a soft shadow line)
    d.rectangle((post_x, arm_y, post_x + S(26), H), fill=(245, 245, 245), outline=(180, 180, 180), width=2)
    d.rectangle((post_x, arm_y, W - S(10), arm_y + S(22)), fill=(245, 245, 245), outline=(180, 180, 180), width=2)
    d.ellipse((post_x - S(4), arm_y - S(14), post_x + S(30), arm_y + S(14)), fill=(245, 245, 245))
    # chains
    sx0, sx1, sy = S(120), S(380), S(130)
    for cx in (sx0 + S(30), sx1 - S(30)):
        for k in range(5):
            y = arm_y + S(22) + k * S(14)
            d.ellipse((cx - S(5), y, cx + S(5), y + S(12)), outline=(90, 90, 90), width=max(2, S(3)))
    # rider (brand bar) + main panel
    d.rounded_rectangle((sx0, sy, sx1, sy + S(58)), S(8), fill=BLUE, outline=WHITE, width=S(4))
    def fit(text, size, room):
        while font(size).getlength(text) > room and size > 10:
            size -= 2
        return font(size)
    inner = sx1 - sx0
    d.text(((sx0 + sx1) // 2, sy + S(30)), BRAND, font=fit(BRAND, S(34), inner - S(36)),
           fill=WHITE, anchor="mm")
    py0 = sy + S(66)
    d.rounded_rectangle((sx0, py0, sx1, py0 + S(170)), S(10), fill=WHITE, outline=BLUE, width=S(8))
    d.text(((sx0 + sx1) // 2, py0 + S(88)), "SOLD", font=fit("SOLD", S(104), inner - S(56)), fill=BLUE, anchor="mm")
    return im


def avatar(path, size):
    im = Image.open(path).convert("RGB")
    im = trim_dark_border(im)
    side = int(min(im.width, im.height) * 0.78)          # tighter on the face
    cx, cy = im.width // 2, int(im.height * 0.46)
    im = im.crop((cx - side // 2, cy - side // 2, cx + side // 2, cy + side // 2)).resize((size, size), Image.LANCZOS)
    ring = 10
    out = Image.new("RGBA", (size + 4 * ring, size + 4 * ring), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    d.ellipse((0, 0, out.width - 1, out.height - 1), fill=BLUE)
    d.ellipse((ring, ring, out.width - 1 - ring, out.height - 1 - ring), fill=WHITE)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    out.paste(im, (2 * ring, 2 * ring), mask)
    return out


def money(v):
    v = float(v)
    return f"${v / 1e6:.2f}M".replace(".00M", "M") if v >= 1e6 else f"${v:,.0f}"


def compose(args, W, H, photo_h):
    canvas = Image.new("RGB", (W, H), BLACK)
    photo = trim_dark_border(Image.open(os.path.join(args.post_dir, args.photo)).convert("RGB"))
    canvas.paste(cover(photo, W, photo_h, 0.35), (0, 0))
    # fade photo into the panel
    grad = Image.new("L", (1, 220))
    for y in range(220):
        grad.putpixel((0, y), int(255 * (y / 219) ** 1.6))
    canvas.paste(Image.new("RGB", (W, 220), BLACK), (0, photo_h - 220), grad.resize((W, 220)))

    # SOLD sign standing in the yard
    sign = hanging_sign(1.0 if W == 1080 else 1.0)
    sx = 40 if args.sign == "left" else W - sign.width - 40
    sy = photo_h - sign.height - 120
    shadow = Image.new("RGBA", sign.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 110), mask=sign.getchannel("A"))
    canvas.paste(shadow.filter(ImageFilter.GaussianBlur(8)), (sx + 10, sy + 12), shadow.filter(ImageFilter.GaussianBlur(8)))
    canvas.paste(sign, (sx, sy), sign)

    d = ImageDraw.Draw(canvas)
    # headshot on the seam, opposite the sign
    av = avatar(args.headshot, 210)
    ax = W - av.width - 50 if args.sign == "left" else 50
    ay = photo_h - av.height // 2 - 30
    canvas.paste(av, (ax, ay), av)

    # numbers
    y = photo_h + 30
    left = 60
    d.text((left, y), "SOLD FOR", font=font(36, "ExtraBold"), fill=GRAY)
    d.text((left, y + 44), money(args.price), font=font(108), fill=WHITE)
    y2 = y + 190
    d.text((left, y2), "EQUITY SPREAD FOR OUR INVESTOR", font=font(36, "ExtraBold"), fill=GRAY)
    d.text((left, y2 + 44), money(args.spread), font=font(108), fill=BLUE)

    # headline + footer
    hy = y2 + 190
    hf = font(52)
    while hf.getlength(args.headline.upper()) > W - 2 * left and hf.size > 30:
        hf = font(hf.size - 2)
    d.text((left, hy), args.headline.upper(), font=hf, fill=WHITE)
    d.line((left, H - 92, W - left, H - 92), fill=(40, 44, 48), width=2)
    d.text((left, H - 50), BRAND, font=font(38), fill=BLUE, anchor="lm")
    d.text((W - left, H - 50), f"Off-market deals · {args.area}", font=font(30, "ExtraBold"), fill=GRAY, anchor="rm")
    return canvas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("post_dir")
    ap.add_argument("--price", required=True)
    ap.add_argument("--spread", required=True)
    ap.add_argument("--headline", default="auto", help='"auto" = least-recently used line from HEADLINES')
    ap.add_argument("--area", default="Miami-Dade")
    ap.add_argument("--sign", default="left", choices=["left", "right"])
    ap.add_argument("--photo", default="property.png")
    ap.add_argument("--headshot", default="D:/Brand/jorge_headshot.png")
    a = ap.parse_args()
    if a.headline == "auto":
        used = []
        for f in sorted(glob.glob(os.path.join(POSTS, "*", "post.json"))):
            if os.path.dirname(os.path.abspath(f)) != os.path.abspath(a.post_dir):
                used.append(json.load(open(f, encoding="utf-8")).get("headline"))
        # never-used lines first (in list order), then the one used longest ago
        last_use = {h: i for i, h in enumerate(used)}
        a.headline = min(HEADLINES, key=lambda h: (last_use.get(h, -1), HEADLINES.index(h)))
    feed = compose(a, 1080, 1350, 760)
    feed.save(os.path.join(a.post_dir, "sold_post.png"))
    json.dump(vars(a), open(os.path.join(a.post_dir, "post.json"), "w", encoding="utf-8"), indent=1)
    print(os.path.join(a.post_dir, "sold_post.png"))


if __name__ == "__main__":
    main()
