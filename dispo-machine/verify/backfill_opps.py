"""Create Buyer Interest opportunities that a blast failed to create.

    python backfill_opps.py --address "580 SE 6th St, Hialeah, FL 33010"
    python backfill_opps.py --address "..." --apply

The 2026-08-20 blast texted 166 buyers and created 126 opportunities: GHL
rate-limited the burst with "Try spacing your requests out" and the workflow
swallowed it. W2 now upserts at 3 per 2s, but a blast that already ran needs
its pipeline repaired.

Who should have one is not a guess: the engagement write-back stamps
buy_last_deal on exactly the buyers who were texted, so that is the roster.
"""
import argparse
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "import"))
import build_import as B  # noqa: E402

PIPELINE = "HyOMHkNNvhRllGNwMZsP"
REACHED_OUT = "f82b7dd3-e631-4338-81ce-2e1a9f9879ec"
OPP_DEAL_ADDRESS = "23Qr6cqR1IP1zFknf5Wn"
LAST_DEAL = "RPLXsO5CyYJtkuvxUnrH"          # buy_last_deal


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--address", required=True)
    ap.add_argument("--apply", action="store_true", help="actually create them")
    args = ap.parse_args()
    want = norm(args.address)

    # ---- who was texted: buy_last_deal is stamped by the send itself ----
    texted, after = {}, None
    while True:
        body = {"locationId": B.LOCATION, "pageLimit": 100,
                "filters": [{"field": "customFields." + LAST_DEAL,
                             "operator": "eq", "value": args.address}]}
        if after:
            body["searchAfter"] = after
        r = B.call("POST", "/contacts/search", body)
        page = r.get("contacts") or []
        if not page:
            break
        for c in page:
            texted[c["id"]] = ((c.get("firstName") or "") + " " + (c.get("lastName") or "")).strip()
        after = page[-1].get("searchAfter")
        if not after:
            break
    print("buyers texted on this deal      : %d" % len(texted))

    # ---- who already has an opportunity ----
    have, page = set(), 1
    while page <= 25:
        r = B.call("GET", "/opportunities/search?location_id=%s&pipeline_id=%s&limit=100&page=%d"
                   % (B.LOCATION, PIPELINE, page))
        batch = r.get("opportunities") or []
        if not batch:
            break
        for o in batch:
            cf = {c["id"]: c.get("fieldValueString", c.get("fieldValue"))
                  for c in (o.get("customFields") or [])}
            if norm(cf.get(OPP_DEAL_ADDRESS)) == want and o.get("contactId"):
                have.add(o["contactId"])
        if len(batch) < 100:
            break
        page += 1
    print("already have an opportunity     : %d" % len(have))

    missing = [(cid, name) for cid, name in texted.items() if cid not in have]
    print("MISSING                         : %d\n" % len(missing))
    if not missing:
        return 0

    for cid, name in missing[:10]:
        print("   %s" % (name or cid))
    if len(missing) > 10:
        print("   ... and %d more" % (len(missing) - 10))

    if not args.apply:
        print("\nreport only. re-run with --apply to create them.")
        return 0

    print("\ncreating, slowly enough not to be rate-limited again...")
    made = failed = 0
    for i, (cid, name) in enumerate(missing, 1):
        try:
            B.call("POST", "/opportunities/upsert", {
                "pipelineId": PIPELINE, "locationId": B.LOCATION,
                "name": (name or "Buyer") + " — " + args.address,
                "pipelineStageId": REACHED_OUT, "status": "open", "contactId": cid,
                "customFields": [{"id": OPP_DEAL_ADDRESS, "fieldValue": args.address}],
            })
            made += 1
        except Exception as e:                                   # noqa: BLE001
            failed += 1
            print("   FAILED %-24s %s" % ((name or cid)[:24], str(e)[-80:]))
        # The whole reason these are missing is a burst that was too fast.
        time.sleep(0.7)
        if i % 25 == 0:
            print("   ... %d/%d" % (i, len(missing)))

    print("\ncreated %d, failed %d" % (made, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
