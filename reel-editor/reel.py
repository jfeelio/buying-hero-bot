"""One entry point for the reel-editor skill.

  python reel.py new <slug> <video> [screenshot ...]   create D:/Reels/<date>-<slug>, move files in, transcribe
  python reel.py words <reel>                         indexed transcript: i:word@start (for writing edit.json)
  python reel.py build <reel> <name>                  captions + render + copy to Downloads
  python reel.py frames <reel> <name> <t> [t ...]     contact strip of output frames for visual QA
  python reel.py history [n]                          graphic styles used by the last n reels (vary them!)
"""
import datetime, glob, json, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REELS = os.environ.get("REELS_DIR", "D:/Reels")
DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")
sys.path.insert(0, HERE)


def new(slug, video, *shots):
    reel = os.path.join(REELS, f"{datetime.date.today():%Y-%m-%d}-{slug}")
    for sub in ("screenshots", "assets", "output"):
        os.makedirs(os.path.join(reel, sub), exist_ok=True)
    shutil.move(video, os.path.join(reel, "raw" + os.path.splitext(video)[1].lower()))
    for s in shots:
        shutil.move(s, os.path.join(reel, "screenshots", os.path.basename(s)))
    raw = glob.glob(os.path.join(reel, "raw.*"))[0]
    if not raw.endswith(".mov"):   # render.py expects raw.mov; remux keeps quality
        from render import ffmpeg_bin
        subprocess.run([ffmpeg_bin(), "-v", "error", "-y", "-i", raw, "-c", "copy",
                        os.path.join(reel, "raw.mov")], check=True)
    subprocess.run([sys.executable, os.path.join(HERE, "transcribe.py"), os.path.join(reel, "raw.mov"),
                    os.path.join(reel, "words.json")], check=True)
    print(reel)
    words(reel)


def words(reel):
    w = json.load(open(os.path.join(reel, "words.json"), encoding="utf-8"))["words"]
    print(" ".join(f"{i}:{x['w']}@{x['s']}" for i, x in enumerate(w)))
    print(f"\n{len(w)} words, {w[-1]['e']:.1f}s")


def build(reel, name):
    from render import build as render
    subprocess.run([sys.executable, os.path.join(HERE, "captions.py"), os.path.join(reel, "words.json"),
                    os.path.join(reel, "edit.json"), os.path.join(reel, "captions.ass")], check=True)
    out = render(reel, name)
    dst = os.path.join(DOWNLOADS, f"{os.path.basename(reel)}_{name}.mp4")
    shutil.copy(out, dst)
    print(f"copied -> {dst}")


def frames(reel, name, *ts):
    from PIL import Image
    from render import ffmpeg_bin
    out = os.path.join(reel, "output", f"{name}.mp4")
    chk = os.path.join(reel, "build", "chk")
    os.makedirs(chk, exist_ok=True)
    tiles = []
    for t in ts:
        p = os.path.join(chk, f"{t}.jpg")
        subprocess.run([ffmpeg_bin(), "-v", "error", "-y", "-ss", t, "-i", out, "-frames:v", "1",
                        "-vf", "scale=216:-1", p], check=True)
        tiles.append(Image.open(p))
    sheet = Image.new("RGB", (216 * len(tiles), tiles[0].height))
    for i, im in enumerate(tiles):
        sheet.paste(im, (i * 216, 0))
    p = os.path.join(chk, f"strip_{name}.jpg")
    sheet.save(p)
    print(p)


def history(n=5):
    reels = sorted(d for d in glob.glob(os.path.join(REELS, "*")) if os.path.exists(os.path.join(d, "edit.json")))
    for d in reels[-int(n):]:
        e = json.load(open(os.path.join(d, "edit.json"), encoding="utf-8"))
        lists = [f"{l.get('style', 'x')}/{l.get('entrance', 'slide')}/{l.get('panel', 'dim')}" for l in e.get("lists", [])]
        print(f"{os.path.basename(d)}: lists={lists or '-'} stats={len(e.get('stats', []))} "
              f"heroes={len(e.get('hero', []))} zooms={len(e.get('zooms', []))} "
              f"icons={[i['icon'] for i in e.get('icons', [])]} broll={len(e.get('overlays', []))}")


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    {"new": new, "words": words, "build": build, "frames": frames, "history": history}[cmd](*args)
