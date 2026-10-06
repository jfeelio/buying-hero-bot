"""Sync every LevelUp (Facebook / Meta) lead from REsimpli into the shared
"Meta Lead Sheet" tab the LevelUp team uses to tune the ads.

One row per lead, matched on phone number, so re-running only updates rows.
Columns A-O are the LevelUp team's own layout. We fill the lead and form
columns only where they are blank, leave B-D (their campaign / ad set / ad
names) alone, and always refresh Quality (N), Motivation (O) and our own
columns P onward.

Claude turns the call notes into a property type, the seller's motivation and
a one-line "why this status" written for the marketing team. With no API key
(or if the call fails) those fall back to plain rule-based text and the sync
still runs.

This repo is PUBLIC: never log names, phones, addresses or notes. Counts only.

Usage:  python sync.py            # write to the sheet
        python sync.py --dry-run  # build rows and print a masked preview
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import time
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "weekly-acq-report"))
from pull import activity, all_leads, log, post, scope_status_ids  # noqa: E402

SHEET_ID = os.environ["LEVELUP_SHEET_ID"]  # secret: the sheet holds seller contact details
TAB = os.environ.get("LEVELUP_SHEET_TAB", "Meta Lead Sheet")
CAMPAIGN_NAME = "LevelUp"
CAMPAIGN_ID = "6abc128f8abb899e4dd9638a"  # fallback if the name lookup fails
MODEL = "claude-sonnet-5-5"
ET = ZoneInfo("America/New_York")

# Our columns, appended after the LevelUp team's A-O.
OUR_HEADERS = ["BH Pipeline", "BH Status", "Call Attempts", "Texts Sent",
               "Reached Seller?", "Why This Status (Buying Hero notes)", "Last Synced"]
OUR_FIRST_COL = 15  # P (0-based)

CONTRACT = {"Under Contract", "New Inventory"}
OFFER = {"Offers Made", "Offer Made"}
UNWORKED = {"New Leads", "New"}  # a lead stays here until someone has a real conversation

FORM_WORDS = [("más_de_", "more than "), ("mas_de_", "more than "), ("lo_antes_posible", "ASAP"),
              ("años", "years"), ("anos", "years"), ("meses", "months"), ("sí", "Yes"), ("si", "Yes"),
              ("no", "No")]


# ---------------------------------------------------------------- REsimpli

def campaign_id():
    try:
        d = post("marketingCampaignList", {"campaignType": 1})["data"]
        for c in (d.get("items") if isinstance(d, dict) else d) or []:
            if c.get("name", "").strip().lower() == CAMPAIGN_NAME.lower():
                return c["_id"]
    except Exception as e:
        log("campaign lookup failed (%s), using the stored id" % e)
    return CAMPAIGN_ID


def strip_html(s):
    s = re.sub(r"<br\s*/?>|</p>", "\n", s or "")
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", s)).strip()


def translate(v):
    v = v.strip()
    if v.lower() in ("sí", "si"):
        return "Yes"
    if v.lower() == "no":
        return "No"
    for a, b in FORM_WORDS[:6]:
        v = v.replace(a, b)
    return v.replace("_", " ").strip().replace("more than 10 years", "More than 10 years")


def form_answers(acts):
    """The Zapier step logs the Facebook form as the first note."""
    for a in sorted(acts, key=lambda a: a.get("createdAt") or 0):
        c = a.get("comment") or ""
        if a.get("activityType") == 8 and "How Soon" in c:
            out = {}
            for q, v in re.findall(r"([^<>?]+\?)\s*([^<]*)", c):
                out[q.strip()] = translate(v)
            return out
    return {}


def pick(answers, key):
    for q, v in answers.items():
        if key.lower() in q.lower():
            return v
    return ""


def gather():
    cid = campaign_id()
    leads, _ = all_leads()
    _, statuses = scope_status_ids()
    mine = sorted((l for l in leads if l.get("marketingCampignId") == cid), key=lambda l: l["createdAt"])
    log("LevelUp leads: %d" % len(mine))
    out = []
    for l in mine:
        det = post("lead/details", {"leadId": l["_id"]})["data"]["leadData"]
        time.sleep(0.6)
        acts = activity(l["_id"], 0)
        st = statuses.get(l.get("mainStatusId"), {})
        contact = (det.get("contactData") or [{}])[0]
        phones = contact.get("phoneNumbers") or []
        phone = next((p["phoneNumber"] for p in phones if p.get("isPrimary")), phones[0]["phoneNumber"] if phones else "")
        emails = contact.get("emails") or []
        notes = [{"when": dt.datetime.fromtimestamp(a["createdAt"] / 1000, ET).strftime("%a %m/%d %I:%M %p"),
                  "by": a.get("createdByName") or "", "text": strip_html(a.get("comment"))[:1500]}
                 for a in sorted(acts, key=lambda a: a.get("createdAt") or 0)
                 if a.get("activityType") == 8 and "How Soon" not in (a.get("comment") or "")
                 and strip_html(a.get("comment"))]
        out.append({
            "id": l["_id"],
            "created": l["createdAt"],
            "name": contact.get("fullName") or "",
            "phone": re.sub(r"\D", "", phone)[-10:],
            "email": next((e["email"] for e in emails if e.get("isPrimary")), emails[0]["email"] if emails else ""),
            "address": (l.get("address") or "").strip(),
            "pipeline": st.get("pipeline") or "",
            "status": (st.get("title") or l.get("mainStatusTitle") or "").replace("☆", "").strip(),
            "dead_reasons": [d.get("title") or d.get("name") for d in det.get("deadReasonsData") or []],
            "answers": form_answers(acts),
            "calls": sum(1 for a in acts if a.get("direction") == "outgoingCall"),
            "texts": sum(1 for a in acts if a.get("direction") == "outgoingSms"),
            "inbound": sum(1 for a in acts if (a.get("direction") or "").startswith("incoming")),
            "notes": notes,
        })
    return out


# ---------------------------------------------------------------- grading

def quality(x, seen_phones):
    if x["phone"] and x["phone"] in seen_phones:
        return "Duplicate"
    if x["status"] in CONTRACT:
        return "A (contract)"
    if x["status"] in OFFER:
        return "B (offer made)"
    if x["pipeline"] == "Dead Leads":
        return "F (dead)"
    if x["status"] in UNWORKED:
        return "No Contact"
    return "C (net lead)"


def reached(x):
    return "No" if x["status"] in UNWORKED and x["pipeline"] != "Dead Leads" else "Yes"


SYSTEM = """You summarise seller leads for LevelUp, the agency running Buying Hero's
Facebook lead ads. Buying Hero is a cash home buyer (wholesaler) in Miami-Dade and
Broward. LevelUp uses your text to tune targeting and the lead form, so write for a
marketer: what kind of seller this was and why the lead sits where it does.

