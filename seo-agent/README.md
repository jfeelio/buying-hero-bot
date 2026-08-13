# Buying Hero — SEO Agent

Programmatic SEO audit + blog planner for [buyinghero.com](https://www.buyinghero.com).

## What it does

1. **Crawls** buyinghero.com (Playwright) — extracts titles, descriptions, H1s, word count, images, schema, etc.
2. **Runs PageSpeed Insights** — mobile + desktop scores, Core Web Vitals
3. **Analyzes on-page issues** — 12-rule engine (critical / warning / info)
4. **Claude AI analysis** — audit report + priority fixes + revised meta titles/descriptions
5. **Generates blog calendar** — 50 South Florida seller keywords with outlines
6. **Outputs** to Google Docs (audit), Google Sheets (blog plan), and local Markdown
7. **Applies changes** to Carrot dashboard via Playwright (optional, gated behind confirmation)

---

## Setup

```bash
cd seo-agent
pip install -r requirements.txt
playwright install chromium
cp .env.template .env
# Fill in .env (see section below)
```

### `.env` values needed

| Key | Where to get it |
|-----|----------------|
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `PAGESPEED_API_KEY` | console.cloud.google.com → enable "PageSpeed Insights API" (free) |
| `GOOGLE_CREDS_PATH` | Point to `../foreclosure-agent/credentials.json` (already exists) |
| `SEO_GOOGLE_SHEET_ID` | Create a Google Sheet, share with service account, paste ID |
| `CARROT_EMAIL` | Your Carrot.com login |
| `CARROT_PASSWORD` | Your Carrot.com password |

---

## Running manually (CLI)

```bash
# Full audit + Claude AI + all outputs (no Carrot edits)
python main.py

# Full run + apply meta changes in Carrot dashboard
python main.py --implement

# Crawl + rules only — no Claude AI cost, good for quick checks
python main.py --audit-only

# Blog content calendar only
python main.py --blog-plan-only
```

---

## Running via Claude Cowork (Recommended)

[Claude Cowork](https://claude.ai/cowork) is the recommended way to run this agent on a schedule without managing bat files or Task Scheduler.

### One-time Cowork setup

1. Open Claude Cowork desktop app
2. Go to **Scheduled** tab → **New Scheduled Task**
3. Configure:
   - **Name:** Buying Hero SEO Audit
   - **Working folder:** `D:\Dropbox\J Feels\Dev\seo-agent`
   - **Frequency:** Monthly (or Manual for on-demand)
   - **Prompt:** (see below)

### Cowork prompt

```
Run the Buying Hero SEO audit pipeline.

Working directory: D:\Dropbox\J Feels\Dev\seo-agent

Steps:
1. Run: python main.py
2. Wait for completion
3. Read the audit report from reports/audit_*.md (latest file)
4. Summarize: top 3 critical issues, PageSpeed homepage scores (mobile + desktop),
   number of blog posts generated, and the Google Doc link if available
5. List the top 5 priority fixes with current vs recommended values

Keep the summary under 20 lines.
```

### For Carrot implementation runs

Use this prompt when you're ready to push meta changes live:

```
Run the Buying Hero SEO audit and apply meta changes to Carrot.

Working directory: D:\Dropbox\J Feels\Dev\seo-agent

Steps:
1. Run: python main.py --implement
2. When prompted "Proceed with implementing N changes?", confirm with y
3. After completion, read reports/changes_applied_*.md
4. Report: how many changes succeeded, how many failed, and list any pages
   that need manual action in Carrot
```

### Recommended schedule

| Task | Frequency | Cowork prompt |
|------|-----------|---------------|
| Full audit + blog plan refresh | Monthly | `python main.py` |
| Quick crawl check (no AI cost) | Weekly | `python main.py --audit-only` |
| Apply Carrot meta changes | After each audit review | `python main.py --implement` |

### Cowork limitations to know

- Runs only while your computer is **awake** and **Cowork is open**
- If you need it to run overnight unattended, use Windows Task Scheduler instead (see below)
- Cloud-based scheduling from Anthropic is coming but not yet available

---

## Running unattended (Windows Task Scheduler)

If you need the audit to run overnight without Cowork open:

Create `run_seo.bat`:
```bat
@echo off
cd /d D:\Dropbox\J Feels\Dev\seo-agent
python main.py >> logs\scheduler.log 2>&1
```

Then add to Windows Task Scheduler targeting that `.bat` file.

---

## Output files

| File | Description |
|------|-------------|
| `reports/audit_YYYY-MM-DD.md` | Full audit report (local) |
| `reports/blog_plan_YYYY-MM-DD.md` | Blog content calendar (local) |
| `reports/crawl_YYYY-MM-DD.json` | Raw crawl data (debug) |
| `reports/changes_applied_YYYY-MM-DD.md` | Carrot edit log |
| Google Doc | Formatted audit report (link printed at end of run) |
| Google Sheets "SEO Blog Plan" tab | 50-topic blog calendar |
| `logs/run_YYYY-MM-DD.log` | Full run log |

---

## Architecture

```
main.py
  ├── Phase 1: scrapers/site_crawler.py     (Playwright crawl)
  ├── Phase 2: scrapers/pagespeed.py        (PageSpeed Insights API)
  ├── Phase 3: analyzers/onpage.py          (rules engine)
  ├── Phase 4: agent.py                     (Claude AI — audit + blog plan)
  ├── Phase 5: outputs/                     (Docs, Sheets, Markdown)
  └── Phase 6: scrapers/carrot_editor.py    (Carrot dashboard — --implement only)
```
