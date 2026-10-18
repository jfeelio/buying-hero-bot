"""
Scrapes new probate case filings (Formal + Summary Administration) from the
Miami-Dade Clerk's OCS (Online Case System) search API.

Strategy:
  - Logs in with the Clerk account first. Anonymous searches hit reCAPTCHA and
    come back empty or "Something Went Wrong".
  - Party Name search matches the START of any party's last name (decedent,
    petitioner, or attorney), so every letter a-z is searched.
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
import string
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

SEARCH_LETTERS = list(string.ascii_lowercase)

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


def _search(s: requests.Session, letter: str, case_type: str, date_from: date, date_to: date) -> list[dict]:
    body = {
        "searchBy": "personaName",
        "compareBy": "secondPartyPersonaName",
        "partyFirstName": "",
        "partyLastName": letter,
        "businessNameName": "",
        "partyType": 0,
        "partyFirstName2": "",
        "partyLastName2": "",
        "caseType": case_type,
        "filingDateFrom": f"{date_from.isoformat()}T00:00:00.000Z",
        "filingDateTo": f"{date_to.isoformat()}T00:00:00.000Z",
        "secondPartyBusinessName2": "",
        "section": 0,
    }
    r = s.post(f"{OCS_API}/CaseInfo/PostSearchByPartyName", json=body, timeout=60)
    r.raise_for_status()
    data = r.json()
    qs = data.get("qs") if isinstance(data, dict) else None
    if not qs:
        raise RuntimeError(f"Unexpected OCS search response: {str(data)[:200]}")

    # qs comes back already URL-encoded; pass it through as the browser does
    r = s.get(f"{OCS_API}/CaseInfo/GetMultipleCaseResult?qs={qs}", timeout=60)
    r.raise_for_status()
    return r.json().get("caseListResult") or []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# The Clerk gives up on a slow search after ~30 s and answers "0 results" with
# HTTP 200, which looks exactly like a real empty result.
#
# Why runs kept failing (Oct 2026): the old fallback retried a slow letter, then fanned
# it out into 26 two-letter prefixes, each retried too -- ~25-30 min for ONE slow letter.
# Any slow stretch pushed the job past GitHub's 45-min hard limit, GitHub killed it, and
# the partial-results path never ran, so a failed night saved 0 rows. Now:
#   * a timed-out search is split by DATE first (2 searches instead of 26), letters last;
#   * a search time budget stops early and hands back what was found so it gets written;
#   * a run of consecutive timeouts means the Clerk is degraded -> stop, don't grind.
SLOW_SECS = 25
SEARCH_BUDGET_SECS = int(float(os.environ.get("PROBATE_SEARCH_BUDGET_MIN", "22")) * 60)
MAX_SLOW_STREAK = int(os.environ.get("PROBATE_MAX_SLOW_STREAK", "8"))


class _Budget:
    """Shared stop conditions for one scrape: wall-clock deadline + consecutive-timeout streak."""

    def __init__(self, secs: float):
        self.deadline = time.time() + secs
        self.slow_streak = 0
        self.stop_reason = ""

    def note(self, slow: bool):
        self.slow_streak = self.slow_streak + 1 if slow else 0
        if self.slow_streak >= MAX_SLOW_STREAK and not self.stop_reason:
            self.stop_reason = f"Clerk degraded: {self.slow_streak} searches in a row timed out"
        if time.time() >= self.deadline and not self.stop_reason:
            self.stop_reason = f"search time budget ({SEARCH_BUDGET_SECS // 60} min) used up"


def _label(prefix, d_from, d_to):
    return f"{prefix}@{d_from:%m/%d}-{d_to:%m/%d}"


def _search_prefix(s, prefix: str, case_type: str, date_from: date, date_to: date,
                   budget: "_Budget") -> tuple[list, list]:
    """Search one name prefix over a date range. A timed-out (slow + empty) answer is
    retried by halving the date range (halves share the middle day; callers dedupe by case
    number) down to 2-day slices, and only a slow 2-day slice falls back to two-letter prefixes.
    Returns (cases, labels of prefix/date slices that still timed out)."""
    if budget.stop_reason:
        return [], [_label(prefix, date_from, date_to)]
    t0 = time.time()
    rows = _search(s, prefix, case_type, date_from, date_to)
    slow = not rows and time.time() - t0 >= SLOW_SECS
    budget.note(slow)
    if not slow:
        return rows, []
    logger.warning(f"Probate OCS: '{_label(prefix, date_from, date_to)}' timed out "
                   f"(empty after {time.time() - t0:.0f}s, streak {budget.slow_streak})")
    if budget.stop_reason:
        return [], [_label(prefix, date_from, date_to)]
    span = (date_to - date_from).days
    # Halve while the range is 3+ days. A 2-day range would "halve" into itself (the
    # halves share the middle day), and the Clerk's end-date semantics aren't verified,
    # so slices never go below 2 days -- from there, fall back to two-letter prefixes.
    if span >= 2:
        mid = date_from + timedelta(days=span // 2)
        r1, m1 = _search_prefix(s, prefix, case_type, date_from, mid, budget)
        r2, m2 = _search_prefix(s, prefix, case_type, mid, date_to, budget)
        return r1 + r2, m1 + m2
    if len(prefix) >= 2:
        return [], [_label(prefix, date_from, date_to)]
    rows, missed = [], []
    for ch in string.ascii_lowercase:
        r, m = _search_prefix(s, prefix + ch, case_type, date_from, date_to, budget)
        rows += r
        missed += m
    return rows, missed


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
    budget = _Budget(SEARCH_BUDGET_SECS)

    missed = []
    for case_type, type_name in CASE_TYPES.items():
        before = len(seen)
        for letter in SEARCH_LETTERS:
            found, still_missed = _search_prefix(s, letter, case_type, date_from, today, budget)
            missed += [f"{type_name[:6].strip()}:{m}" for m in still_missed]
            for c in found:
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
            time.sleep(1)
        logger.info(f"Probate OCS: {type_name}: {len(seen) - before} case(s) {date_from} to {today}")

    result = list(seen.values())
    logger.info(f"Probate OCS: {len(result)} unique case(s) total")
    if budget.stop_reason:
        logger.error(f"Probate OCS: stopped early - {budget.stop_reason}")
        missed.insert(0, budget.stop_reason)
        raise IncompleteSearch(missed, result)
    # Miami-Dade files ~80 Formal + Summary cases a week. Zero across every
    # search means the Clerk is down or blocking us, not a quiet two weeks;
    # fail loudly so the dashboard shows it instead of "success, 0 rows".
    if not result and days_back >= 7:
        raise RuntimeError(f"OCS returned 0 cases for {days_back} days across all searches; Clerk site likely down")
    if missed:
        # Hand back what was found so it still gets written; the caller fails the run after.
        raise IncompleteSearch(missed, result)
    return result
