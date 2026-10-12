#!/usr/bin/env python3
"""
Daily job: find today's REsimpli lead exports in Downloads, validate them, sync
into the Bolt Deals Lead Performance sheet, then archive them.

Pairs with a Claude desktop scheduled task that exports THREE files at 6am EST
(Active, Warm, Dead -- all filtered to Bolt PPC) into Downloads. All three are
picked up in one run; bucket is derived per row from Lead Status, so their
order and filenames do not matter.

Why it validates instead of taking the newest .csv: Downloads is a shared junk
drawer. A bank statement or a buyers list could easily be newer. Syncing one of
those into a sheet an outside PPC vendor reads is worse than syncing nothing,
so unrecognised files are skipped and the job exits non-zero rather than guess.

Usage:
    python daily_sync.py                    # dry run
    python daily_sync.py --apply            # commit + archive
    python daily_sync.py --downloads-dir "D:\\exports" --max-age-hours 48
"""
import argparse
import contextlib
import io
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

from sync_csv import looks_like_lead_export, run_sync

DEFAULT_DOWNLOADS = Path.home() / "Downloads"
ARCHIVE = Path(__file__).resolve().parent / "archive"
LOGS = Path(__file__).resolve().parent / "logs"


def write_log(text):
    """Append a run's output to logs/YYYY-MM-DD.log.

    Logging lives here rather than in the .bat because batch %date% parsing is
    locale-dependent -- on this machine %date% is 'Tue 08/18/2026', so splitting
    on '/' produced a log named '2026-Tue 08-18.log'. Python's datetime is not
    ambiguous.
    """
    LOGS.mkdir(exist_ok=True)
    f = LOGS / (datetime.now().strftime("%Y-%m-%d") + ".log")
    with f.open("a", encoding="utf-8") as fh:
        fh.write("\n===== sync " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                 + " =====\n")
        fh.write(text.rstrip() + "\n")
    return f

# The export set is Active + Warm + Dead. Fewer than this is not fatal (a bucket
# can legitimately be empty) but it is worth flagging in the log.
EXPECTED_FILES = 3


def find_exports(downloads_dir, max_age_hours, pattern="*.csv"):
    """Every CSV that validates as a lead export and is recent enough.

    Returns (paths, rejected) -- paths newest-first.
    """
    d = Path(downloads_dir)
    if not d.is_dir():
        return [], ["Downloads folder not found: " + str(d)]

    candidates = sorted(d.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        return [], ["no CSV files in " + str(d)]

    cutoff = datetime.now() - timedelta(hours=max_age_hours)
    good, rejected = [], []

    for p in candidates:
        mtime = datetime.fromtimestamp(p.stat().st_mtime)
        if mtime < cutoff:
            rejected.append(p.name + " (stale: " + mtime.strftime("%Y-%m-%d %H:%M") + ")")
            continue
        ok, why = looks_like_lead_export(p)
        if not ok:
            rejected.append(p.name + " (" + why + ")")
            continue
        good.append(p)

    return good, rejected


def _run(a):
    print("[" + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "] daily_sync starting")
    print("  looking in : " + a.downloads_dir)
    print("  max age    : " + str(a.max_age_hours) + "h")

    paths, rejected = find_exports(a.downloads_dir, a.max_age_hours, a.pattern)

    if not paths:
        print("\nNOTHING TO SYNC. Skipped:")
        for r in rejected[:10]:
            print("    - " + r)
        print("\nIf the export ran but was skipped, check with:")
        print('  python sync_csv.py "<file>" --show-headers')
        return 1

    print("  found      : " + str(len(paths)) + " export(s)")
    for p in paths:
        print("     - " + p.name)
    if len(paths) != EXPECTED_FILES:
        print("  WARNING: expected " + str(EXPECTED_FILES)
              + " exports (Active/Warm/Dead), found " + str(len(paths))
              + ". A bucket may have failed to export.")
    if rejected:
        print("  skipped    : " + str(len(rejected)) + " other file(s)")
    print("")

    try:
        result = run_sync(paths, a.apply, a.source_match)
    except ValueError as e:
        print("\nSYNC FAILED: " + str(e))
        return 1

    if not result:
        print("\nSYNC FAILED: no result returned")
        return 1

    if not a.apply:
        print("\n[dry run] would archive " + str(len(paths)) + " file(s) after a real run")
        return 0

    if result["rows"] == 0:
        print("\nWARNING: sync wrote ZERO rows. Not archiving, so the files stay "
              "available for inspection.")
        return 1

    if not a.no_archive:
        ARCHIVE.mkdir(exist_ok=True)
        for p in paths:
            dest = ARCHIVE / (datetime.now().strftime("%Y-%m-%d_") + p.name)
            shutil.move(str(p), str(dest))
        print("  archived " + str(len(paths)) + " file(s) -> " + str(ARCHIVE))

    b = result["buckets"]
    q = result["qualification"]
    print("\n[" + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "] done: "
          + str(result["rows"]) + " rows in sheet (" + str(result["new"]) + " new)  |  "
          + ", ".join(k + "=" + str(v) for k, v in sorted(b.items())) + "  |  "
          + ", ".join(k + "=" + str(v) for k, v in sorted(q.items())))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--downloads-dir", default=str(DEFAULT_DOWNLOADS))
    ap.add_argument("--apply", action="store_true", help="write to the sheet")
    ap.add_argument("--source-match", default="",
                    help="empty is correct: the exports are already Bolt-only")
    ap.add_argument("--max-age-hours", type=float, default=26.0,
                    help="ignore exports older than this (default 26h = daily + slack)")
    ap.add_argument("--pattern", default="*.csv")
    ap.add_argument("--no-archive", action="store_true")
    ap.add_argument("--no-log", action="store_true", help="never write a log file")
    a = ap.parse_args()

    # Capture everything so the log is written only when something happened.
    # This runs every 15 minutes; logging idle ticks would bury the real runs.
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            rc = _run(a)
        except Exception as e:                       # noqa - must still log
            print("UNCAUGHT " + type(e).__name__ + ": " + str(e))
            rc = 3
    out = buf.getvalue()

    try:
        sys.stdout.write(out)
    except UnicodeEncodeError:
        sys.stdout.write(out.encode("ascii", "replace").decode("ascii"))

    # rc 1 == "nothing valid to sync", the normal idle result. Stay silent.
    if rc != 1 and not a.no_log:
        f = write_log(out)
        print("logged -> " + str(f))
    return rc


if __name__ == "__main__":
    sys.exit(main())
