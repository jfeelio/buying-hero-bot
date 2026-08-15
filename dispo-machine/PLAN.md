# Buying Hero — Dispo Machine

**Prepared for:** Partner review
**Date:** August 2026
**Status:** Plan locked, pre-build
**Companion doc:** [`../crm-transition/GHL_CRM_PLAN.md`](../crm-transition/GHL_CRM_PLAN.md)

---

## The problem we're solving

Disposition today is three disconnected systems and a manual bottleneck:

- **InvestorLift** markets to their buyer pool. We can't export buyers, so every
  interaction there dies in their platform.
- **InvestorBase** gives us skip-traced buyers within 2 miles of the subject
  property. We export to REsimpli and bulk SMS. Results are decent — but the
  list is discarded after each deal, so we re-rent the same data every time.
- **Master buyer sheet** in Google Sheets. Continuously updated by hand, no
  dedup, no comms integration, no way to segment by buy box at blast time.

The compounding failure: **we cold call almost none of these people**, because
nobody has the bandwidth. Every deal, we pay for buyer data, use it once, and
throw it away.

**Goal:** one centralized buyer database that gets smarter every deal, with AI
handling outreach and inbound across SMS, email, and voice — so a deal can be
dropped in by any team member and worked automatically. Including other
people's deals.

---

## Architecture

Extends the already-approved *buy the plumbing, build the brain* stack. No new
platforms.

```
   Deal intake (GHL form)
            |
            v
   GoHighLevel — main Buying Hero sub-account
   - Buyers as contacts: tags + buy-box custom fields
   - Properties as custom object
   - Smart Lists = match engine
   - Workflows = SMS / email / Voice AI cascade
   - Conversations = one inbox for every reply
            ^                    |
            |                    | webhooks
   n8n (self-hosted)             v
   - InvestorLift capture     Supabase (owned data lake)
   - InvestorBase import      - cross-deal buyer analytics
   - scrub gate               - per-JV-partner reporting
            ^                    |
            |                    v
   Zapier (dumb bridge)       Claude (AI brain)
   - InvestorLift triggers    - pricing feedback, reports
```

### Decisions locked

| Decision | Choice | Rationale |
|---|---|---|
| Buyer DB home | **GHL contacts, main sub-account** | GHL is also the comms engine and inbox — no sync layer to maintain. Not GitHub (PII in a repo, no team UI, no concurrent editing). |
| Buyers vs sellers | **One sub-account, separated by tag** | 10DLC brand + numbers already exist. Two accounts = two inboxes, two logins, two suppression lists for a 4-person team. One global opt-out list is safer. |
| Dispo SMS | **Move off REsimpli to GHL** | Split channels make the inbound bottleneck unsolvable. One inbox is the point. |
| Voice AI | **Native GHL Voice AI** | Logs to contact timeline, books calendars, no extra vendor. Vapi/Retell only if we hit a wall. |
| Cold AI calling | **Build with safeguards** | Reframed as a consent funnel — see Compliance. |
| InvestorLift | **Zapier → n8n → GHL** | Zapier is the only exposed surface; logic lives in n8n where it's versionable. |
| InvestorBase | **Zapier → n8n → GHL** | Same. No public REST API (checked 2026-08-13); their Zapier app is the only programmatic surface. Worth one email to `info@investorbase.com` asking about API access on the $249/mo plan. |
| Analytics | **Supabase mirror** | Same webhook pipeline already being built for sellers. Near-free to extend. |

### Coexistence with the seller side (REsimpli migration)

Buyers and sellers share one sub-account, so the two sides must not collide when
seller contacts and opportunities land. Four rules, established 2026-08-13.

**① The Property object spans both sides — by design.** One address = one
permanent record, across acquisition *and* dispo:

```
seller lead → Property record → Buying Hero Pipeline opp   (acquisition)
                     ↓ under contract
                             → Dispo pipeline opp          (disposition)
                             → Buyer Interest opps         (per buyer)
```

ARV and repair estimates captured during acquisition are already present at
dispo. The two sides cannot hold different numbers for the same house.

**② `prop_address` is unique, so all Property writes must UPSERT.** Search by
address first; update if found, create if not. A blind create fails the moment
the seller side has already filed the house — which, once migration completes,
will be the normal case rather than the exception. The W1 intake form is built
this way from the start.

**③ Every workflow and Smart List filters on `record_type`.** No exceptions.
Without it a seller "contact created" workflow fires on imported buyers, and a
buyer blast Smart List texts seller leads a wholesale deal. Cheap discipline at
4 workflows, a multi-day debug at 20.

**④ The seller import must UPDATE, not overwrite.** Wholesalers and JV partners
already exist here as buyer contacts — 29 of them carry both Buyer and Seller in
`record_type`. Match on phone, merge, append `Seller`; never blank-overwrite, or
the extracted `buy_*` data is destroyed. Build the `sell_*` field schema
*before* importing, not after.

> Consequence to accept, not fix: **opt-outs are global across buyers and
> sellers.** A seller who texts STOP is suppressed as a buyer too. This is
> correct behaviour and is precisely what the single-sub-account decision bought.

