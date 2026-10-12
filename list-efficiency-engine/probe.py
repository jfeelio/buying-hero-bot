#!/usr/bin/env python3
"""
Verified Miami-Dade data-source probes for the List Efficiency Engine.

This is not the pipeline. It records the exact calls confirmed working on
2026-09-10 so Phase 0 does not have to rediscover them.

    python probe.py counts     # county-wide feasibility counts
    python probe.py folio <13-digit folio>   # full sales chain for one property
"""

import sys
import requests

# --- Property Point View: the whole parcel roll, free, no key -----------------
PAGIS = ("https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services"
         "/PaGISView_gdb/FeatureServer/0/query")

SFH = "DOR_DESC LIKE '%SINGLE FAMILY%'"          # DOR_CODE_CUR = '0101'
WINDOW_START = "2026-03-10"                       # 6 months back
ENTITY = ("(TRUE_OWNER1 LIKE '%LLC%' OR TRUE_OWNER1 LIKE '%INC%' "
          "OR TRUE_OWNER1 LIKE '%CORP%' OR TRUE_OWNER1 LIKE '%TRUST%' "
          "OR TRUE_OWNER1 LIKE '%HOLDING%' OR TRUE_OWNER1 LIKE '%PROPERTIES%')")


def count(where: str) -> int:
    r = requests.get(PAGIS, params={"where": where, "returnCountOnly": "true",
                                    "f": "json"}, timeout=60)
    r.raise_for_status()
    return r.json().get("count", 0)


def counts() -> None:
    sold = f"{SFH} AND DATEOFSALE_UTC >= DATE '{WINDOW_START}' AND PRICE_1 > 1000"
    rows = [
        ("all parcels in county", "1=1"),
        ("single-family parcels", SFH),
        (f"SFH sold since {WINDOW_START}", sold),
        ("  ...entity-name buyer", f"{sold} AND {ENTITY}"),
        ("  ...buyer mails elsewhere", f"{sold} AND TRUE_MAILING_ADDR1 <> TRUE_SITE_ADDR"),
        ("  ...owner out of state", f"{sold} AND TRUE_MAILING_STATE <> 'FL'"),
    ]
    for label, where in rows:
        print(f"{label:<32}{count(where):>9,}")


# --- MDPA folio API: full sales chain, grantor/grantee, homestead -------------
MDPA = "https://apps.miamidadepa.gov/PApublicServiceProxy/PaServicesProxy.ashx"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Referer": "https://apps.miamidadepa.gov/PropertySearch/",
}


def folio(folio_number: str) -> None:
    """PaGISView carries only the latest sale; this recovers the whole chain."""
    r = requests.get(MDPA, params={"Operation": "GetPropertySearchByFolio",
                                   "clientAppName": "PropertySearch",
                                   "folioNumber": folio_number},
                     headers=HEADERS, timeout=60)
    r.raise_for_status()
    d = r.json()

    site = (d.get("SiteAddress") or [{}])[0]
    print(f"{site.get('Address','?')}  {site.get('City','')} {site.get('Zip','')}")
    for o in d.get("OwnerInfos") or []:
        print(f"  owner: {o.get('Name')}")

    print("\n  sale date    price        buyer (grantee)             qualified")
    for s in d.get("SalesInfos") or []:
        print(f"  {str(s.get('DateOfSale'))[:10]:<12} "
              f"${s.get('SalePrice') or 0:>11,.0f}  "
              f"{(s.get('GranteeName1') or '')[:26]:<27} "
              f"{s.get('QualificationDescription') or ''}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "counts"
    if cmd == "counts":
        counts()
    elif cmd == "folio" and len(sys.argv) > 2:
        folio(sys.argv[2].replace("-", ""))
    else:
        print(__doc__)
        sys.exit(1)
