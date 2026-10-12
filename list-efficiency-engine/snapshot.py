#!/usr/bin/env python3
"""
Monthly point-in-time snapshot of every single-family parcel in Miami-Dade.

Why this exists: closing overwrites the seller's owner name and mailing address
with the buyer's. That makes absentee / out-of-state / entity-owned status
impossible to reconstruct after a sale -- measured, a sold property looks 1.37x
more absentee than the base population purely as an artifact.

One snapshot a month fixes it going forward. After ~6 months the state-based
lists become scoreable retrospectively.

    python snapshot.py            # start, or resume an interrupted run

Writes data/snapshots/sfh_YYYY-MM-DD.csv while running, then gzips it on
success. Interrupting is safe: the partial .csv stays valid and the next run
picks up from the last folio written.
"""

import csv
import datetime
import gzip
import os
import shutil
import sys
import time

import requests

PAGIS = ("https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services"
         "/PaGISView_gdb/FeatureServer/0/query")
BASE_WHERE = "DOR_DESC LIKE '%SINGLE FAMILY%'"
PAGE = 2000                      # service maxRecordCount
EXPECTED = 387591                # county SFH count as of 2026-09-10

FIELDS = [
    "FOLIO",
    # site: the property itself. City/ZIP are needed for geographic criteria
    # and are NOT overwritten at closing, unlike the mailing block.
    "TRUE_SITE_ADDR", "TRUE_SITE_CITY", "TRUE_SITE_ZIP_CODE", "SUBDIVISION",
    # owner + mailing: overwritten at closing, which is exactly why this
    # snapshot exists -- captured monthly so pre-sale state survives.
    "TRUE_MAILING_ADDR1", "TRUE_MAILING_CITY", "TRUE_MAILING_STATE",
    "TRUE_MAILING_ZIP_CODE",
    "TRUE_OWNER1", "TRUE_OWNER2",
    # physical: immune to sale, so usable as targeting criteria on any set
    "DOR_CODE_CUR", "YEAR_BUILT", "LOT_SIZE",
    "BEDROOM_COUNT", "BATHROOM_COUNT", "HALF_BATHROOM_COUNT",
    "BUILDING_HEATED_AREA", "BUILDING_ACTUAL_AREA",
    # valuation + last sale
    "ASSESSED_VAL_CUR", "PRICE_1", "DATEOFSALE_UTC",
]

OUT_DIR = "data/snapshots"


def fetch(after_folio: str) -> list[dict]:
    """Keyset pagination on FOLIO.

    resultOffset is unsafe here: the service can reorder or shift rows between
    requests, which silently skips or duplicates records. Paging on the sort
    key itself cannot.
    """
    where = BASE_WHERE
    if after_folio:
        where += f" AND FOLIO > '{after_folio}'"
    r = requests.get(PAGIS, params={
        "where": where,
        "outFields": ",".join(FIELDS),
        "orderByFields": "FOLIO ASC",
        "resultRecordCount": PAGE,
        "returnGeometry": "false",
        "f": "json",
    }, timeout=120)
    r.raise_for_status()
    body = r.json()
    if "error" in body:
        raise RuntimeError(body["error"])
    return [f["attributes"] for f in body.get("features", [])]


def resume_point(path: str) -> tuple[str, int]:
    """Last folio written and row count, so an interrupted run continues."""
    if not os.path.exists(path):
        return "", 0
    last, n = "", 0
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            folio = row.get("FOLIO")
            if folio:
                last, n = folio, n + 1
    return last, n


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.date.today().isoformat()
    csv_path = os.path.join(OUT_DIR, f"sfh_{stamp}.csv")
    gz_path = csv_path + ".gz"

    if os.path.exists(gz_path):
        print(f"{gz_path} already exists -- nothing to do.")
        return

    after, total = resume_point(csv_path)
    if after:
        print(f"resuming from folio {after} ({total:,} rows already written)")

    mode = "a" if total else "w"
    with open(csv_path, mode, newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        if not total:
            w.writeheader()
        while True:
            try:
                rows = fetch(after)
            except Exception as e:
                fh.flush()
                print(f"\nstopped at {total:,} rows: {e}")
                print("partial file is valid -- rerun to resume.")
                sys.exit(1)
            if not rows:
                break
            w.writerows(rows)
            total += len(rows)
            after = rows[-1]["FOLIO"]
            fh.flush()                      # a kill mid-run loses nothing
            if total % 40000 < PAGE:
                print(f"  {total:,} rows...", flush=True)
            if len(rows) < PAGE:
                break
            time.sleep(0.3)                 # polite on a free county service

    if total < EXPECTED * 0.98:
        print(f"INCOMPLETE: {total:,} rows, expected ~{EXPECTED:,}. "
              f"Left as {csv_path} -- rerun to resume.")
        sys.exit(1)

    with open(csv_path, "rb") as src, gzip.open(gz_path, "wb") as dst:
        shutil.copyfileobj(src, dst)
    os.remove(csv_path)
    print(f"wrote {gz_path}  ({total:,} rows, "
          f"{os.path.getsize(gz_path)/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
