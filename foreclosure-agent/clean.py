"""
Formatting for every value that lands on a mail sheet, so the sheet and the
letters read clean:

  Property address  "12150 NE Miami Pl"        (letter body, title case)
  Property city     "North Miami" / "Miami"    (never "Unincorporated County")
  Mail address      "9251 SW 13TH STREET"      (envelope window, USPS caps, no periods)
  Person            "Sally Alayon", "Jeffrey McAlpine", "Gus Lanier III"
  Zip               five digits
"""

import re

from zip_city import ZIP_CITY

_DIRECTIONALS = r"\b(Ne|Nw|Se|Sw|N|S|E|W)\b"
_SUFFIXES = {"II", "III", "IV", "JR", "SR"}


def squeeze(value) -> str:
    """Collapse runs of spaces and drop stray edge punctuation ("DRIVE," -> "DRIVE")."""
    return " ".join(str(value or "").split()).strip(" ,;")


def zip5(value) -> str:
    m = re.match(r"\d{5}", squeeze(value))
    return m.group(0) if m else squeeze(value)


def property_street(value) -> str:
    """'12150 NE MIAMI PL' / '12150 Ne Miami Pl' -> '12150 NE Miami Pl'."""
    s = squeeze(value).replace(".", "").title()
    s = re.sub(_DIRECTIONALS, lambda m: m.group(1).upper(), s)
    s = re.sub(r"(\d)(St|Nd|Rd|Th)\b", lambda m: m.group(1) + m.group(2).lower(), s)
    return s


def city(value, zip_code="") -> str:
    """Title-case a city; replace 'Unincorporated County' or blank with the USPS city for the zip."""
    c = squeeze(value)
    if not c or c.lower().startswith("unincorporated"):
        c = ZIP_CITY.get(zip5(zip_code), c)
    return c.title()


def mail_street(value) -> str:
    """'9251 S.W. 13th Street,' -> '9251 SW 13TH STREET' (USPS style for the envelope)."""
    s = squeeze(value).upper().replace(".", "").replace(",", " ")
    return " ".join(s.split())


def mail_city(value) -> str:
    return " ".join(squeeze(value).upper().replace(".", "").split())


def person(value) -> str:
    """'ALAYON, SALLY' -> 'Sally Alayon'; fixes Mc and generational suffixes."""
    s = squeeze(value)
    if "," in s and not s.upper().startswith("ESTATE OF"):
        last, first = [p.strip() for p in s.split(",", 1)]
        s = f"{first} {last}"
    s = s.title()
    s = re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), s)
    s = " ".join(w.upper() if w.upper().rstrip(".") in _SUFFIXES - {"JR", "SR"} else w for w in s.split())
    return re.sub(r"^Estate Of\b", "Estate of", s)
