"""Compose the final reel from a reel folder.

  python render.py D:/Reels/2026-10-15-attorney-mvp v3

Reads <reel>/raw.mov, edit.json, captions.ass -> writes <reel>/output/<name>.mp4

edit.json keys used here:
  overlays: [{"start", "end", "file", "mode": "full"|"card", "from"?, "crop"?: [x,y,w,h], "y"?}]
      full -> covers the frame (scale-to-fill), stills get a slow push-in
      card -> screenshot cropped, rounded, blue border + shadow, slides up into the upper frame
  zooms:    [{"start", "end", "scale"?: 1.08}]     hard punch-in on the talking head
  icons:    [{"t", "icon": lucide-name, "dur"?: 1.6}]  brand badge pops in beside the face
  sfx:      [{"t", "file": sfx/<name>.mp3, "vol"?: 0.35, "peak"?: true}]
            peak=true lines the loudest moment of the sound up with t (for whooshes)
  progress: true|false (default true)       thin brand-blue bar along the bottom
"""
import json, os, shutil, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

W, H, FPS = 1080, 1920, 30
BLUE = (0, 131, 202)
VIDEO_EXT = (".mp4", ".mov", ".webm", ".m4v")
HERE = os.path.dirname(os.path.abspath(__file__))
ICON_SIZE, ICON_X, ICON_Y = 180, 900, 960   # right of the face, above the captions
FACE_Y = 0.35                               # zoom anchor: keep the face in frame


def ffmpeg_bin(name="ffmpeg"):
    found = shutil.which(name)
    if found:
        return found
    pk = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
    for root, _, files in os.walk(pk):
        if f"{name}.exe" in files:
            return os.path.join(root, f"{name}.exe")
    sys.exit("ffmpeg not found")


def filter_path(p):
    # ffmpeg filter args: forward slashes, escaped drive colon, quoted for spaces
    p = os.path.abspath(p).replace("\\", "/").replace(":", "\\:")
    return f"'{p}'"


