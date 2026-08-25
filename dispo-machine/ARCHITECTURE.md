# Dispo Machine — How It Actually Works

**Companion to [`PLAN.md`](PLAN.md).** This is the map: what feeds the buyer
database, how a buyer gets tied to a deal, and who receives what.

---

## The one idea everything else follows from

> **Source decides the SCRIPT. Criteria decide the EXCLUSION.**

Every buyer in the database is a potential buyer for every deal. Where they came
from never removes them — it only changes how we talk to them.

A buyer is removed from a blast for exactly two reasons:

1. **Hard suppression** — DNC, blacklist, unvetted, no phone. Compliance,
   trust, and physics.
2. **An `excl_` rule a human set** after talking to them — "$1M+ only",
   "Gables and Pinecrest only", "no condos".

That's it. Being an InvestorBase buyer pulled for a different property is **not**
a reason to exclude anyone. They are still a cash buyer in your county.

---

## 1. What feeds the buyer database

```mermaid
flowchart LR
  A["<b>Master list</b><br/>121 curated buyers<br/>years of relationships"] -->|"buy_source = BH Main"| DB[("<b>GHL Contacts</b><br/>the buyer database")]
  B["<b>InvestorBase</b><br/>skip-traced buyers<br/>within ~2 mi of a deal"] -->|"Zapier → n8n<br/>buy_source = InvestorBase"| DB
  C["<b>InvestorLift</b><br/>inquiries on a listing<br/>they raised their hand"] -->|"Zapier → n8n<br/>buy_source = InvestorLift"| DB
  D["<b>Referrals / manual</b>"] -->|"buy_source = Referral"| DB

  DB --> E["Every buyer is permanent.<br/>The database only grows."]
```

**The database is cumulative and shared.** Nothing is scoped to one deal. A
buyer sourced for 2165 NW 58th St is available for every deal after it.

### How two records become one buyer

**The join key is the phone number**, normalised to `+1XXXXXXXXXX` before any
write. Every import looks the number up first
(`GET /contacts/search/duplicate?number=…`) and merges into whatever it finds.

**Names are never matched on.** "Marlon Pierre" / "Marlon R. Pierre" /
"PIERRE HOLDINGS LLC" cannot be reliably told apart from three different people.
A wrong merge is unrecoverable; a duplicate is merely annoying.

**An import may only ever ADD.** InvestorBase data is skip-traced and was never
confirmed with anyone, so on a match it is the weaker source:

| Field | On a phone match |
|---|---|
| `buy_source`, `record_type`, `buy_type` | **union** — a buyer is on the master list *and* was returned by an IB pull |
| `buy_ib_property` | **append** — every address they were ever sourced for |
| `buy_notes` | **append** |
| `buy_tier`, `buy_status`, every `excl_*` | **existing wins, always** |
| name, email, company, `source` | **existing wins** if set |
| buy box, beds, zips, sale history | fills blanks only |

Without this the first re-import silently moves a VIP master-list buyer into the
cold segment, resets their tier from a LinkedDeal count, and **reactivates
anyone you blacklisted**. Locked down by `console/merge-policy-test.js`.

**Known gap:** a buyer whose InvestorBase phone differs from the one on file
(cell vs. office) creates a second record. Nothing detects that today — see the
duplicate sweep in [`PLAN.md`](PLAN.md).

---

## 2. How a buyer gets tied to a specific deal

Two different relationships, and conflating them is what caused the earlier
confusion:

| Relationship | Stored as | Meaning |
|---|---|---|
| **Sourced for** | `buy_ib_property` (append-only list) | InvestorBase returned them for this address. Geographic relevance only. |
| **Engaged with** | **Buyer Interest opportunity** | We contacted them about this deal, and here's how far it got. |

```mermaid
flowchart TD
  subgraph CONTACT["Contact record — one per buyer, forever"]
    C1["Jorge Siverio<br/>buy_source: BH Main"]
    C2["buy_ib_property:<br/>2165 NW 58th St<br/>1420 SW 9th Ter"]
  end

  subgraph OPPS["Buyer Interest opportunities — one per buyer PER DEAL"]
    O1["2165 NW 58th — Jorge<br/><i>Reached Out</i>"]
    O2["1420 SW 9th — Jorge<br/><i>Info Sent</i>"]
    O3["789 NE 2nd — Jorge<br/><i>Offer</i>"]
  end

  CONTACT --> O1
  CONTACT --> O2
  CONTACT --> O3
```

**The opportunity is the association.** One buyer, many deals, each with its own
independent status. A contact field can never express this — it overwrites.

