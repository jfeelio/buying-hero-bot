# List Efficiency Engine

Recreating the "deals per list" backtest Tiffany High described — for Miami-Dade,
from public data, using scrapers Buying Hero already runs.

**Status:** design only. Nothing built. Feasibility verified against live county APIs
on 2026-09-10 (numbers below are real query results, not estimates).

---

## What the tool actually does

Stripped of the hype, it is one ratio computed many times:

```
doors_per_deal  =  list_size  /  investor_deals_that_came_off_that_list
```

Four steps:

1. **Numerator** — every single-family home an investor bought in the county in the
   last 6 months. Real recorded sales.
2. **List membership** — for each of those sold homes, which lists it belonged to at
   the time it sold (absentee, probate, tax delinquent, high equity, vacant, combos).
   Each list the property was on gets credit for that deal.
3. **The ratio** — list size ÷ deals credited to it = how many doors you work per deal.
   Lower is more efficient.
4. **Rank** — each list against the county baseline, bucketed Priority 1 / 2 / 3.

Her worked example: a 1,600-record list that produced 47 deals → 1600/47 ≈ **34 doors
per deal**.

---

## Why this is worth building (and why it fixes yesterday's problem)

The ZIP Sniper audit concluded that Buying Hero's own outcome data cannot rank
anything: **16 contracts across 86 ZIPs**, every confidence interval overlapping,
~121,000 pieces needed in a single ZIP to prove it beats average.

This method fixes that by **changing the numerator**. Instead of Buying Hero's 16
contracts, it uses *every investor purchase in Miami-Dade*. Verified today:

| Query against PaGISView (943,544 parcels) | Count |
|---|---|
| Single-family parcels (`DOR_DESC LIKE '%SINGLE FAMILY%'`, code `0101`) | **387,591** |
| SFH sold since 2026-03-10 with price > $1,000 | **4,773** |
| …of those, entity-name buyer (LLC / INC / CORP / TRUST / HOLDINGS) | **1,012** |
| …of those, buyer mailing address ≠ property address | **1,494** |

**~1,000–1,500 investor purchases versus 16 contracts — a 60–90× larger sample.**
That is the difference between a ranking you can act on and the noise in the ZIP report.

Same statistical discipline still applies (see *Guardrails*).

---

## Data sources

### Confirmed working today

**Miami-Dade Property Point View (PaGISView)** — the whole parcel roll, free, no key,
ArcGIS REST, `maxRecordCount` 2,000 so paginate on `resultOffset`.

```
https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/PaGISView_gdb/FeatureServer/0/query
```

Useful fields: `FOLIO`, `TRUE_SITE_ADDR`, `TRUE_MAILING_ADDR1/CITY/STATE/ZIP`,
`TRUE_OWNER1/2/3`, `DOR_CODE_CUR`, `DOR_DESC`, `ASSESSED_VAL_CUR`, `PRICE_1`,
`DATEOFSALE_UTC`, `YEAR_BUILT`, `BEDROOM_COUNT`, `BATHROOM_COUNT`,
`BUILDING_HEATED_AREA`.

For a sale inside the window, `TRUE_OWNER1` **is the buyer** — that is how investors
get identified without any paid data.

**MDPA folio API** — per-property detail, already wrapped in
`foreclosure-agent/scrapers/mdpa.py`. Note the param names are `myAddress` / `myUnit`,
not `address` / `unit`.

```
https://apps.miamidadepa.gov/PApublicServiceProxy/PaServicesProxy.ashx
  ?Operation=GetPropertySearchByFolio&clientAppName=PropertySearch&folioNumber=<13 digits>
```

Returns `SalesInfos[]` with `DateOfSale`, `SalePrice`, **`GranteeName1/2`** (buyer),
**`GrantorName1/2`** (seller), `QualifiedFlag`, `QualificationDescription`,
`SaleInstrument`, `DocumentStamps` — plus `Benefit` (homestead exemption),
`Assessment` / `Taxable`, `MailingAddress`, `PropertyInfo`.

This matters because PaGISView carries **only the most recent sale**. If an investor
bought and flipped inside the window, PaGISView shows the flip and hides the purchase.
Enriching the 4,773 sold folios through this API recovers the true chain — 4,773 calls
is very manageable.

`QualificationDescription` is the numerator's quality filter, and it is essential.
A real chain pulled today (folio `0102000601140`, 667 NW 1 ST) returns:

```
4/16/2026   $490,000   667 FIRST LLC             Qual by exam of deed
7/22/2025   $  6,800   SILVER HILL CAPITAL LLC   Federal, state or local government agency
4/29/2022   $    100   667 NW 1 LLC              Corrective, tax or QCD; min consideration
5/31/2021   $550,000   PROPERTIESJC LLC          Qual by exam of deed
5/13/2019   $    100   JOSE A MILIAN LE          Life Estate interest
```

Only the `Qual by exam of deed` rows are genuine arms-length purchases. Quitclaims,
corrective deeds, life-estate transfers and agency transfers all carry LLC names and
would otherwise inflate the investor count. **Filter on qualification, not just price** —
a price floor alone does not catch these.

### Already scraped in this repo

| List | Where | Has dates |
|---|---|---|
| Probate (Formal Administration) | `foreclosure-agent/scrapers/probate.py` | filing date ✓ |
| Pre-foreclosure / lis pendens | `lis-pendens-agent/`, `scrapers/realforeclose.py` | filing date ✓ |
| Tax deed auctions | `foreclosure-agent/main_tax_deed.py` | auction date ✓ |

