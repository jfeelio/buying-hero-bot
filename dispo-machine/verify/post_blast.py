"""Verify a real blast, against live GHL, after it has gone out.

    python post_blast.py --address "580 SE 6th St, Hialeah, FL 33010"
    python post_blast.py --address "..." --exec 91      # a specific n8n run

The offline suite in ../console proves the LOGIC is right. This proves the
blast actually did what the logic says, to real buyers, in the real database.
They answer different questions and neither replaces the other.

Everything here reads contacts BY ID. GHL's search endpoints return a partial
custom-field projection, which twice made a perfectly good write look like a
failure - verifying against search would produce confident nonsense.
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "import"))
import build_import as B  # noqa: E402  (GHL client + field ids, already battle-tested)

PIPELINE_BUYER_INTEREST = "HyOMHkNNvhRllGNwMZsP"
OPP_DEAL_ADDRESS = "23Qr6cqR1IP1zFknf5Wn"
STAGES = {
    "f82b7dd3-e631-4338-81ce-2e1a9f9879ec": "Reached Out",
    "1e6e6101-700b-4474-95df-a9c37cd24143": "Info Sent",
    "43caef7f-607c-47cd-9961-f2fc9efd7c18": "Interested",
    "89d49335-8392-494b-8e92-11cbc0d1fb6e": "Walked",
    "0f51bb48-9d2c-4d5c-ba44-40bff1354bfb": "Offer",
    "6387bd07-be74-4b34-ac3b-5e27a0eeca30": "Contract Sent",
    "e6df0bba-2f07-4e1e-9135-e1500fbe72e1": "Closed",
    "d347ef6e-a269-4cf4-8a26-eba755429803": "Passed",
}

RELATIONSHIP_NUMBER = "+17868414589"
ROTATION = ["+17864345766", "+17867306407", "+19543292967"]
POOL = [RELATIONSHIP_NUMBER] + ROTATION
MAIN_LINE = "+17869827813"          # seller side - must never carry a buyer text

# gcloud is a .cmd shim on Windows, which subprocess cannot resolve without a
# shell, so the command is assembled as a string and run through one.
VM_SSH = 'gcloud compute ssh n8n-vm --zone=us-east1-b --command'


def vm(script):
    """Run a shell snippet on the n8n VM.

    The SQL contains double-quoted Postgres identifiers ("workflowId") and has
    to survive python -> shell -> gcloud -> ssh -> bash -> psql. Escaping it by
    hand through five layers is how you lose an afternoon, so it goes over
    base64 and is decoded once, on the far side.
    """
    import base64
    b64 = base64.b64encode(script.encode()).decode()
    # errors='replace': the execution blob carries emoji and smart quotes from
    # the teasers, and Windows' default cp1252 decode blows up on them.
    return subprocess.run(
        '%s "echo %s | base64 -d | bash"' % (VM_SSH, b64),
        shell=True, capture_output=True, timeout=180
    ).stdout.decode("utf-8", errors="replace")


# ───────────────────────────────────────────────────────────── reporting
class Report:
    def __init__(self):
        self.passed = 0
        self.failed = []
        self.notes = []

    def ok(self, cond, msg, detail=""):
        if cond:
            self.passed += 1
            print("  PASS  " + msg)
        else:
            self.failed.append(msg + (("  -> " + detail) if detail else ""))
            print("  FAIL  " + msg + (("\n        " + detail) if detail else ""))
        return bool(cond)

    def note(self, msg):
        self.notes.append(msg)
        print("  ....  " + msg)

    def section(self, title):
        print("\n" + title + "\n")


R = Report()


def norm_addr(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def field_map():
    defs = B.call("GET", "/locations/%s/customFields?model=contact" % B.LOCATION)["customFields"]
    return {f["id"]: f["name"] for f in defs}


def contact_fields(contact, names_by_id):
    out = {}
    for f in contact.get("customFields") or []:
        n = names_by_id.get(f["id"])
        if n:
            out[n] = f.get("value", f.get("fieldValue"))
    return out


def opp_field(o, fid):
    for c in o.get("customFields") or []:
        if c.get("id") == fid:
            for k in ("fieldValue", "fieldValueString", "value"):
                if c.get(k) is not None:
                    return str(c[k]).strip()
    return ""


# ───────────────────────────────────────────────────────── the n8n side
def blast_summary(exec_id=None):
    """What the workflow itself reported. None if the VM is unreachable."""
    try:
        if not exec_id:
            q = ("cd /opt/n8n && sudo docker compose exec -T postgres psql -U n8n -d n8n -tAc "
                 "\"select max(id) from execution_entity where \\\"workflowId\\\"='sendblast0001';\"")
            exec_id = vm(q).strip()
        if not str(exec_id).isdigit():
            return None
        q = ("cd /opt/n8n && sudo docker compose exec -T postgres psql -U n8n -d n8n -tAc "
             "\"select data from execution_data where \\\"executionId\\\"=%s;\"" % exec_id)
        raw = vm(q)
        arr = json.loads(raw[raw.find("["):raw.rindex("]") + 1])
        for v in arr:
            if isinstance(v, dict) and "queued" in v and "failed" in v:
                deref = lambda x: arr[int(x)] if isinstance(x, str) and x.isdigit() else x
                return {"execId": exec_id,
                        "queued": deref(v.get("queued")), "failed": deref(v.get("failed")),
                        "opportunities": deref(v.get("opportunities")),
                        "engagementWrites": deref(v.get("engagementWrites"))}
    except Exception as e:                                          # noqa: BLE001
        R.note("could not read the n8n execution log (%s)" % str(e)[:60])
    return None


# ───────────────────────────────────────────────────────────── the checks
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--address", required=True, help="the deal that was blasted")
    ap.add_argument("--exec", dest="exec_id", default=None, help="n8n execution id")
    args = ap.parse_args()
    want = norm_addr(args.address)

    print("\nPOST-BLAST VERIFICATION")
    print("deal: %s\n" % args.address)

    names_by_id = field_map()

    # ── 1. what the workflow said ──────────────────────────────────────
    R.section("1. What the blast reported")
    summary = blast_summary(args.exec_id)
    if summary:
        print("  n8n execution %s: queued=%s failed=%s opps=%s engagementWrites=%s"
              % (summary["execId"], summary["queued"], summary["failed"],
                 summary["opportunities"], summary["engagementWrites"]))
        R.ok(int(summary["failed"] or 0) == 0, "no sends failed",
             "%s failed - read failed_rows in the execution" % summary["failed"])
        R.ok(int(summary["queued"] or 0) > 0, "something was actually sent")
        R.ok(int(summary["opportunities"] or 0) == int(summary["queued"] or 0),
             "one opportunity per buyer texted",
             "queued=%s but opportunities=%s" % (summary["queued"], summary["opportunities"]))
        R.ok(int(summary["engagementWrites"] or 0) == int(summary["queued"] or 0),
             "engagement written for every buyer texted",
             "queued=%s but engagementWrites=%s" % (summary["queued"], summary["engagementWrites"]))
    else:
        R.note("no n8n summary - checking GHL state only")

    # ── 2. the opportunities ───────────────────────────────────────────
    R.section("2. Buyer Interest opportunities")
    res = B.call("GET", "/opportunities/search?location_id=%s&pipeline_id=%s&limit=100"
                 % (B.LOCATION, PIPELINE_BUYER_INTEREST))
    opps = [o for o in (res.get("opportunities") or [])
            if norm_addr(opp_field(o, OPP_DEAL_ADDRESS)) == want
            or want in norm_addr(o.get("name", ""))]
    R.ok(len(opps) > 0, "opportunities exist for this deal", "found none")
    if not opps:
        return finish()

    print("  %d opportunities for this deal" % len(opps))
    tagged = [o for o in opps if norm_addr(opp_field(o, OPP_DEAL_ADDRESS)) == want]
    R.ok(len(tagged) == len(opps), "every opportunity carries opp_deal_address",
         "%d of %d are missing it - the pipeline cannot be filtered by deal"
         % (len(opps) - len(tagged), len(opps)))

    by_stage = {}
    for o in opps:
        by_stage.setdefault(STAGES.get(o.get("pipelineStageId"), "?"), []).append(o)
    print("  stages: " + ", ".join("%s=%d" % (k, len(v)) for k, v in sorted(by_stage.items())))

    name_first = [o for o in opps if not norm_addr(o.get("name", "")).startswith(want)]
    R.ok(len(name_first) == len(opps), "cards lead with the buyer name, not the address")

    if summary and summary.get("queued"):
        R.ok(len(opps) == int(summary["queued"]), "opportunity count matches what was sent",
             "sent %s, found %d opportunities" % (summary["queued"], len(opps)))

    # ── 3. the contacts that were texted ───────────────────────────────
    R.section("3. What landed on the buyers")
    contact_ids = [o.get("contactId") for o in opps if o.get("contactId")]
    R.ok(len(contact_ids) == len(opps), "every opportunity is linked to a contact")

    buyers, bad_reads = [], 0
    for cid in contact_ids:
        try:
            c = B.call("GET", "/contacts/" + cid)["contact"]   # by id, never search
            buyers.append((c, contact_fields(c, names_by_id)))
        except Exception:                                      # noqa: BLE001
            bad_reads += 1
    R.ok(bad_reads == 0, "every contact reads back", "%d could not be fetched" % bad_reads)

    stamped = [b for b in buyers if str(b[1].get("buy_deals_sent") or "").strip() not in ("", "0")]
    R.ok(len(stamped) == len(buyers), "buy_deals_sent stamped on everyone texted",
         "%d of %d have no count" % (len(buyers) - len(stamped), len(buyers)))

    right_deal = [b for b in buyers if norm_addr(b[1].get("buy_last_deal")) == want]
    R.ok(len(right_deal) == len(buyers), "buy_last_deal is this address",
         "%d point somewhere else" % (len(buyers) - len(right_deal)))

    first = [b for b in buyers if b[1].get("buy_first_contacted")]
    R.ok(len(first) == len(buyers), "buy_first_contacted set",
         "%d missing" % (len(buyers) - len(first)))

    # The hook must be what the buyer READ, not the template.
    tokened = [b for b in buyers if "{{" in str(b[1].get("buy_last_hook") or "")]
    R.ok(not tokened, "buy_last_hook holds the personalised opener, not {{first_name}}",
         "%d still carry the raw token" % len(tokened))

    twice = [b for b in buyers if (b[1].get("buy_deals_sent") or 0) and int(b[1]["buy_deals_sent"]) > 1]
    if twice:
        R.note("%d buyers have buy_deals_sent > 1 - fine if they have had earlier deals, "
               "a problem if this was their first" % len(twice))

    # ── 4. sending numbers ─────────────────────────────────────────────
    R.section("4. Sending numbers")
    numbered = [b for b in buyers if b[1].get("buy_from_number")]
    if not numbered:
        # Any blast that ran before the sticky-number build has none of these.
        R.note("no buyer carries buy_from_number - this blast predates sticky numbers")
    else:
        R.ok(len(numbered) == len(buyers), "buy_from_number set on everyone texted",
             "%d of %d have none" % (len(buyers) - len(numbered), len(buyers)))

    off_pool = [b for b in numbered if b[1]["buy_from_number"] not in POOL]
    R.ok(not off_pool, "every number is one of the four buyer numbers",
         ", ".join(sorted({b[1]["buy_from_number"] for b in off_pool})))
    R.ok(not [b for b in numbered if b[1]["buy_from_number"] == MAIN_LINE],
         "the seller-side main line was never used")

    spread = {}
    wrong_rel = []
    for c, f in numbered:
        num = f["buy_from_number"]
        spread[num] = spread.get(num, 0) + 1
        types = f.get("buy_type") or []
        if isinstance(types, str):
            types = [t.strip() for t in types.split(";")]
        relationship = str(f.get("buy_tier") or "").upper() == "VIP" or "JV" in types
        if relationship and num != RELATIONSHIP_NUMBER:
            wrong_rel.append((c.get("firstName"), num))
        if not relationship and num == RELATIONSHIP_NUMBER:
            # Not a failure: a buyer promoted after their first text keeps their number.
            pass
    for num in sorted(spread):
        label = "relationship" if num == RELATIONSHIP_NUMBER else "rotation"
        print("  %-16s %3d  (%s)" % (num, spread[num], label))
    R.ok(not wrong_rel, "VIPs and JV partners are on the relationship number",
         ", ".join("%s on %s" % w for w in wrong_rel[:5]))

    # ── 5. who must NOT have been texted ───────────────────────────────
    R.section("5. Nobody who should have been silent")
    texted_ids = {c.get("id") for c, _ in buyers}
    F = B.FIELD
    for label, filt in (
        ("buy_status = DNC", [{"field": "customFields." + F["buy_status"], "operator": "eq", "value": "DNC"}]),
        ("buy_status = Blacklist", [{"field": "customFields." + F["buy_status"], "operator": "eq", "value": "Blacklist"}]),
    ):
        hits = B.call("POST", "/contacts/search",
                      {"locationId": B.LOCATION, "pageLimit": 100, "filters": filt}).get("contacts") or []
        overlap = [h for h in hits if h["id"] in texted_ids]
        R.ok(not overlap, "%s was not texted (%d on file)" % (label, len(hits)),
             ", ".join((h.get("firstName") or "?") + " " + (h.get("lastName") or "") for h in overlap))

    # A TEST record is only a problem when it rides along on a REAL blast. A run
    # that reached nothing but TEST records is a test send doing its job.
    test_hits = B.call("POST", "/contacts/search",
                       {"locationId": B.LOCATION, "pageLimit": 100,
                        "filters": [{"field": "customFields." + F["buy_type"],
                                     "operator": "eq", "value": "TEST"}]}).get("contacts") or []
    test_texted = [h for h in test_hits if h["id"] in texted_ids]
    if test_texted and len(test_texted) == len(buyers):
        R.note("this was a TEST SEND - only buy_type TEST was reached (%s). "
               "Nothing below about real buyers applies."
               % ", ".join((h.get("firstName") or "?") for h in test_texted))
    else:
        R.ok(not test_texted, "no TEST record rode along on a real blast",
             ", ".join((h.get("firstName") or "?") + " " + (h.get("lastName") or "")
                       for h in test_texted))

    dnd = [c for c, _ in buyers if c.get("dnd") is True]
    R.ok(not dnd, "no contact with DND on was texted", "%d were" % len(dnd))

    # ── 6. replies, if any yet ─────────────────────────────────────────
    R.section("6. Replies so far")
    replied = [(c, f) for c, f in buyers if f.get("buy_replies") and int(f["buy_replies"]) > 0]
    moved = [o for o in opps if STAGES.get(o.get("pipelineStageId")) != "Reached Out"]
    print("  %d of %d buyers have replied; %d opportunities have moved past Reached Out"
          % (len(replied), len(buyers), len(moved)))
    if not replied:
        R.note("no replies yet - re-run this once the first buyer answers")
    else:
        stamped_r = [b for b in replied if b[1].get("buy_last_responded")]
        R.ok(len(stamped_r) == len(replied), "buy_last_responded stamped on everyone who replied")
        # An InvestorLift buyer must never be auto-advanced - a human decides.
        il_moved = []
        for o in moved:
            f = next((f for c, f in buyers if c.get("id") == o.get("contactId")), {})
            src = f.get("buy_source") or []
            if isinstance(src, str):
                src = [s.strip() for s in src.split(";")]
            if "InvestorLift" in src and STAGES.get(o.get("pipelineStageId")) == "Info Sent":
                il_moved.append(o.get("name"))
        R.ok(not il_moved, "no InvestorLift buyer was auto-sent the full post",
             "; ".join(il_moved[:5]))

    return finish()


def finish():
    print("\n" + "-" * 62)
    if R.failed:
        print("%d PASSED, %d FAILED\n" % (R.passed, len(R.failed)))
        for f in R.failed:
            print("  FAIL  " + f)
        print()
        return 1
    print("ALL %d CHECKS PASSED" % R.passed)
    if R.notes:
        print("\nworth a look:")
        for n in R.notes:
            print("  - " + n)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
