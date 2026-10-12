#!/usr/bin/env python3
"""
Rank Buying Hero's own mail lists by how often the doors on them get bought
by an investor -- using competitors' recorded closings as the outcome.

This is the Tiffany High "deals per list" backtest, but run against Buying
Hero's own mail footprint instead of the whole county. That matters because
the mail file records mailing address, list/campaign and date AS OF the mail
date -- the point-in-time snapshot the public roll overwrites at sale.

  numerator   = mailed properties an entity bought in the window (recorded sale)
  denominator = mailed properties on that list
  doors/deal  = denominator / numerator      (lower = more efficient)

Config per Jorge, 2026-09-10: entity-name buyers only, 6-month window,
Miami-Dade only, CSV output.

    python rank.py

Writes to output/:
    list_efficiency_ranking.csv   one row per segment, ranked
    missed_investor_buys.csv      the individual doors we mailed and lost
"""

import collections
import csv
import json
import math
import os
import re

WINDOW_START = "2026-03-10"          # 6 months back from 2026-09-10
SOLD = "data/sold_sfh_6mo.json"      # from probe/pull: PaGISView SFH sales
MAIL = os.environ.get(
    "MAIL_JSON",
    r"C:\Users\jsive\AppData\Local\Temp\claude\D--Dropbox-J-Feels-Dev"
    r"\9db4d972-26f9-4a41-9ff5-135f6ffffc50\scratchpad\mail.json",
)
MIN_DEALS = 10                       # below this a segment is context only

# --- address normalisation ---------------------------------------------------
# The county writes "NW 1 ST"; the mail vendor writes "NW 1ST ST". Strip the
# ordinal suffix and canonicalise street types so the two join.
SUFFIX = {"STREET": "ST", "AVENUE": "AVE", "ROAD": "RD", "DRIVE": "DR",
          "TERRACE": "TER", "PLACE": "PL", "COURT": "CT", "LANE": "LN",
          "BOULEVARD": "BLVD", "CIRCLE": "CIR", "HIGHWAY": "HWY",
          "PARKWAY": "PKWY", "TRAIL": "TRL"}
ORDINAL = re.compile(r"\b(\d+)(ST|ND|RD|TH)\b")


def norm(addr) -> str:
    a = re.sub(r"[.,#]", " ", str(addr).upper())
    a = ORDINAL.sub(r"\1", a)
    return " ".join(SUFFIX.get(t, t) for t in a.split()).strip()


# Entity buyer. Jorge chose entity-name matching over the wider
# "entity OR absentee-mailing" net, so individual investors buying in their
# own name are deliberately excluded.
ENTITY = re.compile(r"\b(LLC|INC|CORP|TRUST|HOLDING|PROPERTIES|LP|LTD"
                    r"|GROUP|CAPITAL|INVEST)\b")
LLC_ONLY = re.compile(r"\bLLC\b")     # strict variant, for a robustness check


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), centre + half)


