#!/usr/bin/env python3
"""
Turn the criteria into a mailable list.

Two steps:

  1. COMBO SEARCH -- single criteria are weak filters (a 1.8x lift on "pre-1950"
     still describes 48,000 houses). Intersections are where the real lift is,
     so test 2- and 3-way combinations of the significant criteria and keep the
     ones with both good lift and enough doors to actually mail.

  2. THE PULL -- apply the winning combo to all 387,591 parcels, then subtract
     what we cannot or should not mail:
        - mailed within EXCLUDE_DAYS (default 180)
        - already sold in the window (door is gone)
        - opted out ("wants to be taken off the list") -- never re-mail these

    python pull.py

Writes output/combo_lift.csv   combinations ranked
       output/target_list.csv  the doors to mail
"""

import collections
import csv
import datetime
import glob
import gzip
import itertools
import json
import math
import os
import re

ENRICHED = "data/llc_purchases_enriched.json"
MAIL = os.environ.get(
    "MAIL_JSON",
    r"C:\Users\jsive\AppData\Local\Temp\claude\D--Dropbox-J-Feels-Dev"
    r"\9db4d972-26f9-4a41-9ff5-135f6ffffc50\scratchpad\mail.json",
)
ZIPSNIPER = os.environ.get(
    "ZIPSNIPER_JSON",
    r"C:\Users\jsive\AppData\Local\Temp\claude\D--Dropbox-J-Feels-Dev"
    r"\9db4d972-26f9-4a41-9ff5-135f6ffffc50\scratchpad\zipsniper.json",
)

PRICE_MIN, PRICE_MAX = 200_000, 600_000
QUALIFIED = ("Qual by exam", "Qual on DOS")
SELLER_ENTITY = re.compile(
    r"\b(LLC|L L C|INC|CORP|LP|LTD|HOLDINGS?|PROPERTIES"
    r"|CAPITAL|INVESTMENTS?|GROUP|REALTY|HOMES|TRUST|BANK)\b")

MIN_COMBO_BUYS = 25          # a combo below this is noise
MIN_COMBO_DOORS = 2000       # a combo smaller than this is not worth a campaign
EXCLUDE_DAYS = int(os.environ.get("EXCLUDE_DAYS", 180))

# Criteria that survived the single-attribute test (profile.py, significant=yes)
CRITERIA = {
    "under 1000 sf":      lambda r: 0 < num(r["BUILDING_HEATED_AREA"]) < 1000,
    "1000-1399 sf":       lambda r: 1000 <= num(r["BUILDING_HEATED_AREA"]) < 1400,
    "1-2 bed":            lambda r: 0 < num(r["BEDROOM_COUNT"]) <= 2,
    "pre-1950":           lambda r: 0 < num(r["YEAR_BUILT"]) < 1950,
    "1950s":              lambda r: 1950 <= num(r["YEAR_BUILT"]) < 1960,
    "city: MIAMI GARDENS": lambda r: site_city(r) == "MIAMI GARDENS",
    "city: MIAMI":        lambda r: site_city(r) == "MIAMI",
    "lot 7.5-10k":        lambda r: 7500 <= num(r["LOT_SIZE"]) < 10000,
}


def num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def site_city(r: dict) -> str:
    return (r.get("TRUE_SITE_CITY") or "").strip().upper()


SUFFIX = {"STREET": "ST", "AVENUE": "AVE", "ROAD": "RD", "DRIVE": "DR",
          "TERRACE": "TER", "PLACE": "PL", "COURT": "CT", "LANE": "LN",
          "BOULEVARD": "BLVD", "CIRCLE": "CIR", "HIGHWAY": "HWY",
          "PARKWAY": "PKWY", "TRAIL": "TRL"}
ORDINAL = re.compile(r"\b(\d+)(ST|ND|RD|TH)\b")


def norm(addr) -> str:
    a = re.sub(r"[.,#]", " ", str(addr).upper())
    a = ORDINAL.sub(r"\1", a)
    return " ".join(SUFFIX.get(t, t) for t in a.split()).strip()


def parse_date(v):
    if v in (None, ""):
        return None
    s = str(v).strip()
    if s.isdigit() and len(s) >= 10:
        try:
            return datetime.datetime.fromtimestamp(
                int(s) / 1000, datetime.timezone.utc).date()
        except (ValueError, OSError, OverflowError):
            return None
    if "/" in s:
        try:
            m, d, y = (int(p) for p in s.split("/")[:3])
            return datetime.date(y, m, d)
        except ValueError:
            return None
    try:
        return datetime.date.fromisoformat(s[:10])
    except ValueError:
        return None


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), c + h)


def load_exclusions():
    """Doors we must not or need not mail."""
    today = datetime.date.today()
    cutoff = today - datetime.timedelta(days=EXCLUDE_DAYS)

    recently_mailed, all_mailed = set(), set()
    g = lambda r, i: str(r[i]).strip() if len(r) > i else ""
    for r in json.load(open(MAIL))[1:]:
        k = norm(g(r, 7))
        all_mailed.add(k)
        d = parse_date(g(r, 15)[:10]) or parse_date(g(r, 14)[:10])
        if d and d >= cutoff:
            recently_mailed.add(k)

    optout = set()
    try:
        zs = json.load(open(ZIPSNIPER))
        leads = zs.get("Leads", [])
        for row in leads[1:]:
            reason = str(row[11]).lower() if len(row) > 11 else ""
            addr = str(row[1]) if len(row) > 1 else ""
            if "taken off the list" in reason and addr.strip():
                # CRM addresses carry ", Miami, FL, 33147" tails; keep the street
                optout.add(norm(addr.split(",")[0]))
    except (OSError, ValueError, KeyError):
        pass

    sold = {norm(r["TRUE_SITE_ADDR"])
            for r in json.load(open("data/sold_sfh_6mo.json"))}

    return recently_mailed, all_mailed, optout, sold


