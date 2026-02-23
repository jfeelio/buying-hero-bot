# Buying Hero Bot — Local Setup (Windows Machine)

## Why Local?
Kiavi's ARV estimator uses Smarty for address autocomplete.
Smarty blocks cloud provider IPs (DigitalOcean, AWS, etc.).
Running OpenClaw on a local Windows machine with a residential ISP
connection bypasses this restriction — Kiavi works perfectly.

## Prerequisites
- Node.js v20+ installed
- Git installed
- Repo cloned to a local folder (e.g. C:\buying-hero-bot)

## Install OpenClaw on Windows
Open PowerShell or Git Bash and run:
```bash
curl -fsSL https://openclaw.ai/install.sh | bash
```

## Configure OpenClaw
1. Run the onboard wizard:
   ```bash
   openclaw onboard
   ```
2. Select **Anthropic** as AI provider, enter API key
3. Select **WhatsApp** as channel, scan QR code
4. Skip skills and hooks

## After Onboarding — Lock Down to Team Numbers
Edit `~/.openclaw/openclaw.json`, set allowFrom:
```json
"allowFrom": [
  "+13052021404",
  "+13059754166",
  "+17863957840",
  "+17868970620"
]
```

## Deploy SOUL.md
Copy the shared SOUL.md to the OpenClaw workspace:
```
C:\Users\[you]\.openclaw\workspace\SOUL.md
```

## ARV Script (Windows)
Run comps via:
```
node C:\buying-hero-bot\kiavi-arv.js "ADDRESS" PURCHASE_PRICE REHAB
```

The SOUL.md exec command for local Windows:
```
node C:/buying-hero-bot/kiavi-arv.js "FULL ADDRESS" PURCHASE_PRICE REHAB
```

## Install Playwright (for Kiavi scraper)
```bash
cd C:\buying-hero-bot
npm install playwright
npx playwright install chromium
```

## Test Kiavi Locally
```bash
node kiavi-arv.js "9590 NW 33rd Ave, Miami, FL 33147" 365000 70000
```
Expected: ARV ~$572,000 (validates residential IP is working)

## OpenClaw Service
OpenClaw installs as a background Windows service automatically.
It starts on boot and runs silently — your machine stays fully usable.
Restart if needed: `openclaw gateway restart`

## Monthly Cost (Local Setup)
| Item | Cost |
|---|---|
| DigitalOcean Droplet | $0 (not needed) |
| Anthropic API | ~$10-30 |
| RentCast API | $0 (not needed — using Kiavi) |
| Kiavi | Free |
| **Total** | **~$10-30/mo** |

## Switching Back to Server
See SWITCHING.md in the repo root.
