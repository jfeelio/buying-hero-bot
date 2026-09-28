"""Turn a raw REsimpli pull into the weekly acquisitions metrics.

Everything the report shows is computed here, deterministically. The narrative
step only gets to *interpret* this dict -- it never invents a number.
"""
import collections
import datetime
import re
from zoneinfo import ZoneInfo

from market import market_of

ET = ZoneInfo("America/New_York")
DAY = 86400000

# Outcome enum -- bare integers in REsimpli with no lookup endpoint. Verified
# against lead outcomes (see appointment-snapshot skill). 0 is the undispositioned
# default, NOT "no answer" as the docs claim.
OUTCOME = {1: "Kept", 2: "Cancelled", 3: "No Show", 0: "No outcome", -1: "No outcome"}
FORMAT = {0: "In person", 1: "Phone"}

# Texts and emails sent from these accounts are auto-replies, drips and task
# reminders, not a person working the lead. Their CALLS still count.
AUTOMATION_SENDERS = {"Jorge Siverio"}
FOLLOW_UP_BUCKETS = ["Offers Made", "Albert Bucket", "Main Follow Up Bucket", "Discovery Done"]
FIRST_NAMES = {"Albert Puig": "Albert", "Luis Melan": "Luis", "Andrew A Paz": "Andrew",
               "Jorge Siverio": "Jorge", "Adrian Llamas": "Adrian"}


def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(s or ""))).strip()


def status_title(s):
    return re.sub(r"\s+", " ", (s or "").replace("☆", "")).strip()  # drops the "☆" marker


def person(name):
    return FIRST_NAMES.get(name, name if name and name != "N/A" else None)


def et(ms):
    return datetime.datetime.fromtimestamp(ms / 1000, ET)


def week_bounds(week_start):
    """week_start: date (a Monday). Returns ms bounds for this week and the prior one."""
    s = datetime.datetime.combine(week_start, datetime.time.min, ET)
    ws = int(s.timestamp() * 1000)
    return ws, ws + 7 * DAY, ws - 7 * DAY


def short_addr(a):
    if not a:
        return None
    parts = [p.strip() for p in a.split(",")]
    return ", ".join(parts[:2]) if len(parts) > 1 else parts[0]


