# n8n → GCP Production Deployment Plan

Goal: move the working local n8n (currently proven on `localhost`) to an always-on
GCP host with a public HTTPS URL, so **real** GHL inbound-call webhooks reach it 24/7.

Status of what we're deploying: `01-inbound-call-attribution.json` — inbound call →
map dialed number to Lead Source → dedup check → create GHL opportunity. Verified locally.

---

## 1. Architecture decision — VM, not Cloud Run

**Recommendation: Compute Engine VM running n8n in Docker.** Not Cloud Run.

Why not Cloud Run: it scales to zero and is request-driven. n8n needs a **persistent,
always-running** process to (a) keep webhooks registered, (b) run scheduled/cron
workflows, and (c) hold execution state. Forcing Cloud Run to stay warm (min-instances=1)
+ external Postgres ends up more complex *and* costs the same as a small always-on VM.
A VM is the standard, well-documented n8n production pattern and the simplest to run for
a 4-person team.

```
Internet (GHL webhooks)
   │  HTTPS
   ▼
[ Caddy ]  ← auto TLS (Let's Encrypt)
   │
   ▼
[ n8n container ] ── [ Postgres container ]  (both via docker-compose on one VM)
```

## 2. Components

| Component | Choice | Notes |
|-----------|--------|-------|
| Compute | **e2-small** (2 vCPU shared, 2GB) | Enough for our volume; can resize up later |
| OS | Container-Optimized OS or Debian 12 | Debian = easier Docker/Caddy |
| Orchestration | **docker-compose**: n8n + Postgres + Caddy | Single-file, reproducible |
| Database | **Postgres** (container on same VM) | SQLite doesn't scale/backup well for prod |
| TLS / reverse proxy | **Caddy** | Automatic HTTPS, ~3 lines of config |
| Public IP | **Reserved static IP** | So DNS never breaks on restart |
| DNS | subdomain, e.g. `automations.buyinghero.com` | Needs a DNS A-record → static IP |
| Secrets | `N8N_ENCRYPTION_KEY` + GHL token | See security section |

## 3. Cost estimate

| Item | ~Monthly |
|------|----------|
| e2-small VM (always-on) | ~$13 |
| 20GB persistent disk | ~$2 |
| Static IP (in use) | ~$0–3 |
| **Total** | **~$15–20/mo** |

Trivial against the ops it runs — but real, so worth confirming before we provision.

## 4. Security (matches the "reputation + seller PII" posture)

- **HTTPS only** — Caddy + Let's Encrypt; firewall opens **443 + 80 + 22** only.
- **SSH locked down** — key-based, ideally restricted to your IP.
- **`N8N_ENCRYPTION_KEY`** — set explicitly and **back it up**. It encrypts all stored
  credentials (the GHL token). Lose it = credentials unreadable. Store a copy in a
  password manager.
- **GHL token** — re-created as an n8n Header Auth credential inside the cloud instance
  (never in the repo, never in chat). Scopes stay minimal (contacts + opportunities r/w).
- **n8n owner login** — strong password; consider n8n's 2FA.
- **`WEBHOOK_URL`** env set to the public HTTPS URL so n8n generates correct webhook links.

## 5. Deployment steps (most driven from here via `gcloud`)

1. Pick/confirm GCP project; enable Compute Engine API.
2. Reserve a static external IP.
3. Create the e2-small VM (Debian 12), firewall rules (80/443/22).
4. Point DNS A-record `automations.buyinghero.com` → static IP.
5. Install Docker + docker-compose on the VM.
6. Drop in `docker-compose.yml` (n8n + Postgres + Caddy) + `Caddyfile` (I'll generate these).
7. Set env: `N8N_ENCRYPTION_KEY`, `WEBHOOK_URL`, `N8N_HOST`, DB creds, `GENERIC_TIMEZONE`.
8. `docker compose up -d` → n8n live at the HTTPS URL.
9. Create n8n owner login; re-create the GHL Header Auth credential (paste token).
10. Import `01-inbound-call-attribution.json`; fix the credential ref; activate.
11. Smoke test: POST a sample payload to the public webhook (as we did locally).

## 6. GHL side — the ONE webhook-sender workflow (built once in GHL UI)

After n8n is public:
- GHL → Automations → Workflows → **Inbound Call** trigger
- Action: **Webhook** → POST to `https://automations.buyinghero.com/webhook/ghl-inbound-call`
- Map fields into the body: `to`, `from`, `contact_id`, `first_name`, `last_name`
- Publish. This is the only thing that ever lives in GHL's builder; all logic stays in n8n.

## 7. Backup / DR

- Workflows already versioned in this repo (`n8n-workflows/*.json`).
- Back up: `N8N_ENCRYPTION_KEY` + nightly Postgres dump (cron → GCS bucket).
- Redeploy from scratch = new VM + compose + restore key + re-import JSON.

---

## Open decisions to confirm before we execute

1. **Domain**: do you control DNS for `buyinghero.com` (to add an `automations.` subdomain)?
   If not, alternatives: a cheap dedicated domain, or use the raw IP with a self-managed cert
   (not recommended).
2. **GCP project**: new dedicated project, or an existing one?
3. **Region**: default `us-east1` (close to Florida) unless you prefer otherwise.
4. **Budget ok** at ~$15–20/mo?

Answer these next session and I can provision most of it from here via `gcloud`.
