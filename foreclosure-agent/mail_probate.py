"""
Probate Mailer — Daily Open Letter Connect send

Run order:
  1. Read the Probate tab and the Probate Mail Log tab
  2. Pick cases due today: Status "Active", fewer than 3 letters sent,
     Next Letter Due on or before today, a full mailing address
  3. Drop anything on the Do-Not-Mail sheet (property OR mailing address)
     and anything the Mail Log says already went out for that letter #
  4. Place one Open Letter Connect order per letter # (1, 2, 3)
  5. For each order that succeeds, append one Mail Log row per piece and
     update the case row: Letters Sent, Letter N Date, Next Letter Due

Letter schedule, counted from letter 1: day 0, day 30, day 90.

OLC_DRY_RUN=1 (the default) logs what would be mailed and writes nothing.
Set OLC_DRY_RUN=0 to place real orders.
"""

import logging
import os
import re
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

import config
from sheets import _get_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

OLC_BASE = os.environ.get("OLC_BASE_URL") or "https://api.openletterconnect.com/api/v1"
OLC_API_KEY = os.environ.get("OLC_API_KEY", "")
OLC_TEMPLATE_ID = int(os.environ.get("OLC_PROBATE_TEMPLATE_ID") or 12923)
OLC_PRODUCT_ID = int(os.environ.get("OLC_PROBATE_PRODUCT_ID") or 0)
DRY_RUN = os.environ.get("OLC_DRY_RUN", "1") != "0"
DAILY_CAP = int(os.environ.get("OLC_DAILY_CAP") or 150)

DNM_SHEET_ID = os.environ.get("DNM_SHEET_ID") or "1J3BjoQztugQnLjQiByp4cv3oEGUH1pJcrBu55kK5gV4"

# Open Letter Connect mails within the US only; foreign heirs are left for hand mailing.
US_STATES = set("""AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV
NH NJ NM NY NC ND OH OK OR PA PR RI SC SD TN TX UT VT VA VI WA WV WI WY GU""".split())

# Days after letter 1 that each later letter is due.
LETTER_OFFSETS = {2: 30, 3: 90}
MAX_LETTERS = 3


# ---------------------------------------------------------------------------
# Address matching (Do-Not-Mail)
# ---------------------------------------------------------------------------

def _street_key(street: str) -> str:
    """'1089 NE 104th St.' and '1089 NE 104 ST' -> '1089 NE 104 ST'."""
    s = re.sub(r"[^A-Z0-9 ]", " ", (street or "").upper())
    s = re.sub(r"\b(\d+)(ST|ND|RD|TH)\b", r"\1", s)
    s = re.sub(r"\b(STREET)\b", "ST", s)
    s = re.sub(r"\b(AVENUE)\b", "AVE", s)
    s = re.sub(r"\b(TERRACE|TERR)\b", "TER", s)
    s = re.sub(r"\b(DRIVE)\b", "DR", s)
    s = re.sub(r"\b(COURT)\b", "CT", s)
    s = re.sub(r"\b(ROAD)\b", "RD", s)
    return " ".join(s.split())


def load_dnm(svc) -> set:
    rows = svc.values().get(spreadsheetId=DNM_SHEET_ID, range="Sheet1!C2:J").execute().get("values", [])
    keys = set()
    for r in rows:
        r = r + [""] * (8 - len(r))
        for street in (r[0], r[4]):          # Property Address (C), Mailing Address (G)
            k = _street_key(street)
            if k:
                keys.add(k)
    logger.info(f"Do-Not-Mail: {len(keys)} addresses loaded")
    return keys


# ---------------------------------------------------------------------------
# Sheet helpers
# ---------------------------------------------------------------------------

def _col(n: int) -> str:
    """0-based column index -> A1 letter (0 -> A, 23 -> X)."""
    s = ""
    n += 1
    while n:
        n, rem = divmod(n - 1, 26)
        s = chr(65 + rem) + s
    return s


def read_tab(svc, tab: str) -> tuple[list, list]:
    vals = svc.values().get(spreadsheetId=config.PROBATE_SHEET_ID, range=f"'{tab}'!A1:Z").execute().get("values", [])
    if not vals:
        return [], []
    header = vals[0]
    rows = [dict(zip(header, r + [""] * (len(header) - len(r)))) for r in vals[1:]]
    return header, rows


def _parse_date(s: str):
    try:
        return date.fromisoformat((s or "").strip())
    except ValueError:
        return None


def _split_name(full: str) -> tuple[str, str]:
    parts = (full or "").split()
    if not parts:
        return "", ""
    if full.upper().startswith("ESTATE OF"):
        return "", full
    return parts[0], " ".join(parts[1:])


# ---------------------------------------------------------------------------
# Open Letter Connect
# ---------------------------------------------------------------------------

def _contact(row: dict) -> dict:
    first, last = _split_name(row["Mail To"])
    return {
        "firstName": first,
        "lastName": last,
        "address1": row["Mail Address"],
        "city": row["Mail City"],
        "state": row["Mail State"],
        "zip": row["Mail Zip"],
        "propertyAddress": row["Property Address"],
        "propertyCity": row["Property City"],
        "propertyState": "FL",
        "propertyZip": row["Property Zip"],
        "meta_data": {"case_number": row["Case Number"], "decedent": row["Decedent"]},
    }


