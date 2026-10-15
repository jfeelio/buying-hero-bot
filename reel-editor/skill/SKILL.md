---
name: reel-editor
description: Edit Jorge's Instagram Reels / TikToks / Shorts after he's cut them in CapCut — Hormozi-style animated captions in Buying Hero brand (Montserrat Black, #0083CA keywords), B-roll from Pixabay, screenshot cards (dashboards, results), list graphics, count-up stats, eased punch-in zooms, icon pops, sound effects and a progress bar — rendered to a finished MP4. Use whenever Jorge sends a video/reel file (usually a path in Downloads) and asks to edit it, caption it, "add captions", "add b-roll", "make this pop", "edit the reel", "do your thing on this video", or sends screenshots to drop into a reel. Also use to re-edit or tweak a reel already in D:\Reels. Pairs with reel-script-writer (script → film → cut → this skill).
---

# Reel Editor

Jorge films and cuts the reel himself in CapCut. You do the "editor" pass: captions,
emphasis, B-roll, screenshots, graphics, zooms, SFX. Output is an MP4 he opens in CapCut
for music (trending audio must be added in-app) and posts.

Code: `C:\Users\jsive\Dropbox\J Feels\Dev\reel-editor\` (run everything from there).
Reels: `D:\Reels\<YYYY-MM-DD>-<slug>\` — raw.mov, screenshots/, assets/, words.json,
edit.json, captions.ass, output/, build/. D: is NOT backed up and is outside Dropbox.
**Never put video or screenshots in Dev** — Dev is pushed to a public GitHub repo.

## Workflow

### 1. Intake
- Jorge gives file paths (usually `C:\Users\jsive\Downloads\...`) and/or pastes screenshots
  into chat (pasted images live in the session's temp `images\` folder — copy those, don't move).
- Pick a short slug from the topic (e.g. `attorney-mvp`). Then:
  `python reel.py new <slug> "<video>" ["<screenshot>" ...]`
  This moves the files in (Downloads stays clean), transcribes on the GPU (~25s), prints the
  indexed transcript `i:word@start`.
- Read the transcript properly. Fix Whisper splits with `merge`/`replace`
  (e.g. `$115` + `,000` → `$115,000`).

### 2. Check what recent reels used — then do something different
`python reel.py history` — Jorge explicitly wants graphics to **change per reel so they're
never the same**. If the last reel used an `x/slide/dim` list, use another style/entrance/panel
this time. Alternate money moments between a hero caption with lead-in and a count-up stat.

### 3. Write the edit plan and get approval BEFORE rendering
Show a compact table: time · what he says · treatment. Cover hero words, lists/stats, B-roll
picks (describe the actual shot), screenshot placement + crop, zooms, icons. Re-rendering is
cheap (~15s) but a wrong concept wastes his review time. Wait for "go" / edits.

### 4. Gather assets
- **B-roll:** `python broll.py search "<query>" <reel>/build` (videos) or `isearch` (vertical
  photos — often better for niche concepts). Each writes a contact sheet; **look at it** and
  pick by ID, then `python broll.py get <id> <reel>/assets/<name>.mp4` / `iget ... .jpg`.
  The shot must literally show what he's saying. If nothing fits, don't settle — use a list or
  stat graphic or just stay on his face. (He rejected "a bunch of documents" for "dirty title".)
- **Screenshots:** view each one, decide the crop box in pixel coords around the number/area
  that proves the claim, place it as a `card` overlay timed to when he says it.
  **Privacy check every time:** no seller names, addresses, phone numbers, emails, folio
  numbers or anything identifying in the visible crop. If unavoidable, tell Jorge and crop
  tighter or ask for a redacted screenshot. Reputation compounds.

### 5. Write `edit.json`, build, QA
`python reel.py build <reel> v1` → captions + render + copies `<reel-folder>_v1.mp4` to Downloads.
Then `python reel.py frames <reel> v1 <t> <t> ...` and **look at the strip** at every graphic,
card, hero and B-roll moment. Check: nothing covering his eyes, text inside the frame,
captions not colliding with graphics. Fix and re-render before handing it over.

### 6. Write the post caption
Every reel gets a long Instagram caption saved to `<reel>/caption.txt` and pasted in chat
(Jorge asked for "a nice and long caption that will keep folks reading"):
- **Line 1 is a second hook** that stands alone above "…more" (a bet, a number, a contrarian claim).
- 200–350 words of short paragraphs (1–3 lines each) with white space: story → proof
  (numbers exactly as the video/screenshot supports them) → the messy/real part → the lesson.
- Use → arrows or 1️⃣2️⃣3️⃣ to mirror any list in the video.
- End with a CTA that starts conversations: comment a word/emoji, or "follow for part 2".
  Then 5–7 hashtags max.
- **Never invent facts** (hours slept, dollar figures, anecdotes he didn't say). Pull details
  only from the transcript, this reel's screenshots, or what he's said in earlier reels. If a
  line would need a fact you don't have, leave it out or mark it `[confirm]`.
- Don't round numbers up past what the screenshot shows (a "~" is fine: $595,906 → ~$600K).

### 7. Deliver
Tell him the Downloads path and summarize what was added (with timestamps) and anything you
chose not to do and why. Paste the caption. Iterate as v2, v3… in the same folder.

## Style rules (Jorge-approved — keep these)

**Caption height — don't "fix" for Instagram's overlay.** GHL's Social Planner preview draws the
post caption over several lines and makes burned-in captions look covered. That preview is NOT
accurate: on Jorge's live Reels the post caption shows only one line. He rejected moving captions
up because they then cover his face. Keep the positions below.

**Captions** (captions.py): Montserrat Black, ALL CAPS, 1–3 words per chunk, white with thick
black outline, centered on the chest (y≈1300). Keywords → brand blue via `emphasis`
(roughly one per sentence: numbers, money, pain words, roles, key nouns). 3–6 `hero` words per
reel shown alone and big. Use `lead_in` to stack set-up words over a hero number
("WE ALMOST LOST" / "$115,000") — he specifically liked that.

**Zooms:** max 3–4 per reel, never two within ~8s, eased (render.py does the easing). He
called out "a lot of zooming jumps" when there were 6. Save them for the hook and the
biggest moments.

**B-roll:** 1.5–2.5s each, full-frame, roughly one per 10–12s at most. 0.25s crossfade in/out
is the default (he found hard cuts not smooth enough). **No whoosh on B-roll cuts** — he
didn't like a sound before every B-roll.
Center-cropped from 16:9 — check the subject survives the crop (set `from` to skip to a
better moment of the clip).

**List graphics** — use whenever he enumerates 2–4 things. Each item appears exactly when he
says it; captions are auto-muted underneath. Rotate across reels:
- `style`: `x` (red ✕ — mistakes, deal-killers) · `check` (blue ✓ — wins, what to do) ·
  `numbered` (1-2-3 — steps, reasons)
- `entrance`: `slide` · `pop` · `drop`
- `panel`: `dim` (whole frame darkens) · `pills` (dark pill behind each row, face stays bright)
Keep item text short (2–4 words). Default y=1150 keeps his face visible; in wide shots where he
stands back from the camera, push it lower (y≈1350) so it stays under his face — check the frame.

**Stats:** big brand-blue count-up for a headline number (`value`, `prefix`/`suffix`,
optional `label`). Use for at most 1–2 numbers per reel; alternate with the hero+lead_in
treatment across reels.

**Icons:** 3–4 Lucide badges per reel beside his head (x=900, y=960), on concrete nouns
(contract → file-text, attorney → scale, money → dollar-sign, legal → shield-check, house,
key-round, search). New icons: `curl -sSf -o icons/<name>.svg
https://cdn.jsdelivr.net/npm/lucide-static@0.460.0/icons/<name>.svg` (ISC license).

**SFX** (`sfx/`, Mixkit free license — previews downloaded locally, never commit them):
SFX are for a few beats, not every cut: `pop_light` 0.18 on icons · `pop_hard` 0.22 on list
items · `pop_long` 0.4 on a hero · `money_bag` 0.9 or `coins` on money. Voice must always
dominate. Whooshes (`whoosh_fast`/`whoosh_air`/`whoosh_transition`, use `peak:true`) and
`impact` exist but use at most one per reel, on a genuine big reveal — never as a B-roll habit.

**Progress bar:** on by default (`"progress": true`).

## edit.json reference
```json
{
  "merge": [[147, 148]], "replace": {"147": "$115,000"},
  "emphasis": [2, 15, 17], "hero": [92, 101, 147], "lead_in": {"147": [144, 145, 146]},
  "overlays": [
    {"start": 6.3, "end": 8.8, "file": "assets/signing.mp4", "mode": "full", "from": 1},
    {"start": 49.0, "end": 52.0, "file": "screenshots/dash.png", "mode": "card", "crop": [x, y, w, h], "y": 760}
  ],
  "lists": [{"start": 19.4, "end": 28.6, "style": "x", "entrance": "slide", "panel": "dim",
             "items": [{"t": 19.52, "text": "Heirs won't sign"}, {"t": 20.88, "text": "Dirty title"}]}],
  "stats": [{"start": 48.0, "end": 51.8, "value": 115000, "prefix": "$", "label": "We almost lost"}],
  "zooms": [{"start": 3.52, "end": 5.9, "scale": 1.06}],
  "icons": [{"t": 34.84, "icon": "scale"}],
  "sfx": [{"t": 48.62, "file": "sfx/money_bag.mp3", "vol": 0.9}],
  "progress": true
}
```
Word indices come from `reel.py words`. Times are seconds in the raw video.
Don't put a hero caption and a stat on the same moment — pick one.

## Gotchas
- Pexels API keys are paused — Pixabay key is in `reel-editor/.pixabay_key` (gitignored).
  Pixabay asks that searches be cached 24h (broll.py does this in `.cache/`).
- ffmpeg isn't on PATH in older shells; render.py/reel.py locate the WinGet install themselves.
  For ad-hoc ffmpeg in bash: `export PATH="$PATH:$(ls -d /c/Users/jsive/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg*/ffmpeg-*/bin | head -1)"`.
- Rendering uses `h264_nvenc` (RTX 4070). ~15s for a 90s reel.
- Code changes: commit from a scratchpad clone of github.com/jfeelio/buying-hero-bot with
  `-c user.name=Jorge -c user.email=jorge@buyinghero.com`; never commit sfx/, .pixabay_key,
  node_modules/, work/ or any reel content.
