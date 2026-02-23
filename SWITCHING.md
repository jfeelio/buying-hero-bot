# Buying Hero Bot — Setup Switching Guide

Two parallel setups exist. Either can be the active bot at any time.
WhatsApp is linked to one setup at a time.

---

## Setup A — DigitalOcean Server
**Status:** Built, running, WhatsApp linked
**ARV Source:** RentCast (Kiavi blocked by cloud IP restriction)
**Cost:** ~$36-86/mo
**Uptime:** 24/7 independent of local machine
**Docs:** server/README.md

### Activate Server Setup
1. SSH in: `ssh root@138.197.20.145`
2. Re-link WhatsApp if needed: `openclaw channels login --channel whatsapp`
3. Verify: `openclaw gateway health`

---

## Setup B — Local Windows Machine
**Status:** In progress
**ARV Source:** Kiavi (works — residential IP)
**Cost:** ~$10-30/mo (Anthropic API only)
**Uptime:** Depends on machine being on
**Docs:** local/README.md

### Activate Local Setup
1. Ensure OpenClaw service is running: `openclaw gateway status`
2. Re-link WhatsApp if needed: `openclaw channels login --channel whatsapp`
3. Verify: `openclaw gateway health`

---

## Switching Between Setups
WhatsApp can only be linked to one instance at a time.

**To switch from Server → Local:**
1. On server: `openclaw channels logout --channel whatsapp`
2. On local machine: `openclaw channels login --channel whatsapp` (scan QR)

**To switch from Local → Server:**
1. On local machine: `openclaw channels logout --channel whatsapp`
2. SSH into server, run: `openclaw channels login --channel whatsapp` (scan QR)

---

## Shared Files (work on both setups)
| File | Purpose |
|---|---|
| SOUL.md | Bot system prompt — copy to ~/.openclaw/workspace/SOUL.md on active setup |
| kiavi-arv.js | Kiavi ARV scraper (Node.js — works on any OS) |
| rentcast.js | RentCast comp puller (Node.js — works on any OS) |
| CLAUDE.md | Buying Hero operating manual |

## Setup-Specific Files
| File | Purpose |
|---|---|
| server/get-comps.sh | Linux bash script — calls RentCast (server only) |
| local/README.md | Windows local setup guide |
| server/README.md | DigitalOcean server guide |

---

## API Keys
| Key | Server | Local |
|---|---|---|
| Anthropic | Set via openclaw onboard | Set via openclaw onboard |
| RentCast | /root/.openclaw/.env on server | Not needed (using Kiavi) |
| Kiavi | Free, no key needed | Free, no key needed |

---

## SOUL.md Exec Command Differences
**Server (Linux):**
```
bash /root/buying-hero-bot/get-comps.sh "ADDRESS" PURCHASE REHAB
```

**Local (Windows):**
```
node C:/buying-hero-bot/kiavi-arv.js "ADDRESS" PURCHASE REHAB
```
