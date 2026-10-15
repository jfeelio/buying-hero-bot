"""Build Hormozi-style ASS captions from words.json + edit.json.

edit.json keys used here:
  merge:    [[i, j], ...]        join word i..j into one token (e.g. "$115" ",000")
  replace:  {"i": "text"}        fix a transcription error
  emphasis: [i, ...]             brand-blue keyword
  hero:     [i, ...]             shown alone, bigger, blue, with a punch-in
  lead_in:  {"hero_i": [i, ...]} words stacked above a hero ("ALMOST LOST" / "$115,000")
"""
import json, sys

W, H = 1080, 1920
FONT = "Montserrat Black"
BLUE = "&H00CA8300&"   # #0083CA in ASS BGR order
WHITE = "&H00FFFFFF&"
SIZE, HERO_SIZE = 118, 200
Y = 1300               # caption baseline-centre; sits on the chest, clear of the face
MAX_WORDS, MAX_CHARS, GAP_BREAK = 3, 16, 0.35


def ts(t):
    t = max(t, 0)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def tokens(words, edit):
    merged = {i: j for i, j in edit.get("merge", [])}
    out, i = [], 0
    while i < len(words):
        j = merged.get(i, i)
        text = "".join(w["w"] for w in words[i:j + 1])
        text = edit.get("replace", {}).get(str(i), text)
        out.append({"i": i, "w": text, "s": words[i]["s"], "e": words[j]["e"]})
        i = j + 1
    return out


def chunk(toks, hero, lead_words):
    chunks, cur = [], []
    for k, t in enumerate(toks):
        if t["i"] in lead_words:
            if cur and cur[-1]["i"] not in lead_words:
                chunks.append(cur); cur = []
            cur.append(t)
            continue
        if t["i"] in hero:
            if cur: chunks.append(cur)
            chunks.append([t]); cur = []
            continue
        if cur:
            text_len = sum(len(x["w"]) + 1 for x in cur) + len(t["w"])
            gap = t["s"] - cur[-1]["e"]
            if len(cur) >= MAX_WORDS or text_len > MAX_CHARS or gap > GAP_BREAK:
                chunks.append(cur); cur = []
        cur.append(t)
        if t["w"][-1] in ".,?!":
            chunks.append(cur); cur = []
    if cur: chunks.append(cur)
    return chunks


def clean(w):
    return w.upper().rstrip(".,")


def build(words_path, edit_path, out_path):
    words = json.load(open(words_path, encoding="utf-8"))["words"]
    edit = json.load(open(edit_path, encoding="utf-8"))
    emph, hero = set(edit.get("emphasis", [])), set(edit.get("hero", []))
    lead_in = {int(k): v for k, v in edit.get("lead_in", {}).items()}
    lead_words = {i for v in lead_in.values() for i in v}
    toks = tokens(words, edit)
    by_i = {t["i"]: t for t in toks}
    chunks = chunk(toks, hero, lead_words)

    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Cap,{FONT},{SIZE},{WHITE},{WHITE},&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,7,4,5,40,40,0,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    # list / stat graphics replace the captions while they're on screen
    mutes = [(g["start"], g["end"]) for g in edit.get("lists", []) + edit.get("stats", [])]
    for n, c in enumerate(chunks):
        start = c[0]["s"]
        nxt = chunks[n + 1][0]["s"] if n + 1 < len(chunks) else c[-1]["e"] + 0.6
        end = nxt if nxt - c[-1]["e"] < 0.6 else c[-1]["e"] + 0.25
        if any(start < b and c[-1]["e"] > a + 0.1 for a, b in mutes):   # any spoken overlap
            continue
        end = min([end] + [a for a, b in mutes if a > start])          # never run under a graphic
        is_hero = len(c) == 1 and c[0]["i"] in hero
        pop = (r"\fscx70\fscy70\t(0,90,\fscx112\fscy112)\t(90,160,\fscx100\fscy100)" if is_hero
               else r"\fscx85\fscy85\t(0,80,\fscx100\fscy100)")
        # long hero words shrink to stay inside the frame (~0.47 * size px per glyph)
        hero_size = min(HERO_SIZE, int(980 / (0.47 * len(clean(c[0]["w"]))))) if is_hero else 0
        size = rf"\fs{hero_size}" if is_hero else ""
        parts = []
        for t in c:
            col = BLUE if (t["i"] in emph or t["i"] in hero) else WHITE
            parts.append(rf"{{\c{col}}}{clean(t['w'])}")
        y = Y - 150 if all(t["i"] in lead_words for t in c) else Y
        text = rf"{{\pos({W // 2},{y}){size}{pop}}}" + " ".join(parts)
        if is_hero and c[0]["i"] in lead_in:
            # lead-in stays put (no pop) on the line above; only the hero punches in
            lead = " ".join(clean(by_i[i]["w"]) for i in lead_in[c[0]["i"]])
            lines.append(f"Dialogue: 0,{ts(start)},{ts(end)},Cap,,0,0,0,,"
                         rf"{{\pos({W // 2},{Y - 150})}}{lead}")
            text = rf"{{\pos({W // 2},{Y + 40}){size}{pop}}}" + " ".join(parts)
        lines.append(f"Dialogue: 0,{ts(start)},{ts(end)},Cap,,0,0,0,,{text}")
    open(out_path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"{len(chunks)} caption chunks -> {out_path}")


if __name__ == "__main__":
    build(*sys.argv[1:4])
