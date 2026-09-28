"""Market classification for Buying Hero leads.

Buying Hero works Miami-Dade AND Broward. Copied from the appointment-snapshot
skill's pull_week.py -- if you add a city there, add it here too.
"""
import re

# --- market definition ------------------------------------------------------
# Buying Hero works Miami-Dade AND Broward. Palm Beach and anything further out
# is out-of-market and worth flagging before an appointment gets booked.
MIAMI_DADE = {
    "miami", "miami beach", "north miami", "north miami beach", "miami gardens",
    "miami lakes", "miami springs", "miami shores", "hialeah", "hialeah gardens",
    "homestead", "florida city", "opa locka", "opa-locka", "cutler bay",
    "coral gables", "doral", "aventura", "sunny isles beach", "key biscayne",
    "palmetto bay", "pinecrest", "south miami", "sweetwater", "west miami",
    "bal harbour", "bay harbor islands", "surfside", "golden beach",
    "kendall", "princeton", "goulds", "perrine", "richmond heights",
    "country club", "the hammocks", "tamiami", "westchester", "fontainebleau",
    "unincorporated county", "medley", "virginia gardens", "el portal",
    "biscayne park", "indian creek", "islandia", "naranja", "leisure city",
}
BROWARD = {
    "fort lauderdale", "ft lauderdale", "hollywood", "pembroke pines", "miramar",
    "coral springs", "davie", "plantation", "sunrise", "weston", "deerfield beach",
    "pompano beach", "lauderhill", "tamarac", "margate", "coconut creek",
    "oakland park", "hallandale", "hallandale beach", "dania beach", "dania",
    "cooper city", "parkland", "wilton manors", "lauderdale lakes",
    "north lauderdale", "southwest ranches", "lighthouse point", "hillsboro beach",
    "lauderdale by the sea", "west park", "pembroke park", "sea ranch lakes",
}


# Broward ZIPs that sit inside the Miami-Dade numeric band, so they have to be
# tested first. Everything else in 33010-33299 is Miami-Dade.
BROWARD_ZIPS = ({"33004", "33008", "33009", "33093", "33097", "33071"}
                | {str(z) for z in range(33019, 33030)}
                | {str(z) for z in range(33060, 33070)}
                | {str(z) for z in range(33073, 33077)}
                | {str(z) for z in range(33081, 33085)}
                | {str(z) for z in range(33301, 33389)})


# Every US state except Florida.
OTHER_STATES = "|".join("""al ak az ar ca co ct de ga hi id il in ia ks ky la me md ma mi mn ms mo mt
ne nv nh nj nm ny nc nd oh ok or pa ri sc sd tn tx ut vt va wa wv wi wy dc""".split())


def market_of(address, city=None):
    """Return (label, in_market) where label is Miami-Dade, Broward, Out of market
    or Unknown.

    Unknown means the address is too incomplete to place. That is a data-hygiene
    problem, NOT an out-of-market one -- keep the two apart, or incomplete records
    get reported as if Albert booked outside the market.
    """
    blob = " ".join(str(x or "") for x in (city, address)).lower()
    blob = re.sub(r"[,.]", " ", blob)

    # a non-Florida state settles it immediately
    # ("PA 19107", "PA USA 19107", or a bare trailing "dublin GA")
    tail = blob.strip()
    # A Florida ZIP (32xxx-34xxx) overrides a stray word that looks like a state.
    if (re.search(r"\b(%s)\b(\s+usa)?\s+(?!3[234])\d{5}" % OTHER_STATES, tail)
            or re.search(r"\s(%s)(\s+usa)?\s*$" % OTHER_STATES, tail)):
        return "Out of market", False

    # city name is the most reliable signal
    for name in sorted(MIAMI_DADE, key=len, reverse=True):
        if name in blob:
            return "Miami-Dade", True
    for name in sorted(BROWARD, key=len, reverse=True):
        if name in blob:
            return "Broward", True

    # fall back to ZIP -- Broward first, since its ZIPs interleave with Dade's
    for z in re.findall(r"\b(33\d{3})\b", blob):
        if z in BROWARD_ZIPS:
            return "Broward", True
        if "33010" <= z <= "33299":
            return "Miami-Dade", True
        return "Out of market", False

    if re.search(r"\bfl\b|\bflorida\b", blob):
        return "Out of market", False
    return "Unknown", False
