# Buying Hero Bot — Server Setup (DigitalOcean)

## Quick Facts
- **Droplet IP:** [redacted — check your DigitalOcean dashboard]
- **Region:** New York
- **Plan:** Basic, $6/mo, 1GB RAM + 2GB swap
- **OS:** Ubuntu 22.04
- **Repo on server:** /root/buying-hero-bot

## SSH Access
```bash
ssh root@YOUR_DROPLET_IP
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
- RentCast key: [stored in /root/.openclaw/.env — never commit to repo]

## WhatsApp Allowed Numbers
[stored in /root/.openclaw/openclaw.json — allowFrom array — do not commit to repo]

## Deploying Changes
After editing files locally:
```bash
# Deploy SOUL.md
scp SOUL.md root@YOUR_DROPLET_IP:/root/.openclaw/workspace/SOUL.md
scp server/get-comps.sh root@YOUR_DROPLET_IP:/root/buying-hero-bot/get-comps.sh

# Restart gateway
ssh root@YOUR_DROPLET_IP "systemctl --user restart openclaw-gateway"
```

## Kiavi on Server (Why It Doesn't Work)
Kiavi's address autocomplete uses Smarty API (embedded key — blocked from cloud IPs).
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
