"""
Miami-Dade Property Appraiser (MDPA) API client.

Two-step lookup:
  1. GetAddress  -> returns Strap (folio with dashes, e.g. 02-3214-018-0010)
                    and Owner1 name
  2. GetPropertySearchByFolio -> returns MailingAddress + OwnerInfos

All calls require clientAppName=PropertySearch.
"""

import logging
import urllib.parse

import requests

logger = logging.getLogger(__name__)

BASE = "https://apps.miamidadepa.gov/PApublicServiceProxy/PaServicesProxy.ashx"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://apps.miamidadepa.gov/PropertySearch/",
}

EMPTY_RESULT = {
    "owner_first": "",
    "owner_last": "",
    "mailing_address": "",
    "mailing_city": "",
    "mailing_state": "",
    "mailing_zip": "",
}


def _parse_owner_name(raw: str) -> tuple[str, str]:
    """
    Parse MDPA OwnerInfos[0].Name field.
    Format: "FIRSTNAME [MIDDLE] LASTNAME [SUFFIX]"
    Legal suffixes (LE, TRS, EST OF, etc.) are stripped.
    Entity names (LLC, INC, &W, etc.) are kept whole in owner_last.
    Returns (owner_first, owner_last), all uppercase.
    """
    raw = raw.strip().upper()
    if not raw:
        return "", ""

    # Strip trailing legal suffixes
    SUFFIXES = (" EST OF", " EST", " TRS", " TR", " TRUSTEE", " LE")
    for suffix in SUFFIXES:
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)].strip()
            break

    # Entity / co-owner patterns — keep full name in owner_last
    ENTITY_KEYWORDS = ("LLC", "INC", "LTD", "CORP", "TRUST", "&W", "&H", "AND WIFE", "ET AL", "ET UX")
    for kw in ENTITY_KEYWORDS:
        if kw in raw:
            return "", raw

    parts = raw.split()
    if len(parts) == 1:
        return "", parts[0]
    # FIRSTNAME [MIDDLE ...] LASTNAME
    first = parts[0]
    last = parts[-1]
    return first, last


def _strap_to_folio(strap: str) -> str:
    """Convert '02-3214-018-0010' -> '0232140180010' (remove dashes)."""
    return strap.replace("-", "")


