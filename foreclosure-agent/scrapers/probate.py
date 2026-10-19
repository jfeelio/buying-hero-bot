"""
Scrapes new probate case filings (Formal + Summary Administration) from the
Miami-Dade Clerk's OCS (Online Case System) search API.

Strategy:
  - Logs in with the Clerk account first. Anonymous searches hit reCAPTCHA and
    come back empty or "Something Went Wrong".
  - Searches by FILING DATE + case type (OCS "File Date" search). Until Oct 2026 this
    looped a Party Name search over every letter a-z, but the Clerk's name search got
    slow enough that common prefixes ("a", "s", even "ma") hit its 30 s cutoff and came
    back empty, and the nightly run died at GitHub's 45-min limit with nothing saved.
    The date search returns every case of a type in ~0.3 s and needs no name at all.
  - The date search caps each answer at 200 cases, so it runs in 7-day windows (~50-90
    cases each) and splits any window that comes back full.
  - Case types: FORMAL ADMINISTRATION and SUMMARY ADMINISTRATION $1000 AND MORE.
    The other summary codes (25106, 25640) had zero filings in testing.
  - Keeps CLOSED cases. A summary case often closes within weeks, once the
    order hands title to the heirs, and those heirs are the best leads.
  - Date range: last N days (configurable). Deduplicates by local case number.

Returns per case:
  case_number, case_id, case_style, case_type, case_status, decedent_first,
  decedent_last, filing_date
"""

import logging
import os
import re
import time
from datetime import date, timedelta
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

LOGIN_PAGE = "https://www2.miamidadeclerk.gov/UserManagementServices/?hs=ocs"
LOGIN_POST = "https://www2.miamidadeclerk.gov/UserManagementServices/Home/LoginOrRegister"
OCS_API = "https://www2.miamidadeclerk.gov/ocs/api"

CASE_TYPES = {
    "25043": "FORMAL ADMINISTRATION",
    "25565": "SUMMARY ADMINISTRATION $1000 AND MORE",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
}


# ---------------------------------------------------------------------------
# Name parsing
# ---------------------------------------------------------------------------