def analyze(raw, week_start, now=None):
    ws, we, pws = week_bounds(week_start)
    now_ms = int((now or datetime.datetime.now(ET)).timestamp() * 1000)
    leads = {l["_id"]: l for l in raw["leads"]}
    scope_ids = set(raw["scope_status_ids"])
    in_scope = lambda lid: leads.get(lid, {}).get("mainStatusId") in scope_ids
    acts = raw["activities"]

    def rows_in(lid, a, b):
        return [r for r in acts.get(lid, []) if a <= (r.get("createdAt") or 0) < b]

    def lead_view(lid):
        l = leads.get(lid, {})
        mkt, inm = market_of(l.get("address"))
        src = l.get("marketingTitle") or ""
        return {"address": l.get("address"), "short": short_addr(l.get("address")),
                "status": status_title(l.get("mainStatusTitle")), "source": src,
                "market": mkt, "in_market": inm,
                # Mail goes to Miami-area properties, so an out-of-state address on a
                # mail lead is almost always the owner's mailing address typed in.
                "likely_mailing_address": mkt == "Out of market" and "ppc" not in src.lower()
                                          and any(w in src.lower() for w in ("mail", "absentee", "probate", "foreclosure"))}

    # ---------------------------------------------------------------- appointments
    def appts_between(a, b):
        return sorted([x for x in raw["appointments"]
                       if a <= (x.get("startDateTimeInTimeStamp") or 0) < b],
                      key=lambda x: x["startDateTimeInTimeStamp"])

    def appt_row(a):
        lid = a.get("subModuleId")
        wk = rows_in(lid, ws, we)
        changes = [(r["createdAt"], clean(r.get("comment"))) for r in wk
                   if re.search(r"changed lead status", r.get("comment") or "", re.I)]
        after = [c for c in sorted(changes) if c[0] >= a["startDateTimeInTimeStamp"]]
        nxt = None
        if after:
            t = after[-1][1]
            m = re.search(r" to (.+?)$", t)
            nxt = {"day": et(after[-1][0]).strftime("%a"), "to": (m.group(1) if m else t)[:90]}
        owner = (a.get("assignUserId") or [{}])[0]
        return {
            "when": et(a["startDateTimeInTimeStamp"]).strftime("%a %d %b, %H:%M"),
            "title": a.get("title"), "lead_id": lid,
            "format": FORMAT.get(a.get("appointmentSubType"), "Not set"),
            "outcome": OUTCOME.get(a.get("appointmentStatus"), "No outcome"),
            "occurred": a["startDateTimeInTimeStamp"] <= now_ms,
            "qualification_set": a.get("qualification") not in (-1, None),
            "owner": " ".join(filter(None, [owner.get("firstName"), owner.get("lastName")])),
            "calls": sum(1 for r in wk if r.get("direction") in ("outgoingCall", "incomingCall")),
            "activities": len(wk), "next": nxt, "lead": lead_view(lid),
            "created_this_week": ws <= (a.get("createdAt") or 0) < we,
        }

    appts = [appt_row(a) for a in appts_between(ws, we)]
    done = [a for a in appts if a["occurred"]]
    fmt = collections.defaultdict(lambda: collections.Counter())
    for a in appts:
        fmt[a["format"]]["booked"] += 1
        fmt[a["format"]][a["outcome"]] += 1
    created = [x for x in raw["appointments"] if ws <= (x.get("createdAt") or 0) < we]
    upcoming = [x for x in raw["appointments"] if (x.get("startDateTimeInTimeStamp") or 0) >= we]
    prev_appts = appts_between(pws, ws)

    # ---------------------------------------------------------------- offers
    def offers_between(a, b):
        out = {}
        for lid in acts:
            for r in rows_in(lid, a, b):
                c = clean(r.get("comment"))
                if re.search(r"offer created successfully|to (Active|Cold) Leads \(Offers? Made\)", c, re.I):
                    if lid not in out or r["createdAt"] < out[lid]["ms"]:
                        out[lid] = {"ms": r["createdAt"], "by": person(r.get("createdByName"))}
        rows = []
        for lid, o in sorted(out.items(), key=lambda x: x[1]["ms"]):
            v = lead_view(lid)
            rows.append({"when": et(o["ms"]).strftime("%a %d %b, %H:%M"), "by": o["by"], "lead_id": lid,
                         "from_appointment": any(a["lead_id"] == lid for a in appts), **v})
        return rows

    offers = offers_between(ws, we)
    prev_offers = offers_between(pws, ws)

    # ---------------------------------------------------------------- intake
    def new_between(a, b):
        return sorted([l for l in leads.values() if a <= (l.get("createdAt") or 0) < b],
                      key=lambda l: l["createdAt"])

    new = new_between(ws, we)
    by_source = collections.OrderedDict()
    for l in sorted(new, key=lambda l: l.get("marketingTitle") or ""):
        by_source.setdefault(l.get("marketingTitle") or "Unknown", []).append(status_title(l.get("mainStatusTitle")))
    by_source = sorted(({"source": k, "n": len(v), "statuses": collections.Counter(v).most_common()}
                        for k, v in by_source.items()), key=lambda x: -x["n"])

    method = collections.Counter()
    new_rows = []
    for l in new:
        lid = l["_id"]
        created_ms = l["createdAt"]
        after = sorted([r for r in acts.get(lid, []) if (r.get("createdAt") or 0) >= created_ms],
                       key=lambda r: r["createdAt"])
        how = None
        for r in after:
            m = re.search(r"New lead created (?:via )?(.+?) (?:from|in) ", clean(r.get("comment")))
            if m:
                how = {"openApi": "web form (PPC/API)", "manually": "hand entry"}.get(m.group(1), m.group(1))
                break
        swept = lid in acts or lid in raw.get("swept", [])
        dead = status_title(l.get("mainStatusTitle")) == "Dead Lead"
        method[how or ("not swept (Dead)" if dead else "unknown")] += 1
        calls_out = [r for r in after if r.get("direction") == "outgoingCall"]
        calls_in = [r for r in after if r.get("direction") == "incomingCall"]
        first = calls_out[0] if calls_out else None
        hours = round((first["createdAt"] - created_ms) / 3600000, 1) if first else None
        v = lead_view(lid)
        new_rows.append({
            "created": et(created_ms).strftime("%a %d %b, %H:%M"), "lead_id": lid, **v,
            "dead": dead, "how": how, "first_call_hours": hours,
            "first_call_by": person(first.get("createdByName")) if first else None,
            "inbound_calls": len(calls_in), "outbound_calls": len(calls_out),
            "arrived_late": created_ms >= we - 12 * 3600000,
            "still_new": v["status"] in ("New Leads",),
            "no_address": not l.get("address"),
        })

    buckets = [("Under 30 minutes", lambda h: h is not None and h < 0.5),
               ("Same day, under 3 hours", lambda h: h is not None and 0.5 <= h < 3),
               ("3 to 12 hours", lambda h: h is not None and 3 <= h < 12),
               ("Next day, 12 to 40 hours", lambda h: h is not None and 12 <= h < 40),
               ("Over 40 hours", lambda h: h is not None and h >= 40),
               ("No outbound call yet", lambda h: h is None)]
    speed = []
    for label, f in buckets:
        rs = [r for r in new_rows if f(r["first_call_hours"])]
        speed.append({"label": label, "n": len(rs),
                      "who": collections.Counter(r["first_call_by"] for r in rs if r["first_call_by"]).most_common()})

    def no_call_reason(r):
        if r["dead"]:
            return "Dead"
        if r["arrived_late"]:
            return "Arrived in the last 12 hours of the week"
        if r["market"] == "Out of market":
            return "Out of market"
        if not r["still_new"]:
            return "Worked live on the inbound call (status moved to %s)" % r["status"]
        return None

    no_call = [dict(r, reason=no_call_reason(r)) for r in new_rows if r["first_call_hours"] is None]
    real_misses = [r for r in no_call if r["reason"] is None]
    slow = [r for r in new_rows if r["first_call_hours"] is not None and r["first_call_hours"] >= 40]
    out_of_market_new = [r for r in new_rows if r["market"] == "Out of market"]
    ppc = [r for r in new_rows if "ppc" in (r["source"] or "").lower()]

    # ---------------------------------------------------------------- calls
    live_rows = [r for lid in acts if in_scope(lid) for r in rows_in(lid, ws, we)]
    prev_live_rows = [r for lid in acts if in_scope(lid) for r in rows_in(lid, pws, ws)]
    people = collections.defaultdict(lambda: {"out": 0, "leads": set(), "in": 0, "sms": 0, "auto_sms": 0})
    unrouted_in = 0
    days = collections.OrderedDict((d, {"out": 0, "in": 0}) for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
    for r in live_rows:
        d, who = r.get("direction"), r.get("createdByName")
        p = person(who)
        day = et(r["createdAt"]).strftime("%a")
        if d == "outgoingCall" and p:
            people[p]["out"] += 1
            people[p]["leads"].add(r.get("subModuleId"))
            days[day]["out"] += 1
        elif d == "incomingCall":
            days[day]["in"] += 1
            if p:
                people[p]["in"] += 1
            else:
                unrouted_in += 1
        elif d in ("outgoingSms", "outgoingEmail") and p:
            people[p]["auto_sms" if who in AUTOMATION_SENDERS else "sms"] += 1
    inbound = [r for r in live_rows if r.get("direction") == "incomingCall"]
    outbound = [r for r in live_rows if r.get("direction") == "outgoingCall"]
    missed = [r for r in inbound if r.get("voiceCallStatus") != "completed"]
    calls = {
        "people": sorted(({"name": k, "out": v["out"], "leads": len(v["leads"]), "in": v["in"],
                           "sms": v["sms"], "auto_sms": v["auto_sms"]} for k, v in people.items()),
                         key=lambda x: -(x["out"] + x["in"])),
        "unrouted_in": unrouted_in, "days": days,
        "outbound": len(outbound), "inbound": len(inbound),
        "inbound_missed": len(missed),
        "inbound_missed_breakdown": collections.Counter(r.get("voiceCallStatus") or "unknown" for r in missed).most_common(),
        "outcomes": collections.Counter((r.get("callOutcome") or {}).get("name") or "Blank" for r in outbound).most_common(),
        "sms_in": sum(1 for r in live_rows if r.get("direction") in ("incomingSms", "incomingMms")),
        "leads_touched": len({r.get("subModuleId") for r in live_rows}),
        "activities": len(live_rows),
        "prev_outbound": sum(1 for r in prev_live_rows if r.get("direction") == "outgoingCall"),
        "prev_out_by_person": dict(collections.Counter(
            person(r.get("createdByName")) for r in prev_live_rows
            if r.get("direction") == "outgoingCall" and person(r.get("createdByName")))),
        "prev_inbound": sum(1 for r in prev_live_rows if r.get("direction") == "incomingCall"),
    }
    other_outcomes = dict(calls["outcomes"]).get("Other", 0)

    # ---------------------------------------------------------------- follow-up
    def human_touch(lid):
        return any(r.get("direction") == "outgoingCall" and person(r.get("createdByName"))
                   or (r.get("direction") in ("outgoingSms", "outgoingEmail")
                       and person(r.get("createdByName")) and r.get("createdByName") not in AUTOMATION_SENDERS)
                   for r in rows_in(lid, ws, we))

    followup = []
    for b in FOLLOW_UP_BUCKETS:
        ids = [lid for lid, l in leads.items() if status_title(l.get("mainStatusTitle")) == b and in_scope(lid)]
        t = sum(1 for lid in ids if human_touch(lid))
        followup.append({"bucket": b, "leads": len(ids), "touched": t})

    # ---------------------------------------------------------------- status moves
    moves = collections.Counter()
    for r in live_rows:
        c = clean(r.get("comment"))
        m = re.search(r"Changed Lead status from .+? to (.+?)(?:\s{2,}|$)", c)
        if m:
            moves[status_title(re.sub(r"^(Active|Cold) Leads \((.+)\)$", r"\1: \2", m.group(1).strip()))] += 1

    # ---------------------------------------------------------------- hygiene
    appt_set_leads = {lid for lid in acts if in_scope(lid) for r in rows_in(lid, ws, we)
                      if (r.get("callOutcome") or {}).get("name") == "Appt Set"}
    appt_on_cal = {x.get("subModuleId") for x in raw["appointments"]
                   if (x.get("createdAt") or 0) >= ws - DAY}
    appt_set_missing = [lead_view(lid) | {"lead_id": lid} for lid in sorted(appt_set_leads - appt_on_cal)]
    offers_bad_addr = [o for o in offers if o["market"] != "Miami-Dade" and o["market"] != "Broward"]

    hygiene = [
        {"gap": "Appointment outcome blank", "n": sum(1 for a in done if a["outcome"] == "No outcome"), "of": len(done),
         "detail": ", ".join(a["title"] or "?" for a in done if a["outcome"] == "No outcome"), "hides": "Kept rate"},
        {"gap": "Qualification not set", "n": sum(1 for a in done if not a["qualification_set"]), "of": len(done),
         "detail": ", ".join(a["title"] or "?" for a in done if not a["qualification_set"]), "hides": "Lead-to-qualified rate"},
        {"gap": "Appointment format blank", "n": sum(1 for a in appts if a["format"] == "Not set"), "of": len(appts),
         "detail": ", ".join(a["title"] or "?" for a in appts if a["format"] == "Not set"), "hides": "Phone vs in-person"},
        {"gap": "“Appt Set” logged, nothing on calendar", "n": len(appt_set_missing), "of": None,
         "detail": "; ".join(x["short"] or "no address" for x in appt_set_missing), "hides": "The appointment count"},
        {"gap": "Call outcome logged as “Other”", "n": other_outcomes, "of": len(outbound),
         "detail": "", "hides": "What the call achieved"},
        {"gap": "New lead with no address", "n": sum(1 for r in new_rows if r["no_address"]), "of": len(new_rows),
         "detail": "", "hides": "Market mix and underwriting"},
        {"gap": "New lead still at “New Leads”", "n": sum(1 for r in new_rows if r["still_new"]), "of": len(new_rows),
         "detail": "%d arrived in the last 12 hours" % sum(1 for r in new_rows if r["still_new"] and r["arrived_late"]),
         "hides": "Lead-to-discovery rate"},
        {"gap": "Offer on an address outside Miami-Dade/Broward", "n": len(offers_bad_addr), "of": len(offers),
         "detail": "; ".join(o["short"] or "no address" for o in offers_bad_addr), "hides": "Which property is under offer"},
        {"gap": "Inbound calls with no rep attached", "n": unrouted_in, "of": len(inbound),
         "detail": "Logged as N/A", "hides": "Who answers the phone"},
    ]

    out_of_market_appts = [a for a in appts if a["lead"]["market"] == "Out of market"]

    return {
        "week": {"start": et(ws).strftime("%a %d %b %Y"), "end": et(we - 1).strftime("%a %d %b %Y"),
                 "label": _label(ws) + et(we - 1).strftime(" %Y"),
                 "start_iso": et(ws).date().isoformat()},
        "generated": datetime.datetime.now(ET).strftime("%a %d %b %Y, %H:%M ET"),
        "totals": {
            "appointments": len(appts), "occurred": len(done),
            "unique_sellers": len({a["lead_id"] for a in appts}),
            "kept": sum(1 for a in appts if a["outcome"] == "Kept"),
            "cancelled": sum(1 for a in appts if a["outcome"] == "Cancelled"),
            "no_show": sum(1 for a in appts if a["outcome"] == "No Show"),
            "no_outcome": sum(1 for a in done if a["outcome"] == "No outcome"),
            "offers": len(offers), "offers_from_appointments": sum(1 for o in offers if o["from_appointment"]),
            "new_leads": len(new),
            "appointments_created": len(created),
            "appointments_created_days": collections.Counter(et(x["createdAt"]).strftime("%a") for x in created).most_common(),
            "upcoming_appointments": len(upcoming),
            "followup_leads": sum(f["leads"] for f in followup),
            "followup_touched": sum(f["touched"] for f in followup),
        },
        "trend": [
            {"week": "prior-2", "label": _label(pws - 7 * DAY), "new_leads": len(new_between(pws - 7 * DAY, pws)),
             "appointments": len(appts_between(pws - 7 * DAY, pws)), "kept": None, "offers": None},
            {"week": "prior", "label": _label(pws), "new_leads": len(new_between(pws, ws)),
             "appointments": len(prev_appts),
             "kept": sum(1 for x in prev_appts if x.get("appointmentStatus") == 1),
             "offers": len(prev_offers)},
            {"week": "this", "label": _label(ws), "new_leads": len(new), "appointments": len(appts),
             "kept": sum(1 for a in appts if a["outcome"] == "Kept"), "offers": len(offers)},
        ],
        "appointments": appts,
        "formats": {k: dict(v) for k, v in fmt.items()},
        "out_of_market_appointments": out_of_market_appts,
        "offers": offers,
        "intake": {"by_source": by_source, "method": method.most_common(), "new": new_rows,
                   "out_of_market": out_of_market_new, "ppc": {"n": len(ppc),
                   "out_of_market": [r for r in ppc if r["market"] == "Out of market"],
                   "unknown": [r for r in ppc if r["market"] == "Unknown"]}},
        "speed": speed, "no_call": no_call, "real_misses": real_misses, "slow": slow,
        "followup": followup, "calls": calls, "status_moves": moves.most_common(),
        "hygiene": hygiene,
        "scope_note": "Active + Cold leads only (%d leads); Dead leads excluded except appointment leads."
                      % sum(1 for l in leads.values() if l.get("mainStatusId") in scope_ids),
    }


def _label(ms):
    s, e = et(ms), et(ms + 7 * DAY - 1)
    return "%d %s – %d %s" % (s.day, s.strftime("%b"), e.day, e.strftime("%b"))
