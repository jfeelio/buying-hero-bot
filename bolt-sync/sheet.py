#!/usr/bin/env python3
"""
Upsert REsimpli lead CSV exports into the Bolt Deals Lead Performance sheet.

Copied from crm-transition/resimpli-ppc-zap/sync_csv.py (2026-10-06). The CSVs now
come from the REsimpli API (from_api.py) instead of a desktop export, so the
qualification rules and privacy filter below are unchanged on purpose.

Three exports feed this, all filtered to Bolt PPC in REsimpli:
    Active  -- 6 workflow statuses
    Warm    -- Lead Status "Warm Lead"
    Dead    -- Lead Status "Dead Lead"

Bucket is derived PER ROW from Lead Status, so filenames and processing order
do not matter and the three exports can be synced in any sequence.

HEADER-DRIVEN: the sheet's own header row decides column order. Move columns
around in Google Sheets and this keeps working. Columns the sync does not
produce (anything you add by hand) are preserved, never blanked.

Usage:
    python sync_csv.py a.csv b.csv c.csv            # dry run
    python sync_csv.py a.csv b.csv c.csv --apply
    python sync_csv.py export.csv --show-headers
    python sync_csv.py --plain-format --apply       # strip colours, no sync
"""
import argparse
import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

import os

# Secret (GitHub BOLT_SHEET_ID): the sheet holds seller contact details and this repo is public.
SHEET_ID = os.environ["BOLT_SHEET_ID"]
TAB = "Leads"
CREDS = Path(__file__).resolve().parents[1] / "foreclosure-agent" / "credentials.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Canonical field -> header names accepted in the sheet. Lets you rename or
# reorder columns without touching this file.
ALIASES = {
    "Lead Created":      ["Lead Created", "Lead Created Date", "Date Created", "Created"],
    "Lead ID":           ["Lead ID", "Lead Id", "Property ID"],
    "Lead Bucket":       ["Lead Bucket", "Bucket"],
    "Qualification":     ["Qualification", "Qualified"],
    "Disqualify Reason": ["Disqualify Reason", "Reason", "Dead Lead Reason"],
    "REsimpli Status":   ["REsimpli Status", "Lead Status", "Status"],
    "First Name":        ["First Name"],
    "Last Name":         ["Last Name"],
    "Phone":             ["Phone", "Phone Number"],
    "Email":             ["Email", "Email Address"],
    "Property Address":  ["Property Address", "Property Street Address", "Address"],
    "City":              ["City", "Property City"],
    "State":             ["State", "Property State"],
    "Zip":               ["Zip", "Property Zip"],
    "Lead Source":       ["Lead Source", "Source"],
    "Campaign":          ["Campaign", "Campaign Name"],
    "Tags":              ["Tags", "Tag"],
    "First Seen":        ["First Seen", "Received At"],
    "Last Updated":      ["Last Updated", "Updated"],
}

# Appended to the sheet if absent -- the sync cannot work without them.
REQUIRED = ["Lead Created", "Lead ID", "Lead Bucket", "Qualification",
            "Disqualify Reason"]

# CSV header candidates per canonical field.
CSV_MAP = {
    "Lead ID":           ["Property ID", "Property Id", "Lead Id", "Id"],
    "Lead Created":      ["Lead Created Date", "Created Date", "Date Created"],
    "First Name":        ["First Name", "firstName"],
    "Last Name":         ["Last Name", "lastName"],
    "Phone":             ["Phone Number", "Phone", "Primary Phone"],
    "Email":             ["Email Address", "Email"],
    "Property Address":  ["Property Street Address", "Property Address", "Address"],
    "City":              ["Property City", "City"],
    "State":             ["Property State", "State"],
    "Zip":               ["Property Zip", "Zip", "Zip Code"],
    "Lead Source":       ["Lead Source", "Source"],
    "Campaign":          ["Campaign Name", "Campaign"],
    "REsimpli Status":   ["Lead Status", "Status"],
    "Dead Lead Reason":  ["Dead Lead Reason"],
    "Tags":              ["Tags"],
}

