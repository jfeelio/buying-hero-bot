# Moving Dropbox to a New Drive

Use this whenever the Dropbox folder changes location: new drive, new drive letter, new PC.
Last done: **2026-10-12**, from `D:\Dropbox` (drive failed) to `C:\Users\jsive\Dropbox`.

## The short version

1. Move Dropbox with the Dropbox app, not by copying folders yourself:
   Dropbox icon > Settings > Sync > **Dropbox folder location > Move**. Let it finish syncing.
2. Open Claude Code **in the new Dev folder** (`<new Dropbox>\J Feels\Dev`).
3. Tell Claude: **"We moved Dropbox again. Follow DRIVE_MOVE.md."**
   Or run the check yourself:
   ```
   powershell -ExecutionPolicy Bypass -File drive-move-check.ps1
   ```
4. Fix anything it marks `CHECK` (see below), then run it again until it says **All clear**.

## What a drive move can and can't break

**Can't break: everything that runs on a schedule.** These run in the cloud, not on this PC:
- **GitHub Actions** (repo `jfeelio/buying-hero-bot`): Foreclosures, Tax Auctions, Probate, Probate Mailer
  (Open Letter Connect), Bolt PPC Sheet Sync, LevelUp Sync, Weekly Acquisitions Report, Automation Status, Pokemon Tracker.
- **n8n** at automations.buyinghero.com (Google Cloud VM): DNM sync, MLS sweep, the GitHub job scheduler,
  the report mailer, GHL workflows.

**Can break: the local pieces.** The check script looks at all of these:

| What | Why it breaks | Fix |
|---|---|---|
| Claude's memory (34+ notes about the business) | Claude stores memory by folder path, so a new path starts empty | Script copies it over automatically |
| Files with a full `X:\...\Dropbox\J Feels\Dev` path | Old drive letter | Script lists them; Claude makes them relative (as done for the scripts in Oct 2026) |
| Old Windows scheduled tasks | They store full paths | Should stay **Disabled**, see below |
| Secret files on disk (`credentials.json`, `.env`, `token.json`, `~/.olc_key`) | Gitignored, so GitHub can't restore them; only Dropbox has them | Script confirms they exist |
| Git inside Dropbox | The Dev folder's own `.git` was lost in the Oct 2026 move | Not a problem, see below |

## Already drive-proof (no change needed next time)

These scripts find their files relative to their own folder, not by drive letter:
- All the Google-API scripts in the Dev root (cold call docs, CMA sheet, rehab budget, Luis hours,
  investor pitch, ads strategy) and `dispo-machine/import/build_import.py`
- All five `.bat` launchers (`%~dp0`) and `dispo-machine/console/smoke.js`

## Still uses a full path (check after a move)

- `SOUL.md`: the WhatsApp bot's `node .../kiavi-arv.js` command. If the local bot is in use, update the
  path and recopy SOUL.md to `~/.openclaw/workspace/`.
- `RESTORE.md`, `seo-agent/README.md`: docs only, harmless if stale.

The check script flags any of these that point at an old location.

## Windows scheduled tasks

All of them are **Disabled on purpose**. GitHub Actions does these jobs now, so enabling one would
make that job run twice. The tasks were created "with highest privileges", so changing them needs an
**admin** PowerShell. Two options:

**Delete them (recommended for Foreclosure and Probate, which are fully replaced):**
```powershell
Unregister-ScheduledTask -TaskName 'Buying Hero - Foreclosure Daily' -Confirm:$false
Unregister-ScheduledTask -TaskName 'Buying Hero - Probate' -Confirm:$false
```

**Or repoint them to the new location** (they stay disabled). Set `$dev` first:
```powershell
$dev = 'C:\Users\jsive\Dropbox\J Feels\Dev'   # <- new Dev folder
foreach ($n in 'Buying Hero - Foreclosure Daily','Buying Hero - Lis Pendens Daily','Buying Hero - Probate',
               'Buying Hero - Tax Deed Daily','BuyingHero - Bolt PPC Sheet Sync') {
  $t = Get-ScheduledTask $n -ErrorAction SilentlyContinue; if (-not $t) { continue }
  $old = ("$($t.Actions[0].Execute) $($t.Actions[0].Arguments)").Trim().Replace('"','')
  $rel = $old.Substring($old.IndexOf('J Feels\Dev\') + 12)
  Set-ScheduledTask $n -Action (New-ScheduledTaskAction -Execute "`"$dev\$rel`"" -WorkingDirectory (Split-Path "$dev\$rel"))
}
```

## Git and GitHub

- GitHub is the source of truth for everything that runs. The Dropbox Dev folder is just a working copy.
- Dropbox and git conflict (Dropbox locks git's internal files mid-write). So **all commits are made from a
  fresh clone outside Dropbox** and pushed to GitHub. Do not re-create a `.git` in the Dev root.
- `acquisition-trainer/` and `yt-intel-dashboard/` still have their own `.git`; the script checks
  they have nothing unpushed.
- Deliberately **not** on GitHub (the main repo is public), so Dropbox is their only copy:
  `crm-transition/n8n-workflows/mls-sweep/` (team emails), `appt_week.json`, Bolt lead exports
  (`resimpli-ppc-zap/bolt_*.json`), `list-efficiency-engine/data/`, the realtor referral PDF, and the
  secret files listed above.

## Instructions for Claude

When asked to follow this file after a move:
1. Run `drive-move-check.ps1` from the new Dev folder.
2. For each flagged file, replace the absolute path with a script-relative one (Python:
   `os.path.dirname(os.path.abspath(__file__))`; batch: `%~dp0`; Node: `__dirname`). Docs: update the text.
3. Push any changed tracked files to GitHub master **from a scratchpad clone**, never from the Dropbox copy.
4. Update the memory note `reference_repo_structure.md` with the new location and date, and update
   "Last done" at the top of this file.
5. Re-run the script until it reports **All clear**.