To see every buyer on a deal: open the **Buyer Interest** pipeline and search the
address. Stages, in order:

**Reached Out** → **Info Sent** → **Interested** → Walked → Offer → Contract Sent → Closed / Passed

Every stage is something the *buyer* did, except the first: we sent the teaser
(Reached Out), they replied and got the full house post (Info Sent), they said
they want it (Interested). Workflows resolve stages **by name at runtime**, so
reordering or renaming them in the GHL UI never needs a code change.

---

## 3. Segments — who gets which script

At blast time every eligible buyer lands in exactly one segment. Same deal, same
facts, different opener.

```mermaid
flowchart TD
  DEAL["Deal submitted<br/>2165 NW 58th St"] --> POOL["Pull ENTIRE buyer database"]
  POOL --> SUP{"Hard suppression?<br/>DNC · blacklist · unvetted · no phone"}
  SUP -->|yes| DROP1["Suppressed"]
  SUP -->|no| EXCL{"Does an excl_ rule<br/>match this deal?"}
  EXCL -->|yes| DROP2["Excluded<br/><i>with the reason</i>"]
  EXCL -->|no| SEG["Segment by source + relevance"]
  SEG --> S2["<b>1 · Warm list</b><br/>BH Main / Referral<br/><i>they know us</i>"]
  SEG --> S3["<b>2 · InvestorBase Matched</b><br/>InvestorBase pulled for THIS address<br/><i>bought within ~2 mi</i>"]
  SEG --> S4["<b>3 · General cold</b><br/>InvestorBase from other deals<br/><i>still a real cash buyer</i>"]
```

| # | Segment | Opener | Why it differs |
|---|---|---|---|
| 1 | **Warm list** | familiar, first-name, "got another one" | Existing relationship |
| 2 | **InvestorBase Matched** | leads with the neighborhood | They demonstrably buy on this street |
| 3 | **General cold** | straight, credible, AI disclosure | No relationship, no geographic hook |

Nobody is excluded for being in segment 3 or 4. **Everyone gets contacted;
segments 3 and 4 just get a colder, more careful script.**

---

## 4. The full per-deal flow

```mermaid
flowchart TD
  A["1 · InvestorBase<br/>search the address, select buyers,<br/><b>Send to Zapier</b>"] --> B["Zapier loop → n8n<br/>tier band · >200 cap · dedupe<br/>append buy_ib_property"]
  B --> DB[("Buyer database")]

  C["2 · Deal intake form<br/>address, numbers, description"] --> D["Upsert Property record"]
  D --> E["Pull ENTIRE database<br/>suppress → exclude → segment"]
  E --> F["Build house post<br/><i>template code, no LLM</i>"]
  E --> G["Generate teaser per segment<br/><i>Claude</i>"]
  F --> H["Review page<br/>post · teasers · buyers by segment"]
  G --> H

  H --> I["3 · QA and edit<br/>then Send"]
  I --> J["Send per segment<br/>right script to right buyer"]
  J --> K["Buyer Interest opportunity<br/>per recipient — <i>Reached Out</i>"]

  K --> L["4 · Buyer replies"]
  L --> M["Full house post auto-sends"]
  M --> N["Opportunity → <i>Info Sent</i>"]

  O["InvestorLift inquiry<br/>on this listing"] --> P["Zapier → n8n"]
  P --> DB
  P --> Q["Opportunity on THIS deal<br/><i>Interested</i>"]

  DB -.-> E
```

---

## 5. Traceability — what you can answer

| Question | Where |
|---|---|
| Every buyer contacted about this deal, and their status | Buyer Interest pipeline, search the address |
| Which deals has this buyer been contacted about | Buyer Interest, filter by contact |
| Which deals was this buyer sourced for | `buy_ib_property` on the contact |
| Where did this buyer come from | `buy_source` |
| Why didn't this buyer get the blast | Review page — `excluded` / `suppressed`, with the reason |
| Which buyers should we call to confirm their box | Review page — `review_suggestions` |
| What exactly did we send | `prop_teaser_sms` / `prop_sms_post` on the Property record |

---

## 6. What "exclusion" means — worked examples

Exclusions are **buy-box facts a human confirmed**, never inferred from source.

