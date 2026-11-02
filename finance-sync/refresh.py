"""Daily refresh of the "Finance Revised" cash-flow tab from REsimpli.

Jorge + Adrian keep a daily cash-flow forecast in the Deal Criteria + Master
Sheet. The deals table (rows 21-40) is seeded from REsimpli's Under Contract
leads; this keeps it current. Per row it owns ONLY:

  B seller / C property   -- written when a new deal is added, never after
  D under contract date   \
  E expected close date    > refreshed unless the row's Lock box (V) is ticked
  F assignment fee        /
  W REsimpli status / X REsimpli lead id

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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "weekly-acq-report"))
from pull import THROTTLE, log, post  # noqa: E402

CREDS = Path(os.environ.get("GOOGLE_CREDENTIALS_PATH") or HERE.parent / "foreclosure-agent" / "credentials.json")
TAB = "Finance Revised"
UNDER_CONTRACT = "6aa4dc81d18014f8fc5e535e"
FIRST, LAST = 21, 40        # deal rows
ET = ZoneInfo("America/New_York")
# column letters -> 0-based index in an A:X read
COL = {c: i for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWX")}


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
        out[x["_id"]] = {"B": seller(ld), "C": ld.get("address") or "",
                         "D": day(a.get("underContractDate")), "E": day(a.get("closingDate")),
                         "F": a.get("assignmentFee") or ""}
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

    rows = ws.get(f"A{FIRST}:X{LAST}", value_render_option="UNFORMATTED_VALUE")
    rows += [[]] * (LAST - FIRST + 1 - len(rows))
    cell = lambda row, c: row[COL[c]] if len(row) > COL[c] else ""

    updates, seen, n_upd, n_locked, n_gone = [], set(), 0, 0, 0
    empty = []
    for i, row in enumerate(rows):
        r = FIRST + i
        lid = str(cell(row, "X")).strip()
        if not lid:
            if not str(cell(row, "B")).strip():
                empty.append(r)
            continue
        seen.add(lid)
        if lid in live:
            if cell(row, "V") is True:
                n_locked += 1
            else:
                d = live[lid]
                updates.append({"range": f"D{r}:F{r}", "values": [[d["D"], d["E"], d["F"]]]})
                n_upd += 1
            updates.append({"range": f"W{r}", "values": [["Under Contract"]]})
        else:
            updates.append({"range": f"W{r}", "values": [[status_title(lid)]]})
            n_gone += 1

    new = [lid for lid in live if lid not in seen]
    if len(new) > len(empty):
        log("WARNING: %d new deals but only %d empty rows - add rows to the deals table" % (len(new), len(empty)))
    for lid, r in zip(new, empty):
        d = live[lid]
        updates.append({"range": f"A{r}:F{r}", "values": [[True, d["B"], d["C"], d["D"], d["E"], d["F"]]]})
        updates.append({"range": f"V{r}:X{r}", "values": [[False, "Under Contract", lid]]})

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
