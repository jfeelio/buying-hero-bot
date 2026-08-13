"""Pokemon Sealed Investment Tracker — daily price refresh.

Phase 1: TCGCSV prices + curated set lifecycle.
Phase 2 (planned): eBay sold-listing comps.
"""
import logging
from datetime import datetime, timezone

from config import DEFAULT_MSRP, PREMIUM_TIER_SETS, WHOLESALE_PATTERNS
from lifecycle import load_lifecycle, months_since
from sheets_writer import apply_conditional_formatting, write_full_replace
from tcgcsv import fetch_groups, fetch_sealed_for_group

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _msrp_for(product_type: str, msrp_overrides: dict) -> float | None:
    if product_type in msrp_overrides:
        return msrp_overrides[product_type]
    return DEFAULT_MSRP.get(product_type)


def _premium_pct(price: float | None, msrp: float | None) -> float | None:
    if price is None or msrp is None or msrp <= 0:
        return None
    return (price / msrp - 1) * 100


def _format_premium(pct: float | None) -> str:
    return f"{pct:+.1f}%" if pct is not None else ""


def _is_wholesale(name: str) -> bool:
    lower = name.lower()
    return any(p in lower for p in WHOLESALE_PATTERNS)


def investment_score(
    status: str,
    months: int | None,
    premium_pct: float | None,
    product_type: str,
    set_code: str,
    is_wholesale: bool,
) -> int:
    """Transparent 0-100 score. See README/CLAUDE for rubric."""
    if is_wholesale:
        return 0  # not scored — separate "Wholesale" rating

    score = 0

    status_pts = {"Discontinued": 40, "Final Print Run": 25, "In Print": 15, "Upcoming": 5}
    score += status_pts.get(status, 0)

    # Months sweet spot: 12-30 months post-release (scarcity catalyst just hitting)
    if months is None or months < 0:
        score += 0
    elif 12 <= months <= 30:
        score += 20
    elif 6 <= months < 12 or 30 < months <= 48:
        score += 12
    elif months > 48:
        score += 8
    else:
        score += 3

    # Premium vs MSRP — context-dependent
    if premium_pct is None:
        score += 0
    elif status == "Discontinued":
        if premium_pct < 50:
            score += 20  # undervalued for OOP product
        elif premium_pct < 200:
            score += 18
        elif premium_pct < 400:
            score += 12
        elif premium_pct < 800:
            score += 6
        else:
            score += 0  # overheated
    else:
        # In-print: low premium is the win (buy at MSRP, sell at scarcity)
        if premium_pct < 0:
            score += 20
        elif premium_pct < 30:
            score += 15
        elif premium_pct < 100:
            score += 8
        else:
            score += 0

    type_pts = {
        "Booster Box": 10,
        "Booster Bundle": 7,
        "Elite Trainer Box": 6,
        "Ultra Premium Collection": 5,
        "Premium Collection": 4,
        "Special Collection": 3,
        "Tin": 2,
    }
    score += type_pts.get(product_type, 0)

    score += 10 if set_code in PREMIUM_TIER_SETS else 5

    return score


def rating(score: int, is_wholesale: bool, status: str) -> str:
    if is_wholesale:
        return "Wholesale"
    if status == "Upcoming":
        return "Pre-Release"
    if score >= 80:
        return "Strong Buy"
    if score >= 65:
        return "Buy"
    if score >= 45:
        return "Hold"
    return "Pass"


def build_rows() -> list[list]:
    lifecycle = load_lifecycle()
    tracked_ids = {int(gid) for gid in lifecycle}
    logger.info(f"Tracking {len(tracked_ids)} sets from lifecycle config")

    all_groups = fetch_groups()
    target_groups = [g for g in all_groups if g.get("groupId") in tracked_ids]
    logger.info(f"TCGCSV returned {len(all_groups)} groups; matched {len(target_groups)}")

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows: list[list] = []

    for group in target_groups:
        gid = group["groupId"]
        gname = group.get("name", "")
        life = lifecycle.get(str(gid), {})
        msrp_overrides = life.get("msrp", {})

        sealed = list(fetch_sealed_for_group(gid, gname))
        if not sealed:
            logger.info(f"No sealed products for {gname}")
            continue

        for s in sealed:
            mid = s.get("mid_price")
            low = s.get("low_price")
            msrp = _msrp_for(s["product_type"], msrp_overrides)
            # Score against TCGplayer Low (the buy floor) — that's what an investor pays
            premium_for_score = _premium_pct(low, msrp)
            # Display premium uses Mid (more stable, less noisy)
            display_premium = _premium_pct(mid, msrp)

            status = life.get("status", "Unknown")
            set_code = life.get("set_code", "")
            months = months_since(life.get("release_date"))
            wholesale = _is_wholesale(s["product_name"])

            score = investment_score(
                status, months, premium_for_score, s["product_type"], set_code, wholesale
            )
            rating_label = rating(score, wholesale, status)

            rows.append([
                life.get("name", gname),                    # A Set Name
                set_code,                                    # B Set Code
                life.get("reg_mark", ""),                    # C Reg Mark
                status,                                      # D Status
                rating_label,                                # E Investment Rating
                score if not wholesale else "",              # F Investment Score
                life.get("release_date", ""),                # G Release Date
                life.get("est_discontinuation", ""),         # H Est. Discontinuation
                months if months is not None else "",        # I Months Since Release
                s["product_type"],                           # J Product Type
                s["product_name"],                           # K Product Name
                mid if mid is not None else "",              # L TCGplayer Mid
                low if low is not None else "",              # M TCGplayer Low
                _format_premium(display_premium),            # N Premium vs MSRP
                msrp if msrp is not None else "",            # O MSRP
                "",                                          # P eBay Sold 30d Avg (Phase 2)
                "",                                          # Q eBay Sold 30d Count (Phase 2)
                "",                                          # R eBay Last Sold (Phase 2)
                s["url"],                                    # S TCGplayer URL
                now_iso,                                     # T Last Updated
            ])

    rating_order = {"Strong Buy": 0, "Buy": 1, "Hold": 2, "Pass": 3,
                    "Pre-Release": 4, "Wholesale": 5}
    rows.sort(key=lambda r: (
        rating_order.get(r[4], 99),
        -(r[5] if isinstance(r[5], int) else 0),  # score descending
        _neg_date_key(r[6]),                       # release date descending
        r[10],                                     # product name tiebreaker
    ))
    return rows


def _neg_date_key(date_str: str) -> int:
    """Return -YYYYMMDD so an ascending sort yields newest-first."""
    if not date_str:
        return 0
    try:
        return -int(date_str.replace("-", ""))
    except ValueError:
        return 0


def main() -> None:
    rows = build_rows()
    logger.info(f"Built {len(rows)} sealed product rows")
    if not rows:
        logger.warning("No rows to write — aborting")
        return
    write_full_replace(rows)
    apply_conditional_formatting()
    print(f"Pipeline complete. {len(rows)} row(s) written.")


if __name__ == "__main__":
    main()
