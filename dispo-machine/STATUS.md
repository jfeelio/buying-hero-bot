# Dispo Machine — where things stand

**Last updated:** 2026-08-19

Running status. `PLAN.md` is the design, `ARCHITECTURE.md` is how it fits
together, `SMART_LISTS.md` is the build sheet. This file is just "what is done,
what is next, what will bite you."

---

## The one-line version

**The full loop works, verified end to end on 2026-08-19.**

Deal in at `/dispo` → review → send → real SMS → Buyer Interest opportunity →
buyer replies → Claude classifies → full house post auto-sent → opportunity
moves to Info Sent → counters written. Proven with a live test to Jorge's cell.

**No blast has gone to a real buyer yet.** Everything so far has been TEST SEND
to one number, and the buyer 10DLC campaign still gates real volume.

---

## Done

| | |
|---|---|
| **Master buyer import** | 124 buyers + 2 phoneless suppression records. 0 failures. `import/build_import.py --push` — add-only, safe to re-run |
| **W1 Dispo Intake** | `dispointake001` · active · `/webhook/dispo-intake` |
| **W2 Send Teaser Blast** | `sendblast0001` · active · `/webhook/dispo-send` |
| **W12 InvestorBase Capture** | `ibcapture0001` · active |
| **W1c Buyer Reply Handler** | `replyhandler01` · active · `/webhook/buyer-reply` |
| **Deal Console** | https://automations.buyinghero.com/dispo/ |
| **Test suite** | `cd console && npm test` — 9 files, all green, runs offline against the workflow JSON |
| **Test send** | `buy_type = TEST` + a whitelist switch on the review page. Off by default; TEST is held from real blasts |
| **Reply handler** | GHL workflow *Buyer Reply → n8n* is published and firing |

### Live database

```
total contacts           128
record_type = Buyer      127
buy_source  = BH Main    100
buy_tier    = VIP         18
buy_type    = JV          22    held from the first blast by default
buy_type    = Realtor     10    held from the first blast by default
DNC / Blacklist          1 / 3
buy_vetted set             0    blank = blastable, as designed
```

---

## Next, in order

1. **Buyer 10DLC campaign** — *the long pole.* No SMS goes out until this
   clears. Jorge's task, no dependency on anything below.
2. **InvestorBase import (W12).** Next up. It is also the first real test of
   the *Geo-matched cold* segment, which has never had data — `buy_ib_property`
   is what drives it. Run it against the same 2165 NW 58th St deal.
3. **W11 InvestorLift capture** — not built. Spec is agreed: inquiry →
   create/merge contact → `buy_source = InvestorLift` → `buy_vetted = Unvetted`
   → Buyer Interest opportunity at **Interested** → **send nothing, ever**.
   This is what makes the vetting gate do anything; today no record is Unvetted.
   Open question Jorge has not answered: seed a watchlist of known local
   wholesaler names?
4. **First real blast.** Re-submit a deal at `/dispo` to get the buyer-type
   checkboxes, confirm JV + Realtor are held, send.
5. **Stage win probabilities are backwards** after the pipeline reorder
   (Reached Out 80%, Info Sent 40%, Interested 20%). UI-only, 2 minutes.
6. **Nothing here is committed to git.** See below.

---

## Things that will bite you

**`extraction.EXTRACT` is keyed by row number in a 143-row snapshot that no
longer exists.** A buyer was inserted at row 109 on 2026-08-18 and everything
below shifted. `import/rekey.py` re-keys onto identity using the frozen
`GHL Import Dry Run` tab as the row→identity map. **Never index EXTRACT against
a freshly-read sheet** — it silently hands 34 buyers the wrong buy box.

**Three separate GHL tokens.** Rotating one does not touch the others:

| Token | Lives in | Update by |
|---|---|---|
| Claude / MCP | `~/.ghl_pit` **and** the `ghl` MCP header | paste the file, then `claude mcp remove ghl -s user` + re-add |
| n8n automation | n8n credential `Header Auth account` | n8n UI |
| *(any others)* | — | — |

`claude mcp list` reports **✔ Connected for a dead token** — it only proves the
endpoint is reachable. An actual API call is the only real test.

**Cloudflare fronts the LeadConnector API** and rejects a default urllib
User-Agent with a **1010 that reads exactly like an auth failure**. Set a
User-Agent before concluding a token is bad.

**A custom field's `dataType` cannot be changed after creation.** The PUT
returns `200` with the old type and no error. `position` does persist.
`buy_ib_property` is stuck as single-line TEXT, which is why its address list is
`; `-delimited rather than newline.

**GHL `search` endpoints return PARTIAL custom-field projections.** Twice during
the 2026-08-19 debugging a write looked like it had failed when it had not.
**Verify a write by reading the record by id, never via search.** And the same
field comes back under three key names: `fieldValue` (GET opportunity by id),
`fieldValueString` (opportunity search), `value` (contacts). The wrong key does
not error — the field just reads empty.

**`locationId` is required but undocumented** on `POST /conversations/messages`
(in the body) and `GET /opportunities/pipelines` (query string). Both 422 with
`COMMON_LOCATION_ID_UNDEFINED`; the pipelines one surfaces as the misleading
"Buyer Interest pipeline not found". Locked by `console/locationid-test.js`.

**Never assemble a buyer-facing string in an n8n expression field.** A literal
`'{{first_name}}'` nested inside an HTTP node's own `{{ }}` killed every send
with a bare `invalid syntax`. Build the message in a Code node — and remember a
Code node's explicit `return` projection silently drops any field you forget to
list.

**n8n IF booleans reject `undefined`.** `_skip is notTrue` sent every real row
down the FALSE branch, so the engagement write-back never ran *and reported
success*. Test for the thing you want (`contactId` present), not for the absence
of a flag. And count what the write node RETURNED, not what you queued for it.

**Debugging n8n:** the console only ever shows `[object Object]`. The real error
is in `select data from execution_data where "executionId"=N` on the n8n
postgres.

**Merge policy is add-only, everywhere.** W12 and the importer may never
overwrite a tier, status, `excl_` rule, or a name a human set. If you write a
new importer, copy that policy or you will quietly undo the dispo team's work.

**`record_type = Seller` is only for people who actually sell us houses.**
An earlier rule stamped it on JV partners; corrected 2026-08-18. Every workflow
and Smart List filters on this field.

---

## Git

**None of this is committed.** Uncommitted as of 2026-08-19:

```
 M crm-transition/n8n-workflows/03-dispo-intake.cloud.json
 M crm-transition/n8n-workflows/04-investorbase-capture.cloud.json
 M crm-transition/n8n-workflows/05-send-teaser-blast.cloud.json
 M dispo-machine/PLAN.md
 M dispo-machine/ARCHITECTURE.md
?? crm-transition/n8n-workflows/07-buyer-reply-handler.cloud.json
?? dispo-machine/SMART_LISTS.md
?? dispo-machine/console/
?? dispo-machine/import/
```

`console/` and `import/` each carry a `.gitignore`. **`import/payloads*.json`
and `import/import-log.tsv` hold buyer names and phone numbers and must stay
ignored** — this repo is a Dropbox-synced working tree.
