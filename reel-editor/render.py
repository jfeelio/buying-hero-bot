"""Compose the final reel: source video + overlays (b-roll / screenshots) + captions on top.

edit.json "overlays": [
  {"start": 6.3, "end": 8.4, "file": "assets/signing.mp4", "mode": "full"},
  {"start": 49.0, "end": 52.0, "file": "assets/dash.png", "mode": "card", "crop": [x, y, w, h]}
]
  full -> covers the frame (scale-to-fill), stills get a slow push-in
  card -> screenshot cropped, rounded, blue border + shadow, slides up into the upper frame
"""
import json, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFilter

W, H, FPS = 1080, 1920, 30
BLUE = (0, 131, 202)
VIDEO_EXT = (".mp4", ".mov", ".webm", ".m4v")
HERE = os.path.dirname(os.path.abspath(__file__))


def make_card(src, crop, out):
    im = Image.open(src).convert("RGB")
    if crop:
        x, y, w, h = crop
        im = im.crop((x, y, x + w, y + h))
    max_w, max_h = 940, 820
    s = min(max_w / im.width, max_h / im.height)
    im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    pad, border, r = 40, 8, 28
    cw, ch = im.width + 2 * border, im.height + 2 * border
    canvas = Image.new("RGBA", (cw + 2 * pad, ch + 2 * pad), (0, 0, 0, 0))
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((pad, pad + 12, pad + cw, pad + ch + 12), r, fill=(0, 0, 0, 170))
    canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(16)))
    frame = Image.new("RGBA", (cw, ch), BLUE + (255,))
    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, cw - 1, ch - 1), r, fill=255)
    inner_mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(inner_mask).rounded_rectangle((0, 0, im.width - 1, im.height - 1), r - border, fill=255)
    frame.paste(im, (border, border), inner_mask)
    canvas.paste(frame, (pad, pad), mask)
    canvas.save(out)
    return canvas.size


def build(video, edit_path, ass_path, out, workdir):
    edit = json.load(open(edit_path, encoding="utf-8"))
    base = os.path.dirname(os.path.abspath(edit_path))
    inputs, chains = ["-i", video], []
    chains.append(f"[0:v]scale={W}:{H},setsar=1,fps={FPS}[v0]")
    last = "v0"
    for n, o in enumerate(edit.get("overlays", []), start=1):
        src = os.path.join(base, o["file"])
        st, en = o["start"], o["end"]
        dur = en - st
        tag = f"o{n}"
        if o.get("mode", "full") == "card":
            card = os.path.join(workdir, f"card_{n}.png")
            cw, ch = make_card(src, o.get("crop"), card)
            inputs += ["-loop", "1", "-t", f"{en + 1:.3f}", "-i", card]
            chains.append(f"[{n}:v]format=rgba,fade=t=in:st={st}:d=0.15:alpha=1[{tag}]")
            y0 = o.get("y", 760) - ch // 2
            # slide up 120px over the first 0.18s
            ypos = f"{y0}+120*max(0\\,1-(t-{st})/0.18)"
            chains.append(f"[{last}][{tag}]overlay=x=(W-w)/2:y='{ypos}':enable='between(t,{st},{en})'[v{n}]")
        else:
            if src.lower().endswith(VIDEO_EXT):
                skip = o.get("from", 0)
                inputs += ["-ss", f"{skip}", "-t", f"{dur:.3f}", "-i", src]
                fill = (f"[{n}:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                        f"fps={FPS},setsar=1,setpts=PTS-STARTPTS+{st}/TB[{tag}]")
            else:
                frames = int(dur * FPS) + 1
                inputs += ["-loop", "1", "-t", f"{dur:.3f}", "-i", src]
                # oversize then crop a slowly shrinking window = smooth push-in without zoompan jitter
                fill = (f"[{n}:v]scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
                        f"fps={FPS},crop=w='{W * 2}*(1-0.08*n/{frames})':h='{H * 2}*(1-0.08*n/{frames})',"
                        f"scale={W}:{H},setsar=1,setpts=PTS-STARTPTS+{st}/TB[{tag}]")
            chains.append(fill)
            chains.append(f"[{last}][{tag}]overlay=0:0:eof_action=pass:enable='between(t,{st},{en})'[v{n}]")
        last = f"v{n}"
    ass = os.path.relpath(ass_path, HERE).replace("\\", "/")
    chains.append(f"[{last}]subtitles={ass}:fontsdir=fonts[vout]")
    cmd = (["ffmpeg", "-v", "error", "-y"] + inputs +
           ["-filter_complex", ";".join(chains), "-map", "[vout]", "-map", "0:a",
            "-c:v", "h264_nvenc", "-preset", "p5", "-cq", "23", "-maxrate", "8M", "-bufsize", "16M",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out])
    subprocess.run(cmd, check=True, cwd=HERE)
    print(f"rendered -> {out}")


if __name__ == "__main__":
    video, edit_path, ass_path, out = sys.argv[1:5]
    build(video, edit_path, ass_path, out, os.path.dirname(os.path.abspath(edit_path)))
