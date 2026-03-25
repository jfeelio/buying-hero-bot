"""
Scrapes new probate (Formal Administration) case filings from Miami-Dade
County OCS (Online Case System).

Strategy:
  - Searches by Party Name using vowel letters as wildcards (covers ~100% of names)
  - Filters by case type: FORMAL ADMINISTRATION
  - Date range: last N days (configurable)
  - Deduplicates by local case number

Returns per case:
  case_number, case_style, decedent_first, decedent_last, filing_date
"""

import logging
import re
import time
from datetime import date, timedelta

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

OCS_URL = "https://www2.miamidadeclerk.gov/ocs/"
FORMAL_ADMIN_CASE_TYPE = "25043"

# Vowels cover virtually every name; 4 searches per run is sufficient
SEARCH_LETTERS = ["a", "e", "i", "o"]


# ---------------------------------------------------------------------------
# Name parsing
# ---------------------------------------------------------------------------

def _parse_decedent_name(case_style: str) -> tuple[str, str]:
    """
    Extract (first, last) from OCS case style string.

    Formats seen:
      "IN RE: Alayon, Justina"              -> ("JUSTINA", "ALAYON")
      "IN RE: ALMEIDA, FRANCISCO"           -> ("FRANCISCO", "ALMEIDA")
      "IN RE: Bertha Suarez, Bertha Lilia Suarez a/k/a"
                                            -> ("BERTHA", "SUAREZ")
      "IN RE: CLANCY, PETER J."             -> ("PETER J.", "CLANCY")
    """
    name = re.sub(r"^IN RE:\s*", "", case_style, flags=re.IGNORECASE).strip()
    # Drop a/k/a suffix and everything after it
    name = re.split(r"\s+a/k/a\b", name, flags=re.IGNORECASE)[0].strip()

    if "," in name:
        # "LAST, FIRST [MIDDLE]"
        parts = name.split(",", 1)
        last = parts[0].strip().upper()
        first = parts[1].strip().split(",")[0].strip().upper()
    else:
        parts = name.split()
        if len(parts) >= 2:
            first = parts[0].upper()
            last = parts[-1].upper()
        else:
            first = ""
            last = name.upper()

    return first, last


# ---------------------------------------------------------------------------
# OCS page interaction
# ---------------------------------------------------------------------------

def _navigate_and_search(playwright_page, letter: str, date_from: date, date_to: date) -> str:
    """
    Navigate to OCS, fill the Party Name search form, and return page HTML
    after results have loaded.
    """
    playwright_page.goto(OCS_URL, timeout=30000, wait_until="networkidle")
    time.sleep(3)

    playwright_page.get_by_text("Party Name").click()
    time.sleep(3)

    playwright_page.fill("#partyLastName", letter)
    playwright_page.select_option("#caseType", value=FORMAL_ADMIN_CASE_TYPE)
    playwright_page.fill("#filingDateFrom", date_from.strftime("%Y-%m-%d"))
    playwright_page.fill("#filingDateTo", date_to.strftime("%Y-%m-%d"))
    playwright_page.click('button:has-text("SEARCH")')

    # Wait for the SPA results to render
    time.sleep(22)

    return playwright_page.content()


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

def _parse_case_cards(html: str) -> list[dict]:
    """Parse all TitleSearchTab cards from results HTML."""
    soup = BeautifulSoup(html, "lxml")
    cards = soup.find_all("div", class_="TitleSearchTab")
    results = []

    for card in cards:
        style_el = card.find("p", class_="fs-5")
        case_style = style_el.get_text(strip=True) if style_el else ""

        def field(name):
            el = card.find("p", attrs={"data-id": name})
            return el.get_text(strip=True) if el else ""

        case_number = field("Local Case Number")
        filing_date = field("Filing Date")
        case_status = field("Case Status")

        if not case_number:
            continue
        if case_status.upper() != "OPEN":
            continue

        decedent_first, decedent_last = _parse_decedent_name(case_style)
        results.append({
            "case_number": case_number,
            "case_style": case_style,
            "decedent_first": decedent_first,
            "decedent_last": decedent_last,
            "filing_date": filing_date,
        })

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_new_probate_cases(playwright_page, days_back: int = 14) -> list[dict]:
    """
    Return deduplicated list of new Formal Administration probate cases
    filed within the last `days_back` days.
    """
    today = date.today()
    date_from = today - timedelta(days=days_back)
    seen: dict[str, dict] = {}

    for letter in SEARCH_LETTERS:
        logger.info(f"Probate OCS: searching letter='{letter}' {date_from} to {today}")
        html = _navigate_and_search(playwright_page, letter, date_from, today)
        cases = _parse_case_cards(html)
        new = sum(1 for c in cases if c["case_number"] not in seen)
        logger.info(f"  {len(cases)} result(s), {new} new after dedup")
        for c in cases:
            seen.setdefault(c["case_number"], c)

    result = list(seen.values())
    logger.info(f"Probate OCS: {len(result)} unique case(s) total")
    return result
