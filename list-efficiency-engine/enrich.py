#!/usr/bin/env python3
"""
Enrich entity-bought sales with deed qualification and the prior-sale chain.

Two things the parcel layer cannot tell us, both essential:

  1. Whether the transfer was a real arms-length purchase. Of the first 178
     checked, 31% were government-agency foreclosure transfers, quitclaims or
     corrective deeds -- LLC names on deeds that are not purchases. A price
     floor does not catch them; only QualificationDescription does.

  2. What the property looked like BEFORE it sold. Closing overwrites owner
     and mailing address, but SalesInfos keeps the whole chain, so the prior
     sale date gives tenure-at-sale and GrantorName gives the seller.

    python enrich.py

Reads  data/sold_sfh_6mo.json
Writes data/llc_purchases_enriched.json   (resumable -- rerun to continue)
"""

import json
import os
import re
import sys
import time

import requests

SOLD = "data/sold_sfh_6mo.json"
OUT = "data/llc_purchases_enriched.json"

MDPA = "https://apps.miamidadepa.gov/PApublicServiceProxy/PaServicesProxy.ashx"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Referer": "https://apps.miamidadepa.gov/PropertySearch/",
}

# Business entities. Bank trustees (US BANK TRUST, BANK OF NEW YORK TRUST) are
# deliberately NOT here -- they showed up as foreclosure title transfers, not
# investor purchases, and the qualification filter drops them anyway.
ENTITY = re.compile(r"\b(LLC|L L C|INC|CORP|LP|LTD|HOLDINGS?|PROPERTIES"
                    r"|CAPITAL|INVESTMENTS?|GROUP|REALTY|HOMES)\b")


def fetch(folio: str) -> dict:
    r = requests.get(MDPA, params={"Operation": "GetPropertySearchByFolio",
                                   "clientAppName": "PropertySearch",
                                   "folioNumber": folio},
                     headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def main() -> None:
    sold = json.load(open(SOLD))
    targets = [r for r in sold if ENTITY.search(str(r.get("TRUE_OWNER1") or ""))]
    print(f"{len(sold):,} sales -> {len(targets):,} with an entity buyer")

    done = {}
    if os.path.exists(OUT):
        done = {x["FOLIO"]: x for x in json.load(open(OUT))}
        print(f"resuming: {len(done):,} already enriched")

    todo = [r for r in targets if r["FOLIO"] not in done]
    print(f"to fetch: {len(todo):,}\n")

    for i, rec in enumerate(todo):
        folio = rec["FOLIO"]
        try:
            d = fetch(folio)
            sales = d.get("SalesInfos") or []
            cur = sales[0] if sales else {}
            prior = sales[1] if len(sales) > 1 else {}
            benefit = d.get("Benefit") or {}
            exemptions = [b.get("Description", "")
                          for b in (benefit.get("BenefitInfos") or [])]
            done[folio] = {
                **rec,
                "qual": cur.get("QualificationDescription") or "",
                "grantee": cur.get("GranteeName1") or "",
                "grantor": cur.get("GrantorName1") or "",
                "instrument": cur.get("SaleInstrument") or "",
                "sale_date": str(cur.get("DateOfSale"))[:10],
                "prior_sale_date": str(prior.get("DateOfSale"))[:10] if prior else "",
                "prior_sale_price": prior.get("SalePrice") or 0,
                "n_sales_on_record": len(sales),
                "exemptions_now": "; ".join(e for e in exemptions if e),
            }
        except Exception as e:
            done[folio] = {**rec, "qual": "ERROR", "error": str(e)[:120],
                           "grantee": "", "grantor": "", "instrument": "",
                           "sale_date": "", "prior_sale_date": "",
                           "prior_sale_price": 0, "n_sales_on_record": 0,
                           "exemptions_now": ""}

        if (i + 1) % 100 == 0:
            json.dump(list(done.values()), open(OUT, "w"))
            print(f"  {i+1:,}/{len(todo):,}", flush=True)
        time.sleep(0.2)

    json.dump(list(done.values()), open(OUT, "w"))
    errs = sum(1 for x in done.values() if x["qual"] == "ERROR")
    print(f"\nwrote {OUT}  ({len(done):,} records, {errs} errors)")
    if errs:
        print("rerun to retry the errors")


if __name__ == "__main__":
    main()
