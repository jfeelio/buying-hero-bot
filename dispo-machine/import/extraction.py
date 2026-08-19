"""Hand-reviewed buy-box extraction from the master sheet's prose notes.

Keyed by ROW NUMBER IN THE ORIGINAL 143-row `MAIN Dispo Tab` snapshot, which is
why `rekey.py` exists: on 2026-08-18 a buyer was inserted at row 109 and every
row below it shifted by one. Applying these keys to the live sheet directly
would hand 34 buyers the previous buyer's buy box. Never index this map against
a freshly-read sheet - go through `rekey.py`.

conf = how literal the note was:
  High   - buyer stated it outright ("Broward only", "max 315k")
  Medium - clear but inferred (buyer type from "active flipper")
  Low    - hedged in the source ("Might only buy in Broward")
Silence is never a guess: no note -> no criteria -> matches county-wide.
"""
import re

TREASURE = "St. Lucie; Martin; Indian River"

# Per-row extraction from the prose notes. Reviewed by hand against every
# non-empty note. conf = how literal the note was:
#   High   - buyer stated it outright ("Broward only", "max 315k")
#   Medium - clear but inferred (buyer type from "active flipper")
#   Low    - hedged in the source ("Might only buy in Broward")
# Silence is never a guess: no note -> no criteria, matches county-wide.
EXTRACT = {
    2:   dict(counties="St. Lucie", conf="Medium"),
    8:   dict(counties="Miami-Dade", hoods="Homestead", conf="High"),
    10:  dict(counties="Broward", conf="High"),
    11:  dict(counties="Broward", conf="High"),
    12:  dict(counties="Miami-Dade", hoods="Coral Gables; Pinecrest; Hialeah", conf="High"),
    14:  dict(pmin=1000000, types="SFR; Land", high_end="Yes", conf="High"),
    15:  dict(pmin=1000000, types="SFR; Land", high_end="Yes", conf="High"),
    16:  dict(counties="Miami-Dade", hoods="Coral Gables", conf="Low"),
    17:  dict(conf="High", note_flag="FIRST-LOOK: attorney, sees contracts. Only tier that may receive scarcity hooks."),
    18:  dict(rehab="Turnkey Only", conf="High"),
    19:  dict(btype="type:landlord", conf="Medium"),
    20:  dict(sqft_min=1800, conf="High", note_flag="Noted lowballer"),
    21:  dict(pmax=315000, conf="High"),
    23:  dict(btype="type:flipper", conf="Medium"),
    25:  dict(counties="Miami-Dade", btype="type:flipper", conf="High"),
    29:  dict(btype="type:flipper; type:realtor", conf="Medium"),
    31:  dict(counties="Miami-Dade", hoods="Homestead", btype="type:flipper; type:landlord", conf="Medium"),
    32:  dict(conf="Low", note_flag="Claims 'all of Florida' - unconfirmed, left blank"),
    33:  dict(counties="Broward; Miami-Dade", types="SFR", conf="High"),
    34:  dict(counties="Miami-Dade; Broward; Palm Beach", btype="type:realtor", conf="Medium"),
    35:  dict(btype="type:landlord", conf="Medium"),
    36:  dict(btype="type:flipper", conf="Medium"),
    37:  dict(counties="Miami-Dade", hoods="Homestead", conf="High"),
    39:  dict(counties="Miami-Dade; Broward", sqft_min=950, conf="High"),
    40:  dict(conf="Low"),
    41:  dict(conf="Low", note_flag="Not ready until May 2026"),
    42:  dict(counties="Miami-Dade; Broward; Hillsborough; Pinellas", btype="type:flipper; type:realtor", conf="Medium"),
    43:  dict(counties="Broward; Miami-Dade", pmax=600000, types="SFR; 2-4 Unit; 5+ Unit", conf="High"),
    45:  dict(types="SFR; 2-4 Unit", btype="type:landlord", conf="Medium"),
    46:  dict(high_end="Yes", btype="type:flipper", conf="High"),
    57:  dict(conf="Low"),
    60:  dict(counties="Broward", btype="type:jv; type:realtor", conf="Medium"),
    63:  dict(counties="Broward", conf="Low", note_flag="Source hedged ('might') - verify before relying on it"),
    69:  dict(counties="Miami-Dade", hoods="Pinecrest", btype="type:builder", conf="High"),
    70:  dict(counties="Miami-Dade", hoods="Coral Gables; Pinecrest; Hialeah", high_end="Yes", conf="High"),
    73:  dict(conf="High", dnc=True, note_flag="DO NOT CONTACT - explicit in source"),
    75:  dict(counties=TREASURE, btype="type:flipper", conf="High"),
    76:  dict(btype="type:builder", conf="High"),
    79:  dict(counties="St. Lucie", conf="High"),
    82:  dict(counties="Miami-Dade", conf="High"),
    83:  dict(counties="Miami-Dade", hoods="Liberty City", conf="High"),
    84:  dict(rehab="Medium", types="SFR; 2-4 Unit", btype="type:landlord", conf="High"),
    86:  dict(rehab="Full Gut", btype="type:flipper", conf="High"),
    87:  dict(btype="type:flipper", conf="Medium"),
    88:  dict(btype="type:realtor", conf="Medium"),
    102: dict(btype="type:jv", conf="High"),
    105: dict(counties="Miami-Dade", hoods="Hialeah", btype="type:jv", conf="High"),
    113: dict(counties=TREASURE, btype="type:flipper; type:builder", conf="High"),
    117: dict(sqft_min=1800, conf="High"),
    128: dict(counties="Miami-Dade", oos="Yes", btype="type:jv", conf="High"),
    129: dict(counties="St. Lucie", conf="High"),
    130: dict(counties="Palm Beach", conf="High"),
    131: dict(counties="St. Lucie", conf="High"),
    133: dict(btype="type:realtor", conf="Medium"),
    134: dict(btype="type:realtor", conf="Medium"),
    136: dict(counties="Miami-Dade", types="2-4 Unit", conf="Medium"),
    137: dict(counties="St. Lucie", btype="type:jv", conf="High"),
    138: dict(oos="Yes", btype="type:jv", conf="High"),
    139: dict(pmin=1000000, high_end="Yes", conf="High"),
    140: dict(types="SFR", sqft_min=2000, conf="High"),
    141: dict(counties="Miami-Dade; Broward", conf="High", note_flag="BANNED - misrepresents assignments"),
    142: dict(conf="High", note_flag="BANNED - Deal Fiends list"),
}

