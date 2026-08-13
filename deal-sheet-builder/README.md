# Buying Hero — Deal Sheet

A Google Sheet replication + improvement of the existing Deal Analyzer at <https://jfeelio.github.io/buying-hero-bot/>. Two tabs:

- `⚙️ Config` — global defaults (MAO %, assignment target, min spread, APR, etc.). Editable yellow cells. Changes cascade to every deal tab via named ranges.
- `🏠 Deal Calculator` — the main calculator. Use this directly OR duplicate it (via menu/bot) to spawn a per-deal tab named after the property address.

## Setup

### 1. Build the sheet structure (one-time)

Already done if you ran `python build_sheet.py`. Sheet:
<https://docs.google.com/spreadsheets/d/16of8fZhqeYlF_UzBWX3GoYiIOZJKT6F57JhzvKV5s0g/edit>

Re-run anytime to rebuild Config + Deal Calculator (won't touch existing per-deal tabs you've already created).

### 2. Install the Apps Script

1. Open the sheet → **Extensions → Apps Script**
2. Replace any existing `Code.gs` with the contents of `apps_script.gs`
3. Save (Ctrl+S), authorize when prompted
4. Reload the sheet — a **🏠 Buying Hero** menu appears top right

### 3. (Optional) Deploy as Web App for bot integration

Only needed if you want the **Create Deal Tab** button in `docs/index.html` to work.

1. Apps Script: **Deploy → New deployment → Web app**
2. Execute as: **Me**, Who has access: **Anyone**, click **Deploy**
3. Copy the Web app URL → paste into `docs/index.html` `WEB_APP_URL`
4. Commit + push

## How to use it

### From the sheet
- **🏠 Buying Hero → ➕ New Deal from Address…** — prompts for an address, duplicates the Deal Calculator, names the new tab after the address, fills in the address bar + date.
- You then fill in Purchase / Rehab / ARV in the yellow cells. Everything else auto-calculates.
- Each per-deal tab keeps its own numbers forever. The Deal Calculator stays clean as your template.

### From the bot
- Open <https://jfeelio.github.io/buying-hero-bot/>
- Run your numbers
- Type the property address in **💾 Save Deal to Google Sheet** field
- Click **Create Deal Tab** — opens the new pre-filled tab in a new window

### Changing global defaults
- Open `⚙️ Config`, edit any yellow cell. Updates propagate to every existing and future deal tab.
- To override a default for a single deal, just type the value in that deal's yellow input cell.

## What's on every deal tab

1. **🏠 Address bar** (set from the menu/bot)
2. **📐 Deal Inputs** — Purchase, Rehab, Hold, ARV, Sqft
3. **🎯 MAO Analysis** — auto-computed MAO using `Config!B5` (your editable MAO %), GO/NO-GO badge
4. **💰 Net Profit + ROI** — big color-coded number (green ≥$25K · amber $12–25K · red <$12K)
5. **🛡️ Underwriting Gate (5 checks from CLAUDE.md):**
   - Spread ≥ Min Threshold ($12K default)
   - Net Profit ≥ Assignment Target ($25K default)
   - Purchase ≤ MAO
   - Rehab $/sqft sanity
   - ARV verified externally (manual dropdown)
6. **⚙️ Parameters** — Assignment Target, Origination Points, APR, Down % (pull from Config, overrideable)
7. **💵 Purchase Closing Costs**
8. **🏦 Hard Money Loan** (loan amount, interest, origination, appraisal, other)
9. **📅 Holding Costs** (utilities/insurance/HOA per month × hold + auto property tax)
10. **🏷️ Sale Closing Costs** (commissions, doc stamps, title)
11. **📊 MAO Sensitivity** at 70/72/74/76/78/80%
12. **⚠️ Rehab Overage Stress Test** — net profit at +$0/$5K/$10K/$15K/$20K rehab
13. **📞 Buyer Interest Log** — track 48-hour velocity rule
14. **🔍 Due Diligence Checklist** — title, permits, code violations, taxes, HOA, occupancy (dropdowns)
15. **🔗 Comp Links** — pre-filled Kiavi / Zillow / Redfin / MDC Property Appraiser / Google search
16. **📝 Notes**

## Files

- `build_sheet.py` — re-runnable sheet builder (Python + service account)
- `apps_script.gs` — Apps Script for the menu + web app endpoint
- `README.md` — this file

Service account credentials are read from `../foreclosure-agent/credentials.json`.