# Present in the export, deliberately never written -- the sheet is shared with
# an outside PPC vendor.
BLOCKED = ["mailing address", "mail address", "notes", "comment", "teams",
           "buyer email", "buyer phone number", "buyer name"]

# Rules set by Jorge 2026-08-18 against the real 159-lead export set,
# amended 2026-09-13:
#   Active + "New Leads"   -> Not Yet Worked  (see NOT_WORKED below)
#   Active + anything else -> Qualified
#   Warm / Dead            -> Unqualified
#
# "Not Yet Worked" is a THIRD value, not a flavour of Unqualified. A lead in
# New Leads has had no discovery, so we have no basis to call it either way --
# reporting it as Unqualified charged our own follow-up backlog to the PPC
# vendor's scorecard. Qualified rate is therefore Qualified / (Qualified +
# Unqualified); Not Yet Worked is counted and reported separately, because it
# measures OUR discovery throughput, not their traffic quality.
DEAD_STATUS = "dead lead"
WARM_STATUS = "warm lead"
NOT_WORKED = "Not Yet Worked"
ACTIVE_NOT_WORKED = ["new leads"]

# Tags that disqualify an Active lead no matter how far it progressed. These
# are PERMANENT defects -- the property can never become a deal, so no amount
# of follow-up changes the outcome. Contrast with bolt-no answer /
# bolt-unresponsive, which are contact problems: the lead may still convert,
# so those stay Qualified (Jorge, 2026-08-18).
OVERRIDE_DISQUALIFYING_TAGS = ["bolt-out of state", "bolt-listed asking retail"]

# Fields where an existing sheet value is kept (see run_sync).
STICKY = ["First Name", "Last Name", "Phone", "Email", "Property Address", "City", "State",
          "Zip", "Lead Created"]


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def map_csv(headers):
    by_norm = {norm(h): h for h in headers if h}
    out = {}
    for field, cands in CSV_MAP.items():
        for c in cands:
            if norm(c) in by_norm:
                out[field] = by_norm[norm(c)]
                break
    return out


def map_sheet(header_row):
    """sheet header name -> canonical field (or None if we don't produce it)."""
    out = {}
    for h in header_row:
        for field, names in ALIASES.items():
            if norm(h) in {norm(n) for n in names}:
                out[h] = field
                break
        else:
            out[h] = None
    return out


def looks_like_lead_export(path):
    """Reject unrelated CSVs in Downloads -- syncing a bank statement into the
    vendor's sheet because it was newest is worse than syncing nothing."""
    try:
        with Path(path).open(newline="", encoding="utf-8-sig") as f:
            headers = next(csv.reader(f), [])
    except Exception:
        return False, "unreadable"
    m = map_csv(headers)
    if "Lead ID" not in m:
        return False, "no Lead ID column"
    if len(m) < 3:
        return False, "only " + str(len(m)) + " recognisable column(s)"
    return True, str(len(m)) + " columns recognised"


def classify(row, cm):
    """(bucket, qualification, reason) from Lead Status -- order-independent."""
    status = str(row.get(cm.get("REsimpli Status", ""), "")).strip()
    ns = norm(status)
    tags = str(row.get(cm.get("Tags", ""), "")).strip()
    dead = str(row.get(cm.get("Dead Lead Reason", ""), "")).strip()

    if ns == norm(DEAD_STATUS):
        return "Dead", "Unqualified", (dead or tags or "Dead Lead")
    if ns == norm(WARM_STATUS):
        return "Warm", "Unqualified", (dead or tags or "Warm Lead")

    # Permanent-defect tags outrank progress: an out-of-state or already-listed
    # property cannot become a deal however far it got in the pipeline.
    hits = [t.strip() for t in tags.split(",")
            if t.strip() and any(norm(o) in norm(t) for o in OVERRIDE_DISQUALIFYING_TAGS)]
    if hits:
        return "Active", "Unqualified", ", ".join(hits)

    # No discovery yet -> no verdict. Reason carries the tags when there are
    # any, but stays empty otherwise: the qualification column already says
    # "Not Yet Worked", so repeating it in the reason column adds nothing.
    if ns and any(norm(s) == ns for s in ACTIVE_NOT_WORKED):
        return "Active", NOT_WORKED, tags
    return "Active", "Qualified", ""