def _parse_decedent_name(case_style: str) -> tuple[str, str]:
    """
    Extract (first, last) from OCS case style string.

    Formats seen:
      "IN RE: Alayon, Justina"              -> ("JUSTINA", "ALAYON")
      "In RE:DIMLER, DORIS DEETS"           -> ("DORIS DEETS", "DIMLER")
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
# Clerk session
# ---------------------------------------------------------------------------

def _clerk_credentials() -> tuple[str, str]:
    """CLERK_USERNAME / CLERK_PASSWORD env vars, else ~/.clerk_creds (line 1 user, line 2 password)."""
    user = os.environ.get("CLERK_USERNAME", "")
    pw = os.environ.get("CLERK_PASSWORD", "")
    if user and pw:
        return user, pw
    creds = Path.home() / ".clerk_creds"
    if creds.exists():
        lines = creds.read_text(encoding="utf-8").splitlines()
        if len(lines) >= 2:
            return lines[0].strip(), lines[1].strip()
    raise RuntimeError("Clerk credentials missing: set CLERK_USERNAME/CLERK_PASSWORD or ~/.clerk_creds")


def _login() -> requests.Session:
    user, pw = _clerk_credentials()
    s = requests.Session()
    s.headers.update(HEADERS)

    page = s.get(LOGIN_PAGE, timeout=30)
    page.raise_for_status()
    m = (re.search(r'name="ApplicationCallID"[^>]*value="([^"]*)"', page.text)
         or re.search(r'value="([^"]*)"[^>]*name="ApplicationCallID"', page.text))

    s.post(LOGIN_POST, timeout=30, data={
        "ApplicationCallID": m.group(1) if m else "",
        "userName": user,
        "password": pw,
        "btnCall": "Login",
        "ServicesType": "Individual",
    }).raise_for_status()

    s.get(f"{OCS_API}/home/UserLogin", timeout=30)
    info = s.get(f"{OCS_API}/settings/loggedin", params={"requestUserInfo": "true"}, timeout=30)
    if "true" not in info.text.lower():
        raise RuntimeError(f"Clerk OCS login failed: {info.text[:200]}")
    logger.info("Probate OCS: logged in to Clerk account")
    return s


RESULT_CAP = 200   # the OCS search returns at most this many cases per query
WINDOW_DAYS = 7


def _search_by_filed_date(s: requests.Session, case_type: str, date_from: date, date_to: date) -> list[dict]:
    """All cases of one type filed date_from..date_to (both inclusive)."""
    body = {
        "filingDateFrom": f"{date_from.isoformat()}T00:00:00.000Z",
        "filingDateTo": f"{date_to.isoformat()}T00:00:00.000Z",
        "caseType": case_type,
        "section": 0,
    }
    r = s.post(f"{OCS_API}/CaseInfo/PostSearchByFiledDate", json=body, timeout=60)
    r.raise_for_status()
    data = r.json()
    qs = data.get("qs") if isinstance(data, dict) else None
    if not qs:
        raise RuntimeError(f"Unexpected OCS search response: {str(data)[:200]}")
    # qs comes back already URL-encoded; pass it through as the browser does
    r = s.get(f"{OCS_API}/CaseInfo/GetMultipleCaseResult?qs={qs}", timeout=60)
    r.raise_for_status()
    return r.json().get("caseListResult") or []


def _search_window(s, case_type: str, date_from: date, date_to: date) -> list[dict]:
    """Search one window; if it comes back at the 200-case cap, split it so nothing is cut off."""
    rows = _search_by_filed_date(s, case_type, date_from, date_to)
    if len(rows) < RESULT_CAP:
        return rows
    if date_from >= date_to:
        logger.warning(f"Probate OCS: {date_from} alone returned {len(rows)} (the cap); some cases may be missing")
        return rows
    mid = date_from + timedelta(days=(date_to - date_from).days // 2)
    logger.info(f"Probate OCS: {date_from}..{date_to} hit the {RESULT_CAP} cap, splitting")
    return (_search_window(s, case_type, date_from, mid)
            + _search_window(s, case_type, mid + timedelta(days=1), date_to))


class IncompleteSearch(RuntimeError):
    """Some prefixes kept timing out; the cases found are still returned on .cases."""

    def __init__(self, missed: list, cases: list):
        super().__init__(f"Clerk search timed out for {len(missed)} name prefix(es): {', '.join(missed[:20])}")
        self.missed, self.cases = missed, cases


def get_new_probate_cases(days_back: int = 14) -> list[dict]:
    """
    Return deduplicated list of Formal + Summary Administration probate cases
    filed within the last `days_back` days.
    """
    today = date.today()
    date_from = today - timedelta(days=days_back)
    s = _login()
    seen: dict[str, dict] = {}

    for case_type, type_name in CASE_TYPES.items():
        before = len(seen)
        start = date_from
        while start <= today:
            end = min(start + timedelta(days=WINDOW_DAYS - 1), today)
            for c in _search_window(s, case_type, start, end):
                case_number = c.get("caseNumber", "")
                if not case_number or case_number in seen:
                    continue
                first, last = _parse_decedent_name(c.get("caseStyle", ""))
                seen[case_number] = {
                    "case_number": case_number,
                    "case_id": c.get("caseID"),
                    "case_style": c.get("caseStyle", ""),
                    "case_type": c.get("caseType", type_name),
                    "case_status": c.get("caseStatus", ""),
                    "decedent_first": first,
                    "decedent_last": last,
                    "filing_date": c.get("filingDate", ""),
                }
            start = end + timedelta(days=1)
            time.sleep(1)
        logger.info(f"Probate OCS: {type_name}: {len(seen) - before} case(s) {date_from} to {today}")

    result = list(seen.values())
    logger.info(f"Probate OCS: {len(result)} unique case(s) total")
    # Miami-Dade files ~80 Formal + Summary cases a week. Zero means the Clerk is down
    # or blocking us, not a quiet two weeks; fail loudly so the dashboard shows it.
    if not result and days_back >= 7:
        raise RuntimeError(f"OCS returned 0 cases for {days_back} days; Clerk site likely down")
    return result
