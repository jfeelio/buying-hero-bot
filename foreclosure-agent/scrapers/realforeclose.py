"""
Scrapes upcoming Miami-Dade foreclosure auction listings from RealForeclose.com.

Correct URL (as of 2026):
  https://www.miamidade.realforeclose.com/index.cfm?zaction=AUCTION&zmethod=PREVIEW&AUCTIONDATE=MM/DD/YYYY

Page structure:
  Each auction is a  div.AUCTION_ITEM  containing a  table.ad_tab
  Rows: <td class="AD_LBL"> label </td> <td class="AD_DTA"> value </td>

Key fields extracted:
  Case #              -> case_number
  Final Judgment Amount -> opening_bid
  Property Address    -> street (line 1) + "CITY, ST- ZIP" (line 2)
"""

import logging
import re
import time
from datetime import date, timedelta

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.miamidade.realforeclose.com/index.cfm"
PAGE_SIZE = 25


def _weekdays_for_next_n_weeks(weeks: int) -> list:
    today = date.today()
    days = []
    for offset in range(weeks * 7):
        d = today + timedelta(days=offset)
        if d.weekday() < 5:  # Monday-Friday
            days.append(d)
    return days


def _fetch_page(page, auction_date: date, start_row: int) -> str:
    url = (
        f"{BASE_URL}?zaction=AUCTION&zmethod=PREVIEW"
        f"&AUCTIONDATE={auction_date.strftime('%m/%d/%Y')}"
        f"&StartRow={start_row}"
    )
    try:
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        try:
            page.wait_for_selector(".AUCTION_ITEM", timeout=6000)
        except Exception:
            pass  # No auctions on this date — that's fine
        return page.content()
    except Exception as e:
        logger.warning(f"Playwright fetch failed for {auction_date} row {start_row}: {e}")
        return ""


def _parse_address(raw: str) -> tuple[str, str, str, str]:
    """
    Parse the multi-line Property Address field.
    Format:
      Line 1: STREET ADDRESS
      Line 2: CITY, ST- ZIP   (note dash before zip)

    Returns (street, city, state, zip_code).
    """
    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    if not lines:
        return "", "", "FL", ""

    street = lines[0].title() if lines else ""
    city, state, zip_code = "", "FL", ""

    if len(lines) >= 2:
        # "MIAMI BEACH, FL- 33140"
        city_state_zip = lines[1]
        # Split on last comma to separate city from state/zip
        if "," in city_state_zip:
            comma_idx = city_state_zip.rfind(",")
            city = city_state_zip[:comma_idx].strip().title()
            state_zip = city_state_zip[comma_idx + 1:].strip()
            # Remove dash before zip: "FL- 33140" -> "FL 33140"
            state_zip = re.sub(r"-\s*", " ", state_zip).strip()
            parts = state_zip.split()
            state = parts[0] if parts else "FL"
            zip_code = parts[1] if len(parts) > 1 else ""
        else:
            city = city_state_zip.title()

    return street, city, state, zip_code


def _parse_listings(html: str, auction_date: date) -> list:
    soup = BeautifulSoup(html, "lxml")
    items = soup.find_all("div", class_="AUCTION_ITEM")
    listings = []

    for item in items:
        record = {"auction_date": auction_date.strftime("%m/%d/%Y")}
        last_label = ""

        for row in item.find_all("tr"):
            lbl_td = row.find("td", class_="AD_LBL")
            dta_td = row.find("td", class_="AD_DTA")
            if not lbl_td or not dta_td:
                continue

            label = lbl_td.get_text(strip=True).rstrip(":").lower()
            value = dta_td.get_text(strip=True)

            # Empty label = continuation of previous field (e.g. city/state/zip
            # row that follows the street address row)
            if not label:
                label = last_label
            else:
                last_label = label

            if "case #" in label or label == "case":
                record["case_number"] = value
            elif "auction type" in label:
                record["auction_type"] = value.upper()
            elif "certificate #" in label:
                record["certificate_number"] = value
            elif "final judgment" in label or label == "opening bid":
                # Final Judgment Amount (foreclosure) or Opening Bid (tax deed)
                record["opening_bid"] = value
            elif "parcel id" in label:
                record["parcel_id"] = value
            elif "assessed value" in label:
                record["assessed_value"] = value
            elif "property address" in label or label == "address":
                if "property_address" not in record:
                    # First occurrence = street address row
                    record["property_address"] = value.title()
                else:
                    # Second occurrence (empty-label continuation) = "MIAMI BEACH, FL- 33140"
                    if "," in value:
                        comma_idx = value.rfind(",")
                        city = value[:comma_idx].strip().title()
                        state_zip = re.sub(r"-\s*", " ", value[comma_idx + 1:].strip())
                        parts = state_zip.split()
                        record["property_city"] = city
                        record["property_state"] = parts[0] if parts else "FL"
                        record["property_zip"] = parts[1] if len(parts) > 1 else ""

        # Only keep records that have a case number
        if not record.get("case_number"):
            continue

        record.setdefault("auction_type", "FORECLOSURE")
        record.setdefault("certificate_number", "")
        record.setdefault("opening_bid", "")
        record.setdefault("parcel_id", "")
        record.setdefault("assessed_value", "")
        record.setdefault("property_address", "")
        record.setdefault("property_city", "")
        record.setdefault("property_state", "FL")
        record.setdefault("property_zip", "")
        listings.append(record)

    return listings


def _has_next_page(html: str) -> bool:
    soup = BeautifulSoup(html, "lxml")
    next_link = soup.find("a", string=lambda t: t and "next" in t.lower())
    return next_link is not None


def get_all_auctions(playwright_page, weeks: int = 8) -> list:
    all_listings = []
    auction_days = _weekdays_for_next_n_weeks(weeks)

    for auction_date in auction_days:
        date_str = auction_date.strftime("%m/%d/%Y")
        start_row = 1
        page_num = 0
        seen_cases_this_date: set = set()

        while True:
            page_num += 1
            logger.info(f"Scraping {date_str} page {page_num} (StartRow={start_row})")
            html = _fetch_page(playwright_page, auction_date, start_row)

            if not html:
                break

            listings = _parse_listings(html, auction_date)

            # Filter: require a property address
            listings = [l for l in listings if l.get("property_address")]

            # Pagination guard: stop if all case numbers on this page are already seen
            new_cases = [l for l in listings if l["case_number"] not in seen_cases_this_date]
            if not new_cases:
                logger.info(f"  no new cases — stopping pagination for {date_str}")
                break

            logger.info(f"  found {len(new_cases)} new listing(s)")
            for l in new_cases:
                seen_cases_this_date.add(l["case_number"])
            all_listings.extend(new_cases)

            if not _has_next_page(html):
                break

            start_row += PAGE_SIZE
            time.sleep(1.0)

    logger.info(f"Total auction listings scraped: {len(all_listings)}")
    return all_listings
