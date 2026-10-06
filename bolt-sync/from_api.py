"""Daily Bolt PPC vendor sheet sync, fed by the REsimpli API.

Replaces the Claude-desktop CSV export + office-PC task, which stalled on
Aug 31 2026. Pulls every lead on the "Bolt PPC" campaign, writes them as one
CSV in the same shape REsimpli's export used, and hands it to sheet.py, so the
qualification rules (Jorge, 2026-08-18 / 09-13) and the privacy filter are the
exact ones the vendor has been seeing.

Pipeline -> the export's "Lead Status":
  Dead Leads                      -> "Dead Lead"   (Dead, Unqualified)
  Cold Leads / Referred to Agent  -> "Warm Lead"   (Warm, Unqualified)
  anything else                   -> the status title (Active rules apply)

This repo is PUBLIC: log counts only.

Usage:  python from_api.py            # write the sheet
        python from_api.py --dry-run
"""
import argparse
import csv
import datetime as dt
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "weekly-acq-report"))
from pull import all_leads, log, post, scope_status_ids  # noqa: E402

import sheet  # noqa: E402

CAMPAIGN_ID = "6aa4f3c24ded82f2fd087b6d"  # Bolt PPC
WARM_PIPELINES = {"Cold Leads", "Referred to Agent"}
HEADERS = ["Property ID", "Lead Created Date", "First Name", "Last Name", "Phone Number",
           "Email Address", "Property Street Address", "Property City", "Property State",
           "Property Zip", "Lead Source", "Campaign Name", "Lead Status", "Dead Lead Reason", "Tags"]


def split_address(a):
    """'11865 Sw 183rd St, Miami, FL 33177' -> street, city, state, zip."""
    parts = [p.strip() for p in (a or "").split(",")]
    street, city, state, zp = parts[0] if parts else "", "", "", ""
    if len(parts) >= 3:
        city = parts[1]
        tail = parts[-1].replace("USA", "").split() or [""]
        if tail and tail[-1].isdigit():
            zp = tail[-1]
            tail = tail[:-1]
        if tail:
            state = tail[0]
        if len(parts) >= 4 and not state:  # "..., FL, USA 33157"
            state = parts[-2]
    elif len(parts) == 2:
        city = parts[1]
    return street, city, state, zp


def fmt_phone(p):
    d = "".join(ch for ch in p or "" if ch.isdigit())[-10:]
    return "(%s) %s-%s" % (d[:3], d[3:6], d[6:]) if len(d) == 10 else (p or "")


def rows():
    leads, _ = all_leads()
    _, statuses = scope_status_ids()
    mine = [l for l in leads if l.get("marketingCampignId") == CAMPAIGN_ID]
    log("Bolt PPC leads: %d" % len(mine))
    out = []
    for l in mine:
        det = post("lead/details", {"leadId": l["_id"]})["data"]["leadData"]
        time.sleep(0.6)
        st = statuses.get(l.get("mainStatusId"), {})
        pipe = st.get("pipeline") or ""
        title = st.get("title") or l.get("mainStatusTitle") or ""
        if pipe == "Dead Leads":
            status = "Dead Lead"
        elif pipe in WARM_PIPELINES:
            status = "Warm Lead"
        else:
            status = title
        c = (det.get("contactData") or [{}])[0]
        phones = c.get("phoneNumbers") or []
        phone = next((p["phoneNumber"] for p in phones if p.get("isPrimary")), phones[0]["phoneNumber"] if phones else "")
        emails = c.get("emails") or []
        street, city, state, zp = split_address(l.get("address"))
        out.append({
            "Property ID": l["_id"],
            # UTC date, like REsimpli's own export: an evening lead is dated the next day.
            "Lead Created Date": dt.datetime.fromtimestamp(l["createdAt"] / 1000, dt.timezone.utc).strftime("%Y-%m-%d"),
            "First Name": c.get("firstName") or "", "Last Name": c.get("lastName") or "",
            "Phone Number": fmt_phone(phone), "Email Address": next((e["email"] for e in emails if e.get("isPrimary")),
                                                         emails[0]["email"] if emails else ""),
            "Property Street Address": street, "Property City": city, "Property State": state, "Property Zip": zp,
            "Lead Source": "Google Adwords/PPC", "Campaign Name": "Bolt PPC",
            "Lead Status": status,
            "Dead Lead Reason": ", ".join(filter(None, (d.get("title") or d.get("name") for d in det.get("deadReasonsData") or []))),
            "Tags": ", ".join(t.get("label", "") for t in l.get("tags") or [] if not t.get("isDeleted")),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    data = rows()
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HEADERS)
        w.writeheader()
        w.writerows(data)
        path = f.name
    try:
        res = sheet.run_sync([path], apply=not a.dry_run)
    finally:
        os.unlink(path)
    # Counted by the automation status check.
    print("Bolt sheet sync complete. %d rows in sheet (%d new)." % (res["rows"], res["new"]))


if __name__ == "__main__":
    main()