# 'Areas of Interest' column -> structured geography
AOI = {
    "treasure coast": (TREASURE, ""),
    "homestead": ("Miami-Dade", "Homestead"),
    "broward": ("Broward", ""),
    "miami dade": ("Miami-Dade", ""),
    "miami dade, broward": ("Miami-Dade; Broward", ""),
    "coral gables, pinecrest": ("Miami-Dade", "Coral Gables; Pinecrest"),
    "pinecrest, coral gables": ("Miami-Dade", "Coral Gables; Pinecrest"),
}

# Type column -> (tier, buy_type, source). The column conflated all three.
TYPE_MAP = {
    "Ultra VIP":      ("VIP", "",        "BH Main"),
    "Builder Buyers": ("",    "Builder", "BH Main"),
    "JV Partners":    ("",    "JV",      "BH Main"),
    "Realtor":        ("",    "Realtor", "BH Main"),
    "BANNED":         ("",    "",        "BH Main"),
    "InvestorLift":   ("",    "",        "InvestorLift"),
    "InvestorBase":   ("",    "",        "InvestorBase"),
}


def norm_phone(p):
    d = re.sub(r"\D", "", p or "")
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    return f"+1{d}" if len(d) == 10 else ""


def source_from_notes(notes, cur):
    """Notes often record provenance the Type column never got."""
    n = (notes or "").lower()
    if cur:
        return cur
    if "investorbase" in n or "investor base" in n:
        return "InvestorBase"
    if re.search(r"\bon il\b|found il|from il|investorlift", n):
        return "InvestorLift"
    return "BH Main"


TYPE_LABEL = {"jv": "JV"}


def clean_types(raw):
    """'type:flipper; type:realtor' -> 'Flipper; Realtor'"""
    out = []
    for t in (raw or "").split(";"):
        t = t.strip().removeprefix("type:")
        if t:
            out.append(TYPE_LABEL.get(t, t.capitalize()))
    return out


