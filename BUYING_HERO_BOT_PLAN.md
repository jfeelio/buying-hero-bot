# Buying Hero — Offer Intelligence Bot
## Build Plan & Progress Tracker

---

## Status Legend
- [ ] Not started
- [x] Complete
- [~] In progress

---

## Decisions Locked In

| Decision | Choice |
|---|---|
| Chat interface | WhatsApp via OpenClaw |
| AI brain | Claude (Anthropic API) |
| ARV / comps | Kiavi (local) / RentCast (server fallback) |
| Hosting | Local Windows machine (active) + DigitalOcean server (standby) |
| Version control | GitHub + GitHub CLI (HTTPS protocol) |
| Deal analysis | Replicated from "NEW VERSION Investment Calc" tab only |
| Assignment profit target | $25,000 |
| MAO formula | (78% × ARV) - Repairs - $25,000 |
| Comp strategy | RentCast pulls comps, bot estimates ARV automatically |
| Web form | GitHub Pages — built LAST after bot is complete |

---

## Pre-Configured Deal Defaults (Set Once)

These are baked into the bot from the spreadsheet and only change if your HML terms change.

| Parameter | Value |
|---|---|
| HML origination points | 1.75% |
| HML APR | 11.24% |
| HML down payment required | 10% |
| % of rehab financed by lender | 100% |
| Title fees (purchase) | $1,700 |
| Title insurance rate (purchase) | 0.60% |
| Gov. recording rate | 1.25% |
| Home inspection | $275 |
| Mobile notary | $350 |
| Survey | $545 |
| Transaction coordination | $600 |
| Utilities/month | $100 |
| Builders insurance/month | $560 |
| Property tax rate | 1% |
| HOA/month | $70 |
| Buyers agent (sale) | 3% |
| Sellers agent (sale) | 3% |
| Doc stamps rate (sale) | 0.70% |
| Title fee (sale) | $400 |
| Title insurance rate (sale) | 0.38% |
| Hold months (default) | 5 |
| Assignment profit target | $25,000 |

---

## Bot Input / Output

### Team sends to WhatsApp:
- Property address
- Rehab estimate
- Purchase price / offer (optional — bot will also calculate MAO)
- Hold months (optional — defaults to 5)

### Bot returns:
```
📍 [Address]

ARV (RentCast):         $XXX,XXX
Comps used:             [3 addresses + prices + $/sqft]

--- OFFER ---
MAO (78% - Repairs - $25K): $XXX,XXX

--- FULL DEAL ANALYSIS ---
Purchase Price:          $XXX,XXX
Rehab:                   $XX,XXX
Purchase Closing Costs:  $XX,XXX
Total Acq. (no loan):    $XXX,XXX

Hard Money Loan:         $XXX,XXX
  Interest (X months):  $X,XXX
  Origination (1.75%):  $X,XXX
Total Lending Cost:      $XX,XXX

Total All-In Cost:       $XXX,XXX

Holding Costs:           $X,XXX
Sale Closing Costs:      $XX,XXX
Net Sale Proceeds:       $XXX,XXX

--- RETURNS ---
HARD MONEY
  Out of Pocket:         $XX,XXX
  Net Profit:            $XX,XXX
  Cash-on-Cash ROI:      XX%

ALL CASH
  Out of Pocket:         $XXX,XXX
  Net Profit:            $XX,XXX
  Cash-on-Cash ROI:      XX%

VERDICT: ✅ GO / ⚠️ MARGINAL / ❌ NO GO
```

---

## Phase Checklist

### Phase 1 — GitHub Setup
- [x] Git installed
- [x] GitHub CLI installed (v2.87.2)
- [x] GitHub CLI authenticated (HTTPS)
- [x] Create private `buying-hero-bot` repository
- [x] Initialize local project folder and push first commit

### Phase 2 — DigitalOcean Droplet
- [x] Create DigitalOcean account
- [x] Spin up Basic Droplet — Ubuntu 22.04, $6/mo, NY or Atlanta region, name: `buying-hero-bot`
- [x] Note Droplet IP address
- [x] SSH into Droplet
- [x] Install system dependencies (Node.js, Python, Git)
- [x] Clone `buying-hero-bot` repo onto server

### Phase 3 — OpenClaw Installation & WhatsApp Setup
- [x] Install OpenClaw via CLI installer on Droplet
- [x] Run `openclaw onboard` wizard
- [x] Connect Anthropic API key
- [x] Link WhatsApp via QR code scan
- [x] Lock down `allowFrom` to team numbers only

### Phase 4 — System Prompt (Buying Hero Brain)
- [x] Write system prompt with Buying Hero operating parameters
- [x] Include MAO formula, rejection thresholds, South Florida context
- [x] Define structured response format
- [x] Commit to GitHub

### Phase 5 — RentCast API Integration
- [x] Create RentCast account
- [x] Get RentCast API key
- [x] Build comp-pulling logic (0.5–1 mile radius, same bed/bath, last 6 months)
- [x] Test comp results against known South Florida deals
- [x] Commit to GitHub

### Phase 6 — Deal Analysis Engine
- [ ] Replicate all formulas from "NEW VERSION Investment Calc" tab in code
- [ ] Hard-code all default parameters (HML rates, closing costs, etc.)
- [ ] Wire RentCast ARV into MAO formula
- [ ] Build full P&L output (Hard Money + All Cash strategies)
- [ ] Build Go / Marginal / No-Go verdict logic
- [ ] Commit to GitHub

### Phase 7 — Testing & Hardening
- [ ] Run 5–10 past real deals through the bot
- [ ] Verify all math matches spreadsheet exactly
- [ ] Confirm WhatsApp locked to team numbers only
- [ ] Document QR re-scan process
- [ ] Tag v1.0 on GitHub

### Phase 8 — GitHub Pages Form (Last)
- [ ] Replicate deal analysis logic as static HTML/JS form
- [ ] Host at `yourusername.github.io/buying-hero`
- [ ] Real-time calculations as team types
- [ ] Advanced panel for editing HML rates and closing cost defaults
- [ ] Mobile and desktop friendly
- [ ] Commit and deploy

---

## Monthly Cost Estimate

| Item | Cost |
|---|---|
| DigitalOcean Droplet | $6 |
| Anthropic API (Claude) | ~$10–30 |
| RentCast API | ~$20–50 |
| GitHub | Free |
| GitHub Pages | Free |
| **Total** | **~$36–86/month** |

---

## Key Files in This Repo

| File | Purpose |
|---|---|
| `CLAUDE.md` | Buying Hero operating manual — Claude's permanent instructions |
| `BUYING_HERO_BOT_PLAN.md` | This file — build plan and progress tracker |
| `Copy of Real Estate Investing Calculators.xlsx` | Source spreadsheet — deal analysis logic reference |

---

## Notes & Reminders

- RentCast does NOT pull from MLS — it uses public records + scraped listings. ARV estimates are automated but should be validated against known deals during testing.
- OpenClaw WhatsApp connection drops every few weeks — re-scan QR with: `openclaw channels login --channel whatsapp`
- All sensitive keys (Anthropic API, RentCast API) go in environment variables — never committed to GitHub.
- Partners must approve any changes to default HML rates or closing cost parameters.
