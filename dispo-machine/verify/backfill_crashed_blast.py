"""Repair a blast whose workflow died after sending but before writing anything.

    python backfill_crashed_blast.py --address "14440 Sw 145th Pl, Miami, FL 33186" --match "Country Walk"
    python backfill_crashed_blast.py --address "..." --match "..." --apply

On 2026-08-22 W2 texted ~150 buyers and was then killed mid-execution by an n8n
restart. The sends landed; nothing else did. No Buyer Interest opportunities, no
engagement write-back, no buy_last_deal. The console reported HTTP 502.

That combination is worse than a clean failure. With no opportunity for the new
deal, the reply handler falls back to each buyer's still-open opportunity on the
PREVIOUS deal and answers with the wrong property - which is exactly what
happened to two buyers before anyone noticed.

backfill_opps.py cannot repair this one: it builds its roster from buy_last_deal,
which is written by the very step that never ran. So the roster here comes from
the only record that survived - the messages GHL actually sent. That is also a
better source, because it is evidence of delivery rather than of intent.

Idempotent: a contact that already has an opportunity on this address is skipped,
so a partial run can simply be run again.
"""
import argparse
import datetime
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "import"))
import build_import as B  # noqa: E402

PIPELINE = "HyOMHkNNvhRllGNwMZsP"
OPP_DEAL_ADDRESS = "23Qr6cqR1IP1zFknf5Wn"
OPP_TIER = "9teeY5fWTPptnVygRVae"
OPP_SOURCE = "hJ06opXeHtm3nt072Wog"
OPP_SEGMENT = "hLc4zz9NtnpjwlCQERMV"

BUY_TIER = "6LvZFW4TVSaFYDx60Yaj"
BUY_SOURCE = "kmikehE2YPSxJILEMzmb"
BUY_IB_PROPERTY = "1U5el72JVQVwymjhJkxJ"
BUY_LAST_DEAL = "RPLXsO5CyYJtkuvxUnrH"
BUY_DEALS_SENT = "Bm5OguP73NrZtf05KoRH"
BUY_LAST_CONTACTED = "H7h5xLsf4fEK7RWmUPjE"
BUY_FROM_NUMBER = "bg8DOGK7FWRtlBtz5kIO"


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


def stage_ids():
    pipes = B.call("GET", "/opportunities/pipelines?locationId=%s" % B.LOCATION)["pipelines"]
    bi = [p for p in pipes if p["id"] == PIPELINE][0]
    out = {}
    for s in bi["stages"]:
        out[s["name"].strip().lower()] = s["id"]
    return out