def parse_date(s):
    """REsimpli exports ISO (2026-07-25); webhooks send 'Aug 18, 2026'."""
    s = str(s or "").strip()
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def get_service():
    creds = Credentials.from_service_account_file(str(CREDS), scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def get_gid(svc):
    meta = svc.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    return next(s["properties"]["sheetId"] for s in meta["sheets"]
                if s["properties"]["title"] == TAB)


def ensure_columns(svc, apply=False):
    """Read the sheet header; append any REQUIRED column that's missing."""
    row = svc.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=TAB + "!1:1").execute().get("values", [[]])
    header = [h for h in (row[0] if row else []) if str(h).strip()]
    known = {norm(n) for h in header for n in ALIASES.get(map_sheet([h])[h] or "", [h])}
    missing = [c for c in REQUIRED
               if not any(norm(a) in {norm(h) for h in header} for a in ALIASES[c])]
    if not missing:
        return header
    print("  missing column(s): " + ", ".join(missing)
          + ("  -> appending" if apply else "  -> would append"))
    if not apply:
        return header + missing
    header = header + missing
    svc.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range=TAB + "!1:1",
        valueInputOption="RAW", body={"values": [header]}).execute()
    return header


def plain_format(svc, header_len, apply=False):
    """Strip conditional-format colour rules; keep a plain bold header."""
    meta = svc.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    sh = next(s for s in meta["sheets"] if s["properties"]["title"] == TAB)
    gid = sh["properties"]["sheetId"]
    rules = sh.get("conditionalFormats", [])
    print("  conditional-format rules present: " + str(len(rules))
          + ("  -> removing" if apply and rules else ""))
    if not apply:
        return
    reqs = [{"deleteConditionalFormatRule": {"sheetId": gid, "index": i}}
            for i in range(len(rules) - 1, -1, -1)]
    reqs += [
        # plain header: bold only, default background
        {"repeatCell": {
            "range": {"sheetId": gid, "startRowIndex": 0, "endRowIndex": 1,
                      "endColumnIndex": header_len},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 1, "green": 1, "blue": 1},
                "textFormat": {"bold": True,
                               "foregroundColor": {"red": 0, "green": 0, "blue": 0}}}},
            "fields": "userEnteredFormat(backgroundColor,textFormat)"}},
        # Data range: reset BOTH background and text colour.
        # Setting only the background once left white text on white -- the rows
        # were there and completely invisible. Always pair the two.
        {"repeatCell": {
            "range": {"sheetId": gid, "startRowIndex": 1, "endColumnIndex": header_len},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 1, "green": 1, "blue": 1},
                "textFormat": {"bold": False,
                               "foregroundColor": {"red": 0, "green": 0, "blue": 0}}}},
            "fields": "userEnteredFormat(backgroundColor,textFormat)"}},
        {"updateSheetProperties": {
            "properties": {"sheetId": gid, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount"}},
    ]
    svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID,
                                   body={"requests": reqs}).execute()
    print("  formatting set to plain")


def qualification_colors(svc, apply=False):
    """Light green on Qualified, light red on Unqualified, light amber on
    Not Yet Worked, in whichever column currently holds Qualification.
    Idempotent -- clears its own rules first.

    Uses TEXT_EQ, not TEXT_CONTAINS: "Unqualified" contains the string
    "Qualified", so a contains-rule would paint every Unqualified cell green.

    Amber rather than red on Not Yet Worked is the whole point of the third
    value -- it must not read as a negative verdict at a glance.
    """
    row = svc.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range=TAB + "!1:1").execute().get("values", [[]])
    header = [h for h in (row[0] if row else []) if str(h).strip()]
    smap = map_sheet(header)
    col = next((i for i, h in enumerate(header) if smap.get(h) == "Qualification"), None)
    if col is None:
        print("  no Qualification column found -- skipping colours")
        return
    print("  Qualification is column " + chr(65 + col) + ("  -> colouring" if apply
                                                          else "  -> would colour"))
    if not apply:
        return

    meta = svc.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    sh = next(s for s in meta["sheets"] if s["properties"]["title"] == TAB)
    gid = sh["properties"]["sheetId"]
    existing = sh.get("conditionalFormats", [])

    reqs = [{"deleteConditionalFormatRule": {"sheetId": gid, "index": i}}
            for i in range(len(existing) - 1, -1, -1)]

    rng = [{"sheetId": gid, "startRowIndex": 1,
            "startColumnIndex": col, "endColumnIndex": col + 1}]
    for word, bg in (("Qualified",   (0.851, 0.918, 0.827)),   # #D9EAD3 green
                     ("Unqualified", (0.957, 0.800, 0.800)),   # #F4CCCC red
                     (NOT_WORKED,    (0.988, 0.898, 0.804))):  # #FCE5CD amber
        reqs.append({"addConditionalFormatRule": {"index": 0, "rule": {
            "ranges": rng,
            "booleanRule": {
                "condition": {"type": "TEXT_EQ",
                              "values": [{"userEnteredValue": word}]},
                "format": {
                    "backgroundColor": {"red": bg[0], "green": bg[1], "blue": bg[2]},
                    "textFormat": {"foregroundColor":
                                   {"red": 0, "green": 0, "blue": 0}}}}}}})

    svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID,
                                   body={"requests": reqs}).execute()
    print("  cleared " + str(len(existing)) + " old rule(s), applied 2")


