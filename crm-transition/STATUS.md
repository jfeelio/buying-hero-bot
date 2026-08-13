# CRM Transition — Status & Where We Left Off

**Last updated:** 2026-07-10

Living handoff doc — current state, decisions locked, and next steps for the
REsimpli → GoHighLevel + Claude migration.

---

## Current status: GHL trial connected to Claude ✅

- Started a **GHL trial** and connected it to Claude Code via the **official
  LeadConnector MCP server**.
- MCP server registered at **user scope**, name `ghl`, endpoint
  `https://services.leadconnectorhq.com/mcp/anthropic/v2`.
- Auth via a **scoped Private Integration Token (PIT)** + `locationId` header.
  `claude mcp get ghl` shows **✔ Connected**.
- **Why PIT, not OAuth:** the OAuth flow requested *all* GHL scopes (payments,
  social, store, etc.). PIT lets us grant least-privilege instead.
- **Scopes granted:** contacts, conversations/messages, opportunities, custom
  fields, tags, calendars, locations (read), phone numbers + number pools (read).
  Deliberately excluded: payments, invoices, products, store, social planner, ads.

> ⚠️ **Known gotcha:** GHL MCP tools load at Claude Code **startup**. After adding
> the server mid-session, a **restart** is required before the `ghl` tools are
> callable. (This is why the first live test is pending a restart.)

---

## Decisions locked

| Decision | Choice | Rationale |
|---|---|---|
| CRM platform | **GoHighLevel** | Only option bundling CRM + dialer + attribution + workflows + official MCP + data ownership at ~$297. Cheaper/open vs REsimpli walled garden. |
| Architecture | **GHL → Supabase → Claude** | "Buy the plumbing, build the brain." Own our data; Claude is the AI layer. |
| Dialer | **GHL native LC Phone** to start | Moderate call volume. Smrtphone is a pre-approved upgrade at ~150+ dials/rep/day. |
| Dialer AI features | **Ignore them** | Claude does transcription/summaries/scoring better downstream. Pick dialer on throughput, not AI. |
| Team access | **claude.ai custom connector** (Team plan) | Non-technical team uses plain chat; founder uses Claude Code. |
| Connection auth | **Scoped PIT** (least-privilege) | Avoids OAuth's all-scopes grant. |

---

## Next steps (in order)

1. **Restart Claude Code**, then run the **live read test** (search contacts /
   list pipelines) to confirm the read/write loop end-to-end.
2. **Build the custom-field schema** so Claude can write intelligence onto each
   lead: Motivation Score, AI Priority (A/B/C), AI Next Action, Estimated ARV,
   Repair Estimate, MAO (78% ARV − repairs − $25k), Estimated Equity, Occupancy,
   Title Status, Timeline to Sell.
3. **Wire webhooks → Supabase** (owned data lake): contact/stage/call/SMS/transcript
   events.
4. **Set up campaign tracking numbers** (Number Pools) for per-channel attribution.
5. **Junk-cleanup workflow** for spam auto-created leads.
6. **Team rollout** on claude.ai connector (scoped PIT, least-privilege).
7. **Scheduled agents:** daily A-list call sheet, weekly leadership report.

---

## Companion docs still to draft (in this folder)

- `pit-scopes.md` — least-privilege PIT scope reference
- `team-connector-guide.md` — one-page team setup for the claude.ai connector
- `rollout-checklist.md` — week-by-week checklist with owners
- `custom-fields.md` — full field schema (name, type, options, who fills it)
- `crm-comparison.md` — GHL vs Close/HubSpot/REsimpli/Podio rationale (for partner Q&A)

---

## Reference

- **Plan doc:** [GHL_CRM_PLAN.md](GHL_CRM_PLAN.md)
- **Repo:** https://github.com/jfeelio/Main-BuyingHero (private) → `crm-transition/`
- **MCP server name:** `ghl` (user scope) — do not commit the PIT anywhere.
