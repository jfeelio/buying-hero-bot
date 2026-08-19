# Post-blast verification

    python post_blast.py --address "580 SE 6th St, Hialeah, FL 33010"
    python post_blast.py --address "..." --exec 91     # pin a specific n8n run

Run it right after a blast, and again the next morning once buyers have replied.

## What this is, and what it is not

`../console/npm test` proves the **logic** is right. It runs offline against the
workflow JSON, so it cannot drift from what executes — but it never touches a
real buyer.

This proves the blast **actually did** what the logic says, in the live
database, to real people. Neither replaces the other.

## What it checks

| | |
|---|---|
| **1** | What the workflow reported — queued, failed, opportunities, engagement writes, and that those numbers agree with each other |
| **2** | One Buyer Interest opportunity per buyer, all carrying `opp_deal_address` so the pipeline filters by deal |
| **3** | `buy_deals_sent`, `buy_last_deal`, `buy_first_contacted`, and that `buy_last_hook` holds the personalised opener rather than a raw `{{first_name}}` |
| **4** | Every buyer got a sending number, from the pool, never the seller-side main line; VIPs and JV partners on the relationship number |
| **5** | Nobody who should have been silent was texted — DNC, Blacklist, DND, and no TEST record riding along on a real blast |
| **6** | Replies: `buy_last_responded` stamped, and no InvestorLift buyer auto-advanced to Info Sent |

## Two things it deliberately does not fail on

**A test send.** If every buyer reached carries `buy_type = TEST`, that is a test
send doing its job, reported as a note. A TEST record *alongside* real buyers is
a failure, because that is the case that actually matters.

**A blast that predates a feature.** No `buy_from_number` on anyone means the
blast ran before sticky numbers existed, not that the write-back broke.

## Why it reads contacts by id

GHL's `search` endpoints return a **partial** custom-field projection. Verifying
against search twice made a perfectly good write look like a failure during the
build. Every contact here is fetched by id.