def place_order(letter_no: int, rows: list) -> str:
    """Place one OLC order for these rows. Returns the OLC order id."""
    body = {
        "contacts": [_contact(r) for r in rows],
        "productId": OLC_PRODUCT_ID,
        "templateId": OLC_TEMPLATE_ID,
        "name": f"Probate letter {letter_no} - {date.today().isoformat()}",
    }
    r = requests.post(
        f"{OLC_BASE}/orders",
        json=body,
        headers={"Authorization": f"Bearer {OLC_API_KEY}"},
        timeout=120,
    )
    if r.status_code >= 300:
        raise RuntimeError(f"OLC order failed ({r.status_code}): {r.text[:500]}")
    data = r.json().get("data") or {}
    order_id = str(data.get("id") or "")
    if not order_id:
        raise RuntimeError(f"OLC returned no order id: {r.text[:500]}")
    logger.info(f"  OLC order {order_id}: status={data.get('status')} payment={data.get('paymentStatus')} cost={data.get('cost')}")
    return order_id


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(today: date = None):
    # Eastern date, matching the dates main_probate.py writes.
    today = today or datetime.now(ZoneInfo("America/New_York")).date()
    logger.info("=" * 60)
    logger.info(f"Probate mailer starting ({'DRY RUN - nothing is sent or written' if DRY_RUN else 'LIVE'})")
    logger.info(f"  Template {OLC_TEMPLATE_ID}, product {OLC_PRODUCT_ID}, cap {DAILY_CAP}")
    logger.info("=" * 60)

    if not DRY_RUN and (not OLC_API_KEY or not OLC_PRODUCT_ID):
        logger.error("OLC_API_KEY and OLC_PROBATE_PRODUCT_ID are required for a live run")
        sys.exit(1)

    svc = _get_service().spreadsheets()
    header, cases = read_tab(svc, config.PROBATE_TAB)
    _, log_rows = read_tab(svc, config.PROBATE_MAIL_LOG_TAB)
    already = {(r["Case Number"], str(r["Letter #"])) for r in log_rows}
    dnm = load_dnm(svc)
    col = {name: i for i, name in enumerate(header)}

    due = {}  # letter # -> list of rows
    skipped = {"dnm": 0, "no address": 0, "non-US": 0, "already logged": 0}
    for i, row in enumerate(cases, start=2):          # sheet row number
        row["_row"] = i
        if row["Status"].strip().lower() != "active":
            continue
        sent = int(row["Letters Sent"] or 0)
        next_due = _parse_date(row["Next Letter Due"])
        if sent >= MAX_LETTERS or not next_due or next_due > today:
            continue
        if not (row["Mail Address"] and row["Mail City"] and row["Mail Zip"]):
            skipped["no address"] += 1
            continue
        if not (re.fullmatch(r"\d{5}(-\d{4})?", row["Mail Zip"].strip()) and row["Mail State"].strip().upper() in US_STATES):
            skipped["non-US"] += 1
            logger.info(f"  Non-US address, mail by hand: {row['Case Number']} {row['Mail To']}, {row['Mail City']} {row['Mail State']} {row['Mail Zip']}")
            continue
        if _street_key(row["Property Address"]) in dnm or _street_key(row["Mail Address"]) in dnm:
            skipped["dnm"] += 1
            logger.info(f"  Do-Not-Mail: {row['Case Number']} {row['Property Address']}")
            continue
        letter_no = sent + 1
        if (row["Case Number"], str(letter_no)) in already:
            skipped["already logged"] += 1
            logger.warning(f"  {row['Case Number']} letter {letter_no} is already in the Mail Log; fix its row")
            continue
        due.setdefault(letter_no, []).append(row)

    total = sum(len(v) for v in due.values())
    logger.info(f"Due today: {total} piece(s) {[(k, len(v)) for k, v in sorted(due.items())]} | skipped {skipped}")
    if total > DAILY_CAP:
        logger.error(f"{total} pieces exceeds the daily cap of {DAILY_CAP}; nothing sent. Raise OLC_DAILY_CAP to proceed.")
        sys.exit(1)

    failures = 0
    for letter_no, rows in sorted(due.items()):
        for r in rows:
            logger.info(f"  L{letter_no} {r['Case Number']} -> {r['Mail To']}, {r['Mail Address']}, "
                        f"{r['Mail City']} {r['Mail State']} {r['Mail Zip']} ({r['Address Source']})")
        if DRY_RUN:
            continue
        try:
            order_id = place_order(letter_no, rows)
        except Exception as e:
            failures += 1
            logger.error(f"Letter {letter_no}: {e}")
            continue

        # Log every piece first, so a failed row update can never cause a re-mail.
        stamp = today.isoformat()
        svc.values().append(
            spreadsheetId=config.PROBATE_SHEET_ID,
            range=f"'{config.PROBATE_MAIL_LOG_TAB}'!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [[stamp, r["Case Number"], letter_no, r["Mail To"], r["Mail Address"],
                              r["Mail City"], r["Mail State"], r["Mail Zip"], r["Address Source"],
                              order_id, OLC_TEMPLATE_ID, "Ordered"] for r in rows]},
        ).execute()

        updates = []
        for r in rows:
            first = _parse_date(r["Letter 1 Date"]) or today
            nxt = (first + timedelta(days=LETTER_OFFSETS[letter_no + 1])).isoformat() if letter_no < MAX_LETTERS else ""
            for name, value in ((f"Letter {letter_no} Date", stamp), ("Letters Sent", letter_no), ("Next Letter Due", nxt)):
                updates.append({"range": f"'{config.PROBATE_TAB}'!{_col(col[name])}{r['_row']}", "values": [[value]]})
        svc.values().batchUpdate(
            spreadsheetId=config.PROBATE_SHEET_ID,
            body={"valueInputOption": "RAW", "data": updates},
        ).execute()
        logger.info(f"Letter {letter_no}: {len(rows)} piece(s) ordered ({order_id}), logged and updated")

    logger.info("=" * 60)
    logger.info(f"Probate mailer complete. {total} piece(s) {'would be ' if DRY_RUN else ''}mailed, {failures} failed order(s).")
    logger.info("=" * 60)
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    run()
