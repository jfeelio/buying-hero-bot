# Buying Hero Bot — Server Setup (DigitalOcean)

## Quick Facts
- **Droplet IP:** 138.197.20.145
- **Region:** New York
- **Plan:** Basic, $6/mo, 1GB RAM + 2GB swap
- **OS:** Ubuntu 22.04
- **Repo on server:** /root/buying-hero-bot

## SSH Access
```bash
ssh root@138.197.20.145
```
SSH key is at `~/.ssh/id_ed25519` on your Windows machine.

## OpenClaw
- **Install location:** /usr/lib/node_modules/openclaw
- **Config:** /root/.openclaw/openclaw.json
- **Workspace/SOUL.md:** /root/.openclaw/workspace/SOUL.md
- **Service:** runs as systemd user service
- **Start/stop:** `systemctl --user restart openclaw-gateway`
- **Status:** `systemctl --user status openclaw-gateway`
- **Health:** `openclaw gateway health`
- **WhatsApp re-link:** `openclaw channels login --channel whatsapp`

## ARV Source
- **Kiavi scraper** — blocked by Smarty on DigitalOcean IPs (cloud provider restriction)
- **RentCast fallback** — working, sold comps only, 1.5 mile radius, 180 days
- **Current active:** RentCast (Kiavi unreliable from this IP)

## API Keys (stored on server only — never in repo)
- Anthropic: set during OpenClaw onboard wizard
- RentCast: stored in /root/.openclaw/.env and openclaw.json env.vars
- RentCast key: 9cba4e7f5539467c82fdb4d9a830cb31

## WhatsApp Allowed Numbers
- +13052021404 (Partner 1 — active)
- +13059754166 (Partner 2 — add back when ready)
- +17863957840 (Lead Manager — add back when ready)
- +17868970620 (Acquisitions Manager — add back when ready)

## Deploying Changes
After editing files locally:
```bash
# Deploy SOUL.md
scp SOUL.md root@138.197.20.145:/root/.openclaw/workspace/SOUL.md
scp server/get-comps.sh root@138.197.20.145:/root/buying-hero-bot/get-comps.sh

# Restart gateway
ssh root@138.197.20.145 "systemctl --user restart openclaw-gateway"
```

## Kiavi on Server (Why It Doesn't Work)
Kiavi's address autocomplete uses Smarty API with key `181762873287145751`.
Smarty explicitly blocks cloud provider IPs:
> "Embedded key authentication is not allowed from public cloud providers"
DigitalOcean IPs are flagged. Residential IPs (home/office) work fine.
This is why the local Windows setup was created.

## Monthly Cost
| Item | Cost |
|---|---|
| DigitalOcean Droplet | $6 |
| Anthropic API | ~$10-30 |
| RentCast API | ~$20-50 |
| **Total** | **~$36-86/mo** |
