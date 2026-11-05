"""Generate an AI scene of Jorge from reference photos with Gemini image editing.

Usage: python gen_scene.py <out.png> "<scene prompt>" [--model gemini-3-pro-image] [--refs a.jpg b.jpg]
Reference photos default to D:/Carousels/_source-photos/*. Output is 4:5 (1080x1350 friendly).
"""
import argparse, base64, glob, io, json, os, sys, urllib.request
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
KEY = open(os.path.join(HERE, ".gemini_key")).read().strip()
REF_DIR = "D:/Carousels/_source-photos"

# Front-facing refs only: the two side-profile photos pulled the nose narrow/pointed (Jorge flagged it 2026-11-05).
DEFAULT_REFS = ["10C89F39-A053-4860-981F-E24E2B709092.png", "IMG_0943_00.jpeg"]
IDENTITY = ("Use the man in the reference photos as the subject. Keep his face, hairline, beard, skin tone, "
            "eye color and build exactly as in the references; it must be clearly recognizable as the same person. "
            "Copy his NOSE exactly: medium-wide with a soft, rounded, slightly bulbous tip and wide nostrils, straight "
            "bridge - never narrow, pointed or slim. Fuller round cheeks; do not beautify or slim his face. "
            "Photorealistic, natural lighting, shot on a modern phone or DSLR, no text, no logos, no watermarks. "
            "Vertical 4:5 photo that fills the entire frame edge to edge (no borders, blank areas or empty bands). "
            "Keep his head below the top third so the upper area is calm real background (wall, sky) that can sit under headline text.")


def b64img(path, max_side=1280):
    im = Image.open(path).convert("RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=90)
    return {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}}


def generate(prompt, out, model="gemini-3-pro-image", refs=None):
    refs = refs or [os.path.join(REF_DIR, f) for f in DEFAULT_REFS]
    parts = [b64img(r) for r in refs] + [{"text": f"{IDENTITY}\n\nScene: {prompt}"}]
    body = {"contents": [{"parts": parts}],
            "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "4:5", **({"imageSize": "2K"} if "pro" in model else {})}}}
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": KEY})
    try:
        res = json.load(urllib.request.urlopen(req, timeout=180))
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode()[:600]}")
    for c in res.get("candidates", []):
        for p in c.get("content", {}).get("parts", []):
            d = p.get("inline_data") or p.get("inlineData")
            if d:
                os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
                open(out, "wb").write(base64.b64decode(d["data"]))
                from trim import trim
                cut = trim(out)
                if any(cut):
                    print("trimmed padding band (top, bottom px):", cut)
                print("saved", out); return out
    sys.exit("no image returned: " + json.dumps(res)[:600])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("prompt")
    ap.add_argument("--model", default="gemini-3-pro-image"); ap.add_argument("--refs", nargs="*")
    a = ap.parse_args()
    generate(a.prompt, a.out, a.model, a.refs)
