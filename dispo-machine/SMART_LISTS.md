# Smart lists — build sheet

**Smart lists cannot be created through the GoHighLevel API.** There is no CRUD
operation for them (checked 2026-08-17), the same as pipelines and custom-object
schemas: UI-only. Each one below is built by hand, once, and then never touched
again — the membership updates itself because it is a live filter.

What *is* automated is the checking. `POST /contacts/search` accepts the same
field filters the UI does, so every recipe here has been run against the live
database. Build the list, then run the matching command and confirm the two
numbers agree.

**Where:** GHL → **Contacts** → **Smart Lists** → *+ Add Smart List* → name it,
add the filters, save.

---

## Before you start

Every filter below uses **AND** — verified: adding a second condition narrowed a
live query from 3 contacts to 1.

**Field names in the UI are exactly the field names below** (`buy_tier`,
`record_type`, …). They sort alphabetically, so `buy_*` fields cluster together
and `excl_*` fields cluster below them.

> **Counts are not meaningful yet.** The database holds 3 contacts and 1 buyer
> until the 121 master buyers are imported. Build the lists now anyway — they
> populate themselves — but do the count check after the import.

---

## The lists

### 1. Blast Eligible
**The denominator for everything.** Should match what the Deal Console reports
as the buyer pool before per-deal exclusions.

| Field | Operator | Value |
|---|---|---|
| `record_type` | is | Buyer |
| `buy_status` | is | Active |
| `excl_all_blasts` | is not | Yes |
| Phone | is not empty | |

### 2. VIP Buyers
Call these. Do not text them.

| Field | Operator | Value |
|---|---|---|
| `record_type` | is | Buyer |
| `buy_tier` | is | VIP |

*(Duplicate this three times for A / B / C if you want tier lists.)*

### 3. Never Contacted
Onboarding queue. Everyone in it until the first blast runs.

| Field | Operator | Value |
|---|---|---|
| `record_type` | is | Buyer |
| `buy_last_contacted` | is empty | |

### 4. Went Quiet
Re-engagement. **Needs a date, so edit the value once a quarter** — GHL has no
relative-date filter on custom date fields.

| Field | Operator | Value |
|---|---|---|
| `record_type` | is | Buyer |
| `buy_status` | is | Active |
| `buy_last_contacted` | is before | *a date 90 days ago* |

### 5. Responsive Buyers
The list worth protecting. Everyone who has ever replied.

| Field | Operator | Value |
|---|---|---|
| `buy_replies` | is greater than | 0 |

### 6. Missing Tier
104 of 121 today. Working this list down is what makes tier mean anything.

| Field | Operator | Value |
|---|---|---|
| `record_type` | is | Buyer |
| `buy_tier` | is empty | |

### 7. No Phone
Unreachable, so invisible to every other list. Pure data quality.

| Field | Operator | Value |
|---|---|---|
| `record_type` | is | Buyer |
| Phone | is empty | |

### 8. Held From Blasts
**An audit list, not an operational one.** Somebody has to periodically ask
whether each hold is still true. A hold nobody revisits is a buyer you quietly
lost.

| Field | Operator | Value |
|---|---|---|
| `excl_all_blasts` | is | Yes |

### 9. DNC / Blacklist
Compliance audit. Should only ever grow deliberately.

| Field | Operator | Value |
|---|---|---|
| `buy_status` | is one of | DNC, Blacklist |

### 10. Institutional
Over 200 linked deals — iBuyers, title companies, data artifacts. Parked
automatically by the InvestorBase import.

| Field | Operator | Value |
|---|---|---|
| `buy_deals_count` | is greater than | 200 |

### 11. JV Partners
The 29 who are both buyer and seller — the group most likely to break on a
careless import. Check this list after every migration step.

| Field | Operator | Value |
|---|---|---|
| `record_type` | is one of | Buyer, Seller |

> **Verify this one by eye after building it.** Depending on how GHL treats a
> multi-select "is one of", it may return *either* rather than *both*. If the
> count looks like all your buyers, it is matching either — and the honest
> version is a saved search on `record_type` = Seller, cross-checked against
> Blast Eligible.

### 12. New This Week
Import QA. Run this after every InvestorBase pull.

| Field | Operator | Value |
|---|---|---|
| `record_type` | is | Buyer |
| Date Added | is after | *a date 7 days ago* |

---

### 13. InvestorLift · Unvetted
**The dispo queue.** Everyone who inquired through InvestorLift and has not yet
been cleared by a human. They are held from every blast until someone flips
`buy_vetted` to Vetted — because some InvestorLift inquiries are competing
wholesalers fishing for the address, not buyers.

| Field | Operator | Value |
|---|---|---|
| `buy_source` | contains | InvestorLift |
| `buy_vetted` | is | Unvetted |

**The one flip:** open the contact, set `buy_vetted` = **Vetted**. That is the
entire action. They blast normally from the next deal onward, forever.

### 14. Known Snakes
Institutional memory. Never delete these records — a deleted snake gets
re-imported next month and has to be re-identified from scratch.

| Field | Operator | Value |
|---|---|---|
| `buy_vetted` | is | Rejected |

