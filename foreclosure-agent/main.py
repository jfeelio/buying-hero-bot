"""
Foreclosure Agent — Daily Pipeline Orchestrator

Run order:
  1. Initialize Google Sheet header row
  2. Load dedup state (seen_cases.json + Sheet column N)
  3. Open Playwright browser (used for both scraping and Zillow)
  4. Scrape all upcoming auction listings (RealForeclose, next 8 weeks)
  5. Filter out already-seen case numbers
  6. For each new listing:
       a. Enrich with MDPA owner/mailing data
       b. Enrich with Zillow Zestimate (with delay)
  7. Append enriched rows to Google Sheet
  8. Persist updated seen_cases.json
"""

import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

import config
from dedup import filter_new_cases, load_seen_cases, save_seen_cases
from scrapers.mdpa import get_owner_info
from scrapers.realforeclose import get_all_auctions
from scrapers.zillow import launch_browser
from sheets import append_rows, ensure_header_row

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
log_file = LOG_DIR / f"run_{date.today().isoformat()}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Row builder
# ---------------------------------------------------------------------------

def build_row(listing: dict, owner: dict) -> list:
    """Assemble a flat list matching SHEET_COLUMNS order."""
    first = owner.get("owner_first", "")
    last = owner.get("owner_last", "")
    # If first name is blank but last name has a value, promote last -> first
    if not first and last:
        first, last = last, ""
    return [
        "",                                        # Sent (blank until mailed)
        "",                                        # Company
        first,
        last,
        owner.get("mailing_address", ""),
        owner.get("mailing_city", ""),
        owner.get("mailing_state", ""),
        owner.get("mailing_zip", ""),
        listing.get("property_address", ""),       # Address
        listing.get("property_city", ""),          # City
        listing.get("property_state", "FL"),       # State
        listing.get("property_zip", ""),           # Zip
        "",                                        # Value (reserved)
    ]


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run():
    logger.info("=" * 60)
    logger.info("Foreclosure Agent starting")
    logger.info("=" * 60)

    # Step 1: Ensure sheet headers
    logger.info("Step 1: Ensuring Google Sheet header row")
    try:
        ensure_header_row()
    except Exception as e:
        logger.error(f"Sheet header setup failed: {e}")
        sys.exit(1)

    # Step 2: Load dedup state
    logger.info("Step 2: Loading dedup state")
    seen = load_seen_cases()
    logger.info(f"  Seen: {len(seen)} case(s)")

    with sync_playwright() as pw:
        browser, context, page = launch_browser(pw)
        try:
            # Step 3: Scrape auction listings (uses same Playwright browser)
            logger.info("Step 3: Scraping auction listings")
            try:
                all_listings = get_all_auctions(page, weeks=config.WEEKS_AHEAD)
            except Exception as e:
                logger.error(f"Scraper failed: {e}")
                sys.exit(1)
            logger.info(f"  Scraped {len(all_listings)} total listing(s)")

            # Filter out tax deed auctions — handled by main_tax_deed.py
            all_listings = [l for l in all_listings if l.get("auction_type", "").upper() != "TAXDEED"]
            logger.info(f"  {len(all_listings)} foreclosure listing(s) after removing tax deeds")

            # Step 4: Filter already-seen cases
            logger.info("Step 4: Filtering already-seen cases")
            new_listings = filter_new_cases(all_listings, seen)

            if not new_listings:
                logger.info("No new listings found. Pipeline complete.")
                return

            logger.info(f"  {len(new_listings)} new listing(s) after dedup")

            # Step 4b: Filter to auction dates at least 14 days from today
            # (need 2 weeks lead time for direct mail to be effective)
            logger.info("Step 4b: Filtering to auctions starting 2+ weeks out")
            today = date.today()
            cutoff = today + timedelta(days=14)
            within_window = []
            too_soon = []
            for listing in new_listings:
                try:
                    auction_dt = datetime.strptime(listing["auction_date"], "%m/%d/%Y").date()
                except (ValueError, KeyError):
                    auction_dt = None
                if auction_dt and auction_dt >= cutoff:
                    within_window.append(listing)
                else:
                    too_soon.append(listing)

            logger.info(f"  {len(within_window)} qualifying (auction >= {cutoff.strftime('%m/%d/%Y')}), "
                        f"{len(too_soon)} too soon / invalid (skipped)")

            if not within_window:
                logger.info("No qualifying listings found. Pipeline complete.")
                return

            new_listings = within_window

            # Step 5: Enrich with MDPA + Zillow
            logger.info("Step 5: Enriching listings")
            enriched_rows = []
            new_case_numbers = set()

            for i, listing in enumerate(new_listings, start=1):
                case = listing.get("case_number", "?")
                addr = listing.get("property_address", "")
                city = listing.get("property_city", "")
                state = listing.get("property_state", "FL")
                zip_code = listing.get("property_zip", "")

                logger.info(f"  [{i}/{len(new_listings)}] Case {case}: {addr}")

                # MDPA
                owner = get_owner_info(addr, city, state)

                # Skip listings with no mailing address
                if not owner.get("mailing_address", "").strip():
                    logger.info(f"    Skipping case {case} — no mailing address")
                    new_case_numbers.add(case)  # still mark seen so we don't retry
                    continue

                row = build_row(listing, owner)
                enriched_rows.append(row)
                new_case_numbers.add(case)

        finally:
            browser.close()

    # Step 6: Append to Google Sheet
    logger.info("Step 6: Appending rows to Google Sheet")
    success = append_rows(enriched_rows)

    # Step 7: Update seen_cases.json (only on successful write)
    if success:
        logger.info("Step 7: Saving seen cases")
        save_seen_cases(seen | new_case_numbers)
        logger.info(f"  Saved {len(seen | new_case_numbers)} total seen cases")
    else:
        logger.error("Sheet write failed -- seen_cases.json NOT updated (will retry next run)")

    logger.info("=" * 60)
    logger.info(f"Pipeline complete. {len(enriched_rows)} row(s) added.")
    logger.info("=" * 60)


if __name__ == "__main__":
    run()