def _get_address(address: str, unit: str = "") -> dict | None:
    """
    Call GetAddress. Returns the first MinimumPropertyInfo dict on success.
    """
    try:
        resp = requests.get(
            BASE,
            params={
                "Operation": "GetAddress",
                "clientAppName": "PropertySearch",
                "myAddress": address,
                "myUnit": unit,
                "from": "1",
                "to": "200",
            },
            headers=HEADERS,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning(f"MDPA GetAddress failed for '{address}': {e}")
        return None

    infos = data.get("MinimumPropertyInfos") or []
    if not infos:
        return None
    return infos[0]


def _get_folio(folio_number: str) -> dict | None:
    """
    Call GetPropertySearchByFolio. Returns full response dict on success.
    folio_number: digits only, no dashes (e.g. '0232140180010').
    """
    try:
        resp = requests.get(
            BASE,
            params={
                "Operation": "GetPropertySearchByFolio",
                "clientAppName": "PropertySearch",
                "folioNumber": folio_number,
            },
            headers=HEADERS,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning(f"MDPA GetPropertySearchByFolio failed for folio '{folio_number}': {e}")
        return None

    if not data.get("Completed", True) and data.get("Message"):
        logger.warning(f"MDPA folio lookup error: {data.get('Message')}")
        return None

    return data


def get_property_by_owner_name(last_name: str, first_name: str = "") -> dict:
    """
    Look up Miami-Dade property by owner name (used for probate decedent lookups).

    Searches MDPA GetOwners with "LAST FIRST", scores matches by name overlap,
    and returns the best active match's property + mailing info.
    Returns EMPTY_RESULT if no usable match found.
    """
    if not last_name:
        return EMPTY_RESULT.copy()

    search_term = f"{last_name} {first_name}".strip().upper()

    try:
        resp = requests.get(
            BASE,
            params={
                "Operation": "GetOwners",
                "clientAppName": "PropertySearch",
                "ownerName": search_term,
                "from": "1",
                "to": "200",
            },
            headers=HEADERS,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning(f"MDPA GetOwners failed for '{search_term}': {e}")
        return EMPTY_RESULT.copy()

    infos = data.get("MinimumPropertyInfos") or []
    if not infos:
        logger.info(f"MDPA: no owner match for '{search_term}'")
        return EMPTY_RESULT.copy()

    # Filter out government/county-owned records
    active = [
        i for i in infos
        if "MIAMI-DADE" not in (i.get("Owner1") or "").upper()
        and "COUNTY" not in (i.get("Owner1") or "").upper()
        and "AC" in (i.get("Status") or "").upper()
    ] or infos

    # Score by name match quality — require whole-word last name match
    import re as _re
    ln_upper = last_name.upper()
    fn_upper = first_name.upper() if first_name else ""
    ln_pattern = _re.compile(r"\b" + _re.escape(ln_upper) + r"\b")

    def score(item):
        owner1 = (item.get("Owner1") or "").upper()
        s = 0
        if ln_pattern.search(owner1):
            s += 2
        if fn_upper and fn_upper in owner1:
            s += 1
        return s

    scored = [(score(i), i) for i in active]
    best_score, best = max(scored, key=lambda x: x[0])
    # Require at least a last-name word match; skip if no real match
    if best_score == 0:
        logger.info(f"MDPA: no word-boundary match for last name '{ln_upper}'")
        return EMPTY_RESULT.copy()
    strap = best.get("Strap", "")
    if not strap:
        return EMPTY_RESULT.copy()

    folio = _strap_to_folio(strap)
    site_address = (best.get("SiteAddress") or "").title()
    site_city = (best.get("Municipality") or "").title()
    logger.info(
        f"MDPA GetOwners: best match strap={strap} owner={best.get('Owner1')} "
        f"site={site_address}, {site_city} for '{search_term}'"
    )

    detail = _get_folio(folio)
    if not detail:
        return EMPTY_RESULT.copy()

    owner_infos = detail.get("OwnerInfos") or []
    owner_raw = owner_infos[0].get("Name", "") if owner_infos else ""
    first, last = _parse_owner_name(owner_raw)

    mail = detail.get("MailingAddress") or {}
    mailing_address = (mail.get("Address1") or "").strip()
    addr2 = (mail.get("Address2") or "").strip()
    if addr2:
        mailing_address += " " + addr2
    mailing_city = (mail.get("City") or "").strip()
    mailing_state = (mail.get("State") or "").strip() or "FL"
    mailing_zip = (mail.get("ZipCode") or "").strip()

    logger.info(
        f"MDPA GetOwners: success for '{search_term}' -> "
        f"{owner_raw} | {mailing_address}, {mailing_city}, {mailing_state} {mailing_zip}"
    )

    return {
        "owner_first": first,
        "owner_last": last,
        "mailing_address": mailing_address.upper(),
        "mailing_city": mailing_city.upper(),
        "mailing_state": mailing_state.upper(),
        "mailing_zip": mailing_zip,
        "property_address": site_address,
        "property_city": site_city,
        "property_state": "FL",
        "property_zip": mailing_zip if mailing_address.upper() == site_address.upper() else "",
    }


def get_owner_info_by_folio(parcel_id: str) -> dict:
    """
    Look up owner/mailing by parcel ID in strap format (e.g. '34-2104-005-1720').
    Skips the GetAddress step — goes directly to GetPropertySearchByFolio.
    Used for tax deed enrichment where the Parcel ID is already on the listing.
    """
    if not parcel_id:
        return EMPTY_RESULT.copy()

    folio = _strap_to_folio(parcel_id)
    logger.info(f"MDPA: folio lookup for parcel_id '{parcel_id}' -> folio '{folio}'")

    detail = _get_folio(folio)
    if not detail:
        logger.warning(f"MDPA: no result for folio '{folio}'")
        return EMPTY_RESULT.copy()

    owner_infos = detail.get("OwnerInfos") or []
    owner_raw = owner_infos[0].get("Name", "") if owner_infos else ""
    first, last = _parse_owner_name(owner_raw)

    mail = detail.get("MailingAddress") or {}
    mailing_address = (mail.get("Address1") or "").strip()
    addr2 = (mail.get("Address2") or "").strip()
    if addr2:
        mailing_address += " " + addr2
    mailing_city = (mail.get("City") or "").strip()
    mailing_state = (mail.get("State") or "").strip() or "FL"
    mailing_zip = (mail.get("ZipCode") or "").strip()

    logger.info(
        f"MDPA: folio success for '{parcel_id}' -> "
        f"{owner_raw} | {mailing_address}, {mailing_city}, {mailing_state} {mailing_zip}"
    )

    return {
        "owner_first": first,
        "owner_last": last,
        "mailing_address": mailing_address.upper(),
        "mailing_city": mailing_city.upper(),
        "mailing_state": mailing_state.upper(),
        "mailing_zip": mailing_zip,
    }


def get_owner_info(property_address: str, city: str = "", state: str = "FL") -> dict:
    """
    Returns owner and mailing info dict. Always returns a dict (empty strings on failure).
    """
    if not property_address:
        return EMPTY_RESULT.copy()

    # Build address query — include city if available for better matching
    address_query = property_address.strip()
    if city:
        address_query = f"{address_query}, {city}"

    # Step 1: GetAddress -> Strap
    address_info = _get_address(address_query)
    if not address_info:
        logger.warning(f"MDPA: no address match for '{property_address}'")
        return EMPTY_RESULT.copy()

    strap = address_info.get("Strap", "")
    owner1 = address_info.get("Owner1", "")

    if not strap:
        logger.warning(f"MDPA: no Strap in GetAddress response for '{property_address}'")
        return EMPTY_RESULT.copy()

    folio = _strap_to_folio(strap)
    logger.info(f"MDPA: found strap {strap} (folio {folio}) for '{property_address}'")

    # Step 2: GetPropertySearchByFolio -> MailingAddress + OwnerInfos
    detail = _get_folio(folio)
    if not detail:
        # Fall back to just the owner name from step 1
        first, last = _parse_owner_name(owner1)
        logger.info(f"MDPA: folio lookup failed, returning name only for '{property_address}'")
        return {
            "owner_first": first,
            "owner_last": last,
            "mailing_address": "",
            "mailing_city": "",
            "mailing_state": "",
            "mailing_zip": "",
        }

    # Extract owner name (prefer OwnerInfos[0].Name over GetAddress Owner1)
    owner_infos = detail.get("OwnerInfos") or []
    owner_raw = owner_infos[0].get("Name", owner1) if owner_infos else owner1
    first, last = _parse_owner_name(owner_raw)

    # Extract mailing address
    mail = detail.get("MailingAddress") or {}
    mailing_address = (mail.get("Address1") or "").strip()
    addr2 = (mail.get("Address2") or "").strip()
    if addr2:
        mailing_address += " " + addr2
    mailing_city = (mail.get("City") or "").strip()
    mailing_state = (mail.get("State") or "").strip() or "FL"
    mailing_zip = (mail.get("ZipCode") or "").strip()

    logger.info(f"MDPA: success for '{property_address}' -> {owner_raw} | {mailing_address}, {mailing_city}, {mailing_state} {mailing_zip}")

    return {
        "owner_first": first,
        "owner_last": last,
        "mailing_address": mailing_address.upper(),
        "mailing_city": mailing_city.upper(),
        "mailing_state": mailing_state.upper(),
        "mailing_zip": mailing_zip,
    }
