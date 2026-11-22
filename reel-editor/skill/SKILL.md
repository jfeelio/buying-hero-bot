---
name: reel-editor
description: Edit Jorge's Instagram Reels / TikToks / Shorts after he's cut them in CapCut — Hormozi-style animated captions in Buying Hero brand (Montserrat Black, #0083CA keywords) OR the Premium style (mixed-font kinetic captions with big words behind the speaker), B-roll from Pixabay, screenshot cards (dashboards, results), list graphics, count-up stats, eased punch-in zooms, icon pops, sound effects and a progress bar — rendered to a finished MP4. Use whenever Jorge sends a video/reel file (usually a path in Downloads) and asks to edit it, caption it, "add captions", "add b-roll", "make this pop", "edit the reel", "do your thing on this video", or sends screenshots to drop into a reel. Also use to re-edit or tweak a reel already in D:\Reels. Pairs with reel-script-writer (script → film → cut → this skill).
---

# Reel Editor

Jorge films and usually cuts the reel himself in CapCut (sometimes he sends raw takes instead; see 1b). You do the "editor" pass: captions,
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

### 1b. RAW mode — when Jorge sends uncut takes instead of a final cut
Jorge sends two kinds of input: usually a **final cut** (one video he cut in CapCut → step 1 above), sometimes
**raw takes** (a folder or several clips, repeats, restarts, multiple locations). Raw mode builds the cut
first, then everything from step 2 on is the same. Code: `raw.py` (approved 2026-11-15, "dude thats actually
pretty awesome").
1. `python reel.py raw <slug> "<folder or clips>"` moves the clips to `<reel>/clips/`, transcribes each one, and
   prints each transcript with `[Ns gap]` markers plus a contact sheet per clip. **Look at the sheets** (locations,
   framing, where he stands).
2. Map the story: which lines exist, and which have **competing takes** (same line said 2+ times). Write
   `<reel>/cuts.json` (format in raw.py's docstring): a `compare` group per contested line, then the `cuts`
   list in story order. Ordering rules: hook first; you can reorder lines for flow (put payoffs and funny bits
   where they land); mix locations in the middle.
3. `python reel.py score <reel>` gives the delivery scorecard (pace, dead air, loudness, end-fade, pitch
   variation) and Gemini's blind A/B listen (gemini-3.1-pro-preview, audio only, cents per reel, key
   `Dev/carousel/.gemini_key`). Pick the winner. When the scorecard and Gemini disagree, say so and let Jorge decide.
4. **Crop:** the clips are 4K, so punch in with `"crop": {"zoom", "cx", "cy"}` on wide shots so his face reads
   on a phone (head at ~25-30% from the top; lake wide shots used 1.4-1.9). Leave walk-to-camera and already-close
   shots at 1.0. Cut OUT to wide on a scenery moment ("look at this").
5. `python reel.py assemble <reel>` writes raw.mov (1080x1920@30 from the originals) + words.json and prints
   the pieces, the seams and a **QA transcript**. Read it. Every line must end on a full word. Whisper end-times
   run early (cut ends snap to the waveform's real silence) and Whisper can invent words at the end of a take
   (check the waveform before "fixing" one). Lines that run back-to-back from the same take must be ONE cut.
   Trimmed pauses inside a take auto-punch-in 12% to hide the jump.
6. Show Jorge the cut list (time · clip · line · why this take) with the rough cut if he wants to review.
   If he said "finalize", go straight on to step 2.

### 1c. Ask: Classic or Premium style? (every reel)
Jorge wants the choice per reel (2026-11-17: "I really like this one but the previous style might be good sometimes").
Ask once, with a one-line recommendation:
- **Classic**: Hormozi captions (Montserrat Black ALL CAPS, 1-3 words), list/stat graphics, icons. Fast (~15s render).
  Best for screenshot-proof reels, deal numbers, desk/indoor shots, busy backgrounds.
- **Premium**: mixed-font kinetic captions, big words BEHIND him, whip-in lists, light color grade. ~4.5 min/min
  of video. Best when there's open sky/wall above his head (outdoor, wide or mid shots) and a story/mindset reel.
  Approved on the 11-17 nature reel ("dude that shit came out sick").
Set `"style": "premium"` in edit.json for Premium (see the Premium section). Everything else (B-roll, cards,
zooms, music, SFX) works the same in both.

### 1d. Three hooks, one winner (every reel)
Jorge 2026-11-22: borrowed from a short-form agency playbook he liked (@loganforsyth): every video gets **3 hooks**
and only the winner ships. The first ~3 seconds decide the reel, so don't bet them on one guess.
- **Write 3 hooks that each take a different angle**, not three rewordings of one line. Use one of each:
  **number** ("$260K of equity, and the house never hit the MLS"), **contrarian** ("Most bad flips aren't bad
  buys"), and **story/curiosity** ("I almost walked away from this one"). Spoken hooks stay under ~3s / 10 words.
  Facts come from the transcript or real deals only, the same rule as captions.
- **Raw mode (1b):** ask Jorge to film all 3 hook lines, so he'd film 3 opening lines instead of 1. Put them in one
  `compare` group (`"Hook"`) in cuts.json. `reel.py score` gives the delivery read and Gemini's blind pick. Show
  Jorge the 3 with the scores and let him choose. The scores are only a pre-screen; a real audience is the test.
- **Final-cut mode (1):** the spoken opening is fixed, so vary what's ON SCREEN in the first 3s instead: hook
  text (lead_in + hero over the first words, or a text card), and a cold-open B-roll or screenshot vs. his face.
  Render the variants as `output/hook_A.mp4`, `hook_B.mp4` and `hook_C.mp4`. Content-sync ignores non-vN names,
  so they won't post by accident. Copy the winner to the next vN.
- **Caption line 1 is a 4th hook.** Make it a different angle from the spoken hook that ships.
- Log the 3 hooks and which one won in `<reel>/hooks.json` (`{"A": "...", "B": "...", "C": "...", "winner": "A",
  "why": "..."}`), so we learn which angle wins for this audience over time.
- Real-audience testing with Instagram **Trial Reels** (shown to non-followers first) is NOT built yet. See the
  Hook Lab tab in the Content Ideas sheet for idea-level hooks.

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
  The shot must literally show what he's saying. Check the Pixabay page title `get`/`iget` prints:
  a "gas" search returned medical O2 regulators and electric meters before the right shot (yellow
  gas pipe). Jorge likes 4-5 full-frame cutaways per reel to "take my video out and fade in
  something else" — full mode with the default crossfade. If nothing fits, don't settle — use a list or
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
- **Audience is investors, buyers and wholesalers, never sellers.** Jorge doesn't want sellers
  finding him on IG: no "want to sell / we buy houses / DM us your property" CTAs or seller-benefit
  copy. Sellers can appear in the *story* ("a seller tried to back out"), never as the reader.
- End with ONE CTA that starts conversations with investors, rotated (or "follow for part 2").
  **CTA rotation (Jorge 2026-11-10: "not always comment DEALS").** One CTA per caption, buyers only. Before
  writing, check the Caption column of the last 3 rows in the Content Tracker (and the Carousel Pipeline) and pick
  one they didn't use. Use "DEALS" no more than about 1 post in 4. Bank (reword it freely so it fits the post):
    - Comment "DEALS" and we'll add you to the buyers list.
    - DM us your buy box (area, price range, flip or hold) and we'll send deals that match.
    - Comment the area you're buying in 👇 and we'll reach out when we have one there.
    - Follow @officialbhproperties so you see the next deal before it's gone.
    - DM us "LIST" and we'll get you our off-market deals first.
    - Want deals vetted like this one? Send us a DM and we'll add you to the buyers list.
    - Send this to the partner or lender you buy with 👇
    - NEVER "tag a buyer" (Jorge 11-15: people will never tag their buyers)
  Then 5–7 hashtags max.
- **Never invent facts** (hours slept, dollar figures, anecdotes he didn't say). Pull details
  only from the transcript, this reel's screenshots, or what he's said in earlier reels. If a
  line would need a fact you don't have, leave it out or mark it `[confirm]`.
- Don't round numbers up past what the screenshot shows (a "~" is fine: $595,906 → ~$600K).

### 7. Deliver
Run `python "C:/Users/jsive/Dropbox/J Feels/Dev/content-sync/content_sync.py" --scan` once the version
and caption.txt are final. That adds/updates the Content Tracker row and uploads the MP4 to GHL media, which is
what the cloud scheduler posts from. Re-run it after every new version (v2, v3…).
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
("WE ALMOST LOST" / "$115,000") — he specifically liked that. The default stack (lead-in y=1150) can land on his chin/mouth, worse under a zoom: check the frame and set `"lead_in_y": 1260` (hero follows 190px below) and stat `"y": 1360` when it does (11-15 reel).

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
Keep item text short (2–4 words). **Rapid-fire lists:** when he rattles off a long string (6-8 things), list EVERY item, each popping on its word: `"row_h": 112, "y": 1230` keeps 7 rows under his face (Jorge 11-15: "listed them all really fast... drives the point home"). Default y=1150 keeps his face visible; in wide shots where he
stands back from the camera, push it lower (y≈1350) so it stays under his face — check the frame.

**Stats:** big brand-blue count-up for a headline number (`value`, `prefix`/`suffix`,
optional `label`). Use for at most 1–2 numbers per reel; alternate with the hero+lead_in
treatment across reels.

**Screenshot cards:** when his face fills the upper frame, place cards at `"y": 420` with
`"max_h": 560` (logo ~520) so they sit above his eyes. Wide documents (permit records, forms)
render as strips but stay readable at full size — check at phone scale, crop to the key rows.

**Headshot stickers** (shoutouts): `"mode": "sticker"` with a cut-out PNG (flood-fill the white
page off first), `"label"`, optional `"sub"`, `"x"`/`"y"`. In the wide desk shot, x≈230 / 850,
y≈760, `max_w` 330 keeps both clear of his face. **Edge safety:** Edits/IG trim a few px off the
edges. On the 10-30 reel the pills hung 6px past the frame and the "V" and "ES" got cut on the live
post. render.py now keeps every card/sticker pixel 60px (`SAFE`) inside the frame and prints when
it moves one. If it moves a sticker onto his face, shrink `max_w` rather than ignoring it.

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

## Premium style (`"style": "premium"`)
`reel.py build` renders a clean pass (B-roll, cards, stickers, zooms, music, SFX, progress, and icons if
listed; no captions and no classic lists), then `premium.py` cuts him out of every frame (RVM matting,
CPU ~9 fps, cached in build/matte.mp4, so caption-only re-renders are ~1.5 min) and draws the text. Spec goes in
`edit.json` → `"premium"` (full reference in premium.py's docstring):
```json
"style": "premium",
"premium": {
  "serif": [3, 19], "serif_blue": [57], "key": [9, 34], "big": [80],
  "lists": [{"words": [37, 39, 41, 43]}],
  "heroes": [
    {"lines": [{"text": "HOARDER", "word": 21}, {"text": "HOUSE.", "word": 22}], "x_at": 6.85},
    {"lines": [{"text": "GET YOUR", "word": 166}, {"text": "MIND", "word": 168}, {"text": "RIGHT.", "word": 169}],
     "glitch": true, "end": 99}
  ]
}
```
Captions auto-chunk (punctuation, gaps, 5 words max). Use `"breaks": [i]` to force a split.
Jorge-approved rules (11-17):
- **Heroes (behind him): 4-6 per reel**, on the punch words of the hook, the turn and the close. ALWAYS white
  Anton (brand blue disappeared on sky/lake). They hold ≥1.9s after the last line (automatic). He said 0.8-1.4s
  "goes away way too quickly". The last hero can hold to the end (`"end": 99`) with `glitch`.
- A crossed-out idea gets `x_at`. The X draws BEHIND him too. He called out an X in front of his face, so never
  draw anything over his face.
- Heroes only work when there's space above his head. Check the strip: a close-up with his head at the top of
  the frame leaves no room, so skip heroes there or put them on wider shots.
- Captions: sentence case Montserrat ExtraBold. `key` = bright brand-blue UPPERCASE (about 1 per sentence),
  `serif` = elegant italic on feeling/abstract words (wondering, beautiful, challenges), `serif_blue` on a few
  payoff words, `big` = one oversized serif word alone (1-2 per reel).
- Lists (`premium.lists`): rapid-fire enumerations. Each word whips in big, alternating Anton/serif, all white.
  Keep the classic list's pop SFX timed to each word.
- Grade `"light"` is the default. The first grade was too dark ("whole reel looks too dark"), so don't go moodier.
- Classic `icons` usually clash with the premium look; leave them out unless Jorge asks.
- Delivery is the same: highest vN (or final*) in output/ is what content-sync posts.

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
- **Cutting a bad edit out of his video** (dead air / jump): find the silent span with an
  0.1s loudness scan, re-encode raw.mov without it (keep `raw_original.mov`), then shift every
  time in words.json and edit.json after the cut by its length. Keep word indices unchanged
  (edit.json points at them); re-transcribe only to confirm the words around the cut.
- **Windows Smart App Control (on, enforcing since Oct 2026) blocks faster-whisper's native libs**
  (ctranslate2, PyAV): "An Application Control policy has blocked this file". `transcribe.py`
  falls back automatically to `transcribe.js` (transformers.js on Microsoft's signed ONNX Runtime,
  `onnx-community/whisper-large-v3-turbo_timestamped`, ~40-75 s on CPU). Don't try to disable SAC
  (it's permanent) and don't run Whisper on the n8n VM (2 vCPU / ~1 GB free — would starve n8n).
- Jorge may create the reel folder himself (e.g. `D:\Reels\2026-10-23 - Permit Busters\` with the
  .mp4 + PNGs loose). Then skip `reel.py new`: move PNGs into screenshots/, remux the video to
  raw.mov with ffmpeg `-c copy`, run `python transcribe.py <reel>/raw.mov <reel>/words.json`.
- Pexels API keys are paused — Pixabay key is in `reel-editor/.pixabay_key` (gitignored).
  Pixabay asks that searches be cached 24h (broll.py does this in `.cache/`).
- ffmpeg isn't on PATH in older shells; render.py/reel.py locate the WinGet install themselves.
  For ad-hoc ffmpeg in bash: `export PATH="$PATH:$(ls -d /c/Users/jsive/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg*/ffmpeg-*/bin | head -1)"`.
- Rendering uses `h264_nvenc` (RTX 4070). ~15s for a 90s reel (classic). Premium: matte ~3 min/min, render ~1.5 min/min.
- Premium needs `onnxruntime` (CPU; installed) and downloads the 15 MB RVM model to `.cache/` on first use
  (github.com/PeterL1n/RobustVideoMatting releases, GPL-3.0; it's used as a tool, not redistributed).
- A **Scheduled** tracker row is frozen: a new version won't replace it. To swap the file: set Status = Draft →
  `content_sync.py` (unschedules) → `--scan` (uploads) → Status = Approved → `content_sync.py`, then verify the
  GHL post's media URL.
- Code changes: commit from a scratchpad clone of github.com/jfeelio/buying-hero-bot with
  `-c user.name=Jorge -c user.email=jorge@buyinghero.com`; never commit sfx/, .pixabay_key,
  node_modules/, work/ or any reel content.
