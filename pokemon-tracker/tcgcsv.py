"""TCGCSV client — fetch Pokemon sealed product prices.

TCGCSV (https://tcgcsv.com) is a free public mirror of TCGplayer's product
and price data. Refreshes ~daily. No auth required.

We pull groups (sets), products, and prices, then filter to sealed only.
"""
import logging
from typing import Iterable, Iterator

import requests

from config import TCGCSV_BASE, POKEMON_CATEGORY_ID

logger = logging.getLogger(__name__)

# Order matters: first match wins, so put the more specific product types first
# (e.g. "Ultra Premium Collection" before "Premium Collection").
SEALED_TYPE_PATTERNS: list[tuple[str, list[str]]] = [
    ("Ultra Premium Collection", ["ultra premium collection", "ultra-premium collection", "upc"]),
    ("Elite Trainer Box", ["elite trainer box", "etb"]),
    ("Premium Collection", ["premium collection"]),
    ("Booster Box", ["booster box", "booster display"]),
    ("Booster Bundle", ["booster bundle"]),
    ("Special Collection", ["special collection", "collection box", "collection"]),
    ("Tin", ["tin"]),
]

# Sealed-adjacent names we explicitly don't want (singles, supplies, half-products, etc.)
EXCLUDE_PATTERNS = [
    "single pack",
    "single booster",
    "code card",
    "promo card",
    "playmat",
    "sleeves",
    "deck box",
    "card sleeves",
    "binder",
    "portfolio",
    "loose pack",
    "blister pack",
    "half booster box",  # Costco retail variant — niche, distorts vs full-box MSRP
]


def _is_card(product: dict) -> bool:
    """Cards in TCGCSV have a 'Number' (card number) field in extendedData; sealed products don't."""
    for entry in product.get("extendedData") or []:
        if entry.get("name") == "Number":
            return True
    return False


def classify_product_type(name: str) -> str | None:
    """Return a product-type label, or None if not a sealed product we track."""
    lower = name.lower()
    for excl in EXCLUDE_PATTERNS:
        if excl in lower:
            return None
    for label, patterns in SEALED_TYPE_PATTERNS:
        for p in patterns:
            if p in lower:
                return label
    return None


_HEADERS = {
    "User-Agent": "buying-hero-pokemon-tracker/1.0 (+https://github.com/jfeelio/buying-hero-bot)",
    "Accept": "application/json",
}


def _get_json(url: str) -> list[dict]:
    r = requests.get(url, headers=_HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict):
        return data.get("results", [])
    return data


def fetch_groups() -> list[dict]:
    return _get_json(f"{TCGCSV_BASE}/{POKEMON_CATEGORY_ID}/groups")


def fetch_products(group_id: int) -> list[dict]:
    return _get_json(f"{TCGCSV_BASE}/{POKEMON_CATEGORY_ID}/{group_id}/products")


def fetch_prices(group_id: int) -> dict[int, dict]:
    """Return {productId: best_price_row} — collapses multi-subtype rows."""
    rows = _get_json(f"{TCGCSV_BASE}/{POKEMON_CATEGORY_ID}/{group_id}/prices")
    by_pid: dict[int, dict] = {}
    for p in rows:
        pid = p.get("productId")
        if pid is None:
            continue
        # Sealed products don't really have subtypes — first non-empty row is fine
        if pid not in by_pid:
            by_pid[pid] = p
    return by_pid


def fetch_sealed_for_group(group_id: int, group_name: str) -> Iterator[dict]:
    """Yield normalized sealed-product dicts (with prices merged) for one group."""
    try:
        products = fetch_products(group_id)
        prices = fetch_prices(group_id)
    except Exception as e:
        logger.warning(f"TCGCSV fetch failed for group {group_id} ({group_name}): {e}")
        return

    for prod in products:
        name = prod.get("name") or prod.get("cleanName") or ""
        if _is_card(prod):
            continue
        ptype = classify_product_type(name)
        if not ptype:
            continue
        pid = prod.get("productId")
        price = prices.get(pid, {}) if pid is not None else {}
        yield {
            "group_id": group_id,
            "group_name": group_name,
            "product_id": pid,
            "product_name": name,
            "product_type": ptype,
            "url": prod.get("url") or (f"https://www.tcgplayer.com/product/{pid}" if pid else ""),
            "mid_price": price.get("midPrice"),
            "low_price": price.get("lowPrice"),
            "market_price": price.get("marketPrice"),
        }