### 15. Buyers For One Property
**"Who did InvestorBase find for 2165 NW 58th St?"** `buy_ib_property` holds
every address that buyer has ever been pulled for, semicolon-separated and
append-only, so this works even for a buyer who has come back on six deals.

| Field | Operator | Value |
|---|---|---|
| `buy_ib_property` | contains | *2165 NW 58th* |

Use the street number plus street name only — no city, no ZIP. InvestorBase and
the intake form spell the tail of an address differently.

### 16. InvestorBase Only
Buyers we know *only* from proximity pulls — never on the master list, never
inquired. This is the growth of the database over time.

| Field | Operator | Value |
|---|---|---|
| `buy_source` | contains | InvestorBase |
| `buy_source` | does not contain | BH Main |

*(Swap the second row for `buy_source` **contains** `BH Main` to get the
overlap: master-list buyers InvestorBase independently confirms buy near a
given deal. That overlap is the highest-confidence segment in the database.)*

---

## Filtering the Buyer Interest pipeline by deal

Not a Smart List — Smart Lists are contacts. This is the **Opportunities** view,
and it is what makes the pipeline usable once two or three deals are live at
once.

Every Buyer Interest opportunity the blast creates carries:

| | |
|---|---|
| **Name** | `Jorge Siverio — 2165 NW 58th St. Miami, FL 33142` — buyer first, so the card reads as a person |
| **`opp_deal_address`** | `2165 NW 58th St. Miami, FL 33142` — the field you filter on |

**To see one deal's buyers:** Opportunities → *Buyer Interest* → **Filter** →
`opp_deal_address` **contains** *2165 NW 58th*.

Street number plus street name only — no city, no ZIP. Save it as a view per
active deal and delete the view when the deal closes.

> **Field id** `23Qr6cqR1IP1zFknf5Wn`, model **opportunity** (not contact).
> Opportunity custom fields are written with `fieldValue`; contact custom
> fields use `value`. The wrong key does not error — the field just stays
> empty.

---

## The two GHL cannot express

Both are cross-field conditions with no operator in the filter UI:

| Wanted | Why it does not fit |
|---|---|
| **Interview queue** — an `excl_` rule was set but `excl_verified_date` is empty | Compares two fields to each other. The UI can only compare a field to a constant. |
| **Dead weight** — `buy_deals_sent` ≥ 5 **and** `buy_replies` = 0 | Two counters, and neither exists as data until the blast write-back is built. |

**Parked.** Neither is worth solving until there is real engagement data, and
both are answerable by exporting Blast Eligible to a sheet in the meantime.

---

## Verifying a list

Field ids for the search API:

| Field | id |
|---|---|
| `record_type` | `vGlkrrrRFNhDn4S7Exlv` |
| `buy_status` | `lU8dcFyBnnvoAy9DHQ5o` |
| `buy_tier` | `6LvZFW4TVSaFYDx60Yaj` |
| `buy_source` | `kmikehE2YPSxJILEMzmb` |
| `excl_all_blasts` | `zKxjOzGcLfMNiCUPvw5n` |
| `excl_verified_date` | `LvtCBzEYDDYOkEw5AHcn` |
| `buy_last_contacted` | `H7h5xLsf4fEK7RWmUPjE` |
| `buy_deals_count` | `i7aGGtuBJQDuzTaIUYlX` |
| `buy_deals_sent` | `Bm5OguP73NrZtf05KoRH` |
| `buy_replies` | `lwseYt6ApAYNG8Zg6dsE` |
| `buy_first_contacted` | `rw9HInNhbME2Y2vY27xU` |
| `buy_last_deal` | `RPLXsO5CyYJtkuvxUnrH` |

Re-fetch them any time with
`GET /locations/ib5jEnyqqq06FIEqlVGs/customFields?model=contact`.

Verified operators: `eq` · `not_exists` · `exists` · `contains` (tags and text)
· `gt` / `lt` (numbers and dates). Multiple filters combine with **AND**.

Example — Blast Eligible:

```json
POST /contacts/search
{
  "locationId": "ib5jEnyqqq06FIEqlVGs",
  "pageLimit": 1,
  "filters": [
    { "field": "customFields.vGlkrrrRFNhDn4S7Exlv", "operator": "eq", "value": "Buyer" },
    { "field": "customFields.lU8dcFyBnnvoAy9DHQ5o", "operator": "eq", "value": "Active" }
  ]
}
```

Read `total` from the response and compare it to the smart list. **Ask me to run
any of these** — I can query the live database directly and tell you the number
before or after you build the list.

---

## Why not automate this with tags

Considered and rejected 2026-08-17. GHL *does* expose bulk tag writes
(`POST /contacts/bulk/tags/update/{add|remove}`), and a smart list can filter on
a tag — so membership could be computed in n8n and stamped on.

**It buys nothing for twelve of these fourteen lists.** `buy_tier is VIP` is a
native filter that is correct forever with no workflow, no schedule, and nothing
to break. Wrapping it in a scheduled job that writes tags adds a moving part, a
second source of truth, and a way for the list to be silently wrong when the job
fails. The two lists it would genuinely help are the two already parked for lack
of data.

Revisit only if a rule appears that is both operationally important *and*
impossible to express as a field filter.
