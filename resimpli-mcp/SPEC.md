# REsimpli MCP Connector — Spec

A remote MCP server exposing the REsimpli Open API to the Buying Hero Claude
Team, so the team can query the CRM from Claude on desktop and mobile.

**Status:** spec for review. Nothing built yet.
**Revised 2026-09-20** with corrections verified against the live API — see
the CORRECTED markers. REsimpli confirmed staying for now, so this is live again.
**Decided:** Option B (purpose-built server, OAuth), read-only, whole team.

---

## 1. Why a purpose-built server

Claude custom connectors require a **remote HTTP/SSE MCP server** reachable from
Anthropic's cloud — local stdio servers cannot be used. On Team plans the Owner
adds the connector org-wide and each member authenticates individually, which
means per-user OAuth rather than one shared secret.

Jorge is `primary_owner` of the Buying Hero org, so he can add it.

The alternative (wrapping calls in n8n's MCP Server Trigger) would work but
authenticates with a single bearer token shared across the team — a secret to
distribute and rotate by hand, and it fights the per-member model.

---

## 2. Read-only, by construction

REsimpli's API has `lead/delete`, `buyer/delete`, `vendor/delete` and
`agent/delete`, and **no update endpoint** — there is no undo path. A lead
deleted via API cannot be restored via API.

**No write or delete tool is implemented.** This is not a permission flag
someone can flip; the code to delete simply does not exist, so no prompt
phrasing can reach it. `lead/add` exists in REsimpli's catalog but is not
usable yet and is out of scope regardless.

Second consequence worth stating: the REsimpli key is account-wide and tied to
`jorge@buyinghero.com`. Every call the server makes lands in REsimpli as Jorge.
There is no per-user attribution on REsimpli's side. That is acceptable for
reads and would not be acceptable for writes.

---

## 3. Architecture

```
Claude (web / desktop / mobile)
        │  HTTPS + OAuth 2.1 bearer
        ▼
mcp.buyinghero.com            ← new Caddy route, Let's Encrypt
        │
   resimpli-mcp container     ← new container on the existing n8n-vm
        │  Authorization: <raw key>   (server-side only, never sent to clients)
        ▼
api.resimpli.com/api/v6/openapi
```

Runs on the existing GCP VM `n8n-vm` (`us-east1-b`, project
`buyinghero-automations`) alongside `n8n-n8n-1`, `n8n-postgres-1`, `n8n-caddy-1`.
Added to the same `docker-compose` in `/opt/n8n/`, with a new Caddy site block.
No new infrastructure, no new billing.

DNS: `mcp.buyinghero.com` → `34.23.238.155` (the existing reserved static IP).

---

## 4. Authentication

**Claude → MCP server:** OAuth 2.1 with PKCE. Rather than building an identity
system, the server delegates to **Google as the upstream IdP** and restricts
sign-in to the `buyinghero.com` domain. The team already has Google accounts and
the project already lives in GCP, so this adds no new account surface. Each
member authenticates as themselves; access is revoked by disabling their Google
account.

**MCP server → REsimpli:** the key is read from the container environment
(populated from GCP Secret Manager, the same pattern as `N8N_ENCRYPTION_KEY`).
It is never returned in a tool response, never logged, and never reaches a
client.

Rotation: update the secret, restart the container. No client-side change.

---

## 5. Tool surface

All read-only. Every REsimpli endpoint is `POST`, including reads.

| Tool | REsimpli endpoint | Purpose |
|---|---|---|
| `search_leads` | `/lead/list` | find sellers by text, status, or pipeline |
| `get_lead` | `/lead/details` | full record for one lead |
| `get_lead_activity` | `/callLogList` | call / SMS history for one lead |
| `list_leads_by_status` | `/lead/list` | everything in a given pipeline + status |
| `list_pipelines` | `/getPipelineList` | pipelines and their statuses |
| `search_buyers` | `/buyer/list` | cash buyers with target counties / cities / zips |
| `list_appointments` | `/appointmentList` | upcoming or past, by assignee, with outcome |
| `lookup_reference` | `/marketList`, `/marketingCampaignList`, `/tagList`, `/userList` | campaigns, markets, tags, users |

### Notes on specific tools

**`search_leads`** — `/lead/list` accepts `searchStr`, `mainStatusId[]`,
`page`, `limit` (max 100). It has **no date filter**, so
"leads from last week" requires paginating and filtering server-side. The tool
should accept a date range and do that work rather than exposing the limitation.

**CORRECTED — `pipelineId` is silently ignored.** An earlier draft listed it as
a filter. Passing it returns the FULL database while looking like a filtered
result — the exact silent-partial-data failure section 6 warns about. Scope with
`mainStatusId[]` instead; statuses come from `getPipelineList` →
`items[].mainStatusList[]`.

**`get_lead`** returns 73 fields including `isQualified`, `communications`
(inbound/outbound call and SMS counts with last-contact timestamps),
`callMetrics`, property/valuation/tax data, and tags. The tool should return a
trimmed, readable projection by default with an `include_raw` escape hatch —
73 raw fields is unusable in a chat reply.

**`get_lead_activity`** — `/callLogList` requires `moduleId` (1 = Lead),
`subModuleId` (the lead's ObjectId), `type`, `page`, `limit`. Records carry
`direction` (`outgoingCall` / `incomingCall` / `outgoingSms` / `incomingSms` /
`outgoingEmail` / `taggedComment`), `createdBy` (user ObjectId), `createdAt`,
`status` and `body`. The tool resolves `createdBy` to a name via `/userList`.

**`list_appointments`** — `/appointmentList` supports `isUpcoming`,
`assignUserId[]`, `startDateTime`/`endDateTime`, and `appointmentStatus`
(`0` no answer · `1` kept · `2` not kept · `3` dismissed).

### Deliberately excluded

- Every `*/delete` endpoint.
- `lead/add` and all other writes.
- **Deals / closings.** There is no transactions endpoint — `getPipelineList`
  exposes only moduleType 1–4 (Leads, Buyers, Vendors, Agents), and the
  `transactionPipelineId` on a lead has no list API. "How many deals did we
  close this month" is therefore UNANSWERABLE by this connector. Say so in the
  tool descriptions; the team will ask it from their phones on day one.
- **Tasks** — REsimpli exposes no task endpoint. `taskCount` on `/lead/details`
  is an unpopulated field: it returns `0` on all 397 live leads, and
  `appointmentCount` likewise returns `0` despite 226 appointments existing.
  Do not build a tool on those counters; they carry no data.

---

## 6. Hard-won REsimpli details the implementation must honour

Source of truth: **https://developer.resimpli.com** — the docs site is a React
SPA, so the machine-readable contract is
`https://developer.resimpli.com/openapi-endpoints.json` (34 endpoints).

- Base URL `https://api.resimpli.com/api/v6/openapi`; every endpoint is `POST`.
- Auth header is `Authorization: <raw key>` — **no `Bearer` prefix**.
- **Rate limiting is silent.** Firing ~180 sequential requests with no delay
  produced dropped responses that surfaced as *missing fields*, not errors —
  which reads as real data and is genuinely dangerous for a tool the team
  trusts. The client MUST throttle and retry with backoff, and MUST fail
  loudly rather than returning a partial result.
- **CORRECTED — throttle is ~0.7 s, not 0.1 s.** Measured 2026-09-17: six
  concurrent workers drew immediate `429`s even with backoff; 0.7 s serial ran
  185 lead-detail calls clean with zero failures.
- Error semantics: `401 "Invalid param!"` = Authorization header absent or
  malformed. `401 "Record not found!"` = header arrived, key not recognised.
- `marketingCampignId` is misspelled in the API (no second "a"). Reproduce it
  exactly.
- Pagination: `limit` max 100. Lead list is ~793 records ≈ 8 pages.
- **CORRECTED — paging is NOT stable.** `/lead/list` orders by a mutable field,
  so pages overlap: one pull returned 190 records for 182 unique leads. Records
  can therefore also be MISSED, not just duplicated. Any list tool must dedupe
  by `_id`.
- **`data.count` is the authoritative total** and is the fix for the above: page
  until the unique set matches `count`, and report a shortfall rather than
  silently under-returning.
- `/marketingCampaignList` requires `campaignType` (1 = Lead); it `400`s without
  it.

### Known ObjectIds (this account)

```
market        686e80f9cb41069d6c7735b4   Primary Market (only one)
campaign      6aa4f3c24ded82f2fd087b6d   Bolt PPC
pipeline      6aa4dc81d18014f8fc5e5357   Active Leads
status        6aa4dc81d18014f8fc5e5358   New Leads
```

Pipelines: Active `…5357` · **Cold Leads** `…5346` (CORRECTED — not "Warm")
· Dead `…534d` · Referred to Agent
`…534f`. `mainStatusId` has no lookup endpoint of its own — statuses come back
nested under `getPipelineList` → `items[].mainStatusList[]`.

---

## 7. Data exposure

The connector surfaces seller names, phone numbers, property and mailing
addresses, and call/SMS bodies to anyone in the org who connects. That is
internal CRM data and appropriate for the team.

It is **not** the vendor-facing surface. The Bolt PPC performance sheet has its
own PII rules (no mailing addresses, buyer contacts, or staff emails) — those
rules govern that sheet and are unaffected by this connector. Nothing here
should be pointed at an outside vendor.

---

## 8. Build order

1. Scaffold the MCP server (streamable HTTP) with the 8 tools against a stub.
2. REsimpli client: throttle, retry with backoff, loud failure, key from env.
3. Wire tools to live endpoints. Verify against `data.count` per endpoint
   rather than hard-coded totals — those drift (780 leads on 2026-09-14, 793 on
   2026-09-20; Active 195 -> 184).
4. OAuth via Google, domain-restricted to `buyinghero.com`.
5. Container + Caddy route + DNS for `mcp.buyinghero.com`.
6. Secret into GCP Secret Manager; drop the local `~/.resimpli_key` path.
7. Jorge adds the connector org-wide; one member test-connects from mobile.

Steps 1–3 are testable locally with no deployment.

---

## 9. Open questions

1. **`mcp.buyinghero.com`** — is that the subdomain you want, and do you control
   the DNS zone directly?
2. **Google as IdP** — the OAuth consent screen in GCP project
   `foreclosure-agent-bh` is in **Testing** status, which expires refresh tokens
   every 7 days. It must be published to *In production* before Google backs any
   login here. The same blocker already breaks the Drive credential weekly and
   gates the Gmail send on the weekly MLS sweep. Separately: is everyone on a
   `@buyinghero.com` Google account? Luis
   started 31 Aug; if he's not on the domain yet that gates his access.
3. **Result size caps.** A "list everything" question could return 780 leads.
   Propose a hard cap of 50 records per response with a summary line telling the
   user how to narrow — protects both the context window and the API.
4. **Should Dead leads be searchable?** 389 of 793 (49%) are dead — 54% of
   direct-mail leads vs 30% of PPC. Including them
   makes searches noisier; excluding them by default (with an opt-in flag) is
   probably right, but it's your call.
