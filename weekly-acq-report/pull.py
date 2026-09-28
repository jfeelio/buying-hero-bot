"""Pull everything the weekly acquisitions report needs from REsimpli.

Scope is Active + Cold pipelines only (Jorge, 27 Sep 2026: dead leads carry no
decision value and doubled the run time). Two small exceptions, even if they
have since gone Dead: leads whose appointment fell in the window, and leads
created in the window (so the qualified-lead funnel stays honest).

REsimpli Open API facts this relies on (see memory reference_resimpli_open_api):
  * every endpoint is POST, auth is the raw key with no "Bearer"
  * /lead/list paging is unstable -> dedupe by _id, reconcile against count
  * /appointmentList takes {page, limit} only -- no date filter
  * /activityList needs {moduleId:1, subModuleId, type:1|2}; the two streams
    OVERLAP heavily, so dedupe by _id or every count doubles
  * the API 429s readily; ~0.6s between calls, serial
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = "https://api.resimpli.com/api/v6/openapi/"
PIPELINES_IN_SCOPE = ("Active Leads", "Cold Leads")
THROTTLE = 0.6


def _key():
    k = os.environ.get("RESIMPLI_KEY")
    if k:
        return k.strip()
    return open(os.environ.get("RESIMPLI_KEY_PATH", r"C:\Users\jsive\.resimpli_key")).read().strip()


KEY = None


def post(ep, body, tries=6):
    global KEY
    KEY = KEY or _key()
    for i in range(tries):
        req = urllib.request.Request(
            BASE + ep, data=json.dumps(body).encode(),
            headers={"Authorization": KEY, "Content-Type": "application/json"}, method="POST")
        try:
            return json.loads(urllib.request.urlopen(req, timeout=60).read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and i < tries - 1:
                time.sleep(3 * (i + 1))
                continue
            raise RuntimeError("%s -> HTTP %s %s" % (ep, e.code, e.read().decode()[:200]))
        except (urllib.error.URLError, TimeoutError):
            if i < tries - 1:
                time.sleep(3 * (i + 1))
                continue
            raise


def log(msg):
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


def all_leads():
    leads, count = {}, None
    for attempt in range(3):  # re-pass if unstable paging left us short
        for page in range(1, 30):
            d = post("lead/list", {"page": page, "limit": 100})["data"]
            count = d.get("count", count)
            items = d.get("items") or []
            for x in items:
                leads[x["_id"]] = x
            time.sleep(THROTTLE)
            if len(items) < 100:
                break
        if count is None or len(leads) >= count:
            break
    log("leads: %d of %s" % (len(leads), count))
    return list(leads.values()), count


def scope_status_ids():
    """Status ids for the Active + Cold pipelines. Pipelines have no filter on
    /lead/list (pipelineId is silently ignored), so scope by mainStatusId."""
    d = post("getPipelineList", {"moduleType": 1})["data"]
    items = d.get("items") if isinstance(d, dict) else d
    ids, statuses = set(), {}
    for p in items or []:
        for s in p.get("mainStatusList") or []:
            statuses[s["_id"]] = {"title": s.get("title"), "pipeline": p.get("title")}
            if p.get("title") in PIPELINES_IN_SCOPE:
                ids.add(s["_id"])
    if not ids:
        raise RuntimeError("no Active/Cold statuses found in getPipelineList")
    return ids, statuses


def all_appointments():
    seen = {}
    for page in range(1, 30):
        d = post("appointmentList", {"page": page, "limit": 100})["data"]
        items = d.get("items") or []
        for a in items:
            seen[a["_id"]] = a
        time.sleep(THROTTLE)
        if len(seen) >= d.get("count", 0) or not items:
            break
    return list(seen.values())


def activity(lead_id, since_ms):
    """Both activity streams, deduped, paged back until older than since_ms."""
    rows = {}
    for t in (1, 2):
        for page in range(1, 10):
            r = post("activityList", {"moduleId": 1, "subModuleId": lead_id,
                                      "type": t, "page": page, "limit": 100})
            d = r.get("data")
            items = (d.get("items") or []) if isinstance(d, dict) else []
            for x in items:
                if (x.get("createdAt") or 0) >= since_ms:
                    rows[x["_id"]] = x
            time.sleep(THROTTLE)
            if len(items) < 100 or min((x.get("createdAt") or 0) for x in items) < since_ms:
                break
    return list(rows.values())


def pull(since_ms, appt_window):
    """since_ms: earliest activity worth keeping (start of the comparison week).
    appt_window: (start_ms, end_ms) -- leads with an appointment starting in it
    are swept even when they are no longer Active/Cold."""
    leads, count = all_leads()
    scope_ids, statuses = scope_status_ids()
    appts = all_appointments()

    in_scope = {l["_id"] for l in leads if l.get("mainStatusId") in scope_ids}
    appt_leads = {a.get("subModuleId") for a in appts
                  if a.get("subModuleId")
                  and appt_window[0] <= (a.get("startDateTimeInTimeStamp") or 0) < appt_window[1]}
    # Leads created in the window, even if already Dead: a lead qualified on
    # Monday and killed on Tuesday must still show in the qualified funnel.
    # ~10 extra leads, so this barely touches the "no dead leads" run time.
    fresh = {l["_id"] for l in leads if (l.get("createdAt") or 0) >= since_ms}
    sweep = sorted(in_scope | appt_leads | fresh)
    log("sweeping %d leads (%d Active/Cold + appointment + new-this-window leads)" % (len(sweep), len(in_scope)))

    acts = {}
    for i, lid in enumerate(sweep, 1):
        rows = activity(lid, since_ms)
        if rows:
            acts[lid] = rows
        if i % 50 == 0:
            log("  %d/%d" % (i, len(sweep)))
    return {
        "leads": leads, "lead_count": count, "statuses": statuses,
        "scope_status_ids": sorted(scope_ids), "appointments": appts,
        "activities": acts, "swept": sweep,
    }
