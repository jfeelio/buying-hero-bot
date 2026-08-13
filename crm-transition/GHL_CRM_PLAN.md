# Buying Hero — CRM + AI Platform Plan

**Prepared for:** Partner review
**Date:** July 2026
**Decision needed:** Approve migration from REsimpli to a GoHighLevel-backed CRM + Claude AI brain

---

## The problem we're solving

REsimpli works, but it's a closed box. We can't get our own data out cleanly, we
can't automate lead prioritization the way we want, and their AI add-on runs
~$900/mo for a black box we don't control. We're flying without the metrics and
leverage we need to hit 4–6 deals/month at a $20K average fee.

**Goal:** own our data, automate lead prioritization and reporting, and give the
whole team an AI assistant that actually knows our pipeline — without turning our
4-person team into a software company.

---

## The decision: buy the plumbing, build the brain

Split the problem into two layers and treat them completely differently:

1. **CRM + dialer = buy it (GoHighLevel).** Phone numbers, power dialer, call
   recording, transcription, SMS, pipelines, compliance (A2P 10DLC) — this is
   commodity, regulated plumbing. Rebuilding it would be a massive waste. GHL
   does it all natively in 2026.

2. **AI brain + our data = build it (Supabase + Claude).** This is our actual
   edge and it's cheap. A copy of all our data in our own database, with Claude
   able to read it, rank leads, and generate reports on command.

---

## What it looks like

```
   GoHighLevel (CRM + Dialer)
   - LC Phone: power dialer, call recording, AI transcription, SMS
   - Pipelines, workflows, mobile app (iOS/Android)
   - Call tracking numbers -> campaign/source attribution
            |
            |  webhooks + API (real-time)
            v
   Supabase (OUR data lake)
   - Owned, queryable copy of every lead, call, text, transcript
   - Lock-in insurance: we never get boxed in like REsimpli again
            |
            |  MCP (official GHL connector)
            v
   Claude (our AI brain)
   - Team asks in plain English: prioritize leads, draft messages, pull reports
   - Scheduled agents: daily call list, weekly leadership report
```

---

## What this gives us

- **Own our data.** A live copy of everything in our own database. No vendor can
  lock us out or hold our pipeline hostage.
- **Real attribution.** Every marketing channel (mail, signs, PPC, Google Ads)
  gets its own tracking number. We finally see cost-per-lead and cost-per-contract
  by channel — directly feeding our 10–15% marketing-spend discipline.
- **AI prioritization.** Claude ranks the pipeline every morning: motivation +
  timeline + call attempts + recency = today's A-list call queue, built before the
  team logs in.
- **Team-wide AI assistant.** The Lead Manager and Acquisitions Manager use Claude
  in a normal web browser (and mobile) to prioritize calls, draft seller follow-ups,
  and pull stats — no technical skill required.
- **Leadership insights on autopilot.** Weekly reports (deals by source, conversion
  by channel, pipeline health) generated automatically.

---

## Cost

| Item | Monthly |
|---|---|
| GoHighLevel (likely Unlimited $297 tier — MCP access) | ~$297 |
| Phone usage (Twilio passthrough) | ~$20–60 |
| Supabase (our database) | $0–25 |
| Claude Team plan (per seat, ~4 seats) | per-seat |
| **All-in** | **~$400–600/mo** |

**Versus** the ~$900/mo REsimpli AI upcharge alone — we get more, own our data, and
pay less.

---

## How the team uses it

| Person | Tool | What they do |
|---|---|---|
| Technical partner | Claude Code + GHL MCP | Builds automations, reports, the data pipeline |
| Lead Manager / Acquisitions Mgr | claude.ai (web + mobile) | Plain-English: prioritize calls, draft messages, check stats |

Non-technical team members work entirely in a chat box. The official GHL connector
plugs into Claude's web app — Owner adds it once, each member enables it.

---

## Key facts we verified

- **GHL has iOS + Android apps** (search "LeadConnector" in the app store). Team can
  make/take calls from their phones — *but only calls made through the app get logged,
  recorded, and attributed.* Hard rule: dial through the app, never personal phones.
- **Inbound calls auto-create a lead** tagged to the campaign's tracking number. We'll
  add a junk-cleanup workflow so spam calls don't pollute our metrics.
- **Official GHL MCP server (launched early 2026)** lets Claude read AND write to GHL
  directly — no custom build needed.
- **Google Ads form notifications** can ping the team in real time (native GHL workflow
  — Zapier not even required).

---

## Dialer decision (July 2026)

**Start on GHL native LC Phone. Do not add Smrtphone yet.**

- Current calling profile is a *moderate mix* (follow-up + some outbound, single-line).
  GHL's native sequential power dialer is sufficient and avoids a second vendor/bill.
- Smrtphone's real advantage is its **multi-line auto dialer** (2–4x live conversations/hr),
  which only pays off at high cold-call volume we don't run today.
- Do NOT choose a dialer for its built-in AI (transcription/summaries/keyword tracking) —
  Claude does all of that better once transcripts hit Supabase. AI is our layer, not the vendor's.

**Pre-approved upgrade trigger — move to Smrtphone when ANY is true:**
- Reps consistently exceed ~150 dials/rep/day, OR
- We add a dedicated cold-calling seat/campaign working large lists, OR
- Low connect rates mean reps waste real time on no-answers (multi-line reclaims those hours).

Smrtphone syncs into GHL, so adding it later doesn't disrupt the architecture.

---

## Risks / things to manage

1. **A2P 10DLC registration is the long pole** — start it day one; approval can take
   1–2 weeks and gates all texting.
2. **Shared AI credential.** Claude's Team connector currently uses one shared token
   with no per-user permission scoping. Mitigation: grant least-privilege scopes; fine
   for a trusted 4-person team.
3. **Discipline dependency.** The whole system only works if reps dial through the app.
   This is a training/SOP item, not a tech problem.
4. **Use only the official GHL connector** — never third-party ones that ask for our
   API token (that would hand a stranger our whole CRM).

---

## Rollout (proposed)

- **Week 1–2:** Stand up GHL, port numbers, start 10DLC registration, import leads,
  set up campaign tracking numbers.
- **Week 2–3:** Wire webhooks -> Supabase (our data lake). Build junk-cleanup + Google
  Ads notification workflows.
- **Week 3–4:** Connect Claude via official MCP. Roll out claude.ai to the team.
- **Week 4+:** Turn on scheduled agents — daily A-list call sheet, weekly leadership
  report.

---

## The ask

Approve the move to GoHighLevel (Unlimited tier) + Claude Team, and the ~$400–600/mo
budget. Everything else (Supabase, automations, AI setup) we build in-house at
effectively no added cost. Net result: a disciplined, data-owned acquisition machine
for less than we're paying REsimpli's AI add-on today.
