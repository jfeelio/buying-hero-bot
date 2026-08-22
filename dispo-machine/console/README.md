# Dispo Deal Console

<https://automations.buyinghero.com/dispo/>

One page, two states. The dispo manager fills in a deal, gets back drafts plus
the buyer list they will go to, edits anything they want, and fires the blast
from the same screen.

## Working on it

```bash
npm install          # once — jsdom, for the tests
python build.py      # index.src.html + assets/ -> dist/index.html
npm test             # headless: smoke + contract
bash deploy.sh       # build, test, ship to the VM
```

**Edit `index.src.html`, never `dist/index.html`.** The build inlines the fonts
and logo as `data:` URIs so the result is one self-contained file — Caddy serves
it as a static file with no CDN access.

Open `dist/index.html` in a browser directly to look at it; add `?demo=1` to run
the full flow against mock data with no network calls and nothing that sends.

## Contract with n8n

| | |
|---|---|
| `POST /webhook/dispo-intake` | body = the 26 form fields, keyed on their **exact labels**. Returns the review payload. → W1 `03-dispo-intake` |
| `POST /webhook/dispo-send` | body = the edited messages + which segments are on. → W2 `05-send-teaser-blast` |

Both live in `../../crm-transition/n8n-workflows/`. The URLs are the only
configurable thing and sit in `CONFIG` at the top of the script block.

Three things must stay in lockstep across the two sides:

1. **Form field labels** — `name="Living Area Sqft"` is what W1 maps on.
2. **Segment labels** — `Warm list`, `InvestorBase Matched`,
   `General cold`. W2's `SEG_BY_LABEL` maps these back to the internal keys
   (`warm`, `geo_cold`, `general_cold`).
3. **The review payload shape** — mirrored by `MOCK_REVIEW` in the source.

`contract-test.js` fails on all three. Re-capture the fixture after any W1
change:

```bash
curl -s -X POST https://automations.buyinghero.com/webhook/dispo-intake \
  -H 'Content-Type: application/json' -d @fixtures/sample-deal.json \
  -o fixtures/live-intake.json
```

## Design notes

- **Nothing sends without two clicks.** The send bar asks, lists the segments
  it is about to text, and only then goes.
- **Scrolling is wrapped in try/catch.** A cosmetic failure inside a promise
  handler would otherwise fall through to the catch and report a *successful*
  blast as a failure.
- **Textareas are uncontrolled.** Their values are read at send time, so typing
  never triggers a re-render and never steals focus.
- **SMS segment math is shown live.** One emoji drops the budget from 160
  characters to 70, which matters at 600 recipients.
- The design came from claude.ai; it was rebuilt here as plain HTML/CSS/JS so it
  can be edited directly instead of re-encoded into a 693 KB artifact bundle.
  The visual result is unchanged — every style was inline to begin with.
