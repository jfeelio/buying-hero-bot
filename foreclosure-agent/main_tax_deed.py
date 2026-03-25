"""
Tax Deed Agent — Daily Pipeline Orchestrator

Run order:
  1. Initialize Google Sheet "Tax Deed" tab header row
  2. Load dedup state (seen_tax_deed_cases.json)
  3. Open Playwright browser
  4. Scrape all upcoming auction listings (RealForeclose, next 8 weeks)
  5. Filter to TAXDEED auction type only
  6. Filter out already-seen case numbers
  7. For each new listing:
       a. Enrich with MDPA owner/mailing data (direct folio lookup via Parcel ID)
  8. Append enriched rows to Google Sheet "Tax Deed" tab
  9. Persist updated seen_tax_deed_cases.json
"""

import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

import config
from scrapers.mdpa import get_owner_info_by_folio
from scrapers.realforeclose import get_all_auctions
from scrapers.zillow import launch_browser
from sheets import append_rows

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
log_file = LOG_DIR / f"tax_deed_{date.today().isoformat()}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

SEEN_FILE = Path(__file__).parent / "seen_tax_deed_cases.json"


# ---------------------------------------------------------------------------
# Dedup helpers
# ---------------------------------------------------------------------------

def _load_seen() -> set:
    if not SEEN_FILE.exists():
        return set()
    try:
        return set(json.loads(SEEN_FILE.read_text()))
    except Exception as e:
        logger.warning(f"Could not load seen_tax_deed_cases.json: {e}")
        return set()


def _save_seen(case_numbers: set) -> None:
    try:
        SEEN_FILE.write_text(json.dumps(sorted(case_numbers), indent=2))
    except Exception as e:
        logger.error(f"Could not save seen_tax_deed_cases.json: {e}")


# ---------------------------------------------------------------------------
# Row builder
# ---------------------------------------------------------------------------

def build_row(listing: dict, owner: dict) -> list:
    """Assemble a flat list matching SHEET_COLUMNS order (same as foreclosure tab)."""
    first = owner.get("owner_first", "")
    last = owner.get("owner_last", "")
    if not first and last:
        first, last = last, ""
    return [
        "",                                         # Sent
        "",                                         # Company
        first,
        last,
        owner.get("mailing_address", ""),
        owner.get("mailing_city", ""),
        owner.get("mailing_state", ""),
        owner.get("mailing_zip", ""),
        listing.get("property_address", ""),        # Address
        listing.get("property_city", ""),           # City
        listing.get("property_state", "FL"),        # State
        listing.get("property_zip", ""),            # Zip
        listing.get("assessed_value", ""),          # Value (assessed value for tax deeds)
    ]


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run():
    logger.info("=" * 60)
    logger.info("Tax Deed Agent starting")
    logger.info("=" * 60)

    # Step 1: Load dedup state
    logger.info("Step 2: Loading dedup state")
    seen = _load_seen()
    logger.info(f"  Seen: {len(seen)} case(s)")

    with sync_playwright() as pw:
        browser, context, page = launch_browser(pw)
        try:
            # Step 3: Scrape auction listings (reuses same scraper as foreclosure)
            logger.info("Step 3: Scraping auction listings")
            try:
                all_listings = get_all_auctions(page, weeks=config.TAX_DEED_WEEKS_AHEAD)
            except Exception as e:
                logger.error(f"Scraper failed: {e}")
                sys.exit(1)
            logger.info(f"  Scraped {len(all_listings)} total listing(s)")

            # Step 4: Keep only tax deed auctions
            tax_deed_listings = [
                l for l in all_listings
                if l.get("auction_type", "").upper() == "TAXDEED"
            ]
            logger.info(f"  {len(tax_deed_listings)} tax deed listing(s)")

            # Step 5: Filter already-seen cases
            new_listings = [l for l in tax_deed_listings if l["case_number"] not in seen]
            logger.info(
                f"  {len(new_listings)} new after dedup ({len(seen)} previously seen)"
            )

            if not new_listings:
                logger.info("No new tax deed listings found. Pipeline complete.")
                return

            # Step 6: Filter to auctions at least 14 days out (direct mail lead time)
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

            logger.info(
                f"  {len(within_window)} qualifying (auction >= {cutoff.strftime('%m/%d/%Y')}), "
                f"{len(too_soon)} too soon / invalid (skipped)"
            )

            if not within_window:
                logger.info("No qualifying listings found. Pipeline complete.")
                return

            new_listings = within_window

            # Step 7: Enrich with MDPA (direct folio lookup — no Zillow needed,
            # assessed value is already on the listing)
            logger.info("Step 7: Enriching listings via MDPA folio lookup")
            enriched_rows = []
            new_case_numbers = set()

            for i, listing in enumerate(new_listings, start=1):
                case = listing.get("case_number", "?")
                parcel_id = listing.get("parcel_id", "")
                addr = listing.get("property_address", "")

                logger.info(f"  [{i}/{len(new_listings)}] Case {case}: {addr} (parcel {parcel_id})")

                if parcel_id:
                    owner = get_owner_info_by_folio(parcel_id)
                else:
                    # Fallback to address lookup if parcel ID is missing
                    from scrapers.mdpa import get_owner_info
                    owner = get_owner_info(addr, listing.get("property_city", ""))

                if not owner.get("mailing_address", "").strip():
                    logger.info(f"    Skipping case {case} — no mailing address")
                    new_case_numbers.add(case)
                    continue

                row = build_row(listing, owner)
                enriched_rows.append(row)
                new_case_numbers.add(case)

        finally:
            browser.close()

    # Step 8: Append to Google Sheet (same tab as foreclosure)
    logger.info("Step 8: Appending rows to Google Sheet")
    success = append_rows(enriched_rows)

    # Step 9: Update seen_tax_deed_cases.json
    if success:
        logger.info("Step 9: Saving seen cases")
        _save_seen(seen | new_case_numbers)
        logger.info(f"  Saved {len(seen | new_case_numbers)} total seen cases")
    else:
        logger.error("Sheet write failed -- seen_tax_deed_cases.json NOT updated (will retry next run)")

    logger.info("=" * 60)
    logger.info(f"Pipeline complete. {len(enriched_rows)} row(s) added.")
    logger.info("=" * 60)


if __name__ == "__main__":
    run()
