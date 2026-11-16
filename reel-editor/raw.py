"""Raw multi-clip mode: Jorge's uncut takes -> best take per line -> rough cut -> normal reel (raw.mov + words.json).

  reel.py raw <slug> <clip|folder> [...]   move clips into <reel>/clips, transcribe each, print transcripts with gaps
  (write <reel>/cuts.json by hand: which takes compete, then the cut list)
  reel.py score <reel>                     delivery scorecard + blind Gemini A/B on every "compare" group
  reel.py assemble <reel>                  cut list -> raw.mov + words.json (re-transcribed), QA transcript printed

cuts.json:
  {"compare": {"Hook": [["IMG_0823", 3.7, 11.0], ["IMG_0831", 11.0, 29.4]], ...},
   "cuts": [{"clip": "IMG_0823", "start": 3.75, "end": 27.75, "note": "hook",
             "crop": {"zoom": 1.3, "cx": 0.45, "cy": 0.42}}, ...]}
  crop (optional): punch into the 4K source (zoom 1 = full frame); cx/cy = centre of the kept area, 0-1.
  Where a long pause is trimmed inside one take, the next piece punches in 12% to hide the jump cut
  ("hide_jumps": false on a cut to turn that off).

Lessons baked in (2026-11-15 test): Whisper end-times run early -> every cut end snaps to real silence in
the waveform; Whisper can invent words at a take's end -> trust the waveform; consecutive lines from the same
take must be ONE cut (separate cuts overlap); pauses > GAP inside a cut are trimmed (cut in the silence);
each clip's voice is level-matched; 20-30 ms audio fades stop clicks at seams.
"""
import base64, glob, json, os, shutil, subprocess, sys, urllib.request, wave
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from render import ffmpeg_bin

GAP, PRE, POST = 0.6, 0.12, 0.22
VIDEO_EXT = (".mov", ".mp4", ".m4v")
GEMINI_KEY = os.environ.get("GEMINI_KEY_FILE", os.path.join(HERE, "..", "carousel", ".gemini_key"))
GEMINI_MODEL = "gemini-3.1-pro-preview"   # 2.5-pro is closed to new users (404, 2026-11-15)


# ---------- helpers ----------
def _clips(reel):
    return {os.path.splitext(os.path.basename(f))[0]: f
            for f in sorted(glob.glob(os.path.join(reel, "clips", "*"))) if f.lower().endswith(VIDEO_EXT)}


def _wav(reel, cid):
    return os.path.join(reel, "build", f"a_{cid}.wav")


def _audio(reel, cid, _cache={}):
    p = _wav(reel, cid)
    if p not in _cache:
        w = wave.open(p)
        _cache[p] = (np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768,
                     w.getframerate())
    return _cache[p]


def _words(reel, cid):
    d = json.load(open(os.path.join(reel, "clips", f"{cid}.words.json"), encoding="utf-8"))["words"]
    return [(x["w"], x["s"], x["e"]) for x in d]


def _in(ws, s, e):
    return [w for w in ws if w[1] >= s - 0.05 and w[2] <= e + 0.05]


