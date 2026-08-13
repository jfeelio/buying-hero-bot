import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

_HERE = Path(__file__).resolve().parent

POKEMON_SHEET_ID = os.environ.get(
    "POKEMON_SHEET_ID",
    "1LChNV_Nu0sxArpzZrUDUhHQVdRQPumQ2jtgMbbf-_tE",
)
GOOGLE_CREDS_PATH = os.environ.get("GOOGLE_CREDS_PATH", str(_HERE / "credentials.json"))
SHEET_TAB_NAME = os.environ.get("POKEMON_SHEET_TAB_NAME", "Pokemon Sealed")

TCGCSV_BASE = "https://tcgcsv.com/tcgplayer"
POKEMON_CATEGORY_ID = 3

# Used when a per-set MSRP override isn't provided in set_lifecycle.json.
DEFAULT_MSRP = {
    "Booster Box": 143.64,
    "Elite Trainer Box": 49.99,
    "Ultra Premium Collection": 119.99,
    "Premium Collection": 39.99,
    "Booster Bundle": 26.94,
    "Special Collection": 19.99,
    "Tin": 21.99,
}

SHEET_COLUMNS = [
    "Set Name",            # A
    "Set Code",            # B
    "Reg Mark",            # C
    "Status",              # D
    "Investment Rating",   # E
    "Investment Score",    # F
    "Release Date",        # G
    "Est. Discontinuation",# H
    "Months Since Release",# I
    "Product Type",        # J
    "Product Name",        # K
    "TCGplayer Mid",       # L
    "TCGplayer Low",       # M
    "Premium vs MSRP",     # N
    "MSRP",                # O
    "eBay Sold 30d Avg",   # P
    "eBay Sold 30d Count", # Q
    "eBay Last Sold",      # R
    "TCGplayer URL",       # S
    "Last Updated",        # T
]

# Premium-tier sets — historically strongest sealed appreciators.
# Curated from community consensus (PWCC, Card Cavalcade, etc.).
PREMIUM_TIER_SETS = {
    "SWSH3.5",    # Champion's Path
    "SWSH4.5",    # Shining Fates
    "SWSH07",     # Evolving Skies (blue chip - Charizard alt art)
    "SWSH 25th",  # Celebrations (25th anniv)
    "SWSH09",     # Brilliant Stars (Charizard VStar)
    "SWSH11",     # Lost Origin (Giratina alt art)
    "SWSH12.5",   # Crown Zenith
    "SV03.5",     # 151 (anniv-tier)
    "SV04.5",     # Paldean Fates
    "SV06.5",     # Shrouded Fable
    "SV08.5",     # Prismatic Evolutions
}

# Substrings that mark a product as wholesale (case, set-of-N) rather than retail single.
WHOLESALE_PATTERNS = ["case", "set of", " display"]