### Why not a separate buyer sub-account

Considered and rejected for v1. Clean separation would help if we white-label
dispo for JV partners under their own branding — but that's Phase 5+, and
spinning up a second sub-account later plus migrating buyer contacts is a few
hours of work. Not worth a permanent complexity tax for an option we can buy
later.

---

## Data model

### Buyer contacts

**Classification fields** *(revised 2026-08-13 — these were tags in the
original plan; see below)*

| Field | Shape | Values |
|---|---|---|
| `record_type` | multi-select | Buyer · Seller |
| `buy_tier` | **single**-select | VIP · A · B · C |
| `buy_status` | **single**-select | Active · Dormant · DNC · Blacklist |
| `buy_type` | multi-select | Cash · Flipper · Landlord · Builder · JV · Realtor · Novation · Institutional |
| `buy_source` | multi-select | InvestorLift · InvestorBase · BH Main · Referral |

> **Why these are fields, not tags.** Tags cannot enforce mutual exclusivity.
> Nothing stops a contact carrying `status:active` *and* `status:dnc` at the
> same time — the Smart List sees `status:active` and the person gets blasted.
> That is the single most expensive failure in the system, and a single-select
> field makes it structurally impossible. Tier is exclusive for the same reason.
>
> Type, source and record type stay **multi**-valued because the data genuinely
> is: real buyers are flipper *and* realtor, buyers accumulate sources over
> time, and JV partners sit on both sides of the table (29 of them in the
> master list alone). Forcing those single would destroy information.
>
> **The rule going forward:** a *field* records what a contact **is** — durable
> attributes. A *tag* records what is **happening to them right now** —
> transient campaign or workflow state (`blast:2165-nw-58`). Don't mix them.
>
> The 22 original taxonomy tags were deleted 2026-08-13 so there is only one
> source of truth. The 6 pre-existing generic tags (`cold lead`, `warm lead`,
> `follow-up`, `high priority`, `dead lead`, `remove from list`) are seller-side
> and were left alone.

**`buy_source` is mandatory and set at creation by every intake path.** No
contact enters the database without one. `BH Main` = the Buying Hero master
list (highest trust). Source drives which number pool and which outreach track
a buyer gets — it is not optional metadata, it is a routing key.

> **Tier beyond VIP is unassigned on the master list.** The A/B/C bands derive
> from InvestorBase `LinkedDeal count`; the master sheet carries no equivalent
> signal, so 17 buyers are VIP and the rest have no tier until either an
> InvestorBase match or a human judgment supplies one. The cascade must treat
> "no tier" as its own segment rather than assuming C.

> **Today the sheet's `Type` column conflates four concepts** — tier
> (`Ultra VIP`), buyer type (`Builder Buyers`, `JV Partners`, `Realtor`),
> source (`InvestorLift`, `InvestorBase`), and status (`BANNED`). Splitting
> these into independent tag groups is what makes segmentation possible.

