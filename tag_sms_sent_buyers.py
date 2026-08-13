#!/usr/bin/env python3
"""
Tag buyers in a "dispo" sheet with "SMS Sent" (or any value) in a target column,
based on a phone-number match against a "source" tab (e.g. an SMS-sent list).

Usage:
    python tag_sms_sent_buyers.py \\
        --sms-url   "https://docs.google.com/spreadsheets/d/<ID>/edit?gid=<GID>" \\
        --dispo-url "https://docs.google.com/spreadsheets/d/<ID>/edit?gid=<GID>"

    # Add --apply to write. Without it, a dry run is printed.
    # Override defaults if needed: --phone-col F --tag-col A --tag-value "SMS Sent"

Both URLs must point to the same spreadsheet. Auth uses the service account
at foreclosure-agent/credentials.json (needs edit access to the sheet).
"""

import argparse
import re
import sys
from pathlib import Path

from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

SCRIPT_DIR = Path(__file__).parent.resolve()
CREDS_PATH = SCRIPT_DIR / "foreclosure-agent" / "credentials.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def parse_sheet_url(url: str) -> tuple:
    """Extract (spreadsheet_id, gid) from a Google Sheets URL."""
    m_id = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    m_gid = re.search(r"[?#&]gid=(\d+)", url)
    if not m_id:
        raise ValueError(f"Could not extract spreadsheet ID from URL: {url}")
    if not m_gid:
        raise ValueError(f"Could not extract gid (tab id) from URL: {url}")
    return m_id.group(1), int(m_gid.group(1))


