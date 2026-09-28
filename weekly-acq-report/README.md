# Weekly Acquisitions Report

Every Sunday at 8 PM ET, GitHub Actions pulls the week from REsimpli, writes the
acquisitions report, prints it to PDF and emails it to jorge@buyinghero.com.
It runs in the cloud and does not depend on anyone's PC.

```
GitHub Actions (run_acq_report.yml, Sun 8 PM ET)
  pull.py     REsimpli: leads, pipelines, appointments, activity (Active + Cold only)
  analyze.py  every number in the report, deterministically
  narrate.py  Claude (claude-opus-5) writes the commentary from those numbers only
  render.py   HTML page (IBM Plex / ledger green) -> Chromium -> PDF
  run.py      POSTs the PDF to the n8n mailer
n8n acqreport0001 (automations.buyinghero.com/webhook/acq-report)
  checks X-Report-Key, emails the PDF from the Buying Hero Gmail credential
```

## Run it by hand

From GitHub: **Actions > Weekly Acquisitions Report > Run workflow**. Leave the
date blank for the week just ended, or enter a Monday.

Locally:

```sh
python run.py --week-start 2026-09-21 --no-send     # writes out/*.pdf, sends nothing
python run.py --cache out/raw-2026-09-21.json --no-send   # re-render without the 10-min sweep
```

Locally the REsimpli key is read from `~/.resimpli_key`; set `ANTHROPIC_API_KEY`
for commentary (without it the notes are rule-based).

## Things to know

- **Scope is Active + Cold leads only.** Dead leads are skipped (Jorge's rule),
  except leads whose appointment fell in the week.
- **The sweep takes ~10 minutes.** REsimpli has no date filter on activity, so
  every in-scope lead is read, one call at a time (the API 429s otherwise).
- **REsimpli's two activity streams overlap.** `pull.py` dedupes by `_id`; before
  that fix every call count was doubled.
- **Claude never produces a number.** Every table comes from `analyze.py`. If the
  Claude call fails, the report still goes out with rule-based notes and the
  footer says so.
- **This repo is public.** The workflow never uploads the report or data as
  artifacts, because they contain seller names and addresses.
- **Texts from Jorge's account count as automation** (auto-replies, task
  reminders). His calls still count. Change `AUTOMATION_SENDERS` in
  `analyze.py` if that changes.
- `market.py` is a copy of the classifier in the appointment-snapshot skill. If
  you add a city there, add it here too.

## Secrets (GitHub > Settings > Secrets > Actions)

| Secret | What |
|---|---|
| `RESIMPLI_KEY` | REsimpli Open API key |
| `ANTHROPIC_API_KEY` | Claude API key for the commentary |
| `ACQ_REPORT_WEBHOOK_URL` | `https://automations.buyinghero.com/webhook/acq-report` |
| `ACQ_REPORT_WEBHOOK_KEY` | shared secret; also stored in n8n credential `acqrpthdr0001` and locally in `~/.acq_report_webhook_key` |

To change recipients, edit `RECIPIENTS` in
`crm-transition/n8n-workflows/acq-report/build.js`, run `node build.js` and
re-import (see `crm-transition/n8n-workflows/mls-sweep/README.md` for the
deploy commands; on this n8n version use `n8n publish:workflow` and restart).