def _level(reel, cid, s, e):
    x, sr = _audio(reel, cid)
    seg = x[int(s * sr):int(e * sr)]
    fr = seg[: len(seg) // 160 * 160].reshape(-1, 160)
    rms = np.sqrt(np.mean(fr ** 2, axis=1))
    v = rms[rms > 0.02]
    return float(20 * np.log10(np.mean(v))) if len(v) else -60.0


def _snap_end(reel, cid, e, cap=1.2, quiet=0.15):
    """Push a cut later until the voice has really stopped (quiet s under -40 dB). Whisper end-times run early."""
    x, sr = _audio(reel, cid)
    hop, run = int(0.01 * sr), 0
    for k in range(int(e * sr), min(len(x), int((e + cap) * sr)), hop):
        run = run + 1 if np.sqrt(np.mean(x[k:k + hop] ** 2)) < 0.01 else 0
        if run * 0.01 >= quiet:
            return k / sr - quiet + 0.12
    return e + cap


def _pitch_var(seg, sr):
    """Std of f0 in semitones (autocorrelation, 75-300 Hz) - flat/monotone vs expressive."""
    n, h, lo, hi, f0 = int(0.04 * sr), int(0.01 * sr), int(sr / 300), int(sr / 75), []
    for i in range(0, len(seg) - n, h):
        fr = seg[i:i + n] * np.hanning(n)
        if np.sqrt(np.mean(fr ** 2)) < 0.01:
            continue
        ac = np.correlate(fr, fr, "full")[n - 1:]
        if ac[0] <= 0:
            continue
        lag = lo + int(np.argmax(ac[lo:hi]))
        if ac[lag] / ac[0] > 0.45:
            f0.append(sr / lag)
    f0 = np.array(f0)
    return float(np.std(12 * np.log2(f0 / np.median(f0)))) if len(f0) > 20 else 0.0


def _print_transcript(ws):
    out, prev = [], None
    for w, s, e in ws:
        if prev is not None and s - prev > 0.7:
            out.append(f"[{s - prev:.1f}s gap]")
        out.append(f"{w}@{s:.1f}")
        prev = e
    print(" ".join(out))


# ---------- commands ----------
def raw(reel, *paths):
    """Move clips in, extract audio, transcribe each one."""
    os.makedirs(os.path.join(reel, "clips"), exist_ok=True)
    for sub in ("build", "screenshots", "assets", "output"):
        os.makedirs(os.path.join(reel, sub), exist_ok=True)
    files = []
    for p in paths:
        files += sorted(f for f in glob.glob(os.path.join(p, "*")) if f.lower().endswith(VIDEO_EXT)) if os.path.isdir(p) else [p]
    for f in files:
        shutil.move(f, os.path.join(reel, "clips", os.path.basename(f)))
    for cid, f in _clips(reel).items():
        subprocess.run([ffmpeg_bin(), "-v", "error", "-y", "-i", f, "-vn", "-ac", "1", "-ar", "16000", _wav(reel, cid)], check=True)
        out = os.path.join(reel, "clips", f"{cid}.words.json")
        if not os.path.exists(out):
            subprocess.run([sys.executable, os.path.join(HERE, "transcribe.py"), f, out], check=True)
        dur = float(subprocess.run([ffmpeg_bin("ffprobe"), "-v", "error", "-show_entries", "format=duration",
                                    "-of", "csv=p=0", f], capture_output=True, text=True).stdout.strip() or 0)
        print(f"\n== {cid}  ({dur:.0f}s)")
        _print_transcript(_words(reel, cid))
        sheet = os.path.join(reel, "build", f"sheet_{cid}.jpg")
        step = max(1.0, dur / 12)
        subprocess.run([ffmpeg_bin(), "-v", "error", "-y", "-i", f, "-vf", f"fps=1/{step:.2f},scale=160:-1,tile=12x1",
                        "-frames:v", "1", sheet], check=True)
        print(f"contact sheet: {sheet}")
    print(f"\n{reel}\nNext: write {os.path.join(reel, 'cuts.json')} ('compare' groups + 'cuts'), then reel.py score / assemble")


def _gemini(reel, takes):
    if not os.path.exists(GEMINI_KEY):
        return None
    key = open(GEMINI_KEY).read().strip()
    parts = [{"text": "You are a short-form video editor choosing between takes of the same line for an Instagram Reel "
                      "by a real estate investor talking to camera. Listen to each take. Judge DELIVERY only: confidence, "
                      "energy, natural flow, clarity, conviction (not the wording, not mic/wind noise unless it hurts "
                      'intelligibility). Reply as JSON: {"takes": [{"take": "A", "score": 1-10, "note": "<12 words"}], '
                      '"pick": "A", "why": "<20 words"}'}]
    for lab, (cid, s, e) in zip("ABCDEFGH", takes):
        mp3 = subprocess.run([ffmpeg_bin(), "-v", "error", "-ss", str(s), "-to", str(e), "-i", _wav(reel, cid),
                              "-c:a", "libmp3lame", "-b:a", "64k", "-f", "mp3", "-"], capture_output=True, check=True).stdout
        parts += [{"text": f"Take {lab}:"}, {"inline_data": {"mime_type": "audio/mp3", "data": base64.b64encode(mp3).decode()}}]
    body = {"contents": [{"parts": parts}], "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
                                 data=json.dumps(body).encode(), headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=180))
    return json.loads(r["candidates"][0]["content"]["parts"][-1]["text"])


def score(reel):
    """Scorecard (numbers) + Gemini blind A/B (ears) for each group of competing takes."""
    cfg = json.load(open(os.path.join(reel, "cuts.json"), encoding="utf-8"))
    report = {}
    for g, takes in cfg.get("compare", {}).items():
        print(f"\n{g}")
        rows = []
        for lab, (cid, s, e) in zip("ABCDEFGH", takes):
            x, sr = _audio(reel, cid)
            ws = _in(_words(reel, cid), s, e)
            speak = ws[-1][2] - ws[0][1] if ws else 0
            gaps = [b[1] - a[2] for a, b in zip(ws, ws[1:])]
            v = [_level(reel, cid, s, (s + e) / 2), _level(reel, cid, (s + e) / 2, e)]
            r = dict(take=lab, src=f"{cid} {s}-{e}", words=len(ws), wps=round(len(ws) / speak, 2) if speak else 0,
                     dead_air=round(sum(max(0, q - 0.35) for q in gaps), 1), max_gap=round(max(gaps or [0]), 1),
                     loud_db=round(_level(reel, cid, s, e), 1), end_fade_db=round(v[1] - v[0], 1),
                     pitch_var=round(_pitch_var(x[int(s * sr):int(e * sr)], sr), 2))
            rows.append(r)
            print(f"  {lab} {r['src']:<22} {r['words']:>3}w {r['wps']:>4} w/s  dead-air {r['dead_air']}s (max {r['max_gap']})"
                  f"  loud {r['loud_db']} dB  fade {r['end_fade_db']:+} dB  pitch-var {r['pitch_var']} st")
        ear = None
        try:
            ear = _gemini(reel, takes)
        except Exception as ex:
            print(f"  (Gemini skipped: {ex})")
        if ear:
            print(f"  Gemini pick {ear['pick']}: {ear['why']}")
            for t in ear["takes"]:
                print(f"     {t['take']}: {t['score']}/10  {t['note']}")
        report[g] = {"scorecard": rows, "gemini": ear}
    json.dump(report, open(os.path.join(reel, "build", "takes.json"), "w"), indent=1)


