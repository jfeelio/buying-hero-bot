#!/usr/bin/env python3
"""
What did the LLC-bought properties have in common -- and what criteria pull a
list of ones that haven't sold yet?

Method is a case-control comparison:

    WON  = qualified arms-length LLC purchases, last 6 months
    BASE = all single-family parcels in the county
    lift = P(attribute | WON) / P(attribute | BASE)

Lift above 1 means investors bought that kind of house more often than its
share of the county would predict. That is a targeting criterion.

ONLY attributes that survive a closing are tested. Owner name, mailing address
and assessed value are all overwritten or reassessed at sale -- a sold property
looks 1.37x more absentee than the base population purely as an artifact, so
scoring those here would manufacture signal that isn't there. Physical
attributes, location and tenure are immune or recoverable.

    python profile.py

Reads  data/llc_purchases_enriched.json, data/snapshots/sfh_<today>.csv.gz
Writes output/criteria_lift.csv       every attribute bucket, ranked
       output/investor_paid_profile.csv   what investors actually paid
"""

import collections
import csv
import datetime
import glob
import gzip
import json
import math
import os
import re

ENRICHED = "data/llc_purchases_enriched.json"
MIN_CELL = 25          # below this a bucket is noise, same discipline as rank.py

QUALIFIED = ("Qual by exam", "Qual on DOS")

# Restrict to Buying Hero's operating range. Without this the WON set is
# dominated by a different business: 36% of qualified LLC purchases are over
# $1M, p90 is $3.4M, p95 is $7M -- luxury developers, teardown plays and
# foreign holding vehicles. Unfiltered, the top criteria come back as Miami
# Beach, Coconut Grove and Pinecrest, which is neither BH's market nor BH's
# capital. BH's own mail file offers run p10 $346k / median $421k / p90 $515k.
PRICE_MIN = float(os.environ.get("PRICE_MIN", 200_000))
PRICE_MAX = float(os.environ.get("PRICE_MAX", 600_000))

# Drop investor-to-investor trades. 23% of in-band purchases were bought FROM
# another entity, median seller tenure 0.3 years -- wholesalers and flippers
# reselling within months. Those are not doors a mailer to a homeowner can win,
# and they were single-handedly driving a spurious 2.14x lift on "held <3 yrs".
# Individual sellers have a median tenure of 6.1 years, which is the real market.
SELLER_ENTITY = re.compile(
    r"\b(LLC|L L C|INC|CORP|LP|LTD|HOLDINGS?|PROPERTIES"
    r"|CAPITAL|INVESTMENTS?|GROUP|REALTY|HOMES|TRUST|BANK)\b")


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), c + h)


def band(v, edges, labels):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    for e, lab in zip(edges, labels):
        if v < e:
            return lab
    return labels[-1]


YEAR_E = [1950, 1960, 1970, 1980, 1990, 2000, 9999]
YEAR_L = ["pre-1950", "1950s", "1960s", "1970s", "1980s", "1990s", "2000+"]
SQFT_E = [1000, 1400, 1800, 2400, 99999]
SQFT_L = ["under 1000 sf", "1000-1399 sf", "1400-1799 sf", "1800-2399 sf", "2400+ sf"]
LOT_E = [5000, 7500, 10000, 20000, 9999999]
LOT_L = ["lot <5k sf", "lot 5-7.5k", "lot 7.5-10k", "lot 10-20k", "lot 20k+"]
TEN_E = [3, 7, 12, 20, 999]
TEN_L = ["held <3 yrs", "held 3-7 yrs", "held 7-12 yrs", "held 12-20 yrs", "held 20+ yrs"]


def beds(v):
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return "1-2 bed" if n <= 2 else ("3 bed" if n == 3 else
                                     ("4 bed" if n == 4 else "5+ bed"))


def features(row: dict, tenure_years: float | None) -> list[str]:
    """Every bucket this property belongs to. Immune attributes only."""
    out = []
    for v, e, l in ((row.get("YEAR_BUILT"), YEAR_E, YEAR_L),
                    (row.get("BUILDING_HEATED_AREA"), SQFT_E, SQFT_L),
                    (row.get("LOT_SIZE"), LOT_E, LOT_L)):
        b = band(v, e, l)
        if b:
            out.append(b)
    b = beds(row.get("BEDROOM_COUNT"))
    if b:
        out.append(b)
    city = (row.get("TRUE_SITE_CITY") or "").strip().upper()
    if city:
        out.append(f"city: {city}")
    z = (row.get("TRUE_SITE_ZIP_CODE") or "").strip()[:5]
    if z:
        out.append(f"zip: {z}")
    if tenure_years is not None:
        b = band(tenure_years, TEN_E, TEN_L)
        if b:
            out.append(b)
    return out


