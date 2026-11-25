"""Instagram Reels safe-zone QA: shade the parts of a 1080x1920 frame that IG's UI covers, on a contact sheet.

  python igsafe.py <video.mp4> <out.jpg> [step_s=1.0]

Zones (Reels player, 2026; conservative):
  top     y 0-220            "Reels" header / camera icon
  bottom  y 1540-1920        username, caption line, audio ticker
  right   x 950-1080, y 1000-1540   like / comment / share / remix column
Anything we draw (captions, cards, tables, titles) must sit outside the red. His face doesn't matter here (it's
the video), only our overlays. Review the sheet; QA fails if text or a graphic edge is inside a zone.
"""
import subprocess, sys
from render import ffmpeg_bin

ZONES = [(0, 0, 1080, 220), (0, 1540, 1080, 380), (950, 1000, 130, 540)]


def sheet(video, out, step=1.0):
    boxes = ",".join(f"drawbox=x={x}:y={y}:w={w}:h={h}:color=red@0.32:t=fill" for x, y, w, h in ZONES)
    vf = (f"fps=1/{step},{boxes},scale=270:-1,drawtext=fontfile='C\\:/Windows/Fonts/arial.ttf':text='%{{pts\\:hms}}'"
          f":x=4:y=4:fontsize=18:fontcolor=yellow:box=1:boxcolor=black,tile=8x3")
    subprocess.run([ffmpeg_bin(), "-v", "error", "-y", "-i", video, "-vf", vf, "-frames:v", "1", out], check=True)
    print(out)


if __name__ == "__main__":
    sheet(sys.argv[1], sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 1.0)
