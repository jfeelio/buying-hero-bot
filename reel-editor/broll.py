"""Pixabay b-roll search + download (Pixabay Content License: commercial use, no attribution required).

  python broll.py search "signing contract" work/reel   -> contact sheet of candidates (thumbs_<query>.jpg)
  python broll.py get <video_id> work/reel/assets/x.mp4 -> download the chosen clip
  python broll.py isearch "torn paper" work/reel        -> same, for vertical photos
  python broll.py iget <image_id> work/reel/assets/x.jpg

Key: PIXABAY_KEY env var, or a .pixabay_key file next to this script (gitignored).
Pixabay requires caching results 24h — searches are cached in .cache/.
"""
import hashlib, io, json, os, sys, urllib.parse, urllib.request
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".cache")


def key():
    k = os.environ.get("PIXABAY_KEY")
    if not k:
        p = os.path.join(HERE, ".pixabay_key")
        k = open(p).read().strip() if os.path.exists(p) else None
    if not k:
        sys.exit("No Pixabay key: set PIXABAY_KEY or create reel-editor/.pixabay_key")
    return k


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "buyinghero-reel-editor/1.0"})
    return urllib.request.urlopen(req, timeout=60).read()


def search(q, n=8, kind="videos"):
    os.makedirs(CACHE, exist_ok=True)
    cpath = os.path.join(CACHE, kind + "_" + hashlib.md5(q.encode()).hexdigest() + ".json")
    if os.path.exists(cpath):
        return json.load(open(cpath))
    params = {"key": key(), "q": q, "per_page": n, "safesearch": "true", "order": "popular"}
    if kind == "images":
        params.update(orientation="vertical", image_type="photo")
    url = "https://pixabay.com/api/" + ("videos/" if kind == "videos" else "") + "?" + urllib.parse.urlencode(params)
    hits = json.loads(fetch(url))["hits"]
    json.dump(hits, open(cpath, "w"))
    return hits


def contact_sheet(q, outdir, kind="videos"):
    hits = search(q, kind=kind)
    tw, th = 320, 180
    sheet = Image.new("RGB", (tw * 4, (th + 24) * ((len(hits) + 3) // 4)), "black")
    d = ImageDraw.Draw(sheet)
    for i, h in enumerate(hits):
        if kind == "images":
            v = {"thumbnail": h["webformatURL"], "width": h["imageWidth"], "height": h["imageHeight"]}
            h = dict(h, duration="img")
        else:
            v = h["videos"]["medium"] if h["videos"]["medium"]["url"] else h["videos"]["small"]
        x, y = (i % 4) * tw, (i // 4) * (th + 24)
        try:
            im = Image.open(io.BytesIO(fetch(v["thumbnail"]))).convert("RGB")
            im.thumbnail((tw, th)); sheet.paste(im, (x, y))
        except Exception:
            pass
        d.text((x + 4, y + th + 4), f"{h['id']}  {h['duration']}s  {v['width']}x{v['height']}", fill="white")
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, f"{kind[0]}thumbs_" + "".join(c if c.isalnum() else "_" for c in q) + ".jpg")
    sheet.save(out)
    print(out)


def cached(kind):
    return [h for f in os.listdir(CACHE) if f.startswith(kind + "_")
            for h in json.load(open(os.path.join(CACHE, f)))]


def iget(image_id, out):
    h = next(h for h in cached("images") if str(h["id"]) == str(image_id))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    open(out, "wb").write(fetch(h["largeImageURL"]))
    print(f"{out}  {h['imageWidth']}x{h['imageHeight']}  {h['pageURL']}")


def get(video_id, out):
    hits = cached("videos")
    h = next(h for h in hits if str(h["id"]) == str(video_id))
    v = next(h["videos"][s] for s in ("large", "medium", "small") if h["videos"][s]["url"])
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    open(out, "wb").write(fetch(v["url"]))
    print(f"{out}  {v['width']}x{v['height']}  {h['duration']}s  {h['pageURL']}")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "search":
        contact_sheet(sys.argv[2], sys.argv[3])
    elif cmd == "get":
        get(sys.argv[2], sys.argv[3])
    elif cmd == "isearch":
        contact_sheet(sys.argv[2], sys.argv[3], kind="images")
    elif cmd == "iget":
        iget(sys.argv[2], sys.argv[3])