def main() -> None:
    snaps = [s for s in sorted(glob.glob("data/snapshots/sfh_*.csv.gz"))
             if "fields-v1" not in s]
    if not snaps:
        raise SystemExit("no snapshot -- run snapshot.py first")

    won = set()
    for x in json.load(open(ENRICHED)):
        if (str(x.get("qual", "")).startswith(QUALIFIED)
                and PRICE_MIN <= num(x.get("PRICE_1")) <= PRICE_MAX
                and not SELLER_ENTITY.search(x.get("grantor") or "")):
            won.add(x["FOLIO"])

    # one pass: record which criteria each parcel satisfies
    parcels = []
    with gzip.open(snaps[-1], "rt", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            tags = frozenset(k for k, fn in CRITERIA.items() if fn(r))
            parcels.append((r["FOLIO"], tags, r))

    n_won = sum(1 for f, _, _ in parcels if f in won)
    n_all = len(parcels)
    base_rate = n_won / n_all
    print(f"wins: {n_won}   parcels: {n_all:,}   "
          f"baseline 1 per {n_all/n_won:,.0f} doors\n")

    combos = []
    keys = list(CRITERIA)
    for size in (1, 2, 3):
        for combo in itertools.combinations(keys, size):
            cs = set(combo)
            doors = buys = 0
            for folio, tags, _ in parcels:
                if cs <= tags:
                    doors += 1
                    if folio in won:
                        buys += 1
            if buys < MIN_COMBO_BUYS or doors < MIN_COMBO_DOORS:
                continue
            lo, _ = wilson(buys, doors)
            combos.append({
                "combo": " + ".join(combo),
                "n_criteria": size,
                "county_doors": doors,
                "llc_purchases": buys,
                "doors_per_purchase": round(doors / buys),
                "lift": round((buys / doors) / base_rate, 2),
                "beats_baseline": "yes" if lo > base_rate else "not proven",
            })

    combos.sort(key=lambda c: -c["lift"])
    os.makedirs("output", exist_ok=True)
    with open("output/combo_lift.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(combos[0].keys()))
        w.writeheader()
        w.writerows(combos)

    print(f"{'combo':<52}{'doors':>8}{'buys':>6}{'/buy':>7}{'lift':>7}")
    print("-" * 82)
    for c in combos[:12]:
        print(f"{c['combo'][:51]:<52}{c['county_doors']:>8,}"
              f"{c['llc_purchases']:>6}{c['doors_per_purchase']:>7,}"
              f"{c['lift']:>7.2f}")

    best = next((c for c in combos if c["beats_baseline"] == "yes"), combos[0])
    target = set(best["combo"].split(" + "))
    print(f"\nPULLING: {best['combo']}")

    recent, all_mailed, optout, sold = load_exclusions()
    print(f"  exclusions: mailed <{EXCLUDE_DAYS}d {len(recent):,} | "
          f"opted out {len(optout)} | sold {len(sold):,}")

    out, drop = [], collections.Counter()
    for folio, tags, r in parcels:
        if not target <= tags:
            continue
        k = norm(r["TRUE_SITE_ADDR"])
        if k in optout:
            drop["opted out"] += 1
            continue
        if k in sold:
            drop["already sold"] += 1
            continue
        if k in recent:
            drop[f"mailed <{EXCLUDE_DAYS}d"] += 1
            continue
        out.append({
            "folio": folio,
            "property_address": r["TRUE_SITE_ADDR"],
            "city": r["TRUE_SITE_CITY"],
            "zip": (r["TRUE_SITE_ZIP_CODE"] or "")[:5],
            "owner": r["TRUE_OWNER1"],
            "mailing_address": r["TRUE_MAILING_ADDR1"],
            "mailing_city": r["TRUE_MAILING_CITY"],
            "mailing_state": r["TRUE_MAILING_STATE"],
            "mailing_zip": r["TRUE_MAILING_ZIP_CODE"],
            "absentee": "yes" if norm(r["TRUE_MAILING_ADDR1"]) != k else "no",
            "year_built": r["YEAR_BUILT"],
            "heated_sqft": int(num(r["BUILDING_HEATED_AREA"])),
            "beds": r["BEDROOM_COUNT"],
            "baths": r["BATHROOM_COUNT"],
            "lot_sqft": int(num(r["LOT_SIZE"])),
            "assessed_value": int(num(r["ASSESSED_VAL_CUR"])),
            "last_sale_price": int(num(r["PRICE_1"])),
            "last_sale_date": (parse_date(r["DATEOFSALE_UTC"]) or ""),
            "previously_mailed": "yes" if k in all_mailed else "no",
        })

    out.sort(key=lambda r: (r["city"], r["property_address"]))
    with open("output/target_list.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    for k, v in drop.most_common():
        print(f"    -{v:,} {k}")
    fresh = sum(1 for r in out if r["previously_mailed"] == "no")
    print(f"\nwrote output/target_list.csv  ({len(out):,} doors, "
          f"{fresh:,} never mailed before)")


if __name__ == "__main__":
    main()