def main() -> None:
    sold = json.load(open(SOLD))
    mail = json.load(open(MAIL))[1:]

    bought = {}
    for r in sold:
        owner = str(r.get("TRUE_OWNER1") or "")
        if ENTITY.search(owner):
            bought[norm(r["TRUE_SITE_ADDR"])] = r
    strict = {norm(r["TRUE_SITE_ADDR"]) for r in sold
              if LLC_ONLY.search(str(r.get("TRUE_OWNER1") or ""))}

    g = lambda r, i: str(r[i]).strip() if len(r) > i else ""
    props = collections.defaultdict(
        lambda: {"touches": 0, "camps": set(), "absentee": False,
                 "offer": 0.0, "city": "", "zip": "", "last": ""})
    for r in mail:
        k = norm(g(r, 7))
        p = props[k]
        p["touches"] += 1
        if g(r, 12):
            p["camps"].add(g(r, 12))
        if norm(g(r, 3)) != k:
            p["absentee"] = True
        p["city"], p["zip"] = g(r, 8), g(r, 10)
        p["last"] = max(p["last"], g(r, 15)[:10])
        try:
            p["offer"] = float(g(r, 11))
        except ValueError:
            pass

    total = len(props)
    hits = sum(1 for k in props if k in bought)
    baseline = hits / total

    def segment(label: str, keys: list[str]) -> dict | None:
        n = len(keys)
        if n == 0:
            return None
        k = sum(1 for x in keys if x in bought)
        ks = sum(1 for x in keys if x in strict)
        lo, hi = wilson(k, n)
        rate = k / n
        # A cut verdict stands on its own: if the whole interval sits below
        # baseline, few deals is the finding, not a reason to withhold it.
        # The MIN_DEALS gate only blocks *promotion* -- a great rate on a
        # thin list is what small samples produce by accident.
        if hi < baseline:
            prio = "cut - worse than baseline"
        elif k < MIN_DEALS:
            prio = "3 - too few deals to rank"
        elif lo > baseline and rate / baseline >= 2:
            prio = "1 - pull first"
        elif lo > baseline:
            prio = "2 - next wave"
        else:
            prio = "3 - not distinguishable"
        return {
            "segment": label, "doors_mailed": n, "investor_buys": k,
            "investor_buys_llc_only": ks,
            "doors_per_deal": round(n / k, 1) if k else "",
            "lift_vs_baseline": round(rate / baseline, 2),
            "ci_low_per_1k": round(lo * 1000, 2),
            "ci_high_per_1k": round(hi * 1000, 2),
            "beats_baseline": "yes" if lo > baseline else
                              ("no" if hi < baseline else "not distinguishable"),
            "priority": prio,
        }

    rows = [segment("ALL MAILED (baseline)", list(props))]
    rows.append(segment("absentee owner (per our mail file)",
                        [k for k, v in props.items() if v["absentee"]]))
    rows.append(segment("owner-occupied",
                        [k for k, v in props.items() if not v["absentee"]]))
    for c in sorted({c for v in props.values() for c in v["camps"]},
                    key=lambda x: int(x) if x.isdigit() else 0):
        name = " (Pre-foreclosure, 3 steps)" if c == "272" else ""
        rows.append(segment(f"campaign {c}{name}",
                            [k for k, v in props.items() if c in v["camps"]]))
    for lo_, hi_, lbl in [(0, 300000, "under $300k"), (300000, 400000, "$300-400k"),
                          (400000, 500000, "$400-500k"), (500000, 10**9, "$500k+")]:
        rows.append(segment(f"offer price {lbl}",
                            [k for k, v in props.items() if lo_ <= v["offer"] < hi_]))
    # combos: the intersections are where the real lift usually sits
    rows.append(segment("absentee + under $400k",
                        [k for k, v in props.items()
                         if v["absentee"] and v["offer"] < 400000]))
    rows.append(segment("absentee + campaign 272",
                        [k for k, v in props.items()
                         if v["absentee"] and "272" in v["camps"]]))

    rows = [r for r in rows if r]
    rank = {"1 - pull first": 0, "2 - next wave": 1,
            "cut - worse than baseline": 3}
    rows.sort(key=lambda r: (rank.get(r["priority"], 2),
                             -r["lift_vs_baseline"]))

    os.makedirs("output", exist_ok=True)
    with open("output/list_efficiency_ranking.csv", "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    misses = []
    for k, v in sorted(props.items()):
        if k not in bought:
            continue
        s = bought[k]
        misses.append({
            "property_address": s.get("TRUE_SITE_ADDR"),
            "folio": s.get("FOLIO"),
            "city": v["city"], "zip": v["zip"],
            "bought_by": s.get("TRUE_OWNER1"),
            "sale_price": int(s.get("PRICE_1") or 0),
            "our_offer_price": int(v["offer"] or 0),
            "our_touches": v["touches"],
            "our_campaigns": ", ".join(sorted(v["camps"])),
            "absentee": "yes" if v["absentee"] else "no",
            "last_mailed": v["last"],
            "year_built": s.get("YEAR_BUILT"),
            "heated_sqft": int(s.get("BUILDING_HEATED_AREA") or 0),
            "assessed_value": int(s.get("ASSESSED_VAL_CUR") or 0),
        })
    misses.sort(key=lambda r: -r["sale_price"])
    with open("output/missed_investor_buys.csv", "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(misses[0].keys()))
        w.writeheader()
        w.writerows(misses)

    print(f"baseline: {hits} entity purchases across {total:,} mailed doors "
          f"= 1 per {total/hits:,.0f}")
    print(f"wrote output/list_efficiency_ranking.csv  ({len(rows)} segments)")
    print(f"wrote output/missed_investor_buys.csv     ({len(misses)} doors lost)")


if __name__ == "__main__":
    main()
