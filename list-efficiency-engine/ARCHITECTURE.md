# Building the county-wide list engine

What `rank.py` does today: scores the **53,710 doors we already mailed**.
What Tiffany describes: scores **every list in the county**, then pulls the good
ones — including doors we have never touched.

Different denominator. This document is how to get from one to the other.

---

## Four components

```
[1] LIST BUILDER      county-wide membership per list, with dates
        |
[2] OUTCOME SET       qualified LLC purchases, last 6 months
        |
[3] SCORER            doors_per_deal + CI + priority, per list
        |
[4] PULLER            Priority 1 list, minus what we've already worked  -> CSV
```

Component 4 is the actual deliverable — the mailable list.

---

## The blocker, measured

To score a list you must know **whether a property was on that list when it sold**.

For state-based lists this is impossible from the current roll, because closing
overwrites the seller's details with the buyer's. Measured today:

| | Absentee rate |
|---|---|
| All single-family in county | **22.9%** |
| Single-family sold in the window | **31.3%** |

A sold property looks **1.37× more absentee** than the base population — entirely
because the LLC buyer's mailing address replaced the seller's. Score "absentee"
naively county-wide and you get a 1.37× lift that is **pure artifact**. No signal in it.

### What survives the overwrite

| Attribute class | Point-in-time? | Why |
|---|---|---|
| Probate, lis pendens, tax deed | **Yes** | membership set by a dated filing; ownership is irrelevant |
| Year built, sqft, beds, DOR code | **Yes** | physical, unchanged by sale |
| Tenure at sale | **Recoverable** | prior sale date from folio API `SalesInfos` |
| Grantor (seller) type | **Recoverable** | `GrantorName1` from `SalesInfos` |
| Absentee, out-of-state, entity-owned | **No** | overwritten at closing |
| Assessed value | **No** | reassessed after sale |

**So Phase 1 is the dated distress lists.** Those you already scrape, and their
filing dates make membership point-in-time by construction. No new data needed.

---

## The important split

Two different operations, two different requirements:

- **Pulling a list to mail** — works *today* for every list type. An unsold
  property's current record *is* its current state; nothing is overwritten.
- **Scoring a list retrospectively** — needs point-in-time data, so state-based
  lists are blocked until snapshots accumulate.

You can therefore pull targeted lists this week. You just cannot yet *prove*
which state-based list is best. In the meantime the proxy for that is the mail-file
analysis in `rank.py`, which has real pre-sale data for the 53,710 doors we mailed.

---

## Unblocking the state-based lists

**Start monthly roll snapshots immediately.** All 387,591 SFH, ~30 minutes per pull,
free. Every month of delay is a month of history that does not accumulate. After
6 months, absentee / equity / tenure become scoreable properly. `snapshot.py` does this.

**Also pursue a historical roll.** Florida DOR publishes annual county tax rolls
(NAL — name/address/legal — files) and a sales data file. Their portal is
JavaScript-driven and the direct download could not be confirmed from here. One
Jan-1-2026 NAL file would make the last 6 months scoreable retrospectively and
skip the 6-month wait. Miami-Dade PA's Tax Roll Administration is the other route.

---

## County-wide list sizes, confirmed today

Straight from PaGISView. These are real denominators, available now:

| List | Doors | Share of SFH |
|---|---|---|
| All single-family | 387,591 | 100% |
| Built before 1970 | 191,096 | 49.3% |
| Assessed under $250k | 145,218 | 37.5% |
| Held 15+ years | 122,883 | 31.7% |
| Held 20+ years | 95,390 | 24.6% |
| Absentee (mail ≠ site) | 88,816 | 22.9% |
| Absentee + held 15+ yrs | 30,719 | 7.9% |
| Absentee + assessed < $250k | 26,044 | 6.7% |
| Owner is an entity | 25,030 | 6.5% |
| Out-of-state owner | 6,932 | 1.8% |

For scale: Buying Hero has mailed 53,710 unique doors total. `absentee + held 15+ yrs`
alone is 30,719 doors, most of them never touched.

---

## Component 2 — the outcome set needs finishing

Currently only the 178 matched doors have been enriched with deed qualification.
**All 4,773 sales need it**, because the county-wide numerator is drawn from the
full set, not just our mailed subset.

Why it matters, from the 178 already checked: **only 123 of 178 (69%) were genuine
arms-length purchases.** The rest were government-agency foreclosure transfers,
quitclaims and corrective deeds — LLC names on deeds that are not purchases. And
the junk concentrated in the distressed campaigns (58% of campaign 31's matches,
50% of campaign 272's), which is exactly where it would do the most damage to a
ranking.

Cost: ~4,773 folio API calls, roughly 20 minutes at a polite rate.

---

## Component 4 — the puller

For a Priority 1 list, output the doors worth mailing. Subtract:

1. **Already mailed recently** — join the 147,837-piece mail file; exclude anything
   touched in the last N days (N is a policy choice).
2. **Opted out** — the 65 CRM leads with "wants to be taken off the list", plus any
   DNC. Non-negotiable; this is reputation and legal exposure.
3. **Already sold** — anything in the 4,773. The door is gone.
4. **Dead in CRM** — "no motivation to sell" within some recency window.

What is left is the mail list, ranked by list priority. Output CSV.

---

## Build order

| Phase | Work | Blocked? |
|---|---|---|
| 1 | Enrich all 4,773 sales with deed qualification | no — do first |
| 2 | Start monthly roll snapshots (`snapshot.py`) | no — start now, time-sensitive |
| 3 | Score dated distress lists county-wide (probate / LP / tax deed) | no |
| 4 | Puller: Priority 1 list minus already-worked, to CSV | no |
| 5 | Score state-based lists (absentee / equity / tenure) | yes — needs snapshots or a DOR historical roll |

Phases 1–4 are buildable now. Phase 5 waits on data that starts accumulating
the day Phase 2 runs.
