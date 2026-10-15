"""Compose the final reel from a reel folder.

  python render.py D:/Reels/2026-10-15-attorney-mvp v3

Reads <reel>/raw.mov, edit.json, captions.ass -> writes <reel>/output/<name>.mp4

edit.json keys used here:
  overlays: [{"start", "end", "file", "mode": "full"|"card", "from"?, "crop"?: [x,y,w,h], "y"?}]
      full -> covers the frame (scale-to-fill), stills get a slow push-in; 0.25s crossfade
              in/out by default ("transition": "cut" for a hard cut)
      card -> screenshot cropped, rounded, blue border + shadow, slides up into the upper frame
  zooms:    [{"start", "end", "scale"?: 1.08}]     eased push-in on the talking head
  lists:    [{"start", "end", "items": [{"t", "text"}], "style": x|check|numbered,
              "entrance": slide|pop|drop, "panel": dim|pills}]   each item enters as it's said
  stats:    [{"start", "end", "value": 115000, "prefix": "$", "suffix"?, "label"?: "WE ALMOST LOST"}]
            big brand-blue number counts up from 0 (captions muted underneath)
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
ICON_SIZE, ICON_X, ICON_Y = 180, 900, 760   # right of the head, clear of captions + lead-ins
FACE_Y = 0.35                               # zoom anchor: keep the face in frame
ZOOM_EASE = 0.35                            # seconds to ease in/out of a push-in
XFADE = 0.25                                # B-roll crossfade in/out


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


LIST_STYLES = {           # badge kind -> (lucide icon or None for numbers, colour)
    "x": ("x", "#E5383B"),          # deal-killers, mistakes, what goes wrong
    "check": ("check", "#0083CA"),  # wins, what to do, what you get
    "numbered": (None, "#0083CA"),  # steps, reasons, ranked points
}


def _badge(kind, num, size, outdir):
    from PIL import ImageFont
    icon, colour = LIST_STYLES[kind]
    p = os.path.join(outdir, f"badge_{kind}_{num}.png")
    if icon:
        subprocess.run(["node", os.path.join(HERE, "icon.js"), icon, p, str(size), colour],
                       check=True, capture_output=True)
        return Image.open(p).convert("RGBA")
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((3, 3, size - 4, size - 4), fill=colour, outline="white", width=6)
    font = ImageFont.truetype(os.path.join(HERE, "fonts", "Montserrat-Black.ttf"), int(size * 0.5))
    d.text((size / 2, size / 2 + 2), str(num), font=font, fill="white", anchor="mm")
    return im


def _entrance(kind, p):
    """p in 0..1 (eased) -> (dx, dy, scale)"""
    if kind == "pop":
        s = 0.4 + 0.75 * p if p < 0.8 else 1.0 + 0.15 * (1 - p) / 0.2
        return 0, 0, min(s, 1.15)
    if kind == "drop":
        return 0, int(-70 * (1 - p)), 1.0
    return int(-80 * (1 - p)), 0, 1.0          # slide


def make_list_frames(ls, outdir):
    """Full-frame PNG sequence of a list graphic; each item enters on its spoken cue.

    style:    x | check | numbered        (what the badge says)
    entrance: slide | pop | drop          (how each row arrives)
    panel:    dim | pills                 (darken the whole frame, or a dark pill behind each row)
    """
    from PIL import ImageFont
    os.makedirs(outdir, exist_ok=True)
    st, en, items = ls["start"], ls["end"], ls["items"]
    style, entrance, panel = ls.get("style", "x"), ls.get("entrance", "slide"), ls.get("panel", "dim")
    row_h, x0, bs = 170, 90, 110
    fpath = os.path.join(HERE, "fonts", "Montserrat-Black.ttf")
    size = 76   # shrink until the longest row fits inside a 60px right margin
    while size > 44 and bs + 70 + ImageFont.truetype(fpath, size).getlength(
            max((it["text"].upper() for it in items), key=len)) > W - x0 - 60:
        size -= 2
    font = ImageFont.truetype(fpath, size)
    y0 = ls.get("y", 960) - row_h * len(items) // 2   # ends above Instagram's bottom UI (~1190px)
    rows = []
    for i, it in enumerate(items):   # pre-render each row once
        badge = _badge(style, i + 1, bs, outdir)
        txt = it["text"].upper()
        tw = int(font.getlength(txt))
        im = Image.new("RGBA", (bs + 60 + tw + 40, row_h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        if panel == "pills":
            d.rounded_rectangle((bs // 2, 22, im.width - 1, row_h - 22), (row_h - 44) // 2, fill=(0, 0, 0, 215))
        im.paste(badge, (0, (row_h - bs) // 2), badge)
        d.text((bs + 30, row_h // 2), txt, font=font, fill="white", anchor="lm",
               stroke_width=0 if panel == "pills" else 5, stroke_fill="black")
        rows.append(im)
    n = int((en - st) * FPS)
    for f in range(n):
        t = st + f / FPS
        fade = min(f / 6, (n - 1 - f) / 6, 1.0)
        frame = Image.new("RGBA", (W, H), (0, 0, 0, int(150 * fade) if panel == "dim" else 0))
        for r, (it, im) in enumerate(zip(items, rows)):
            k = (t - it["t"]) * FPS
            if k < 0:
                continue
            p = 1 - (1 - min(k / 6, 1.0)) ** 3            # ease-out
            a = min(p, fade)
            dx, dy, sc = _entrance(entrance, p)
            row = im if sc == 1.0 else im.resize((max(int(im.width * sc), 1), max(int(im.height * sc), 1)))
            row = row.copy()
            row.putalpha(row.getchannel("A").point(lambda v: int(v * a)))
            ox = x0 + dx
            oy = y0 + r * row_h + dy - (row.height - im.height) // 2
            frame.alpha_composite(row, (max(ox, 0), max(oy, 0)))
        frame.save(os.path.join(outdir, f"f_{f:04d}.png"), compress_level=1)


def make_stat_frames(stt, outdir):
    """Count-up number: label on top, the value rolls from 0 to target, then settles with a pulse."""
    from PIL import ImageFont
    os.makedirs(outdir, exist_ok=True)
    st, en, val = stt["start"], stt["end"], float(stt["value"])
    prefix, suffix, label = stt.get("prefix", ""), stt.get("suffix", ""), stt.get("label", "").upper()
    count_t = stt.get("count", 0.9)
    fpath = os.path.join(HERE, "fonts", "Montserrat-Black.ttf")

    def fit(text, size, stroke):   # largest size <= requested that keeps text 60px inside each edge
        while size > 40 and ImageFont.truetype(fpath, size).getlength(text) + 2 * stroke > W - 120:
            size -= 4
        return ImageFont.truetype(fpath, size)
    big = fit(f"{prefix}{val:,.0f}{suffix}", stt.get("size", 210), 10)
    small = fit(label, 84, 6)
    y = stt.get("y", 1040)   # number + label stay above Instagram's bottom UI
    n = int((en - st) * FPS)
    for f in range(n):
        t = f / FPS
        fade = min(f / 5, (n - 1 - f) / 5, 1.0)
        frame = Image.new("RGBA", (W, H), (0, 0, 0, int(110 * fade)))
        d = ImageDraw.Draw(frame)
        p = min(t / count_t, 1.0)
        p = 1 - (1 - p) ** 3
        v = val * p
        txt = f"{prefix}{v:,.0f}{suffix}"
        pulse = 1.0 + (0.08 * np.sin(min((t - count_t) / 0.25, 1) * np.pi) if t > count_t else 0)
        f_big = big if pulse == 1.0 else ImageFont.truetype(big.path, int(big.size * min(pulse, 1.0 + 60 / W)))
        alpha = int(255 * fade)
        if label:
            d.text((W // 2, y - 175), label, font=small, fill=(255, 255, 255, alpha), anchor="mm",
                   stroke_width=6, stroke_fill=(0, 0, 0, alpha))
        d.text((W // 2, y), txt, font=f_big, fill=(0, 131, 202, alpha), anchor="mm",
               stroke_width=10, stroke_fill=(0, 0, 0, alpha))
        frame.save(os.path.join(outdir, f"f_{f:04d}.png"), compress_level=1)


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
    # smoothstep ramp in over ZOOM_EASE, hold, ramp out — no hard jumps
    def ramp(a, b):
        e = ZOOM_EASE
        u = rf"clip(min((t-{a})/{e},({b}-t)/{e}),0,1)"
        return f"({u}*{u}*(3-2*{u}))"
    z = "+".join(f"{z.get('scale', 1.08) - 1:.3f}*{ramp(z['start'], z['end'])}" for z in zooms) or "0"
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
            # soft crossfade in/out instead of a hard cut ("transition": "cut" to disable)
            if o.get("transition", "fade") == "fade":
                fd = min(XFADE, dur / 3)
                fill = fill[:-len(f"[{tag}]")] + (f",format=yuva420p,fade=t=in:st={st}:d={fd}:alpha=1,"
                                                  f"fade=t=out:st={en - fd:.3f}:d={fd}:alpha=1[{tag}]")
            chains.append(fill)
            chains.append(f"[{last}][{tag}]overlay=0:0:eof_action=pass:enable='between(t,{st},{en})'[v{n}]")
        last = f"v{n}"

    for k, ls in enumerate(edit.get("lists", [])):
        n += 1
        d = os.path.join(work, f"list_{k}")
        make_list_frames(ls, d)
        inputs += ["-framerate", str(FPS), "-i", os.path.join(d, "f_%04d.png")]
        chains.append(f"[{n}:v]format=rgba,setpts=PTS-STARTPTS+{ls['start']}/TB[l{n}]")
        chains.append(f"[{last}][l{n}]overlay=0:0:eof_action=pass:enable='between(t,{ls['start']},{ls['end']})'[v{n}]")
        last = f"v{n}"

    for k, stt in enumerate(edit.get("stats", [])):
        n += 1
        d = os.path.join(work, f"stat_{k}")
        make_stat_frames(stt, d)
        inputs += ["-framerate", str(FPS), "-i", os.path.join(d, "f_%04d.png")]
        chains.append(f"[{n}:v]format=rgba,setpts=PTS-STARTPTS+{stt['start']}/TB[st{n}]")
        chains.append(f"[{last}][st{n}]overlay=0:0:eof_action=pass:enable='between(t,{stt['start']},{stt['end']})'[v{n}]")
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