| Real buyer | Rule set | Effect |
|---|---|---|
| David Rojas — *"only $1M+ ARV or land to build"* | `excl_below_price = 1000000` | Skipped on a $335K deal, included on a $1.2M one |
| Francisco Siman — *"Gables, Pinecrest only"* | `excl_outside_neighborhoods = Coral Gables, Pinecrest` | Skipped on Homestead, included on a Gables deal |
| Conrado Martinez — *"ONLY 1,800 sq ft or bigger"* | `excl_below_sqft = 1800` | Skipped on an 805 sq ft house |
| Ralph Goicoria — *"max 315k"* | `excl_above_price = 315000` | Skipped on a $500K deal |
| Wilfredo Barrios — *"DO NOT CONTACT"* | `excl_all_blasts = Yes` | Never contacted |

> **"High end" is not a rule.** It has to be expressed as a number
> (`excl_below_price`) or a place (`excl_outside_neighborhoods`). Vague labels
> can't be enforced and silently do nothing.

**The extracted `buy_*` buy box never filters a blast.** It was parsed from old
prose notes and was never confirmed. It only produces *review suggestions* —
a call list — and the buyer still receives the deal until someone confirms.

---

## 7. Build status

| Piece | Status |
|---|---|
| Buyer database + classification fields | ✅ |
| Exclusion engine | ✅ |
| InvestorBase capture (W12) | ✅ |
| Deal intake + house post + teaser (W1) | ✅ |
| Blast + Buyer Interest opportunities (W2) | ✅ |
| Per-segment teasers | ✅ verified live — four distinct openers per deal |
| **Dispo Deal Console** (intake + review + send, one page) | ✅ [`console/`](console/) |
| **A real blast** | ⛔ never run — no message has ever been sent |
| **InvestorLift capture (W11)** | ❌ |
| **Reply handler (W1c)** | ❌ |
| **Deal dashboard** | ⏸ deferred — use the Buyer Interest pipeline for now |

### The console

<https://automations.buyinghero.com/dispo/> — one page, two states. Source in
[`console/`](console/); `bash console/deploy.sh` builds, tests and publishes it.

```mermaid
flowchart LR
  A["Intake form<br/><i>26 fields</i>"] -->|"POST /webhook/dispo-intake"| B["W1"]
  B -->|"JSON: segments · teasers<br/>posts · buyers"| C["Review state"]
  C -->|"edit anything<br/>hold segments back"| C
  C -->|"POST /webhook/dispo-send<br/><i>what you see is what sends</i>"| D["W2"]
  D --> E["SMS + Buyer Interest opps"]
```

Everything is editable before it sends — four teasers, the WhatsApp post, the
SMS post, the voice brief — each with a Revert. Any segment can be held back,
and the send button counts only what is switched on. `?demo=1` runs the whole
flow against mock data with no network calls.

**Two test suites, both runnable offline** (`npm test` in `console/`):
`smoke.js` drives the page headlessly through submit → edit → toggle → send;
`contract-test.js` renders a captured **live** W1 response and fails if the
backend and front end have drifted apart.

### Deferred: the deal dashboard

**Decision 2026-08-15:** ship on the GHL Buyer Interest pipeline first. It
already answers "every buyer on this deal and their status" for free, inside the
tool the team is already in. Build the custom dashboard once a few real deals
have run through — the pipeline will show us what's actually missing rather than
what we guessed.

What a dashboard would add later: one screen per deal with the four segment
counts, reply rate, time-to-first-reply, `buy_objection_last` themes across
non-responders, and price-reduction pressure — the analytics the pipeline
board cannot show.

---

## Correction log

**2026-08-15 — source-based exclusion was wrong.** InvestorBase buyers sourced
for a different property were being excluded from every other deal. That throws
away the database the imports exist to build. Replaced with segmentation:
everyone is contacted, source only selects the script.

**2026-08-25 — matching the WHOLE address was wrong.** 1125 Highview Rd reported
**0** InvestorBase Matched against 76 buyers that had just imported cleanly.
InvestorBase stamped `1125 Highview Rd, Lantana, FL 33462`; the deal was entered
as `1125 Highview Rd Lake Worth FL 33462`. Both are correct — ZIP 33462 straddles
a municipal line, so USPS says Lake Worth and the municipality is Lantana — but
neither string contained the other, so every matched buyer was scripted as
General cold. The matcher now compares the **street** (house number + name,
suffix canonicalised so `Rd` == `Road`, ordinals reduced so `58 St` == `58th St`,
directionals abbreviated) and the **ZIP when both sides carry one**. City and
state are ignored on purpose: they are the parts the two systems disagree about.
A pull with no parseable street falls back to the old containment test rather
than dropping the buyer. Identical block in W1 and W2, locked byte-for-byte by
`console/addr-match-test.js`.
