"""
Probate Agent — Daily Pipeline

Run order:
  1. Ensure Probate sheet tab has header row
  2. Load seen probate cases (seen_probate_cases.json)
  3. Pull new Formal + Summary Administration filings from the Clerk OCS API
  4. Filter out already-seen case numbers
  5. For each new case:
       a. Look up decedent's property via MDPA owner name search
       b. Skip if no Miami-Dade property found or no mailing address
  6. Append enriched rows to Probate sheet tab
  7. Persist updated seen_probate_cases.json
"""

import json
import logging
import os
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo
from pathlib import Path

import anthropic
import config
from scrapers.heirs import find_recipient
from scrapers.mdpa import get_property_by_owner_name
from scrapers.probate import _login, get_new_probate_cases
from sheets import append_rows, ensure_header_row, get_existing_case_numbers

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
log_file = LOG_DIR / f"probate_{date.today().isoformat()}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

SEEN_FILE = Path(__file__).parent / "seen_probate_cases.json"


# ---------------------------------------------------------------------------
# Dedup helpers
# ---------------------------------------------------------------------------

def load_seen() -> set:
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def save_seen(seen: set) -> None:
    SEEN_FILE.write_text(
        json.dumps(sorted(seen), indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Row builder
# ---------------------------------------------------------------------------

def _clean(value: str) -> str:
    """Collapse runs of spaces and drop stray trailing punctuation ("DRIVE," -> "DRIVE")."""
    return " ".join(str(value or "").split()).strip(" ,;")


def build_row(case: dict, mdpa: dict, heir: dict) -> list:
    """Assemble a flat list matching config.PROBATE_COLUMNS order.

    Mail goes to the heir from the court filings when one was found. Otherwise
    it goes to the property record's mailing address, addressed to the
    petitioner by name, or to "Estate of <decedent>" when there is none.
    """
    case_type = "Summary Admin" if "SUMMARY" in case.get("case_type", "").upper() else "Formal Admin"
    decedent = _clean(f"{case.get('decedent_first', '')} {case.get('decedent_last', '')}").title()
    rc = heir.get("recipient") or {}
    if rc:
        mail_to = _clean(rc.get("name", "")).title()
        relationship = _clean(rc.get("relationship", "")).title()
        mail = [_clean(rc.get("street", "")).upper(), _clean(rc.get("city", "")).upper(),
                _clean(rc.get("state", "")).upper(), _clean(rc.get("zip", ""))]
        source = heir.get("source", "")
    else:
        mail_to = heir.get("petitioner") or f"Estate of {decedent}"
        relationship = "Petitioner" if heir.get("petitioner") else ""
        mail = [mdpa.get("mailing_address", ""), mdpa.get("mailing_city", ""),
                mdpa.get("mailing_state", ""), mdpa.get("mailing_zip", "")]
        source = "Property Record"
    # Eastern date, not the GitHub runner's UTC date, so it matches the team's calendar.
    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    return [
        "Active",                              # Status ("Stop" halts mailing)
        case_type,                             # Type
        case.get("case_number", ""),           # Case Number (dedup key)
        case.get("filing_date", ""),           # Filing Date
        decedent,                              # Decedent
        mdpa.get("property_address", ""),
        mdpa.get("property_city", ""),
        mdpa.get("property_zip", ""),
        mail_to,                               # Mail To
        relationship,
        *mail,                                 # Mail Address / City / State / Zip
        source,                                # Address Source
        rc.get("phone", ""),                   # Heir Phone
        rc.get("email", ""),                   # Heir Email
        heir.get("other_heirs", ""),           # Other Heirs
        0,                                     # Letters Sent (mailer updates)
        "", "", "",                            # Letter 1-3 Date (mailer fills)
        today,                                 # Next Letter Due: letter 1 goes next run
        today,                                 # Date Added
    ]


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run():
    tab = config.PROBATE_TAB
    days_back = config.PROBATE_DAYS_BACK

    logger.info("=" * 60)
    logger.info("Probate Agent starting")
    logger.info(f"  Sheet tab : {tab}")
    logger.info(f"  Days back : {days_back}")
    logger.info("=" * 60)

    sheet_id = config.PROBATE_SHEET_ID

    # Step 1: Ensure sheet headers on Probate tab
    logger.info("Step 1: Ensuring Probate sheet header row")
    try:
        ensure_header_row(tab_name=tab, sheet_id=sheet_id, columns=config.PROBATE_COLUMNS)
        ensure_header_row(tab_name=config.PROBATE_MAIL_LOG_TAB, sheet_id=sheet_id,
                          columns=config.PROBATE_MAIL_LOG_COLUMNS)
    except Exception as e:
        logger.error(f"Sheet header setup failed: {e}")
        sys.exit(1)

    # Step 2: Load seen cases (local JSON + sheet as fallback)
    logger.info("Step 2: Loading seen probate cases")
    seen = load_seen() | get_existing_case_numbers(tab_name=tab, sheet_id=sheet_id, col=config.PROBATE_CASE_COL)
    logger.info(f"  Seen: {len(seen)} case(s) (local JSON + sheet)")

    # Step 3: Pull OCS filings
    logger.info("Step 3: Pulling OCS probate filings")
    try:
        all_cases = get_new_probate_cases(days_back=days_back)
    except Exception as e:
        logger.error(f"Probate scraper failed: {e}")
        sys.exit(1)
    logger.info(f"  Pulled {len(all_cases)} unique case(s)")

    # Step 4: Filter already-seen
    logger.info("Step 4: Filtering already-seen cases")
    new_cases = [c for c in all_cases if c["case_number"] not in seen]
    logger.info(f"  {len(new_cases)} new case(s) after dedup")

    if not new_cases:
        logger.info("No new probate cases found. Pipeline complete.")
        return

    # Step 5: Enrich via MDPA owner name lookup, then find the heir to mail
    logger.info("Step 5: Enriching with MDPA property lookup + heir documents")
    enriched_rows = []
    new_case_numbers = set()
    clerk = _login()
    claude = anthropic.Anthropic() if os.environ.get("ANTHROPIC_API_KEY") else None
    if not claude:
        logger.warning("  ANTHROPIC_API_KEY not set: mailing property-record addresses only")

    for i, case in enumerate(new_cases, start=1):
        case_num = case["case_number"]
        first = case["decedent_first"]
        last = case["decedent_last"]
        logger.info(
            f"  [{i}/{len(new_cases)}] {case_num} ({case['case_type']}, {case['case_status']}): "
            f"{case['case_style']}"
        )

        mdpa = get_property_by_owner_name(last, first)
        new_case_numbers.add(case_num)

        if not mdpa.get("mailing_address", "").strip():
            logger.info(f"    Skipping — no mailing address found in MDPA")
            continue

        if not mdpa.get("property_address", "").strip():
            logger.info(f"    Skipping — no property address found in MDPA")
            continue

        heir = {}
        if claude and case.get("case_id"):
            try:
                heir = find_recipient(clerk, claude, case["case_id"])
            except Exception as e:
                logger.warning(f"    Heir lookup failed, using property record: {e}")
        rc = heir.get("recipient") or {}
        if rc:
            logger.info(f"    Heir: {rc.get('name')} ({rc.get('relationship')}) via {heir.get('source')}")

        row = build_row(case, mdpa, heir)
        enriched_rows.append(row)
        logger.info(
            f"    -> {mdpa['property_address']}, {mdpa['property_city']} | "
            f"mail: {mdpa['mailing_address']}"
        )

    # Step 6: Append to sheet
    logger.info("Step 6: Appending rows to Probate sheet tab")
    success = append_rows(enriched_rows, tab_name=tab, sheet_id=sheet_id)

    # Step 7: Save seen cases
    if success:
        logger.info("Step 7: Saving seen probate cases")
        save_seen(seen | new_case_numbers)
        logger.info(f"  Saved {len(seen | new_case_numbers)} total seen case(s)")
    else:
        logger.error("Sheet write failed — seen_probate_cases.json NOT updated")

    logger.info("=" * 60)
    logger.info(f"Probate pipeline complete. {len(enriched_rows)} row(s) added.")
    logger.info("=" * 60)


if __name__ == "__main__":
    run()
