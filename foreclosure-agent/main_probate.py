"""
Probate Agent — Daily Pipeline

Run order:
  1. Ensure Probate sheet tab has header row
  2. Load seen probate cases (seen_probate_cases.json)
  3. Open Playwright browser
  4. Scrape new Formal Administration filings from Miami-Dade OCS
  5. Filter out already-seen case numbers
  6. For each new case:
       a. Look up decedent's property via MDPA owner name search
       b. Skip if no Miami-Dade property found or no mailing address
  7. Append enriched rows to Probate sheet tab
  8. Persist updated seen_probate_cases.json
"""

import json
import logging
import sys
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

import config
from scrapers.mdpa import get_property_by_owner_name
from scrapers.probate import get_new_probate_cases
from scrapers.zillow import launch_browser
from sheets import append_rows, ensure_header_row

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

def build_row(case: dict, mdpa: dict) -> list:
    """Assemble a flat list matching SHEET_COLUMNS order."""
    first = mdpa.get("owner_first", "")
    last = mdpa.get("owner_last", "")
    if not first and last:
        first, last = last, ""
    return [
        "",                                    # Sent
        "",                                    # Company
        first,
        last,
        mdpa.get("mailing_address", ""),
        mdpa.get("mailing_city", ""),
        mdpa.get("mailing_state", ""),
        mdpa.get("mailing_zip", ""),
        mdpa.get("property_address", ""),
        mdpa.get("property_city", ""),
        mdpa.get("property_state", "FL"),
        mdpa.get("property_zip", ""),
        "",                                    # Value (blank)
    ]


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run():
    tab = config.PROBATE_SHEET_TAB_NAME
    days_back = config.PROBATE_DAYS_BACK

    logger.info("=" * 60)
    logger.info("Probate Agent starting")
    logger.info(f"  Sheet tab : {tab}")
    logger.info(f"  Days back : {days_back}")
    logger.info("=" * 60)

    sheet_id = config.PROBATE_GOOGLE_SHEET_ID

    # Step 1: Ensure sheet headers on Probate tab
    logger.info("Step 1: Ensuring Probate sheet header row")
    try:
        ensure_header_row(tab_name=tab, sheet_id=sheet_id)
    except Exception as e:
        logger.error(f"Sheet header setup failed: {e}")
        sys.exit(1)

    # Step 2: Load seen cases
    logger.info("Step 2: Loading seen probate cases")
    seen = load_seen()
    logger.info(f"  Seen: {len(seen)} case(s)")

    with sync_playwright() as pw:
        browser, context, page = launch_browser(pw)
        try:
            # Step 3: Scrape OCS
            logger.info("Step 3: Scraping OCS probate filings")
            try:
                all_cases = get_new_probate_cases(page, days_back=days_back)
            except Exception as e:
                logger.error(f"Probate scraper failed: {e}")
                sys.exit(1)
            logger.info(f"  Scraped {len(all_cases)} unique case(s)")

            # Step 4: Filter already-seen
            logger.info("Step 4: Filtering already-seen cases")
            new_cases = [c for c in all_cases if c["case_number"] not in seen]
            logger.info(f"  {len(new_cases)} new case(s) after dedup")

            if not new_cases:
                logger.info("No new probate cases found. Pipeline complete.")
                return

            # Step 5: Enrich via MDPA owner name lookup
            logger.info("Step 5: Enriching with MDPA property lookup")
            enriched_rows = []
            new_case_numbers = set()

            for i, case in enumerate(new_cases, start=1):
                case_num = case["case_number"]
                first = case["decedent_first"]
                last = case["decedent_last"]
                logger.info(
                    f"  [{i}/{len(new_cases)}] {case_num}: {case['case_style']}"
                )

                mdpa = get_property_by_owner_name(last, first)
                new_case_numbers.add(case_num)

                if not mdpa.get("mailing_address", "").strip():
                    logger.info(f"    Skipping — no mailing address found in MDPA")
                    continue

                if not mdpa.get("property_address", "").strip():
                    logger.info(f"    Skipping — no property address found in MDPA")
                    continue

                row = build_row(case, mdpa)
                enriched_rows.append(row)
                logger.info(
                    f"    -> {mdpa['property_address']}, {mdpa['property_city']} | "
                    f"mail: {mdpa['mailing_address']}"
                )

        finally:
            browser.close()

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