def duration(path):
    out = subprocess.run([ffmpeg_bin("ffprobe"), "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def peak_time(path):
    raw = subprocess.run([ffmpeg_bin(), "-v", "error", "-i", path, "-ac", "1", "-ar", "8000", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    a = np.abs(np.frombuffer(raw, np.float32))
    env = np.convolve(a, np.ones(400) / 400, mode="same")   # 50ms envelope
    return float(np.argmax(env)) / 8000


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


def make_icon_frames(name, dur, outdir):
    """PNG sequence: overshoot pop in (0 -> 115% -> 100%), hold with a gentle bob, shrink out."""
    os.makedirs(outdir, exist_ok=True)
    badge = os.path.join(outdir, "badge.png")
    subprocess.run(["node", os.path.join(HERE, "icon.js"), name, badge, str(ICON_SIZE)], check=True,
                   capture_output=True)
    src = Image.open(badge).convert("RGBA")
    box = int(ICON_SIZE * 1.3)
    n = int(dur * FPS)
    for f in range(n):
        if f < 5:
            s = [0.3, 0.7, 1.1, 1.15, 1.05][f]
        elif f >= n - 5:
            s = 1.0 - (f - (n - 5) + 1) * 0.19
        else:
            s = 1.0 + 0.03 * np.sin((f - 5) / FPS * 2 * np.pi * 0.8)
        frame = Image.new("RGBA", (box, box), (0, 0, 0, 0))
        sz = max(int(ICON_SIZE * s), 2)
        im = src.resize((sz, sz), Image.LANCZOS)
        frame.paste(im, ((box - sz) // 2, (box - sz) // 2), im)
        frame.save(os.path.join(outdir, f"f_{f:04d}.png"))
    return box


def build(reel, name):
    edit = json.load(open(os.path.join(reel, "edit.json"), encoding="utf-8"))
    video = os.path.join(reel, "raw.mov")
    work = os.path.join(reel, "build")
    os.makedirs(work, exist_ok=True)
    os.makedirs(os.path.join(reel, "output"), exist_ok=True)
    total = duration(video)

    inputs, chains, n = ["-i", video], [], 0

    # talking head + punch-in zooms (hard cut in/out, anchored on the face)
    zooms = edit.get("zooms", [])
    z = "+".join(f"{z.get('scale', 1.08) - 1:.3f}*between(t,{z['start']},{z['end']})" for z in zooms) or "0"
    chains.append(f"[0:v]scale={W}:{H},setsar=1,fps={FPS},"
                  f"scale=w='trunc({W}*(1+{z})/2)*2':h='trunc({H}*(1+{z})/2)*2':eval=frame,"
                  f"crop={W}:{H}:x='(iw-{W})/2':y='(ih-{H})*{FACE_Y}'[v0]")
    last = "v0"

    for o in edit.get("overlays", []):
        n += 1
        src = os.path.join(reel, o["file"])
        st, en = o["start"], o["end"]
        dur = en - st
        tag = f"o{n}"
        if o.get("mode", "full") == "card":
            card = os.path.join(work, f"card_{n}.png")
            cw, ch = make_card(src, o.get("crop"), card)
            inputs += ["-loop", "1", "-t", f"{en + 1:.3f}", "-i", card]
            chains.append(f"[{n}:v]format=rgba,fade=t=in:st={st}:d=0.15:alpha=1[{tag}]")
            y0 = o.get("y", 760) - ch // 2
            ypos = f"{y0}+120*max(0\\,1-(t-{st})/0.18)"
            chains.append(f"[{last}][{tag}]overlay=x=(W-w)/2:y='{ypos}':enable='between(t,{st},{en})'[v{n}]")
        else:
            if src.lower().endswith(VIDEO_EXT):
                inputs += ["-ss", f"{o.get('from', 0)}", "-t", f"{dur:.3f}", "-i", src]
                fill = (f"[{n}:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                        f"fps={FPS},setsar=1,setpts=PTS-STARTPTS+{st}/TB[{tag}]")
            else:
                frames = int(dur * FPS) + 1
                inputs += ["-loop", "1", "-t", f"{dur:.3f}", "-i", src]
                fill = (f"[{n}:v]scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
                        f"fps={FPS},crop=w='{W * 2}*(1-0.08*n/{frames})':h='{H * 2}*(1-0.08*n/{frames})',"
                        f"scale={W}:{H},setsar=1,setpts=PTS-STARTPTS+{st}/TB[{tag}]")
            chains.append(fill)
            chains.append(f"[{last}][{tag}]overlay=0:0:eof_action=pass:enable='between(t,{st},{en})'[v{n}]")
        last = f"v{n}"

    for k, ic in enumerate(edit.get("icons", [])):
        n += 1
        t, dur = ic["t"], ic.get("dur", 1.6)
        d = os.path.join(work, f"icon_{k}")
        box = make_icon_frames(ic["icon"], dur, d)
        inputs += ["-framerate", str(FPS), "-i", os.path.join(d, "f_%04d.png")]
        chains.append(f"[{n}:v]format=rgba,setpts=PTS-STARTPTS+{t}/TB[i{n}]")
        chains.append(f"[{last}][i{n}]overlay=x={ICON_X - box // 2}:y={ICON_Y - box // 2}:eof_action=pass"
                      f":enable='between(t,{t},{t + dur})'[v{n}]")
        last = f"v{n}"

    if edit.get("progress", True):
        n += 1
        inputs += ["-f", "lavfi", "-i", f"color=c=0x0083CA:s={W}x12:r={FPS}:d={total:.3f}"]
        chains.append(f"[{last}][{n}:v]overlay=x='-w+w*t/{total:.3f}':y={H - 12}:shortest=1[v{n}]")
        last = f"v{n}"

    chains.append(f"[{last}]subtitles=captions.ass:fontsdir={filter_path(os.path.join(HERE, 'fonts'))}[vout]")

    # audio: voice + SFX (voice untouched; SFX ducked well under it)
    amix = ["[0:a]aformat=sample_rates=48000:channel_layouts=stereo[a0]"]
    labels = ["[a0]"]
    for k, s in enumerate(edit.get("sfx", [])):
        n += 1
        f = os.path.join(HERE, s["file"])
        lead = peak_time(f) if s.get("peak") else 0.0
        start = max(s["t"] - lead, 0)
        inputs += ["-i", f]
        amix.append(f"[{n}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={s.get('vol', 0.35)},"
                    f"adelay={int(start * 1000)}:all=1[s{k}]")
        labels.append(f"[s{k}]")
    amix.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=first:normalize=0[aout]")

    out = os.path.join(reel, "output", f"{name}.mp4")
    cmd = ([ffmpeg_bin(), "-v", "error", "-y"] + inputs +
           ["-filter_complex", ";".join(chains + amix), "-map", "[vout]", "-map", "[aout]",
            "-c:v", "h264_nvenc", "-preset", "p5", "-cq", "23", "-maxrate", "8M", "-bufsize", "16M",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out])
    subprocess.run(cmd, check=True, cwd=reel)
    print(f"rendered -> {out}")
    return out


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "final")