def assemble(reel):
    """cuts.json 'cuts' -> raw.mov (1080x1920 @30, from the full-res originals) + words.json."""
    cfg = json.load(open(os.path.join(reel, "cuts.json"), encoding="utf-8"))
    clips, cuts = _clips(reel), cfg["cuts"]
    target = float(np.mean([_level(reel, c["clip"], c["start"], c["end"]) for c in cuts]))
    pieces = []
    for c in cuts:
        cid, s, e = c["clip"], c["start"], c["end"]
        ws = _in(_words(reel, cid), s, e)
        groups, cur = [], [ws[0]]
        for a, b in zip(ws, ws[1:]):
            if b[1] - a[2] > c.get("gap", GAP):
                groups.append(cur); cur = []
            cur.append(b)
        groups.append(cur)
        for gi, g in enumerate(groups):
            ps = s if gi == 0 else max(s, g[0][1] - PRE)
            pe = e if gi == len(groups) - 1 else g[-1][2] + POST
            pe = _snap_end(reel, cid, pe)
            if gi < len(groups) - 1:
                pe = min(pe, groups[gi + 1][0][1] - 0.05)
            crop = dict(c.get("crop") or {"zoom": 1.0, "cx": 0.5, "cy": 0.45})
            if gi % 2 and c.get("hide_jumps", True):   # trimmed pause inside one take = jump cut -> punch in 12%
                crop["zoom"] = round(crop["zoom"] * 1.12, 3)
            pieces.append(dict(clip=cid, s=ps, e=pe, gain=target - _level(reel, cid, s, e), crop=crop,
                               note=c.get("note", "") if gi == 0 else ""))
    inputs, fc = [], []
    for i, p in enumerate(pieces):
        inputs += ["-ss", f"{p['s']:.3f}", "-to", f"{p['e']:.3f}", "-i", clips[p["clip"]]]
        cr, vf = p["crop"], []
        if cr and cr.get("zoom", 1) > 1:
            z = cr["zoom"]
            vf.append(f"crop=iw/{z}:ih/{z}:x='min(max(iw*{cr.get('cx', 0.5)}-ow/2,0),iw-ow)'"
                      f":y='min(max(ih*{cr.get('cy', 0.5)}-oh/2,0),ih-oh)'")
        vf += ["scale=1080:1920:flags=lanczos", "fps=30", "setsar=1", "setpts=PTS-STARTPTS"]
        d = p["e"] - p["s"]
        fc.append(f"[{i}:v:0]{','.join(vf)}[v{i}]")
        fc.append(f"[{i}:a:0]aformat=sample_rates=48000:channel_layouts=stereo,asetpts=PTS-STARTPTS,volume={p['gain']:.1f}dB,"
                  f"afade=t=in:d=0.02,afade=t=out:st={d - 0.03:.3f}:d=0.03[a{i}]")
    fc.append("".join(f"[v{i}][a{i}]" for i in range(len(pieces))) + f"concat=n={len(pieces)}:v=1:a=1[v][a]")
    out = os.path.join(reel, "raw.mov")
    subprocess.run([ffmpeg_bin(), "-v", "error", "-y"] + inputs + ["-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]",
                    "-c:v", "h264_nvenc", "-preset", "p6", "-cq", "16", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le", out], check=True)
    t = 0.0
    for p in pieces:
        print(f"{t:5.1f}s  {p['clip']} {p['s']:6.2f}-{p['e']:6.2f} ({p['e'] - p['s']:4.1f}s) {p['gain']:+.1f}dB"
              f"  zoom {p['crop']['zoom']}  {p['note']}")
        t += p["e"] - p["s"]
    json.dump(pieces, open(os.path.join(reel, "build", "pieces.json"), "w"), indent=1)
    subprocess.run([sys.executable, os.path.join(HERE, "transcribe.py"), out, os.path.join(reel, "words.json")], check=True)
    ws = json.load(open(os.path.join(reel, "words.json"), encoding="utf-8"))["words"]
    print(f"\nQA transcript ({t:.1f}s) - check every line ends on a full word:\n" + " ".join(x["w"] for x in ws))
    print("\nseams at: " + ", ".join(f"{sum(q['e'] - q['s'] for q in pieces[:k]):.1f}s" for k in range(1, len(pieces))))