def run_sync(csv_paths, apply=False, source_match=""):
    if isinstance(csv_paths, (str, Path)):
        csv_paths = [csv_paths]

    svc = get_service()
    header = ensure_columns(svc, apply)
    smap = map_sheet(header)
    field_to_col = {v: k for k, v in smap.items() if v}
    unproduced = [h for h, f in smap.items() if f is None]

    # existing rows, keyed by lead id, as {header_name: value}
    idcol = field_to_col.get("Lead ID")
    existing = {}
    if idcol:
        vals = svc.spreadsheets().values().get(
            spreadsheetId=SHEET_ID, range=TAB + "!A2:ZZ").execute().get("values", [])
        i = header.index(idcol)
        for r in vals:
            r = list(r) + [""] * (len(header) - len(r))
            if i < len(r) and r[i]:
                existing[r[i]] = dict(zip(header, r))
    before = len(existing)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    buckets, quals = {}, {}
    match = (source_match or "").lower().strip()

    for p in csv_paths:
        path = Path(p)
        if not path.exists():
            raise ValueError("No such file: " + str(path))
        with path.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            print("  " + path.name + ": empty, skipped")
            continue
        cm = map_csv(list(rows[0].keys()))
        if "Lead ID" not in cm:
            raise ValueError(path.name + ": no Lead ID column found")
        blocked = [h for h in rows[0] if norm(h) in {norm(b) for b in BLOCKED}]

        kept = 0
        for r in rows:
            if match:
                hay = " ".join(str(r.get(cm.get(c, ""), ""))
                               for c in ("Lead Source", "Campaign")).lower()
                if match not in hay:
                    continue
            lid = str(r.get(cm["Lead ID"], "")).strip()
            if not lid:
                continue
            bucket, qual, reason = classify(r, cm)
            buckets[bucket] = buckets.get(bucket, 0) + 1
            quals[qual] = quals.get(qual, 0) + 1
            kept += 1

            prior = existing.get(lid, {})
            produced = {
                "Lead Created": str(r.get(cm.get("Lead Created", ""), "")).strip(),
                "Lead ID": lid, "Lead Bucket": bucket, "Qualification": qual,
                "Disqualify Reason": reason,
                "REsimpli Status": str(r.get(cm.get("REsimpli Status", ""), "")).strip(),
                "Tags": str(r.get(cm.get("Tags", ""), "")).strip(),
                "First Seen": prior.get(field_to_col.get("First Seen", ""), "") or now,
                "Last Updated": now,
            }
            for f in ("First Name", "Last Name", "Phone", "Email",
                      "Property Address", "City", "State", "Zip",
                      "Lead Source", "Campaign"):
                produced[f] = str(r.get(cm.get(f, ""), "")).strip()

            # start from the prior row so hand-added columns survive
            # Contact details already in the sheet win over a blank or differently
            # formatted API value: the API sometimes splits names differently or omits
            # them, and the vendor's view shouldn't churn. New leads take the API value.
            for f in STICKY:
                pv = prior.get(field_to_col.get(f, ""), "")
                if pv:
                    produced[f] = pv
            # Keep a specific reason the team wrote when the lead hasn't changed bucket
            # and the API can only offer a generic one.
            pr = prior.get(field_to_col.get("Disqualify Reason", ""), "")
            pb = prior.get(field_to_col.get("Lead Bucket", ""), "")
            if pr and pb == bucket and (reason in ("", "Dead Lead", "Warm Lead"))                     and norm(pr) != norm("Not yet worked"):
                produced["Disqualify Reason"] = pr

            rec = dict(prior)
            for h in header:
                fld = smap.get(h)
                if fld in produced:
                    rec[h] = produced[fld]
                else:
                    rec.setdefault(h, "")
            existing[lid] = rec

        print("  " + path.name + ": " + str(kept) + " rows"
              + ("  [withheld: " + ", ".join(blocked) + "]" if blocked else ""))

    # ---- sort newest-first by Lead Created ---------------------------
    dcol = field_to_col.get("Lead Created")
    rows_out = list(existing.values())
    rows_out.sort(key=lambda d: (parse_date(d.get(dcol, "")) or datetime.min),
                  reverse=True)
    matrix = [[str(d.get(h, "")) for h in header] for d in rows_out]

    print("\n  buckets      : " + ", ".join(k + "=" + str(v) for k, v in sorted(buckets.items())))
    print("  qualification: " + ", ".join(k + "=" + str(v) for k, v in sorted(quals.items())))
    print("  sheet rows   : " + str(before) + " -> " + str(len(matrix))
          + "  (" + str(len(matrix) - before) + " new)")
    if unproduced:
        print("  columns left untouched: " + ", ".join(unproduced))
    undated = sum(1 for d in rows_out if parse_date(d.get(dcol, "")) is None)
    if undated:
        print("  NOTE: " + str(undated) + " row(s) have no parseable Lead Created "
              "date and sort to the bottom")

    result = {"rows": len(matrix), "new": len(matrix) - before,
              "buckets": buckets, "qualification": quals, "applied": bool(apply)}

    if not apply:
        print("\nDRY RUN -- nothing written.")
        return result

    svc.spreadsheets().values().clear(
        spreadsheetId=SHEET_ID, range=TAB + "!A2:ZZ").execute()
    if matrix:
        svc.spreadsheets().values().update(
            spreadsheetId=SHEET_ID, range=TAB + "!A2",
            valueInputOption="RAW", body={"values": matrix}).execute()
    print("\nWritten, sorted newest-first.")
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_paths", nargs="*")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--source-match", default="")
    ap.add_argument("--show-headers", action="store_true")
    ap.add_argument("--plain-format", action="store_true",
                    help="strip conditional-format colours from the sheet")
    ap.add_argument("--colors", action="store_true",
                    help="green Qualified / red Unqualified on the Qualification column")
    a = ap.parse_args()

    if a.show_headers:
        for p in a.csv_paths:
            with Path(p).open(newline="", encoding="utf-8-sig") as f:
                headers = next(csv.reader(f), [])
            print(str(len(headers)) + " headers in " + Path(p).name + ":")
            for h in headers:
                print("  " + str(h))
        return

    svc = get_service()
    if a.plain_format:
        header = svc.spreadsheets().values().get(
            spreadsheetId=SHEET_ID, range=TAB + "!1:1").execute().get("values", [[]])
        plain_format(svc, len([h for h in header[0] if h]) if header else 20, a.apply)
        if not a.csv_paths:
            return

    if a.colors:
        qualification_colors(svc, a.apply)
        if not a.csv_paths:
            return

    if not a.csv_paths:
        sys.exit("Nothing to do: pass one or more CSV paths.")

    try:
        run_sync(a.csv_paths, a.apply, a.source_match)
    except ValueError as e:
        sys.exit("FATAL: " + str(e))


if __name__ == "__main__":
    main()
