# Windows Restore Guide — Buying Hero Dev Environment

Use this after a full Windows reset to get everything running again.
This file lives in Dropbox and survives the wipe.

---

## 1. Install Prerequisites

| Tool | Version at wipe | Download |
|------|----------------|----------|
| Python | 3.13.1 | https://python.org — check "Add to PATH" during install |
| Node.js | 24.13.1 | https://nodejs.org (LTS) |
| Git | any | https://git-scm.com |

---

## 2. Restore the Dev Folder

Dropbox will sync `D:\Dropbox\J Feels\Dev\` automatically once Dropbox is installed.
Wait for full sync before proceeding.

---

## 3. Foreclosure Agent Setup

### Install Python dependencies
```bat
cd "D:\Dropbox\J Feels\Dev\foreclosure-agent"
pip install -r requirements.txt
playwright install chromium
```

### Restore .env
Create `D:\Dropbox\J Feels\Dev\foreclosure-agent\.env` with this content:
```
GOOGLE_SHEET_ID=1d2Wffl7gGIGikKi5QVPtJfFWCGupWysukZnzhmYBDZ4
GOOGLE_CREDS_PATH=credentials.json
SHEET_TAB_NAME=31. Pre-foreclosure (Clients)
PROBATE_SHEET_TAB_NAME=Probate
PROBATE_GOOGLE_SHEET_ID=1uF-LJ06YXM5dD9jChm-rwhvcOE9UHHLkC8AxYfbAwr0
```

### credentials.json
Already synced via Dropbox — no action needed.

### Test the agent manually
```bat
cd "D:\Dropbox\J Feels\Dev\foreclosure-agent"
python main.py
python main_probate.py
```

---

## 4. Windows Task Scheduler — Foreclosure Agent (Daily)

**Ask Claude Code to run this setup**, or do it manually:

```bat
schtasks /create /tn "Buying Hero - Foreclosure Daily" /tr "\"D:\Dropbox\J Feels\Dev\foreclosure-agent\run_daily.bat\"" /sc daily /st 07:00 /ru "%USERNAME%" /rl HIGHEST /f
```

- **Task name:** Buying Hero - Foreclosure Daily
- **Script:** `D:\Dropbox\J Feels\Dev\foreclosure-agent\run_daily.bat`
- **Schedule:** Daily at 7:00 AM
- **Run as:** current user, highest privileges

---

## 5. Windows Task Scheduler — Probate Agent

```bat
schtasks /create /tn "Buying Hero - Probate" /tr "\"D:\Dropbox\J Feels\Dev\foreclosure-agent\run_probate.bat\"" /sc weekly /d MON /st 07:30 /ru "%USERNAME%" /rl HIGHEST /f
```

- **Task name:** Buying Hero - Probate
- **Script:** `D:\Dropbox\J Feels\Dev\foreclosure-agent\run_probate.bat`
- **Schedule:** Weekly on Monday at 7:30 AM

---

## 6. Lis Pendens Agent Setup

Scrapes Miami-Dade Clerk of Courts daily for new Lis Pendens filings.
Enriches with property data and uploads 3 CSVs to Google Drive automatically.

### Install Python dependencies
```bat
cd "D:\Dropbox\J Feels\Dev\lis-pendens-agent"
pip install -r requirements.txt
```

> No Playwright needed — uses Selenium + Chrome. Chrome must be installed.

### credentials.json + token.json
Both are already synced via Dropbox — **no action needed.**
- `credentials.json` — OAuth2 app credentials (Google Drive API)
- `token.json` — OAuth2 refresh token (auto-refreshed on each run, stays valid)

If `token.json` is missing or expired, run the script once manually in a visible window — it will open a browser to re-authenticate:
```bat
cd "D:\Dropbox\J Feels\Dev\lis-pendens-agent"
python enhanced_master_script.py
```

### Google Drive output folder
All CSVs upload here automatically:
`https://drive.google.com/drive/folders/1XIz0x-abhfLb1RGYZBH4fRj16aVxhdNg`

Files produced daily:
- `lis_pendens_raw_YYYYMMDD.csv` — all raw records from clerk site
- `enriched_lis_pendens_final_YYYYMMDD.csv` — enriched with property data
- `lis_pendens_mail_ready_YYYYMMDD.csv` — cleaned, ready for mail campaign

### Test manually
```bat
cd "D:\Dropbox\J Feels\Dev\lis-pendens-agent"
python enhanced_master_script.py
```

---

## 7. Windows Task Scheduler — Lis Pendens Agent (Daily)

```bat
schtasks /create /tn "Buying Hero - Lis Pendens Daily" /tr "\"D:\Dropbox\J Feels\Dev\lis-pendens-agent\run_daily.bat\"" /sc daily /st 09:00 /ru "%USERNAME%" /rl HIGHEST /f
```

- **Task name:** Buying Hero - Lis Pendens Daily
- **Script:** `D:\Dropbox\J Feels\Dev\lis-pendens-agent\run_daily.bat`
- **Schedule:** Daily at 9:00 AM
- **Output log:** `D:\Dropbox\J Feels\Dev\lis-pendens-agent\lis_pendens_automation.log`

---

## 8. Node / kiavi-arv.js Setup

```bat
cd "D:\Dropbox\J Feels\Dev"
npm install
```

---

## 9. Verify Everything

```bat
:: Check foreclosure agent logs
dir "D:\Dropbox\J Feels\Dev\foreclosure-agent\logs\"

:: Check lis pendens log
type "D:\Dropbox\J Feels\Dev\lis-pendens-agent\lis_pendens_automation.log"

:: Manually trigger foreclosure agent
"D:\Dropbox\J Feels\Dev\foreclosure-agent\run_daily.bat"

:: Manually trigger lis pendens scraper
"D:\Dropbox\J Feels\Dev\lis-pendens-agent\run_daily.bat"
```

---

## Claude Code Note

When you open Claude Code in `D:\Dropbox\J Feels\Dev\` after restore, tell it:
> "I just restored Windows. Please re-create the Task Scheduler tasks."

Claude will use this file to recreate all three scheduled tasks:
- Buying Hero - Foreclosure Daily (daily 7:00 AM)
- Buying Hero - Probate (weekly Mon 7:30 AM)
- Buying Hero - Lis Pendens Daily (daily 9:00 AM)
