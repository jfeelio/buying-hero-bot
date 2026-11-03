"""Daily refresh of the "Finance Revised" cash-flow tab from REsimpli.

Jorge + Adrian keep a daily cash-flow forecast in the Deal Criteria + Master
Sheet. The deals table (rows 21-40) is seeded from REsimpli's Under Contract
leads; this keeps it current. Per row it owns ONLY:

  B seller / C property   -- written when a new deal is added, never after
  D under contract date   \
  E expected close date    > refreshed unless the row's Lock box (V) is ticked
  F assignment fee        /
  W REsimpli status / X REsimpli lead id

Columns are found by their row-20 header text, so the partners can insert
columns (as they did for the Jorge / Adrian splits) without breaking this.
Everything else (escrow, advances, JV, costs, splits, notes, Include?) is the
partners' and is never touched. A deal that leaves Under Contract is not
deleted; W shows its new status and the Flag column (T) asks for a review.

Source fields: lead/details -> leadData.analyticsInfo.{underContractDate,
closingDate, assignmentFee} (epoch ms / dollars).

This repo is PUBLIC: log counts only, never seller names, addresses or money.

Usage:  python refresh.py            # write the sheet
        python refresh.py --dry-run
"""
import argparse
import datetime as dt
import os
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import gspread
from gspread.utils import rowcol_to_a1

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "weekly-acq-report"))
from pull import THROTTLE, log, post  # noqa: E402

CREDS = Path(os.environ.get("GOOGLE_CREDENTIALS_PATH") or HERE.parent / "foreclosure-agent" / "credentials.json")
TAB = "Finance Revised"
UNDER_CONTRACT = "6aa4dc81d18014f8fc5e535e"
HEADER, FIRST, LAST = 20, 21, 40   # deal table header row + deal rows
ET = ZoneInfo("America/New_York")
# key -> its row-20 header (exact; Lock matches on its first word)
HEADERS = {"include": "Include?", "seller": "Seller", "property": "Property",
           "uc": "Under contract", "close": "Expected close", "fee": "Assignment fee",
           "lock": "Lock", "status": "REsimpli status", "id": "REsimpli ID"}


def day(ms):
    return dt.datetime.fromtimestamp(ms / 1000, ET).strftime("%Y-%m-%d") if ms else ""


def seller(ld):
    c = ld.get("contactData") or {}
    c = c[0] if isinstance(c, list) and c else c
    name = " ".join(x for x in ((c.get("firstName") or "").strip(), (c.get("lastName") or "").strip()) if x)
    return name.title() if name.isupper() or name.islower() else name


def under_contract():
    d = post("lead/list", {"page": 1, "limit": 100, "filterData": {"mainStatusId": [UNDER_CONTRACT]}})["data"]
    items = d.get("items") or []
    if d.get("count") is not None and d["count"] != len(items):
        raise RuntimeError("Under Contract count %s != %d returned" % (d["count"], len(items)))
    out = {}
    for x in items:
        if x.get("mainStatusId") != UNDER_CONTRACT:
            raise RuntimeError("status filter ignored by lead/list - refusing to write")
        time.sleep(THROTTLE)
        ld = post("lead/details", {"leadId": x["_id"]})["data"]["leadData"]
        a = ld.get("analyticsInfo") or {}
        out[x["_id"]] = {"seller": seller(ld), "property": ld.get("address") or "",
                         "uc": day(a.get("underContractDate")), "close": day(a.get("closingDate")),
                         "fee": a.get("assignmentFee") or ""}
    return out


def status_title(lead_id):
    time.sleep(THROTTLE)
    try:
        ld = post("lead/details", {"leadId": lead_id})["data"]["leadData"]
        return ld.get("mainStatusTitle") or "Unknown status"
    except Exception:
        return "Not found"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sheet_id = os.environ.get("FINANCE_SHEET_ID")
    if not sheet_id:
        sys.exit("FINANCE_SHEET_ID is not set")
    ws = gspread.service_account(filename=str(CREDS)).open_by_key(sheet_id).worksheet(TAB)

    live = under_contract()
    log("under contract in REsimpli: %d" % len(live))

    header = ws.row_values(HEADER)
    col = {}
    for key, text in HEADERS.items():
        hits = [i for i, h in enumerate(header)
                if (h.strip().startswith(text) if key == "lock" else h.strip() == text)]
        if len(hits) != 1:
            sys.exit("header %r found %d times in row %d - refusing to write" % (text, len(hits), HEADER))
        col[key] = hits[0]
    if not (col["uc"] + 1 == col["close"] and col["close"] + 1 == col["fee"]):
        sys.exit("Under contract / Expected close / Assignment fee must stay side by side")
    a1 = lambda r, key: rowcol_to_a1(r, col[key] + 1)

    rows = ws.get(f"A{FIRST}:{rowcol_to_a1(LAST, len(header))}", value_render_option="UNFORMATTED_VALUE")
    rows += [[]] * (LAST - FIRST + 1 - len(rows))
    cell = lambda row, key: row[col[key]] if len(row) > col[key] else ""

    updates, seen, n_upd, n_locked, n_gone = [], set(), 0, 0, 0
    empty = []
    for i, row in enumerate(rows):
        r = FIRST + i
        lid = str(cell(row, "id")).strip()
        if not lid:
            if not str(cell(row, "seller")).strip():
                empty.append(r)
            continue
        seen.add(lid)
        if lid in live:
            if cell(row, "lock") is True:
                n_locked += 1
            else:
                d = live[lid]
                updates.append({"range": f"{a1(r, 'uc')}:{a1(r, 'fee')}", "values": [[d["uc"], d["close"], d["fee"]]]})
                n_upd += 1
            updates.append({"range": a1(r, "status"), "values": [["Under Contract"]]})
        else:
            updates.append({"range": a1(r, "status"), "values": [[status_title(lid)]]})
            n_gone += 1

    new = [lid for lid in live if lid not in seen]
    if len(new) > len(empty):
        log("WARNING: %d new deals but only %d empty rows - add rows to the deals table" % (len(new), len(empty)))
    for lid, r in zip(new, empty):
        d = live[lid]
        for key, v in (("include", True), ("seller", d["seller"]), ("property", d["property"]),
                       ("uc", d["uc"]), ("close", d["close"]), ("fee", d["fee"]),
                       ("lock", False), ("status", "Under Contract"), ("id", lid)):
            updates.append({"range": a1(r, key), "values": [[v]]})

    stamp = dt.datetime.now(ET).strftime("%m/%d/%Y %I:%M %p ET")
    updates.append({"range": "A3", "values": [[f"Deals last refreshed from REsimpli: {stamp} (daily, automatic)"]]})
    log("updated %d, locked %d, added %d, left Under Contract %d"
        % (n_upd, n_locked, min(len(new), len(empty)), n_gone))
    if args.dry_run:
        log("dry run - nothing written")
        return
    ws.batch_update(updates, value_input_option="USER_ENTERED")
    log("sheet written")


if __name__ == "__main__":
    main()