def conversations():
    """Every conversation, paged the way GHL actually pages them."""
    seen, after, all_c = set(), None, []
    for _ in range(30):
        url = ("/conversations/search?locationId=%s&limit=100"
               "&sortBy=last_message_date&sort=desc" % B.LOCATION)
        if after:
            url += "&startAfterDate=%d" % after
        batch = B.call("GET", url).get("conversations") or []
        fresh = [c for c in batch if c.get("id") not in seen]
        if not fresh:
            break
        for c in fresh:
            seen.add(c["id"])
        all_c += fresh
        last = batch[-1].get("lastMessageDate")
        if not last or len(batch) < 100:
            break
        after = int(last)
    return all_c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--address", required=True, help="deal address, as it should read on the opportunity")
    ap.add_argument("--match", required=True, help="text unique to the teaser that went out")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    stages = stage_ids()
    reached_out = stages.get("reached out")
    info_sent = stages.get("info sent")
    if not reached_out:
        print("no 'Reached Out' stage found")
        return 1

    # ---- roster: who GHL actually sent the teaser to, on this date ----
    print("scanning conversations for outbound '%s' on %s ..." % (args.match, args.date))
    roster = {}
    convs = conversations()
    active = [c for c in convs if c.get("lastMessageDate")]
    for i, c in enumerate(active, 1):
        try:
            m = B.call("GET", "/conversations/%s/messages?limit=25" % c["id"])
        except Exception:                                          # noqa: BLE001
            continue
        msgs = (m.get("messages") or {}).get("messages") or []
        todays = [x for x in msgs if str(x.get("dateAdded"))[:10] == args.date]
        teaser = [x for x in todays
                  if x.get("direction") == "outbound" and args.match in str(x.get("body") or "")]
        if not teaser:
            continue
        first = sorted(teaser, key=lambda x: str(x.get("dateAdded")))[0]
        # did they already get the FULL post for this deal (manually or otherwise)?
        full = any(x.get("direction") == "outbound"
                   and norm(args.address)[:14] in norm(x.get("body"))
                   for x in todays)
        roster[c.get("contactId")] = {
            "name": c.get("contactName") or "",
            "from": first.get("from") or "",
            "status": first.get("status") or "",
            "at": first.get("dateAdded"),
            "full": full,
        }
        if i % 40 == 0:
            print("   ... %d/%d scanned, %d found" % (i, len(active), len(roster)))
    print("buyers texted: %d\n" % len(roster))
    if not roster:
        return 1

    # ---- which of them already have an opportunity on this deal ----
    existing, page = set(), 1
    while page <= 25:
        batch = B.call("GET", "/opportunities/search?location_id=%s&pipeline_id=%s&limit=100&page=%d"
                       % (B.LOCATION, PIPELINE, page)).get("opportunities") or []
        for o in batch:
            if norm(opp_cf(o, OPP_DEAL_ADDRESS)) == norm(args.address):
                existing.add(o.get("contactId"))
        if len(batch) < 100:
            break
        page += 1
    todo = [k for k in roster if k not in existing]
    print("already have an opportunity on this deal : %d" % (len(roster) - len(todo)))
    print("to create                                : %d\n" % len(todo))

    made = failed = stamped = blocked = already_stamped = 0
    segments = {}
    # Iterate the WHOLE roster, not just the buyers needing an opportunity.
    # Being texted and having an opportunity are different facts, and tying them
    # together already caused a miss: on 2026-08-22 five buyers had a previous
    # deal's opportunity manually re-pointed at this address, which made them
    # look "already handled", so they were skipped and kept a buy_last_deal
    # naming the wrong deal. The stamp is decided per contact, below.
    for i, cid in enumerate(roster, 1):
        r = roster[cid]
        try:
            c = B.call("GET", "/contacts/" + cid)["contact"]        # by id, never search
        except Exception as e:                                      # noqa: BLE001
            print("   could not read %s: %s" % (r["name"], str(e)[:50]))
            failed += 1
            continue

        tier = str(cf(c, BUY_TIER) or "").strip()
        src = cf(c, BUY_SOURCE) or []
        if not isinstance(src, list):
            src = [s.strip() for s in str(src).split(";") if s.strip()]
        on_master = any(s in ("BH Main", "Referral") for s in src)
        geo = norm(args.address)[:14] in norm(cf(c, BUY_IB_PROPERTY))
        segment = "Warm list" if on_master else ("InvestorBase Matched" if geo else "General cold")
        segments[segment] = segments.get(segment, 0) + 1

        stage = info_sent if (r["full"] and info_sent) else reached_out
        sent_n = cf(c, BUY_DEALS_SENT)
        try:
            sent_n = int(sent_n)
        except (TypeError, ValueError):
            sent_n = 0

        if not args.apply:
            continue

        # Stamp the contact FIRST, before the opportunity. They were texted - that
        # is a fact about the past, and it must not depend on whether GHL will
        # also accept an opportunity. The first run tied the two together and left
        # 133 buyers with no record of having received the deal at all.
        #
        # But stamp ONCE. buy_deals_sent is a counter, so a second run over the
        # same buyer would claim they were sent the deal twice. buy_last_deal
        # already naming this address is the marker that the stamp has happened.
        if str(cf(c, BUY_LAST_DEAL) or "").strip() == args.address:
            already_stamped += 1
            fields = None
        else:
            fields = [
                {"id": BUY_LAST_DEAL, "value": args.address},
                {"id": BUY_DEALS_SENT, "value": sent_n + 1},
                {"id": BUY_LAST_CONTACTED, "value": args.date},
            ]
            if r["from"]:
                fields.append({"id": BUY_FROM_NUMBER, "value": r["from"]})
        if fields:
            try:
                B.call("PUT", "/contacts/" + cid, {"customFields": fields})
                stamped += 1
            except Exception as e:                                  # noqa: BLE001
                print("   STAMP FAILED %-22s %s" % (r["name"][:22], str(e)[-60:]))
            time.sleep(0.7)

        # They already have an opportunity on this deal - stamped above, nothing
        # left to create.
        if cid in existing:
            continue
        try:
            B.call("POST", "/opportunities/", {
                "pipelineId": PIPELINE, "locationId": B.LOCATION,
                "pipelineStageId": stage, "contactId": cid, "status": "open",
                "name": (r["name"] or "Buyer") + " - " + args.address,
                "customFields": [
                    {"id": OPP_DEAL_ADDRESS, "fieldValue": args.address},
                    {"id": OPP_TIER, "fieldValue": tier if tier and tier != "(none)" else ""},
                    {"id": OPP_SOURCE, "fieldValue": "; ".join(src)},
                    {"id": OPP_SEGMENT, "fieldValue": segment},
                ]})
            made += 1
        except Exception as e:                                      # noqa: BLE001
            msg = str(e)
            # GHL allows ONE opportunity per contact per pipeline. A buyer who
            # still has an open opportunity on the previous deal cannot be given
            # one for this deal - the API rejects it outright. That is a fact
            # about GHL, not a failure of this run, so it is counted separately.
            if "OPPORTUNITY_NO_DUPLICATE" in msg:
                blocked += 1
            else:
                failed += 1
                print("   OPP FAILED %-24s %s" % (r["name"][:24], msg[-60:]))
            time.sleep(0.7)
            continue
        time.sleep(0.7)
        if i % 25 == 0:
            print("   ... %d/%d  (%d opps, %d stamped)" % (i, len(roster), made, stamped))

    print("\nsegments: %s" % segments)
    delivered = sum(1 for r in roster.values() if r["status"] in ("delivered", "sent", ""))
    print("send status: %d delivered/sent, %d other"
          % (delivered, len(roster) - delivered))
    froms = {}
    for r in roster.values():
        froms[r["from"]] = froms.get(r["from"], 0) + 1
    print("from-numbers used: %s" % froms)
    if not args.apply:
        print("\nreport only. re-run with --apply to write.")
    else:
        print("\ncreated %d opportunities, stamped %d contacts, %d failed" % (made, stamped, failed))
        if blocked:
            print(
                "\n%d blocked by OPPORTUNITY_NO_DUPLICATE.\n"
                "GHL permits ONE opportunity per contact per pipeline. These buyers\n"
                "still have an open opportunity on a previous deal in Buyer Interest,\n"
                "so they cannot also be tracked on this one. Close the previous deal's\n"
                "opportunities, or give each deal its own pipeline.\n"
                "Their contact records ARE stamped, so buy_last_deal still tells you\n"
                "which deal they were actually texted about." % blocked)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
