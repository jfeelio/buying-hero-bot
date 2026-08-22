"""Stamp buyer tier, source and segment onto existing Buyer Interest opportunities.

    python backfill_opp_buyer_fields.py --address "580 SE 6th St, Hialeah, FL 33010"
    python backfill_opp_buyer_fields.py --address "..." --apply

GHL's opportunity search cannot filter on a CONTACT's fields - only pipeline,
stage, status, assignee and one contactId. So "show me the VIPs on this deal"
is impossible unless the opportunity carries its own copy. W2 now stamps these
at send time; this fills in opportunities created before that.

Values are read from the contact as it stands today, which for a blast that
went out hours ago is the same thing. For an older deal it is a reconstruction,
not a record of what was true then - so it prints what it will write first.
"""
import argparse
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "import"))
import build_import as B  # noqa: E402

PIPELINE = "HyOMHkNNvhRllGNwMZsP"
F_ADDRESS = "23Qr6cqR1IP1zFknf5Wn"
F_TIER = "9teeY5fWTPptnVygRVae"
F_SOURCE = "hJ06opXeHtm3nt072Wog"
F_SEGMENT = "hLc4zz9NtnpjwlCQERMV"

BUY_TIER = B.FIELD["buy_tier"]
BUY_SOURCE = B.FIELD["buy_source"]
IB_PROPERTY = "1U5el72JVQVwymjhJkxJ"


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def cf(contact, fid):
    for c in contact.get("customFields") or []:
        if c.get("id") == fid:
            return c.get("value", c.get("fieldValue"))
    return None


def opp_cf(o, fid):
    for c in o.get("customFields") or []:
        if c.get("id") == fid:
            for k in ("fieldValue", "fieldValueString", "value"):
                if c.get(k) is not None:
                    return str(c[k]).strip()
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--address", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    want = norm(args.address)

    opps, page = [], 1
    while page <= 25:
        r = B.call("GET", "/opportunities/search?location_id=%s&pipeline_id=%s&limit=100&page=%d"
                   % (B.LOCATION, PIPELINE, page))
        batch = r.get("opportunities") or []
        if not batch:
            break
        opps += [o for o in batch if norm(opp_cf(o, F_ADDRESS)) == want]
        if len(batch) < 100:
            break
        page += 1
    print("opportunities on this deal: %d\n" % len(opps))

    todo = [o for o in opps if not opp_cf(o, F_TIER) and not opp_cf(o, F_SOURCE)]
    print("already stamped : %d" % (len(opps) - len(todo)))
    print("to backfill     : %d\n" % len(todo))
    if not todo:
        return 0

    done = failed = 0
    counts = {}
    for i, o in enumerate(todo, 1):
        cid = o.get("contactId")
        if not cid:
            continue
        try:
            c = B.call("GET", "/contacts/" + cid)["contact"]      # by id, never search
        except Exception as e:                                    # noqa: BLE001
            print("   could not read contact for %s: %s" % (o.get("name"), str(e)[:60]))
            failed += 1
            continue

        tier = str(cf(c, BUY_TIER) or "").strip()
        src = cf(c, BUY_SOURCE) or []
        if not isinstance(src, list):
            src = [s.strip() for s in str(src).split(";") if s.strip()]
        src_s = "; ".join(src)

        # Same rule the engines use, so the label matches what the review page showed.
        on_master = any(s in ("BH Main", "Referral") for s in src)
        pulled = str(cf(c, IB_PROPERTY) or "")
        geo = want in norm(pulled)
        segment = "Warm list" if on_master else ("InvestorBase Matched" if geo else "General cold")
        counts[segment] = counts.get(segment, 0) + 1

        if args.apply:
            try:
                B.call("PUT", "/opportunities/" + o["id"], {"customFields": [
                    {"id": F_TIER, "fieldValue": tier if tier and tier != "(none)" else ""},
                    {"id": F_SOURCE, "fieldValue": src_s},
                    {"id": F_SEGMENT, "fieldValue": segment},
                ]})
                done += 1
            except Exception as e:                                # noqa: BLE001
                failed += 1
                print("   FAILED %-26s %s" % (str(o.get("name"))[:26], str(e)[-70:]))
            time.sleep(0.7)          # these exist because a burst got rate-limited
            if i % 25 == 0:
                print("   ... %d/%d" % (i, len(todo)))

    print("\nsegments: %s" % counts)
    if not args.apply:
        print("\nreport only. re-run with --apply to write.")
    else:
        print("written %d, failed %d" % (done, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