def get_service():
    creds = Credentials.from_service_account_file(str(CREDS_PATH), scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def normalize_phone(s: str) -> str:
    """Digits only, last 10 (handles +1, dashes, parens, etc.)."""
    if not s:
        return ""
    digits = re.sub(r"\D", "", s)
    return digits[-10:] if len(digits) >= 10 else ""


def get_tab_titles(svc, sheet_id: str) -> dict:
    meta = svc.spreadsheets().get(spreadsheetId=sheet_id).execute()
    return {s["properties"]["sheetId"]: s["properties"]["title"] for s in meta["sheets"]}


def read_col(svc, sheet_id: str, tab_name: str, col: str) -> list:
    """Read a single column from row 1 down. Returns list of strings."""
    rng = f"'{tab_name}'!{col}1:{col}"
    result = svc.spreadsheets().values().get(spreadsheetId=sheet_id, range=rng).execute()
    values = result.get("values", [])
    return [(row[0] if row else "") for row in values]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sms-url", required=True,
                        help="Full URL of the SMS-sent tab (with gid)")
    parser.add_argument("--dispo-url", required=True,
                        help="Full URL of the main dispo tab (with gid)")
    parser.add_argument("--phone-col", default="F",
                        help="Column letter holding phone numbers in BOTH tabs (default: F)")
    parser.add_argument("--tag-col", default="A",
                        help="Column letter to write the tag into on the dispo tab (default: A)")
    parser.add_argument("--tag-value", default="SMS Sent",
                        help="The text to write into the tag column (default: 'SMS Sent')")
    parser.add_argument("--apply", action="store_true",
                        help="Write to the sheet (default: dry run)")
    args = parser.parse_args()

    sms_id, sms_gid = parse_sheet_url(args.sms_url)
    dispo_id, dispo_gid = parse_sheet_url(args.dispo_url)
    if sms_id != dispo_id:
        print(f"ERROR: URLs reference different spreadsheets "
              f"({sms_id!r} vs {dispo_id!r}). They must be tabs in the same sheet.")
        return 1

    sheet_id = sms_id
    phone_col = args.phone_col.upper()
    tag_col = args.tag_col.upper()
    tag_value = args.tag_value

    svc = get_service()
    titles = get_tab_titles(svc, sheet_id)
    sms_tab = titles.get(sms_gid)
    dispo_tab = titles.get(dispo_gid)
    if not sms_tab or not dispo_tab:
        print(f"ERROR: tab not found. SMS gid {sms_gid} -> {sms_tab!r}, "
              f"Dispo gid {dispo_gid} -> {dispo_tab!r}")
        return 1

    print(f"Spreadsheet:     {sheet_id}")
    print(f"SMS-sent tab:    {sms_tab!r}  (gid {sms_gid})")
    print(f"Dispo tab:       {dispo_tab!r}  (gid {dispo_gid})")
    print(f"Phone column:    {phone_col}   Tag column: {tag_col}   Tag value: {tag_value!r}")

    sms_phones_raw   = read_col(svc, sheet_id, sms_tab, phone_col)
    dispo_phones_raw = read_col(svc, sheet_id, dispo_tab, phone_col)
    dispo_tags_raw   = read_col(svc, sheet_id, dispo_tab, tag_col)

    # Skip header (row 1) on both tabs.
    sms_phone_set = {normalize_phone(p) for p in sms_phones_raw[1:] if normalize_phone(p)}
    print(f"\nSMS tab: {len(sms_phones_raw) - 1} data rows, "
          f"{len(sms_phone_set)} unique normalized phones.")

    matches = []   # (sheet_row, raw_phone, current_tag)
    blanks = 0
    for offset, raw in enumerate(dispo_phones_raw[1:], start=2):  # offset = sheet row number
        norm = normalize_phone(raw)
        if not norm:
            blanks += 1
            continue
        if norm in sms_phone_set:
            current = dispo_tags_raw[offset - 1] if (offset - 1) < len(dispo_tags_raw) else ""
            matches.append((offset, raw, current))

    print(f"Dispo tab: {len(dispo_phones_raw) - 1} data rows, "
          f"{blanks} with blank phone.")
    print(f"Matches found: {len(matches)}")

    # SMS phones that don't appear in dispo
    dispo_phone_set = {normalize_phone(p) for p in dispo_phones_raw[1:] if normalize_phone(p)}
    unmatched = sorted(sms_phone_set - dispo_phone_set)
    if unmatched:
        print(f"\n{len(unmatched)} SMS phone(s) NOT found in dispo tab:")
        for p in unmatched[:25]:
            print(f"  - {p}")
        if len(unmatched) > 25:
            print(f"  ... and {len(unmatched) - 25} more")

    already_tagged = [m for m in matches if (m[2] or "").strip() == tag_value]
    overwrites     = [m for m in matches if (m[2] or "").strip() and (m[2] or "").strip() != tag_value]
    fresh          = [m for m in matches if not (m[2] or "").strip()]
    print(f"\nOf {len(matches)} matches:")
    print(f"  fresh (col {tag_col} empty):       {len(fresh)}")
    print(f"  already tagged {tag_value!r}: {len(already_tagged)}")
    print(f"  would overwrite other text:  {len(overwrites)}")

    if overwrites:
        print(f"\n  --- rows where col {tag_col} already has OTHER text (will be overwritten) ---")
        for row, phone, current in overwrites[:20]:
            print(f"    row {row:5d}: phone {phone!r:22s} col {tag_col} = {current!r} -> {tag_value!r}")
        if len(overwrites) > 20:
            print(f"    ... and {len(overwrites) - 20} more")

    print("\nPreview (first 10 matches):")
    for row, phone, current in matches[:10]:
        print(f"  row {row:5d}: phone {phone!r:22s} col {tag_col} was {current!r}")

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to write changes.")
        return 0

    to_write = [m for m in matches if (m[2] or "").strip() != tag_value]
    if not to_write:
        print("\nAll matched rows are already tagged — nothing to write.")
        return 0

    body = {
        "valueInputOption": "RAW",
        "data": [
            {"range": f"'{dispo_tab}'!{tag_col}{row}", "values": [[tag_value]]}
            for row, _, _ in to_write
        ],
    }
    svc.spreadsheets().values().batchUpdate(spreadsheetId=sheet_id, body=body).execute()
    print(f"\nWrote {tag_value!r} to {len(to_write)} cell(s) in column {tag_col} of {dispo_tab!r}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