For each lead you get its CRM pipeline and status, the answers the seller gave on the
Facebook form, how many calls and texts went out, and the team's call notes.

Rules:
- Use only facts in the input. Never invent a price, timeline, condition or reason.
- property_type: what the notes say (single family, duplex, condo, townhouse...).
  Empty string if the notes don't say.
- motivation: the seller's reason to sell in a few words (relocation, inherited,
  tired landlord, financial distress...). If unknown, "Unknown, not reached yet" or
  "Not stated".
- status_reason: one or two plain sentences explaining the status. If the seller was
  never reached, say so and give the attempt count. If the form answers contradict
  what the seller said on the phone (timeline, listed, intent to sell), say exactly
  how, because that is what LevelUp most needs to know. If someone other than the
  owner filled out the form, say so.
- Do not comment on Buying Hero's own response times or staff, and do not name staff.
- No em-dash asides, no hype, no emoji."""

SCHEMA = {
    "type": "object",
    "properties": {"property_type": {"type": "string"}, "motivation": {"type": "string"},
                   "status_reason": {"type": "string"}},
    "required": ["property_type", "motivation", "status_reason"],
    "additionalProperties": False,
}


def fallback(x):
    if reached(x) == "No":
        why = "Not reached yet after %d call%s and %d text%s." % (
            x["calls"], "" if x["calls"] == 1 else "s", x["texts"], "" if x["texts"] == 1 else "s")
    elif x["pipeline"] == "Dead Leads":
        why = "Dead" + (": " + ", ".join(filter(None, x["dead_reasons"])) if x["dead_reasons"] else ".")
    else:
        why = "In %s / %s." % (x["pipeline"], x["status"])
    return {"property_type": "", "motivation": "", "status_reason": why}


def summarise_one(client, x):
    """One call per lead: a batched call was seen dropping leads from its answer."""
    payload = {"pipeline": x["pipeline"], "status": x["status"], "dead_reasons": x["dead_reasons"],
               "form": x["answers"], "address": x["address"], "calls_made": x["calls"],
               "texts_sent": x["texts"], "inbound_contacts": x["inbound"], "notes": x["notes"]}
    msg = client.messages.create(
        model=MODEL, max_tokens=2000, system=SYSTEM,
        messages=[{"role": "user", "content": "Lead (JSON):\n\n" + json.dumps(payload, ensure_ascii=False)}],
        extra_body={"output_config": {"format": {"type": "json_schema", "schema": SCHEMA}}},
    )
    if msg.stop_reason not in ("end_turn", "stop_sequence"):
        raise RuntimeError("stop_reason=%s" % msg.stop_reason)
    return json.loads(next(b.text for b in msg.content if b.type == "text"))


def summarise(rows):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        log("no ANTHROPIC_API_KEY, using rule-based notes")
        return {x["id"]: fallback(x) for x in rows}, "fallback"
    import anthropic
    client, out, failed = anthropic.Anthropic(), {}, 0
    for x in rows:
        try:
            out[x["id"]] = summarise_one(client, x)
        except Exception as e:
            failed += 1
            log("Claude call failed for one lead (%s), using rule-based note" % type(e).__name__)
            out[x["id"]] = fallback(x)
    return out, "%s (%d of %d fell back)" % (MODEL, failed, len(rows))


# ---------------------------------------------------------------- sheet

def safe(v):
    v = "" if v is None else str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@") else v


def fmt_phone(p):
    return "(%s) %s-%s" % (p[:3], p[3:6], p[6:]) if len(p) == 10 else p


def col(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def sheets():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    raw = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if raw:
        creds = service_account.Credentials.from_service_account_info(json.loads(raw), scopes=scopes)
    else:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "foreclosure-agent", "credentials.json")
        creds = service_account.Credentials.from_service_account_file(path, scopes=scopes)
    return build("sheets", "v4", credentials=creds, cache_discovery=False).spreadsheets()


def build_rows(leads, notes):
    seen, rows = set(), []
    synced = dt.datetime.now(ET).strftime("%m/%d/%Y %I:%M %p")
    for x in leads:
        q = quality(x, seen)
        if x["phone"]:
            seen.add(x["phone"])
        n = notes[x["id"]]
        a = x["answers"]
        rows.append({
            "phone": x["phone"],
            "fill_if_blank": {  # LevelUp's own columns: never overwrite what they typed
                0: dt.datetime.fromtimestamp(x["created"] / 1000, ET).strftime("%m/%d/%Y %I:%M %p"),
                4: x["name"], 5: x["address"], 6: fmt_phone(x["phone"]), 7: x["email"],
                8: pick(a, "Listed"), 9: n["property_type"], 10: pick(a, "How Soon"),
                11: pick(a, "Investor"), 12: pick(a, "How Long"),
            },
            "always": {13: q, 14: n["motivation"], 15: x["pipeline"], 16: x["status"],
                       17: x["calls"], 18: x["texts"], 19: reached(x), 20: n["status_reason"], 21: synced},
        })
    return rows


def write(api, rows):
    last = col(OUR_FIRST_COL + len(OUR_HEADERS) - 1)
    grid = api.values().get(spreadsheetId=SHEET_ID, range="'%s'!A1:%s" % (TAB, last)).execute().get("values", [])
    header = grid[0] if grid else []
    meta = api.get(spreadsheetId=SHEET_ID, fields="sheets(properties(sheetId,title))").execute()
    sheet_id = next(s["properties"]["sheetId"] for s in meta["sheets"] if s["properties"]["title"] == TAB)

    def digits(r):
        return re.sub(r"\D", "", r[6] if len(r) > 6 else "")[-10:]

    by_phone = {digits(r): i for i, r in enumerate(grid[1:], start=1) if digits(r)}
    # First free row: nothing in the lead columns A-M (N may hold the old dropdown legend).
    used = [i for i, r in enumerate(grid[1:], start=1) if any((c or "").strip() for c in r[:13])]
    nxt = (max(used) + 1) if used else 1

    data, new, upd = [], 0, 0
    if header[OUR_FIRST_COL:OUR_FIRST_COL + len(OUR_HEADERS)] != OUR_HEADERS:
        data.append({"range": "'%s'!%s1:%s1" % (TAB, col(OUR_FIRST_COL), last), "values": [OUR_HEADERS]})
    for r in rows:
        i = by_phone.get(r["phone"]) if r["phone"] else None
        existing = grid[i] if i is not None and i < len(grid) else []
        if i is None:
            i, nxt, new = nxt, nxt + 1, new + 1
        else:
            upd += 1
        for c, v in r["fill_if_blank"].items():
            if not (existing[c] if c < len(existing) else "").strip() and v not in ("", None):
                data.append({"range": "'%s'!%s%d" % (TAB, col(c), i + 1), "values": [[safe(v)]]})
        vals = [r["always"][c] for c in range(13, OUR_FIRST_COL + len(OUR_HEADERS))]
        data.append({"range": "'%s'!N%d:%s%d" % (TAB, i + 1, last, i + 1), "values": [[safe(v) for v in vals]]})

    api.values().batchUpdate(spreadsheetId=SHEET_ID, body={"valueInputOption": "USER_ENTERED", "data": data}).execute()
    # Header style for our columns copied from column O's header; wrap the notes column.
    api.batchUpdate(spreadsheetId=SHEET_ID, body={"requests": [
        {"copyPaste": {"source": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                                  "startColumnIndex": 14, "endColumnIndex": 15},
                       "destination": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                                       "startColumnIndex": OUR_FIRST_COL,
                                       "endColumnIndex": OUR_FIRST_COL + len(OUR_HEADERS)},
                       "pasteType": "PASTE_FORMAT"}},
        {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": 14,
                                  "endColumnIndex": OUR_FIRST_COL + len(OUR_HEADERS)},
                        "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP", "verticalAlignment": "TOP"}},
                        "fields": "userEnteredFormat(wrapStrategy,verticalAlignment)"}},
        {"updateDimensionProperties": {"range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                                                 "startIndex": 20, "endIndex": 21},
                                       "properties": {"pixelSize": 420}, "fields": "pixelSize"}},
    ]}).execute()
    log("sheet: %d new rows, %d updated" % (new, upd))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    leads = gather()
    notes, src = summarise(leads)
    log("notes written by: %s" % src)
    rows = build_rows(leads, notes)
    if args.dry_run:
        for r in rows:  # masked: quality and our columns only
            print(json.dumps({"quality": r["always"][13], "status": r["always"][16],
                              "calls": r["always"][17], "reached": r["always"][19]}))
        return
    write(sheets(), rows)


if __name__ == "__main__":
    main()
