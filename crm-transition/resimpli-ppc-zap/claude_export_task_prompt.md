# Claude desktop scheduled task — REsimpli Bolt PPC export

**Schedule:** Daily, 6:00am EST
**Pairs with:** Windows Task Scheduler job `BuyingHero - Bolt PPC Sheet Sync`
at 6:30am, which picks the files up from Downloads.

Paste the block below as the scheduled task prompt.

---

Export Bolt PPC leads from REsimpli to my Downloads folder. This is a
read-only reporting task — do not create, edit, delete, or change the status of
any lead, and do not send any message from REsimpli.

1. Open https://dashboard.resimpli.com and go to the Leads section. If it asks
   me to log in and you cannot complete it, stop and tell me — do not retry
   repeatedly.

2. Apply the campaign filter first, before touching any bucket:
   set **Campaign Name = "Bolt PPC"**. (Lead Source for these is
   "Google Adwords/PPC".) This filter persists as you move between buckets, so
   set it once, up front.

3. With that filter applied, export three files using the funnel icon to switch
   buckets. Export each one and wait for the download to finish before moving on:
   - **Active** leads (the default view)
   - **Warm Leads**
   - **Dead Leads**

4. Each export downloads as `Exported_Leads_<time>.csv` into Downloads. Leave
   the filenames exactly as they are — the sync job identifies files by their
   contents, not their names.

5. When done, confirm to me: how many rows each of the three exports contained,
   and that the Campaign filter still read "Bolt PPC" for all three.

**Stop and report instead of guessing if:** login fails, the Campaign filter
resets between buckets, a bucket exports zero rows, or any export shows leads
whose Campaign Name is not "Bolt PPC". A wrong export is worse than a missing
one — the sheet is shared with an outside PPC vendor.

---

## Why each instruction is there

- **Filter before buckets.** The filter persisting across buckets is the whole
  reason this is three exports and not three separate filter setups.
- **Leave filenames alone.** `daily_sync.py` validates by header structure
  (needs a Lead ID column plus 2+ recognisable REsimpli fields), so renaming is
  unnecessary and a rename to something odd changes nothing. Filenames are also
  why bucket is derived per row from `Lead Status` instead of from the name.
- **Read-only.** The task has no reason to mutate CRM state, and an agent
  driving a CRM unsupervised at 6am should have the narrowest possible mandate.
- **Report row counts.** The sync logs `WARNING: expected 3 exports, found N`,
  but it cannot tell whether a bucket exported *zero rows* versus failed to
  export. A missing Dead export silently inflates the qualified rate, which is
  the exact metric the PPC vendor optimises on.

## If exports land somewhere other than Downloads

Point the sync at the real folder — edit `DOWNLOADS` in `run_daily_ppc.bat`, or
pass `--downloads-dir` to `daily_sync.py`.