Point-in-time reconstruction works for these because each record carries a filing date.

### Still needed

- **Tax delinquent** — Miami-Dade Tax Collector. Source not yet identified.
- **Code violations / open permits** — county code enforcement open data. Not checked yet.
- **Liens** — Clerk official records.
- **Real equity** — needs recorded mortgage amounts from the Clerk. Assessed value is a
  weak proxy in Florida because Save Our Homes caps distort it badly.
- **Vacancy** — USPS vacancy is vendor-only. Cannot be reconstructed historically.
  Realistically out of scope.

---

## List tiers by buildability

**Tier A — computable county-wide from PaGISView alone, today.** No new scraping.
Absentee owner, out-of-state owner (`TRUE_MAILING_STATE <> 'FL'`), long tenure
(`DATEOFSALE_UTC` age), value bands, year built / age bands, bed-bath profile, and
every combination of those. This alone is a real MVP with a full county denominator.

**Tier B — join to lists already being scraped.** Probate, pre-foreclosure, tax deed.
Smaller lists, so they will likely land in Priority 3 on sample size until more history
accumulates — which is itself worth knowing.

**Tier C — new scrapers.** Tax delinquent, code violations, liens.

**Tier D — paid vendor or skip.** Vacancy, true mortgage equity.

---

## The attribution decision (the one real design choice)

A sold property is on many lists at once — absentee *and* high equity *and* long tenure.
Two options:

- **Single attribution** (pick one list per deal) — arbitrary, and whichever list is
  checked first gets inflated.
- **Credit every list the property belonged to** — lists overlap, deal counts are not
  mutually exclusive, and they do not sum to the total. Combos get scored as their own
  lists.

**Take the second.** It is what Tiffany describes ("every combo you can think of") and
it is the only honest version. It does mean the output cannot be read as a budget
allocation — a deal appearing under four lists is one deal, not four.

---

## The math

```
county_baseline  = 387,591 SFH / total_investor_deals
doors_per_deal   = list_size / deals_credited_to_list
lift             = county_baseline / doors_per_deal
```

Priority buckets, formalising her 1 / 2 / 3:

- **Priority 1** — lift ≥ 2× baseline **and** ≥ 10 deals credited **and** the confidence
  interval clears baseline.
- **Priority 2** — lift ≥ 1× baseline, CI clears baseline, ≥ 10 deals.
- **Priority 3** — fewer than 10 deals, *or* CI overlaps baseline. Context only.
  Explicitly not a ranking.

---

## Guardrails (carried over from the ZIP audit)

1. **Confidence interval on every ratio.** Wilson on the deal rate. A list whose
   interval overlaps the county baseline does not get a priority — it goes to Priority 3.
   This is exactly her "too small to trust yet," made explicit.
2. **Minimum 10 credited deals** before a list is ranked at all.
3. **Report list size alongside every ratio.** A great ratio on a 40-record list is
   not a strategy.

---

## Honest limitations — read before acting on the output

1. **It measures other investors' closings, not your conversion.** A list being
   efficient market-wide says nothing about your response rate on it.
2. **It is channel-blind.** A property that sold to an investor may have come from
   mail, a cold call, a door knock, an agent, or another wholesaler. The list gets
   credit regardless. This does not tell you direct mail works on that list.
3. **Correlation, not causation.** Absentee owners sell to investors more partly
   because absentee owners sell more, full stop.
4. **The most efficient list is the most competed-for.** Efficiency computed on closed
   deals is backward-looking. Every other investor in Miami-Dade can run this same
   query. Your marginal response on a hammered list may be worse than the ratio implies.
5. **"150 records, 4 contracts" is not a mail result.** That is a 2.7% contract rate on
   records — roughly 200× Buying Hero's 0.013% contracts per mail piece. A number like
   that comes from hand-working 150 doors: deep skip trace, cold calls, door knocks.
   The *list ranking* is the transferable part. The *conversion rate* is a function of
   how hard the doors get worked. Do not budget 4 contracts from 150 mailers.

---

## Build phases

| Phase | Work | Output |
|---|---|---|
| 0 | Pull the 4,773 sold SFH, enrich via folio API for grantee/grantor chain, classify investor vs retail buyer | verified numerator |
| 1 | Tier A lists county-wide, ratios + Wilson CIs, priority buckets | first real ranking |
| 2 | Join Tier B (probate / LP / tax deed) by folio and date | distressed lists scored |
| 3 | Tier C scrapers (tax delinquent, code violations) | fuller coverage |
| 4 | Output to Google Sheet + refresh on a schedule | operational |

Phase 0 + 1 is the whole idea proven. Everything after is coverage.

---

## Open questions for Jorge

1. **Investor definition.** Entity name only (1,012 deals), or entity *or* absentee
   buyer (1,494)? The wider net catches individual investors buying in their own name
   but also catches ordinary second-home buyers. Recommend running both and comparing —
   if the rankings agree, the definition does not matter much.
2. **Window.** 6 months as she describes, or 12 for tighter intervals on the small
   distressed lists? Twelve doubles the sample but blends older market conditions.
3. **Scope.** Miami-Dade only, or include Broward? Broward is a separate county API and
   roughly doubles Phase 0 work.
4. **Where does output live** — a tab in an existing sheet, or its own dashboard?