**Custom fields — buy box** (the match engine's input)

| Field | Type |
|---|---|
| `buy_counties` | **multi-select** — all 67 FL counties ([values](field-values.md)) |
| `buy_neighborhoods` | **multi-select** — neighborhoods / sub-markets ([values](field-values.md)) |
| `buy_zips` | text |
| `buy_price_min` / `buy_price_max` | number |
| `buy_prop_types` | multi (SFR, 2–4, 5+, condo, land) |
| `buy_rehab_appetite` | light / medium / heavy / full gut / turnkey-only |
| `buy_financing` | **multi** — cash / hard money / private / DSCR |
| `buy_close_days` | 7 / 14 / 21 / 30+ |
| `buy_pof_on_file` / `buy_pof_date` | y/n + date — **two fields** |
| `buy_sqft_min` | number |
| `buy_beds_typ` / `buy_baths_typ` / `buy_sqft_typ` | what they actually buy (from purchase history) |
| `buy_out_of_state` · `buy_high_end` · `buy_relationship_building` | flags carried from the master sheet |
| `buy_entity_name` | LLC / company |

**Custom fields — history & engagement**

| Field | Purpose |
|---|---|
| `buy_deals_count`, `buy_last_purchase`, `buy_avg_price` | track record |
| `buy_last_contacted`, `buy_last_responded` | engagement |
| `buy_objection_last` | **written by AI on every call** |
| `buy_last_hook` | last opener used — generator may not repeat it |
| `buy_consent_status`, `buy_consent_date`, `buy_consent_source` | consent record |
| `buy_scrub_date` | DNC/litigator scrub timestamp |
| `buy_notes` | original prose from the master sheet — never discarded |
| `buy_extract_confidence` | high / medium / low / needs review — set by the AI extraction pass |

> `buy_objection_last` is the field nobody builds and the one that compounds.
> After 20 deals we know which buyers say "too much rehab" vs "wrong zip" vs
> "you're $15K high" — and pricing gets sharper every cycle.

**Field naming rule:** buyer fields prefix `buy_`, seller fields `sell_`. GHL
shows every custom field on every contact; without prefixes this is unusable
within a month.

### Property (custom object)

Object key **`custom_objects.property`** — note the plural `custom_objects`
prefix; the API docs example says singular and is wrong. Every field is
`prop_`-prefixed for consistent merge fields in templates.

**Property Details:** `prop_address` (primary display, **unique**) ·
`prop_city` · `prop_county` · `prop_neighborhood` · `prop_zip` · `prop_type` ·
`prop_beds` · `prop_baths` · `prop_sqft` · `prop_year_built` ·
`prop_description` · `prop_access_notes` · `prop_photos_url` · `prop_comps_url`

**Deal Economics & Dispo:** `prop_arv` · `prop_repair_est` ·
`prop_asking_price` · `prop_mao` (auto: 78% ARV − repairs − $25K) ·
`prop_contract_status` · `prop_close_date` · `prop_emd_terms` ·
`prop_il_listing_url` · `prop_deal_owner` (buying-hero / jv:name) ·
`prop_fee_split` · `prop_dispo_status` · `prop_days_on_market` ·
`prop_price_reductions`

> **`prop_neighborhood` was missing from the original model.** The narrowing
> rule in [`field-values.md`](field-values.md) compares `buy_neighborhoods`
> against the property's neighborhood — with no field on the property side there
> is nothing to compare to, and the rule silently degrades to county-only
> matching. It carries the same 87 values as `buy_neighborhoods`; the two
> picklists must be kept in sync or matching breaks quietly.

**`prop_address` is unique.** Duplicate addresses are rejected at write time.
Two consequences the team needs to know: address formatting must be
consistent (use the county record format — `123 SW 4th St` and
`123 SW 4th Street` register as different properties), and a returning dead
deal reuses its existing Property record rather than creating a second one.

### Pipelines

- **Dispo** (one opportunity per property): Intake → Packaged → Live → Offers In → Under Contract → Assigned → Dead
- **Buyer Interest** (one per buyer-property pair): **Reached Out** → Info Sent → Walked → Offer → Contract Sent → Closed → Passed

> Stage 1 was renamed from *Interested* to **Reached Out** (2026-08-14) so the
> pipeline states what actually happened. It now maps exactly onto the two-step
> mechanic: **Reached Out** = teaser sent; **Info Sent** = they replied and got
> the full house post. "Interested" was a claim about the buyer we hadn't earned.
>
> **The blast creates one opportunity per buyer who actually received the text** —
> named `{address} — {buyer}`. This is the durable buyer↔deal association: open
> the pipeline, search the address, see every buyer tied to that deal and how far
> they got. A contact field cannot express it, because a buyer belongs to many
> deals over time and a single field overwrites. The workflow resolves the stage
> **by name at runtime**, so renaming or reordering stages needs no code change.

> The Buyer Interest pipeline **replaces the per-deal tab.** Today the master
> list is copied into a fresh tab every deal and outreach is tracked by hand in
> `Current Deal Notes` / `Status`. Those become opportunity stages, tracked
> automatically, for every deal, forever.

---

## Source data — profiled

### Master buyer sheet (`! Buying Hero - Real Estate Team`)

**The curated master is the first tab, `MAIN Dispo Tab` — 143 rows, of which
121 are distinct callable contacts.** The ~1,000-row per-deal tabs
(`2165 NW 58 St`, `352 sw kentwood`, `4200 Dispo`, …) are InvestorBase pulls,
not the master list. Earlier profiling conflated the two.

`MAIN Dispo Tab` fill rates (of 143): first name 139 · phone 122 · notes 110 ·
last name 106 · type 91 · date added 33 · company 26 · email 17 ·
areas of interest 14.

The low email fill (17) matters: **email is not a viable second channel for the
warm list.** SMS and voice carry the load until emails are collected on reply.

| Sheet column | Maps to |
|---|---|
| First / Last Name | contact name |
| Phone | phone — **dedupe key** |
| Email | email |
| Company | `buy_entity_name` |
| Type = `Ultra VIP` | `tier:vip` |
| Type = `Builder Buyers` | `type:builder` |
| Type = `JV Partners` | `type:jv` |
| Type = `Realtor` | `type:realtor` |
| Type = `BANNED` | `status:blacklist` |
| Type = `InvestorLift` / `InvestorBase` | `src:*` — currently mis-filed as tier |
| Areas of Interest | `buy_counties` / `buy_zips` |
| Out of State? / High End Flips / Building Relationship | corresponding flags |
| Overall Notes | `buy_notes` **+ AI extraction pass** |
| Current Deal Notes / Status | → Buyer Interest opportunity stage |

**AI extraction pass (Phase 0).** 854 rows carry buy-box criteria as prose.
Parsing them into structured fields is what makes the database useful on day
one instead of after six months of manual entry. Real examples:

| Note | Extracts to |
|---|---|
| *"only looking for arv's of $1M+, or land to build 1M+"* | `buy_price_min=1000000`, `buy_prop_types=[SFR, Land]` |
| *"ONLY 1,800 sq ft or bigger"* | `buy_sqft_min=1800` |
| *"Broward only"* | `buy_counties=[Broward]` |
| *"Prefers turnkey properties"* | `buy_rehab_appetite=turnkey-only` |
| *"Gables, Pinecrest only, Hialeah warehouses"* | `buy_zips`, commercial interest |

Every extraction is written with a confidence flag and stays reviewable — the
prose is never discarded.

### InvestorBase export (sample: `352 SW Kentwood Rd`, 84 rows)

Richer than expected — **the buy box auto-populates**, no manual entry.

| CSV column | Maps to |
|---|---|
| Entity Name | `buy_entity_name` |
| First / Last Name | contact name |
| **Wireless 1** | phone — explicitly wireless, TCPA-relevant |
| Beta: Possible Email | email — **low confidence, do not cold-blast** |
| Buyer Type (`flipper` / `landlord`) | `type:flipper` / `type:landlord` |
| Property Type (`SFR` / `Land`) | `buy_prop_types` |
| City / Zip of purchase | derive `buy_counties`, `buy_zips` |
| Bedrooms / Bathrooms / Sqft | `buy_beds_typ` / `buy_baths_typ` / `buy_sqft_typ` |
| Most Recent + Prior Sale Price | derive `buy_price_min` / `buy_price_max` |
| Most Recent Sale Date | `buy_last_purchase` |
| LinkedDeal count | `buy_deals_count` → tier band |
| Buyer Mailing Address/City/State/Zip | mailing address |

**Tier banding from `LinkedDeal count`, with a sanity cap:**

| Deals | Tier |
|---|---|
| 1–4 | `tier:c` |
| 5–14 | `tier:b` |
| 15–49 | `tier:a` |
| 50–200 | `tier:a` + manual review |
| **>200** | `type:institutional` — **excluded from calling** |

The cap is not optional: the sample maxes at **23,078** linked deals against a
994 average. Those are iBuyers, title companies and data artifacts, not local
flippers who will buy a wholesale deal.

**Coverage:** wireless 77%, email 70%. Roughly a quarter of any InvestorBase
list is uncallable — plan volume accordingly.

---

## Subsystems

**① Intake.** One **n8n-hosted form** (not a GHL form — see below), filled by
the Dispo manager. Address, ARV, repairs, asking price, beds/baths/sqft, photos,
contract status, close date, `deal_owner`, `fee_split`, plus a **free-text full
property description** (the standout features, condition, what makes it a deal).
Upserts the property record, builds the matched buyer segment, and hands the
description to the message generator. Any team member can drop in a deal —
including someone else's.

> **No MAO computation at intake** (decided 2026-08-13). MAO is an *acquisition*
> decision — by the time a deal reaches dispo it is already under contract and
> the number was settled. Asking price is what buyers see and what the match
> engine filters on. `prop_mao` remains as a field for acquisition or JV
> reporting to populate; the intake form neither asks for it nor derives it.

> **Why an n8n form rather than a GHL form.** GHL forms map natively to
> *contact* fields, not custom-object records — a GHL form cannot create a
> Property record directly, and whether GHL workflows can trigger on
> custom-object creation is unverified. The n8n Form Trigger has neither limit,
> is a bookmarkable phone-friendly URL, and is versionable from the repo. Replies
> and pipelines still live in GHL; only the intake door sits outside it.

**①a The house post format — deterministic, not AI-written.**

Buying Hero has a proven post format used for WhatsApp deal drops. It is built
by **template code from the intake fields, not by the LLM**:

```
🏠 *{address}, {city}, FL {zip}*

⭐{headline}

🟠 *Details*
 · Beds/Bath: 2/1
 · Living Area: 805 sq ft
 · Lot Size: 6,345 sq ft
 · Roof is 3 years old
 · Key Upgrades - PVC plumbing, impact windows and doors, updated panel
 · AC age unknown
 · {extra highlights, one per line}
 · NO HOA
 · No liens or violations
 · *VACANT AT CLOSE*

🟠 *Comps*
 · {one per line}

💰 *Price:* Only $335,000

📈 *ARV:* ~$470,000

📸 *Photos/Videos:*
{drive link}
💵 *Escrow:* $10,000
```

> **Why template code rather than the message generator.** Prices, comps, sqft
> and escrow are facts. Rendering them from the form guarantees they cannot be
> paraphrased, rounded, or invented — the failure mode that would cost the most
> credibility with buyers. It is also free and instant. The LLM is reserved for
> the part that genuinely needs writing: the teaser and its hook.
>
> **Two variants are produced.** WhatsApp renders `*text*` as bold; SMS does not
> and would show literal asterisks to the buyer, so the SMS variant is the same
> content with asterisks stripped.

**①b Message generation (AI).** From the intake description, the AI drafts the
teaser and hook for that property, which the Dispo manager approves or edits
before anything sends:

1. **Teaser SMS** *(AI-written)* — beds/baths, city, ARV, price, one standout
   feature, soft CTA. **No address.** Withholding it is the mechanic: it forces a
   reply, which produces an engagement signal, opens a conversation thread for
   the AI to work, and qualifies interest before we reveal anything.
   > *"3/2 in North Miami Beach, ARV 315, price 150. Impact windows and doors
   > already in. Let me know if you want more details."*
2. **Full package = the house post, SMS variant** *(template code)* — auto-sent
   when the buyer replies asking for details. **Identical content to the WhatsApp
   drop**, asterisks stripped. There is no separately generated "full package":
   the house format already carries address, details, comps, price, ARV, photos
   and escrow, so generating a second version would only create a way for the two
   to disagree.
3. **Email version** — the same post, long form, with an AI-written subject line.
4. **Voice AI context** *(AI-written)* — the property brief Agents A–D answer
   from, so the phone, the text, and the email never contradict each other.

> **The two-step is the whole mechanic** (confirmed 2026-08-13): cold SMS gets
> the **teaser only**; the full house post goes out **on reply**. WhatsApp is a
> broadcast to people who already know us, so it gets the full post immediately.
> Sending the full post as the first cold touch would give away the deal without
> ever capturing the engagement signal.

**Hook rotation is a hard requirement.** No buyer should ever receive the same
opener twice, and no two deals go out with the same message shape.

- A hook library seeds the AI (*"Got another banger for you"*, *"This one might
  be a good fit for you"*, *"New one just came across my desk"*), and it
  generates fresh variants per deal rather than cycling a fixed list.
- `buy_last_hook` on each contact records what they last received; the
  generator is forbidden from reusing it.
- Hook and tone vary by tier — VIPs get the familiar, personal opener; cold
  InvestorBase buyers get a straight, credible intro with AI disclosure.
- Every send merges `{{first_name}}` and the sender name (e.g. Andrew), so no
  two messages are byte-identical. This is also the single cheapest carrier
  anti-filtering measure available — it serves deliverability and voice at once.

**② Match — exclusionary, not inclusionary** *(reversed 2026-08-13)*.

**Default: every active buyer with a phone receives every deal.** A buyer is
removed only when a human deliberately set an `excl_*` rule after talking to
them.

| Layer | Fields | Effect |
|---|---|---|
| **Hard suppression** | `record_type`, `buy_status` (DNC/Blacklist), missing phone | Compliance and physics. Not preferences |
| **Exclusion rules** | `excl_all_blasts` · `excl_below_price` · `excl_above_price` · `excl_below_sqft` · `excl_prop_types` · `excl_outside_counties` · `excl_outside_neighborhoods` | The **only** thing that removes a buyer from a blast |
| **Provenance** | `excl_notes` · `excl_verified_date` | Who set the rule, why, and when it was last confirmed |

> **Why the reversal.** The `buy_*` buy box was extracted from prose notes, some
> of them years old, none confirmed with the buyer. Filtering on it means a buyer
> whose 2024 note said *"Broward only"* silently stops hearing about Miami-Dade
> deals — and **a silent exclusion is invisible**: no bounce, no complaint, no
> signal. You lose the buyer and never learn why. Over-sending to a buyer who
> isn't interested costs one ignored text. Those are not symmetric risks.
>
> Only 34 of 121 buyers have extracted counties at all, so inclusionary matching
> would also have suppressed the 87 buyers whose data is merely *missing*.

**The `buy_*` data still earns its keep — as an interview queue, not a filter.**
When extracted data contradicts a deal but no `excl_*` rule exists, the run emits
a **review suggestion**: *"notes say Broward only — confirm with buyer, then set
an excl_ rule if true."* The buyer still receives the blast. Stale data becomes
a to-do list for buyer conversations instead of a silent gate.

Every run returns four lists: `included`, `excluded` (with reason, note and
verification date), `suppressed`, and `review_suggestions`.

**③ Outreach cascade.** Sequencing is where the money is:

| When | Action |
|---|---|
| T+0 | **Teaser SMS** to matched VIP/A · email package to all matched · InvestorLift listing live |
| on reply | **House post (SMS variant) auto-sent**, buyer enters Buyer Interest pipeline, AI fields questions |
| T+2h | AI voice → VIP/A non-responders |
| T+24h | Teaser SMS + AI voice → matched B/C non-responders |
| T+48h | **Price-truth call** — AI asks the 30 highest-value non-responders *"what would you need to see on this one?"* → writes `buy_objection_last` |
| T+72h | No contract → price decision, made on objection data instead of a guess |

Cold InvestorBase traffic runs as a **parallel, isolated track** — separate
number pool, separate campaign, separate agent.

**④ Inbound (the actual bottleneck).** Every channel into one Conversations
inbox. Conversation AI answers from the property record — price, ARV, repair
scope, EMD terms, access, deadline — 24/7. Escalates to a human only on: offer
amount stated, "send the contract," "when can I walk it," or a price counter.
Auto-books walkthroughs. Every interested buyer becomes a Buyer Interest
opportunity.

**⑤ Capture (compounding).** InvestorLift *New Buyer / New Lead / New Offer* →
Zapier → n8n → deduped upsert into GHL, tagged `InvestorLift`.

**InvestorBase uses the same path** — it has no public REST API, but it does
have a Zapier app, so W12 is the W11 plumbing again rather than a bespoke CSV
importer. Triggers: *New Buyer Export*, **Multiple Buyers Export**, *Buyers
List Automation*, *Multiple Buyers List Automation*, and **Send Offer Details**
(fires when someone submits an offer on one of your listings — this one feeds
the Buyer Interest pipeline directly, not just the contact database).

> **Every InvestorBase trigger is a manual click** — "Send to Zapier". There is
> no background sync. This does not remove the human step; it removes the CSV
> download, the column mapping and the hand dedupe. Select all → one click →
> n8n handles mapping, tier banding, the >200 LinkedDeal cap, phone dedupe and
> the scrub gate before anything reaches GHL.
>
> **Cost trap:** Zapier bills per task. If *Multiple Buyers Export* fires once
> per buyer, an 84-row export burns 84 tasks against a ~750/mo cheap tier — about
> 9 deals. Keep the Zap to a **single step** that forwards the raw payload to an
> n8n webhook with zero logic in Zapier. Confirm bundling behaviour when built.

Every property's skip-traced list permanently enriches the database instead of
dying in REsimpli.

**Every deal makes the machine better.** This is the exit ramp from renting
buyer data forever.

**⑥ Learning loop.** Responses update buy-box fields. Closings bump
`buy_deals_count` and tier. Three blasts with no response → `status:dormant` →
quarterly reactivation. Opt-outs → `status:dnc`, globally suppressed.

---

## Workflows to build

| # | Workflow |
|---|---|
| W1 | Property intake → upsert record + matched segment |
| W1b | **AI message generation** — teaser, full package, email, voice brief; hook rotation |
| W1c | **Teaser → house post (SMS variant) auto-send on reply** |
| W2 | Warm blast (SMS + email, tier cascade) |
| W3 | Cold blast (InvestorBase, isolated pool) |
| W4 | AI voice — warm non-responder |
| W5 | AI voice — price-truth call |
| W6 | AI voice — cold consent funnel |
| W7 | Inbound AI responder + escalation |
| W8 | Opt-out handler → global suppression |
| W9 | Buyer enrichment from responses |
| W10 | Dormancy + quarterly reactivation |
| W11 | InvestorLift capture (n8n) |
| W12 | InvestorBase capture via Zapier → n8n + scrub gate (reuses W11 plumbing) |

## AI agents

| Agent | Role |
|---|---|
| **A — Dispo Inbound** | Conversation AI on SMS/email, property-context aware |
| **B — Warm Buyer Voice** | Outbound to opted-in list |
| **C — Price-Truth Voice** | Objection extraction at T+48h |
| **D — Cold Consent Voice** | InvestorBase, opt-in as primary objective |

---

## Compliance controls

Two call lists with very different postures. The master buyer list is opted-in
— low risk, move immediately. InvestorBase skip-traced numbers are not, and AI
voice is an artificial voice hitting cell phones, which is where TCPA and
Florida FTSA exposure lives.

**The cold track is designed as a consent funnel, not a permanent exposure.**
Agent D's primary objective is not selling the property — it's earning the
opt-in: *"want me to add you to our buyer list so you get these first?"* A yes
writes `buy_consent_*` and promotes them to the warm list permanently. Every
deal shrinks the cold surface and grows the opted-in list until the risk
retires itself.

Hard requirements:

- **DNC + litigator scrub gates every import.** No record is callable until
  scrubbed and `buy_scrub_date` is set. Highest-ROI single control.
- **AI discloses it is an AI** in the opening line.
- **Opt-out → `status:dnc` instantly**, suppressed across SMS, email and voice,
  permanently, account-wide.
- **Prefer the LLC/business line** over the cell where InvestorBase provides both.
- **Recordings retained** as evidence.
- GHL native caps (1 call/number/day, 8am–8pm contact-local) already sit inside
  FTSA limits.
- **Counsel reviews the cold script once before go-live.** An hour of attorney
  time against per-call statutory damages is the cheapest item in this build.

### 10DLC

Brand is registered and vetted — that's the slow layer and it's done. But the
existing campaign's registered use case is **seller follow-up**; buyer dispo
blasts are a different use case with a different opt-in story. Sending buyer
content on the seller campaign is campaign misuse and draws carrier filtering.

Multiple campaigns register under one brand, and adding a campaign to a vetted
brand typically clears in days rather than the 1–2 weeks a cold-start brand
takes. **File the warm buyer campaign in Phase 0** with a clean, truthful
opt-in description.

The current buyer test number sits on the seller campaign — fine for testing,
**not for production blasts.**

### Number pools (deferred, decide before Phase 1 go-live)

Split by risk, not convenience: warm buyer SMS (3–4), cold InvestorBase SMS
(3–4, deliberately isolated), Voice AI outbound (1–2), seller numbers
untouched. Local 305/786/954.

Carrier filtering is **silent** — no error, messages just don't arrive. An
isolated cold pool means filtering burns cheap replaceable numbers instead of
poisoning deliverability to the opted-in list that's actually worth money.
Merge address/city/beds/price into every message so no two sends are identical.

---

## Build phases

| Phase | Deliverable | Timing |
|---|---|---|
| **0 — Foundation** | Buyer 10DLC campaign filed · MCP connection fixed · tag taxonomy + custom fields + property object + pipelines built · master sheet imported, deduped, scrubbed | Week 1 |
| **1 — Match + Blast** | Intake form live · match Smart Lists · W1–W3 · SMS/email templates → **one-button blast** | Week 2 |
| **2 — Inbound** | Agent A · W7 · W8 · escalation + calendar booking · Buyer Interest automation → **replies handled without a human until a real offer** | Week 3 |
| **3 — Capture** *(parallel)* | W11 InvestorLift · W12 InvestorBase + scrub gate · Supabase mirror → **DB grows automatically** | Week 3–4 |
| **4 — Voice** | Agent B + W4 · Agent C + W5 → **cold-call capacity problem solved for the warm list** | Week 5–6 |
| **5 — Cold + Analytics** | Agent D + W6 (post counsel + scrub vendor) · W9 · W10 · dispo analytics · JV reporting → **full machine + dispo-as-a-service** | Week 7+ |

---

## Cost

| Item | Monthly |
|---|---|
| GoHighLevel | existing |
| Zapier (InvestorLift bridge, cheapest tier) | ~$30 |
| Phone numbers (~10) | ~$15–30 |
| DNC/litigator scrub vendor | quote needed |
| Supabase | $0–25 |

**Per deal blast:** ~$25 SMS + ~$60 AI voice ≈ **under $150 against a $20K
assignment fee.** Cost is not the constraint. Bandwidth is — and this removes
bandwidth from the critical path.

---

## Open items

**Blocking Phase 0:**

1. ✅ ~~Property custom object~~ — created in the UI 2026-08-12, fields pushed
   via API. (The public API exposes no `POST /objects/`; only read, schema
   *update*, and record CRUD.)
2. ✅ ~~Dispo + Buyer Interest pipelines~~ — created in the UI 2026-08-13.
   (The public API exposes no pipeline-create operation at all.)
   - Dispo `jCqzNRCw67Snkhq0I6l6` · Buyer Interest `HyOMHkNNvhRllGNwMZsP`

**Phase 0 has no blockers remaining.** Next action is the live import of the
121 reviewed contacts.

**Received:**

- ✅ Master buyer sheet — profiled, mapping built
- ✅ InvestorBase sample export — profiled, mapping built

**Blocking later phases:**

3. **Buyer 10DLC campaign filed** — before Phase 1 go-live
4. **Scrub vendor selection + quote** (Phase 5)
5. **Counsel review of the cold script** (Phase 5)

### API surface — what Phase 0+ can and cannot automate

Established by probing the live connection, not from docs. Worth keeping: it
decides which build steps are scriptable and which need a human in the UI.

| Object | API? | Notes |
|---|---|---|
| Tags | ✅ create | `locations--create-tag` |
| Contact custom fields | ✅ create | **`locations.create-custom-field` only.** The newer `/custom-fields/` domain rejects contacts: *"Api does not support objectKey of type contact or opportunity"* — it is custom-objects-only |
| Contacts / records | ✅ full CRUD | import is scriptable |
| Custom object **fields** | ✅ create | via `/custom-fields/` with `objectKey` |
| Custom object **schema** | ❌ | no `POST /objects/` — UI only |
| Pipelines + stages | ❌ | no create operation — UI only |

Undocumented but working: `locations.create-custom-field` accepts an `options`
array of strings for `SINGLE_OPTIONS` / `MULTIPLE_OPTIONS`, returned as
`picklistOptions`. It is absent from the operation's published schema.

---

## Geography — two fields, one rule

Full picklists in **[`field-values.md`](field-values.md)**.

- **`buy_counties`** — multi-select, all 67 Florida counties. Core market is
  Miami-Dade, Palm Beach, Broward; the rest are listed so a JV deal outside the
  market never needs a schema change.
- **`buy_neighborhoods`** — multi-select, sub-market refinement. Holds
  neighborhoods (Liberty City, Wynwood) and municipalities (Coral Gables,
  Homestead) alike.

**The interaction rule:** an empty `buy_neighborhoods` means the buyer matches
county-wide. A populated one **narrows** the match to those neighborhoods only —
it never widens it. That is what keeps a *"Gables and Pinecrest only"* buyer
from receiving Homestead deals, which is how good buyers learn to ignore us.

⚠️ **Liberty County** (panhandle) and **Liberty City** (Miami-Dade
neighborhood) are unrelated values in different fields. Never let one
auto-complete into the other.

---

## Hook library — starter set

Seeds for the generator, not a fixed rotation. It writes fresh variants per
deal; `buy_last_hook` blocks reuse against the same buyer.

| # | Hook | Tier |
|---|---|---|
| 1 | *"Hey {{first_name}}, it's Andrew from Buying Hero. Got another banger for you"* | VIP / A |
| 2 | *"Hey {{first_name}} — this one might be a good fit for you."* | any |
| 3 | *"{{first_name}}, Andrew w/ Buying Hero. Just locked one up in {{city}}, thought of you."* | VIP / A |
| 4 | *"{{first_name}} — new {{beds}}/{{baths}} in {{city}}. Numbers actually work on this one."* | B / C |
| 5 | *"Hey {{first_name}}, got a new one in {{city}} before it goes out to the full list."* | **VIP only — see below** |

**Honesty constraint on scarcity hooks.** Hook 5 and anything like it may only
be sent to a tier that genuinely receives first look. The master sheet already
records a real first-dibs relationship (*"our attorney… technically gets first
dibs on all deals since he sees the contracts"*), so the claim is true for that
group and false for everyone else. The generator is not permitted to invent
exclusivity, urgency, or competing-offer claims that aren't real. Buyers compare
notes; a hook that gets caught out costs more than it earns.

---

## Resume point

**MCP connection: working.** Bound to sub-account `ib5jEnyqqq06FIEqlVGs`
(Buying Hero). `list_locations` still returns an empty list — that is cosmetic,
not a fault: the connection is single-location, so the bound location is
injected automatically and every operation resolves against it. Don't chase it.

The sub-account was effectively empty at build time — 1 seller pipeline, 0
custom fields, 7 disposable test contacts. No migration risk, no collisions.

### Done — 2026-08-12

- ✅ **Tag taxonomy — 22 tags.** `record:*` (2), `tier:*` (4), `type:*` (8),
  `status:*` (4), `src:*` (4). Six pre-existing generic tags (`cold lead`,
  `warm lead`, `follow-up`, `high priority`, `dead lead`, `remove from list`)
  were left in place — they're seller-side and harmless.
- ✅ **31 `buy_*` contact custom fields**, all under one field folder
  (`PzBSCA27g7JBIDDIXa3v`) so they don't sprawl across every contact record.
  Keys landed exactly as the Smart Lists expect — `contact.buy_counties`,
  `contact.buy_price_min`, etc.
  - `buy_counties` — 67 FL counties
  - `buy_neighborhoods` — 87 values (Miami-Dade 48 · Broward 24 · Palm Beach 14
    · `Other`)

**Three deviations from the spec above, all deliberate:**

| Change | Why |
|---|---|
| `buy_financing` is multi-select, not single | Buyers routinely use more than one. Never narrows a match |
| `buy_pof_on_file` split into a Yes/No + a separate `buy_pof_date` | "y/n + date" cannot be one GHL field |
| Added `buy_extract_confidence` | Phase 0 step 5 requires a confidence flag; there was no field to write it to |

- ✅ **Property custom object** — created in the UI, key `custom_objects.property`,
  `prop_address` primary + unique. **27 fields** pushed via API across two
  folders: *Property Details* (`GEwh92ZottzqsAWaiSVO`) and *Deal Economics &
  Dispo* (`fDcgdgv1klLgXLUOoesr`).
  - Added `prop_neighborhood` — **not in the original model**, but the
    narrowing rule is inert without it (see Property section).
  - `prop_description` added as the free-text intake field W1b generates from.

**Picklist keys:** GHL strips hyphens and spaces from option keys
(`miami-dade` → `miamidade`) but preserves labels verbatim. Match on labels,
not keys. `prop_county` / `buy_counties` and `prop_type` / `buy_prop_types`
were seeded from identical label lists so the Smart Lists compare cleanly.

### Next — Phase 0 remainder

- ✅ **Import dry run + extraction pass** — written to the
  **`GHL Import Dry Run`** tab of the master sheet for review. Source tab never
  touched, nothing written to GHL.
  - 143 source rows → **121 contacts to create** · 21 no phone · 1 duplicate
    (Rick / Rick Guzman) · 3 blacklist · 1 explicit DNC (Wilfredo Barrios,
    *"ALBERT BUYER DO NOT CONTACT"*)
  - Buy-box extracted from 110 prose notes: 34 buyers get counties, 10 get
    neighborhoods. Confidence: 40 High · 16 Medium · 6 Low · 48 Needs Review
    (note present, no buy-box criteria in it)
  - `Type` column split into its four real dimensions; source recovered from
    prose where the column was blank (*"found on investorbase"*, *"found IL"*)

### Next — Phase 0 remainder

1. **[UI — blocks everything below]** Create the **Dispo** and **Buyer
   Interest** pipelines by hand. Not creatable via API.
2. Partner review of the dry-run tab, then the live import of the 121.
3. File the buyer 10DLC campaign (parallel, no dependency on any of the above —
   and it is the long pole for Phase 1 go-live).

### Outreach posture — decided 2026-08-13

Partners elected to run **SMS and voice against InvestorBase and InvestorLift
buyers alike**, rather than holding InvestorBase on a consent-funnel-only track.
The isolated cold number pool still applies — that is a deliverability control,
not a consent one, and mixing the pools risks the opted-in list that actually
earns money.

The controls that remain load-bearing and are **not** waived by this decision:

- **DNC + litigator scrub gates every import.** No record is callable until
  scrubbed and `buy_scrub_date` is set. Nothing currently carries one.
- **AI discloses it is an AI** in the opening line.
- **Opt-out → instant suppression**, account-wide, across all channels.
- **Counsel reviews the cold script once before go-live.**

> **`buy_consent_status` stays factual.** It records how a contact actually
> reached us — InvestorBase skip-traced rows are marked `Not Opted In` even
> though they will now be contacted. Outreach policy is a separate decision from
> the consent record; a consent field edited to match policy is worthless as
> evidence precisely when it is needed.
