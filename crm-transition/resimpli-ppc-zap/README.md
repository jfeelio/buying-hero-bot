# Bolt Deals (PPC) → Lead Performance Sheet

Every lead from the **Bolt Deals** PPC number lands in a Google Sheet flagged
Qualified / Unqualified / Pending, so the PPC vendor optimises on lead *quality*
rather than lead *count*.

- **Sheet:** [Buying Hero Bolt Deals Lead Performance](https://docs.google.com/spreadsheets/d/1DWoTMtTO83CSRF4XPSoF-baOI9S-p65ELgTVeBMOxsM/edit)
- **Tabs:** `Leads` (vendor-facing, gid=0, 21 cols) · `Raw Payloads` (diagnostic)
- Both tabs are built, formatted, and colour-coded. Qualification column is
  conditionally formatted green / red / amber.

## The blocker

REsimpli allows **one outgoing webhook**, and it is already taken:

| | |
|---|---|
| Friendly Name | Airmail Integration |
| Webhook Id | `6a2ae253de27fc09da986bd0` |
| Endpoint | `https://api.airmaildirect.com/v1/...` |
| Triggers | New Lead Created · Lead Status Change · Transaction Management Status Change |

AirMail is the **direct-mail** vendor and needs that hook for their metrics.
Bolt Deals is **PPC**. The two have nothing to do with each other, so the fix
must not disturb AirMail.

## ROUTE IN USE: drip webhook step (found 2026-08-18)

REsimpli **drips** can include a "webhook post" step. This bypasses the single
global webhook slot entirely and never touches AirMail.

It is also *better* than the global webhook: a drip is scoped, so enrolling only
Bolt Deals leads makes REsimpli do the filtering. The Zap then needs no Filter
step and possibly no Code step.

**Verify in the REsimpli UI:**
1. Enrollment must be automatic on Lead Source / Campaign Name — not manual.
2. Drips typically fire on *enrollment only*. If so, a second drip is needed
   that enrolls when a lead is marked qualified, or the Qualified flip never
   reaches the sheet.
3. Set the webhook step to Day 0 / immediate. Drips are built for delays.

**Test target:** use the Zapier Catch Raw Hook URL itself. Do NOT use
webhook.site or any public request bin — the payload carries seller names,
phone numbers, and free-text notes with personal detail.

**Cost:** Webhooks by Zapier is a Premium app and requires a paid Zapier plan.

## CONFIRMED 2026-08-18: the drip fires on ENROLLMENT ONLY

Tested. The drip posts when the lead enters it, and does **not** re-fire when
the lead is later marked Qualified. Left alone, every row in the sheet reads
`Pending` forever — lead counts with no quality signal, i.e. the exact problem
this project exists to solve.

Key property that makes this fixable: the payload always carries the lead's
**current** `Qualified` and `Dead Lead Reason`. So ANY re-fire refreshes the
row. A qualification-specific event is not required.

**Option A (preferred, real-time):** a second drip enrolling on the
qualification change or on entering a qualified/dead Lead Status, posting to the
same Zapier URL. Depends on what enrollment conditions REsimpli's drip builder
offers — unverified.

**Option B (guaranteed fallback):** one drip with webhook steps at Day 0, 3, 7,
14. Each re-posts current state, so qualification lands whenever the team gets
to it. Lag is irrelevant — PPC vendors optimise weekly.

> Zapier task cost on B: ~4 fires/lead. 100 leads/mo ≈ 400 tasks, and every Zap
> step counts. Starter is 750/mo. Trim to Day 0/3/14 if tight.

Both rely on **Lookup Spreadsheet Row (create-if-missing) → Update Spreadsheet
Row**. Never "Create Spreadsheet Row" — that stacks a duplicate per fire.

## Zap structure (Catch RAW Hook)

1. **Catch Raw Hook** — Raw Hook gives ONE JSON string, so nothing is mappable
   until step 2 parses it. This is why a Google Sheets step placed directly
   after the trigger has no fields to map.
2. **Code by Zapier → Run JavaScript** — paste `parse-lead.js`.
   Input `raw` → 1. Raw Body · Input `sourceMatch` → the Bolt Deals string.
3. **Filter** — `isBoltDeals` exactly matches `yes`. Skip if the drip already
   enrolls only Bolt Deals leads.
4. **Lookup Spreadsheet Row** — `Leads` tab, Lookup Column `Lead ID`, value
   `leadId`, tick *create if it doesn't exist yet*.
5. **Update Spreadsheet Row** — row from step 4.

Map `Received At` only in the create case, never in Update, or each re-fire
overwrites first-touch time and destroys the vendor's timeline.

## Dead ends (do not re-litigate)

| Idea | Why it's dead |
|---|---|
| Second global webhook | Only one slot; taken by AirMail Integration |
| Share / relay AirMail's webhook | Endpoint is `api.airmaildirect.com` — **we do not control it and cannot read what it receives** |
| REsimpli Zapier app trigger | App has **write actions only** (Create Lead, Create Buyer). No triggers. |
| REsimpli REST API pull | `api.resimpli.com` is NXDOMAIN; no public docs; token appears to be write-only |

## CURRENT STATE -- LIVE, 159 leads (2026-08-18)

Nightly CSV sync **replaces** the Zapier route. The drip webhook fires on
enrollment only and can never refresh qualification; an export re-reads every
lead's current state, backfills history, and costs nothing per run.

```
6:00am EST  Claude desktop task -> THREE exports to Downloads
              Active / Warm / Dead, all filtered to Bolt PPC
6:30am EST  Task Scheduler -> run_daily_ppc.bat -> daily_sync.py
              validate -> sync_csv.run_sync([all three]) -> archive
```

### Bucket + qualification rules (Jorge, 2026-08-18)

Bucket is derived PER ROW from `Lead Status`, so filenames and processing order
are irrelevant and the three exports can arrive in any sequence.

| Condition | Result |
|---|---|
| `Lead Status` = `Dead Lead` | Dead / **Unqualified** (reason = Dead Lead Reason) |
| `Lead Status` = `Warm Lead` | Warm / **Unqualified** |
| Active + tag `bolt-out of state` or `bolt-listed asking retail` | **Unqualified** -- permanent defects, outrank progress |
| Active + `New Leads` | **Unqualified** (not yet worked) |
| Active, anything else | **Qualified** |

`bolt-no answer` and `bolt-unresponsive after disco` deliberately stay Qualified:
those are contact problems, not property defects, and the lead can still convert.

Result: **60 Qualified / 99 Unqualified = 38%**, in line with the 30-40% inbound
benchmark in CLAUDE.md. (An earlier rule that counted workflow buckets as wins
gave 71%, which would have led the vendor to overrate Bolt.)

### Header-driven schema

`sync_csv.py` reads the sheet's own header row and maps by **column name**, not
position. Reorder or rename columns in Google Sheets and the sync follows.
Columns it does not produce are **preserved, never blanked**, so anything added
by hand survives. Accepted aliases live in `ALIASES`.

Required columns are appended automatically if absent: `Lead Created`,
`Lead ID`, `Lead Bucket`, `Qualification`, `Disqualify Reason`.

Rows are rewritten sorted by `Lead Created` **descending** -- newest first.

Formatting is plain: bold header, no conditional colour fills (Jorge's call).

### Real data facts

- All three exports: `Lead Source` = `Google Adwords/PPC`, `Campaign Name` =
  `Bolt PPC`. Already Bolt-only, so `SOURCE_MATCH` is EMPTY. Each run logs a
  source breakdown as a tripwire if that ever widens.
- **159 unique leads, zero ID overlap** between the three exports.
- **The CSV export has no `Qualified` column** (the webhook payload does).
- `Lead Created Date` is ISO (`2026-07-25`); webhooks use `Aug 18, 2026`. Both
  parse.
- Dead Lead Reasons are the actionable PPC signal: *Not the owner*,
  *Non-working phone number*, *Property already listed on MLS*, *Seller wants
  too much for the house*.

### Privacy

The sheet is shared with an outside PPC vendor. `Mailing Address`, `Buyer Name`,
`Buyer Email`, `Buyer Phone Number` and the ~20 staff-role columns are never
mapped, so they cannot be written.

> Verified by exact whole-cell comparison against the source CSVs. 35 apparent
> "mailing address" matches turned out to be REsimpli storing the *same string*
> in `Property Street Address` and `Mailing Address` for owner-occupied leads.
> Not a leak -- but re-check per-cell, not by substring, if this is ever audited.

## Files

| File | Status |
|---|---|
| `sync_csv.py` | **Working, tested end-to-end.** CSV -> Leads tab upsert keyed on Lead ID. |
| `run_daily_ppc.bat` | Task Scheduler launcher. Picks newest .csv from `EXPORT_DIR`, logs to `logs\YYYY-MM-DD.log`. |
| `parse-lead.js` | Zapier Code step. Superseded by `sync_csv.py`, kept in case real-time arrival is wanted later. |
| `send_test_payload.py` | Posts a synthetic Bolt Deals payload at a webhook URL. Diagnostic. |
| `probe_api.py` | REsimpli API probe. Concluded: no reachable read API. |

## Running it

```
# always dry-run first -- writes nothing
python sync_csv.py "C:\path\export.csv"

# inspect real header names if the mapping looks wrong
python sync_csv.py "C:\path\export.csv" --show-headers

# see every lead regardless of source, to find the Bolt Deals identifier
python sync_csv.py "C:\path\export.csv" --source-match ""

# commit
python sync_csv.py "C:\path\export.csv" --apply
```

Then schedule `run_daily_ppc.bat` in Task Scheduler. Set `SOURCE_MATCH` in that
file to the real Bolt Deals identifier first.

## Verified behaviour (tested against the live sheet, rows since removed)

- Auto-maps 13/15 columns from REsimpli-style headers with no configuration.
- Filters correctly: 4-row CSV with 3 Bolt Deals + 1 Direct Mail -> 3 synced.
- Three-state qualification: 1 Qualified / 1 Unqualified (reason `Wrong Number`)
  / 1 Pending.
- **Upsert works.** Re-running after a lead flipped to qualified produced
  `update 3, append 0` -- no duplicate rows.
- `Received At` is preserved from the existing row; only `Last Updated` moves.
- **PII withheld.** `Mailing Address` and `Notes` were present in the CSV and
  did NOT reach the sheet. Verified by scanning the written rows.

## LIVE 2026-08-18 -- 80 real Bolt PPC leads loaded

First real run: `Exported_Leads_34253 PM.csv` (65 columns, 80 rows) -> 80 rows
written, 57 Qualified / 18 Unqualified / 5 Pending. Verified no owner mailing
address, buyer contact, or staff email reached the sheet.

### Real taxonomy (from the export, not guessed)

- `Lead Source` = **Google Adwords/PPC**, `Campaign Name` = **Bolt PPC**, on all
  80 rows. The export is already Bolt-only, so `SOURCE_MATCH` is EMPTY in
  `run_daily_ppc.bat`. Each run logs a source/campaign breakdown as a tripwire.
- **The CSV export has no `Qualified` column.** The webhook payload does; the
  export does not. Status + Tags are therefore the only signal.
- `Dead Lead Reason` is blank on all 80. **Tags carry the real disqualification
  signal** -- `bolt-no answer`, `bolt-listed asking retail`, `bolt-out of state`,
  `bolt-unresponsive after disco`, `ghost-call`. These are written into the
  `Disqualify Reason` column so the vendor sees WHY, not just that a lead failed.

### Qualification precedence

1. Explicit `Qualified=true` column, if a source ever has one.
2. **Outcome statuses** -- `Offers Made`, `Discovery Done`, `Under Contract`.
   These win outright; a stale tag does not undo demonstrated progress.
3. `Dead Lead Reason`, then **disqualifying tags**.
4. **Workflow buckets** -- `Albert Bucket`, `Follow Up Bucket`. These describe
   where a lead sits, not a verdict, so tags outrank them.
5. Everything else Pending.

Pending is never folded into Unqualified. An untouched lead is not a failed
lead, and reporting it as one pushes the vendor away from working campaigns.

> **Open business question.** Counting Albert Bucket + Follow Up as Qualified
> yields a **71% qualified rate** (57/80). CLAUDE.md benchmarks inbound at
> 30-40%. Jorge chose this deliberately on 2026-08-18, but if the vendor
> optimises against 71% they will overrate Bolt. To flip: move
> `"albert bucket"` / `"follow up bucket"` from `WORKING_QUALIFIED` to
> `PENDING_STATUSES` in `sync_csv.py`.

## Still open

1. **The real Bolt Deals identifier.** Everything currently filters on the
   string `bolt` as a guess. Confirm the actual `Lead Source` / `Campaign Name`
   on a Bolt Deals lead -- the one seen so far was `Direct Mail` / `Website`.
2. **Where REsimpli's lead export lives**, and its real CSV headers. Needed to
   automate the export step in Playwright.
3. Whether REsimpli login uses 2FA. Design assumes a persistent browser profile,
   which sidesteps it either way.
4. `parse-lead.js` maps `Timeline to Sell` / `Motivation` / `Property Condition`
   from the Lead Questions array; the CSV export may not carry those. They sync
   as blank until confirmed.