def parse_date(v) -> datetime.date | None:
    """The two sources disagree on format and neither is ISO.

    MDPA SalesInfos gives "4/16/2026"; the parcel layer's DATEOFSALE_UTC is
    epoch milliseconds. Calling fromisoformat on either returns nothing, which
    silently dropped every tenure bucket on the first run.
    """
    if v in (None, ""):
        return None
    s = str(v).strip()
    if s.isdigit() and len(s) >= 10:            # epoch ms from ArcGIS
        try:
            return datetime.datetime.fromtimestamp(
                int(s) / 1000, datetime.timezone.utc).date()
        except (ValueError, OSError, OverflowError):
            return None
    if "/" in s:                                # M/D/YYYY from MDPA
        try:
            m, d, y = (int(p) for p in s.split("/")[:3])
            return datetime.date(y, m, d)
        except ValueError:
            return None
    try:
        return datetime.date.fromisoformat(s[:10])
    except ValueError:
        return None


def years_between(a, b) -> float | None:
    d1, d2 = parse_date(a), parse_date(b)
    if not d1 or not d2:
        return None
    return abs((d2 - d1).days) / 365.25


def main() -> None:
    snaps = sorted(glob.glob("data/snapshots/sfh_*.csv.gz"))
    snaps = [s for s in snaps if "fields-v1" not in s]
    if not snaps:
        raise SystemExit("no usable snapshot -- run snapshot.py first")
    snap_path = snaps[-1]

    won_recs = json.load(open(ENRICHED))
    won = {}
    for x in won_recs:
        if not str(x.get("qual", "")).startswith(QUALIFIED):
            continue
        try:
            price = float(x.get("PRICE_1") or 0)
        except (TypeError, ValueError):
            continue
        if not (PRICE_MIN <= price <= PRICE_MAX):
            continue
        if SELLER_ENTITY.search(x.get("grantor") or ""):
            continue
        won[x["FOLIO"]] = x
    print(f"enriched entity purchases: {len(won_recs):,}")
    print(f"  qualified, ${PRICE_MIN/1000:.0f}k-${PRICE_MAX/1000:.0f}k, "
          f"individual seller: {len(won):,}")
    print(f"base population:           {snap_path}")

    today = datetime.date.today().isoformat()
    base_ct = collections.Counter()
    won_ct = collections.Counter()
    n_base = n_won = 0
    paid = []

    with gzip.open(snap_path, "rt", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            folio = row["FOLIO"]
            w = won.get(folio)
            if w:
                # tenure the SELLER had, from the prior sale in the chain
                ten = years_between(w.get("prior_sale_date") or "",
                                    w.get("sale_date") or "")
                for f in features(row, ten):
                    won_ct[f] += 1
                n_won += 1
                try:
                    paid.append((float(w.get("PRICE_1") or 0),
                                 float(row.get("BUILDING_HEATED_AREA") or 0)))
                except ValueError:
                    pass
            else:
                # an unsold parcel's own last-sale date gives current tenure
                ten = years_between(row.get("DATEOFSALE_UTC") or "", today)
                for f in features(row, ten):
                    base_ct[f] += 1
                n_base += 1

    print(f"  base parcels: {n_base:,}   won parcels matched: {n_won:,}\n")

    rows = []
    for feat, wc in won_ct.items():
        bc = base_ct.get(feat, 0)
        if wc < MIN_CELL:
            continue
        p_won = wc / n_won
        p_base = bc / n_base if n_base else 0
        if not p_base:
            continue
        lift = p_won / p_base
        # is the won rate on this bucket distinguishable from the base rate?
        lo, hi = wilson(wc, wc + bc)
        base_share = n_won / (n_won + n_base)
        rows.append({
            "criterion": feat,
            "county_doors": bc + wc,
            "llc_purchases": wc,
            "pct_of_purchases": round(100 * p_won, 1),
            "pct_of_county": round(100 * p_base, 1),
            "lift": round(lift, 2),
            "doors_per_purchase": round((bc + wc) / wc, 0),
            "significant": "yes" if lo > base_share else
                           ("negative" if hi < base_share else "no"),
        })

    rows.sort(key=lambda r: -r["lift"])
    os.makedirs("output", exist_ok=True)
    with open("output/criteria_lift.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    if paid:
        prices = sorted(p for p, _ in paid if p > 1000)
        with open("output/investor_paid_profile.csv", "w", newline="",
                  encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["percentile", "price_paid"])
            for q in (10, 25, 50, 75, 90):
                w.writerow([f"p{q}", int(prices[int(len(prices)*q/100)])])

    sig = [r for r in rows if r["significant"] == "yes"]
    print(f"{'criterion':<26}{'county':>9}{'buys':>7}{'lift':>7}{'per buy':>9}")
    print("-" * 60)
    for r in sig[:20]:
        print(f"{r['criterion'][:25]:<26}{r['county_doors']:>9,}"
              f"{r['llc_purchases']:>7}{r['lift']:>7.2f}"
              f"{int(r['doors_per_purchase']):>9,}")
    print(f"\nwrote output/criteria_lift.csv ({len(rows)} buckets, "
          f"{len(sig)} significant)")
    if paid:
        print(f"wrote output/investor_paid_profile.csv  "
              f"median paid ${prices[len(prices)//2]:,.0f}")


if __name__ == "__main__":
    main()
