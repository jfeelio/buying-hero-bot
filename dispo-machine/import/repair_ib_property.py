"""Collapse repeated addresses in buy_ib_property.

    python repair_ib_property.py            # report only
    python repair_ib_property.py --apply    # write the fixes

InvestorBase's Zap repeats the searched address once per row and joins them, so
the 77-buyer Hialeah pull wrote the same address 77 times into one 2,540-char
field on every contact. W12 now collapses this at write time; this repairs the
records already written.

It only ever SHORTENS a value, and only when the string is provably a single
unit repeated. Two genuinely different addresses are left alone - that field is
append-only and losing a real entry would cost a buyer their geo match.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_import as B  # noqa: E402

FIELD_ID = "1U5el72JVQVwymjhJkxJ"          # buy_ib_property
SEPS = [",", ", ", ";", "; ", "\n"]


def collapse(value):
    """Return the single repeated unit, or the value unchanged.

    Same algorithm as the workflow: pad with a candidate separator, then find
    the shortest unit the whole string is periodic on.
    """
    t = str(value or "").strip()
    if not t:
        return ""
    for sep in SEPS:
        padded = t + sep
        n = len(padded)
        for d in range(1, n // 2 + 1):
            if n % d:
                continue
            if all(padded[i] == padded[i - d] for i in range(d, n)):
                unit = padded[:d]
                if unit.endswith(sep):
                    return unit[: -len(sep)].strip()
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the fixes")
    args = ap.parse_args()

    ids, after = [], None
    while True:
        body = {"locationId": B.LOCATION, "pageLimit": 100,
                "filters": [{"field": "customFields." + FIELD_ID, "operator": "exists"}]}
        if after:
            body["searchAfter"] = after
        res = B.call("POST", "/contacts/search", body)
        page = res.get("contacts") or []
        if not page:
            break
        ids += [c["id"] for c in page]
        after = page[-1].get("searchAfter")
        if not after:
            break

    print("contacts with buy_ib_property: %d\n" % len(ids))

    fixed = clean = failed = 0
    for cid in ids:
        try:
            c = B.call("GET", "/contacts/" + cid)["contact"]   # by id: search truncates
        except Exception as e:                                 # noqa: BLE001
            print("  could not read %s: %s" % (cid, str(e)[:70]))
            failed += 1
            continue
        cur = ""
        for f in c.get("customFields") or []:
            if f["id"] == FIELD_ID:
                cur = str(f.get("value", f.get("fieldValue")) or "")
        new = collapse(cur)
        name = ((c.get("firstName") or "") + " " + (c.get("lastName") or "")).strip() or "(no name)"
        if new == cur:
            clean += 1
            continue
        print("  %-24s %5d -> %3d chars   %s" % (name[:24], len(cur), len(new), new[:44]))
        if args.apply:
            try:
                B.call("PUT", "/contacts/" + cid,
                       {"customFields": [{"id": FIELD_ID, "value": new}]})
                fixed += 1
            except Exception as e:                             # noqa: BLE001
                print("      WRITE FAILED: %s" % str(e)[:90])
                failed += 1

    print("\nalready clean: %d   needing repair: %d   written: %d   failed: %d"
          % (clean, len(ids) - clean - failed, fixed, failed))
    if not args.apply and len(ids) - clean:
        print("\nreport only. re-run with --apply to write.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
