# UI design prompt — Dispo Deal Console

Paste the block below into claude.ai to design the page. The constraints at the
end are what make the result deployable to `automations.buyinghero.com/dispo/`
rather than a mockup that has to be rebuilt.

---

Build a single self-contained HTML page called the **Buying Hero Dispo Deal Console**.

## Who uses it

The disposition manager at a South Florida real-estate wholesaling company. He
opens this on a laptop or phone right after locking up a house, fills in the
deal, and within seconds gets back a ready-to-post listing plus the list of cash
buyers it will go to. He uses it several times a week under time pressure. It is
an internal operations tool, not a marketing site — dense, fast and legible
beats spacious and decorative.

## The page has two states

**State 1 — Intake.** A form, grouped into sections. Do not render 26 fields as
one long column.

*Property*
- Address (text, required, full address e.g. `2165 NW 58th St. Miami, FL 33142`)
- County (dropdown: Miami-Dade, Broward, Palm Beach, St. Lucie, Martin, Indian River, Monroe, Collier, Lee, Orange, Osceola, Hillsborough, Pinellas, Polk, Other)
- Neighborhood (dropdown, ~87 Miami-Dade/Broward/Palm Beach sub-markets, optional)
- Property Type (dropdown: SFR, 2-4 Unit, 5+ Unit, Condo, Land)
- Beds · Baths · Living Area Sqft · Lot Size Sqft · Year Built (numbers)

*Condition & highlights*
- Headline (text, required — the single biggest selling point, e.g. "New Roof plus Impact Windows and Doors")
- Roof Age · AC Age (short text, blank means unknown)
- Key Upgrades (textarea)
- HOA · Liens or Violations (short text)
- Occupancy (dropdown: VACANT AT CLOSE, Vacant Now, Tenant Occupied, Owner Occupied, Occupancy Unknown)
- Extra Highlights (textarea, one per line)

*Numbers*
- Asking Price · ARV · Repair Estimate · Escrow (currency, Escrow defaults to 10000)
- Close Date (date)

*Comps & media*
- Comps (textarea, one per line, e.g. `1846 NW 49 ST, Miami, FL 33142 - Sold for $480,000 on 7/10/26`)
- Photos Videos URL (url, required)

*Notes*
- Access Notes · Additional Details (textareas, optional)

Address, Headline and the three numbers deserve visual prominence — they drive
everything downstream.

**State 2 — Review.** Replaces the form on the same page after submit. Never a
separate page.

- A clear, calm banner: **nothing has been sent yet, these are drafts**
- Deal header: the address, and whether the record was created or updated
- **Four segment stat tiles** with counts. These decide which script each buyer
  gets: `1 Inquired` (asked about this property — hottest) · `2 Warm list`
  (existing relationships) · `3 Geo-matched cold` (sourced within ~2 miles of
  this address) · `4 General cold` (sourced for a different deal)
- Source breakdown (BH Main / InvestorBase / InvestorLift / Referral) and how
  many were imported in the last 2 hours
- **WhatsApp post** — monospace, preserves line breaks exactly, with a working
  **Copy** button. This gets pasted into a WhatsApp group verbatim, so the block
  must be visually unmistakable and easy to select. Sample content:

```
🏠 *2165 NW 58th St. Miami, FL 33142*

⭐New Roof plus Impact Windows and Doors

🟠 *Details*
 · Beds/Bath: 2/1
 · Living Area: 805 sq ft
 · Lot Size: 6,345 sq ft
 · Roof is 3 years old
 · AC age unknown
 · NO HOA
 · *VACANT AT CLOSE*

🟠 *Comps*
 · 1846 NW 49 ST, Miami, FL 33142 - Sold for $480,000 on 7/10/26

💰 *Price:* Only $335,000

📈 *ARV:* ~$450,000

💵 *Escrow:* $10,000
```

- **Teaser SMS** — an *editable* textarea, pre-filled. This is the first cold
  touch and deliberately contains no street address. Label it so that's obvious.
- **SMS post** — what auto-sends after a buyer replies. Read-only, collapsible.
- **Buyer tables**: *Included* (name, tier VIP/A/B/C, segment, source, phone) ·
  *Excluded* (with the reason a human set) · *Worth a call* (buyers whose old
  notes disagree with this deal — they still get it, but should be confirmed)
- **Voice AI brief** — collapsible
- A primary **Send teaser to N buyers** button. Visually the most important
  element on the page, and clearly distinct from everything else, because it
  sends real text messages.

## Visual direction

Match the company's existing internal tooling:

- Ink `#0f172a`, secondary text `#64748b`, muted `#94a3b8`
- Surfaces `#ffffff`, `#fafbfd`, `#f1f5f9`, borders `#e2e8f0`
- Primary `#1d4ed8`, tints `#eff6ff` / `#bfdbfe`
- Green `#4ade80` on `#f0fdf4` · amber `#fbbf24` on `#fffbeb` · red `#f87171` on `#fff1f2`
- System font stack: `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`

Confident and quiet. No gradients, no decorative illustration, no emoji in the
interface chrome (emoji inside the post content is real data and must render
as-is). Everything left-aligned. Must work on a phone.

## Hard constraints — these decide whether it can ship

1. **One self-contained `.html` file.** All CSS and JS inline.
2. **No external requests at all** — no CDN scripts, no Google Fonts, no remote
   images or icons. Use system fonts and inline SVG only.
3. **Do not make any network calls.** On submit, hide the form and show the
   review state populated with realistic mock data. The real backend is wired
   in later.
4. **Keep the field labels exactly as written above** and set each input's
   `name` attribute to that exact label (e.g. `name="Living Area Sqft"`). The
   backend maps on those strings.
5. Put the review state's mock data in **one clearly-marked JS object near the
   top** so it can be swapped for a live response.
6. Responsive; wide tables scroll inside their own container rather than
   forcing the page to scroll sideways.
7. Light theme only.
