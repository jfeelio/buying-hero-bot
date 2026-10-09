"""Fill in Buying Hero's side of every LevelUp (Facebook / Meta) lead on the
"Meta Lead Sheet" tab of LevelUp's KPI workbook, and rebuild a
"BH Reconciliation" tab listing every gap between their list and our CRM.

Their rows are the master list. The Facebook campaign fills columns A-M; we
never write to A-M and never add rows to their tab. Each of their rows is
matched to a REsimpli lead (phone, then email, then exact name) and we write
Quality (N), Motivation (O) and our own columns P onward.

The reconciliation tab has three parts: leads in our CRM that are missing
from their sheet, leads on their sheet that never reached our CRM, and field
differences (address, contact details, form answers, out-of-market).

Claude turns the call notes into a property type, the seller's motivation, a
market guess and a one-line "why this status" written for the marketing team.
With no API key (or if the call fails) those fall back to plain rule-based
text and the sync still runs.

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
import unicodedata
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "weekly-acq-report"))
from pull import activity, all_leads, log, post, scope_status_ids  # noqa: E402

SHEET_ID = os.environ["LEVELUP_SHEET_ID"]  # secret: the sheet holds seller contact details
TAB = os.environ.get("LEVELUP_SHEET_TAB", "Meta Lead Sheet")
CAMPAIGN_NAME = "LevelUp"
CAMPAIGN_ID = "6abc128f8abb899e4dd9638a"  # fallback if the name lookup fails
MODEL = "claude-sonnet-5-5"
ET = ZoneInfo("America/New_York")

RECON_TAB = os.environ.get("LEVELUP_RECON_TAB", "BH Reconciliation")

# Our columns, appended after the LevelUp team's A-O.
OUR_HEADERS = ["BH Pipeline", "BH Status", "BH Property Type", "Call Attempts", "Texts Sent",
               "Reached Seller?", "Why This Status (Buying Hero notes)", "In Our Market?", "Last Synced"]
OUR_FIRST_COL = 15  # P (0-based)
WHY_COL = OUR_FIRST_COL + 6

# Their columns (0-based), read only.
C_DATE, C_NAME, C_ADDR, C_PHONE, C_EMAIL = 0, 4, 5, 6, 7
C_LISTED, C_TIMELINE, C_CASH, C_OWNED = 8, 10, 11, 12

CONTRACT = {"Under Contract", "New Inventory"}
OFFER = {"Offers Made", "Offer Made"}
UNWORKED = {"New Leads", "New"}  # a lead stays here until someone has a real conversation

FORM_WORDS = [("más_de_", "more than "), ("mas_de_", "more than "), ("lo_antes_posible", "ASAP"),
              ("años", "years"), ("anos", "years"), ("meses", "months"), ("sí", "Yes"), ("si", "Yes"),
              ("no", "No")]

# Buying Hero buys in Miami-Dade and Broward. ZIP ranges are approximate but
# cover every residential ZIP in both counties; Keys (Monroe) ZIPs are excluded.
MONROE = {33001, 33036, 33037, 33040, 33041, 33042, 33043, 33044, 33045, 33050, 33051, 33052, 33070}
BROWARD = ({33004, 33009, 33441, 33442, 33093, 33097} | set(range(33019, 33030)) | set(range(33060, 33078))
           | set(range(33081, 33085)) | set(range(33301, 33395)))
DADE = ({33090, 33092} | set(range(33010, 33019)) | set(range(33030, 33057)) | set(range(33101, 33200))
        | set(range(33231, 33300))) - MONROE - BROWARD
DADE_CITIES = ["miami", "hialeah", "homestead", "florida city", "doral", "kendall", "cutler bay", "palmetto bay",
               "pinecrest", "coral gables", "sweetwater", "medley", "aventura", "sunny isles", "surfside",
               "key biscayne", "opa-locka", "opa locka", "westchester", "bal harbour", "bay harbor", "el portal",
               "biscayne park", "golden beach", "north bay village", "virginia gardens"]
BROWARD_CITIES = ["fort lauderdale", "ft lauderdale", "ft. lauderdale", "hollywood", "pembroke pines", "miramar",
                  "davie", "plantation", "sunrise", "weston", "coral springs", "pompano", "deerfield", "margate",
                  "coconut creek", "tamarac", "lauderhill", "lauderdale lakes", "oakland park", "wilton manors",
                  "dania", "hallandale", "cooper city", "southwest ranches", "parkland", "lighthouse point",
                  "west park"]


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

def quality(x, dup):
    if dup:
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



def market_from_address(addr):
    """Miami-Dade / Broward / Outside market from a ZIP or a city name, '' if neither is there."""
    a = (addr or "").lower()
    zips = re.findall(r"(?<!\d)(3[2-4]\d{3})(?!\d)", a)
    if zips:
        z = int(zips[-1])
        return "Miami-Dade" if z in DADE else "Broward" if z in BROWARD else "Outside market"
    # Broward first: a Broward address can sit on a "Miami" street (Miami Gardens Dr),
    # but a Dade address almost never names a Broward city.
    if any(c in a for c in BROWARD_CITIES):
        return "Broward"
    if any(c in a for c in DADE_CITIES):
        return "Miami-Dade"
    return ""


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
- market: which county the property is in, from the address or the notes:
  "Miami-Dade", "Broward", "Outside market" (any other county, state or country), or
  "Unknown" if you cannot tell. Use what you know of Florida cities.
- status_reason: one or two plain sentences explaining the status. If the seller was
  never reached, say so and give the attempt count. If the form answers contradict
  what the seller said on the phone (timeline, listed, intent to sell), say exactly
  how, because that is what LevelUp most needs to know. If someone other than the
  owner filled out the form, say so. If the property is outside Miami-Dade and
  Broward, say so.
- Do not comment on Buying Hero's own response times or staff, and do not name staff.
- No em-dash asides, no hype, no emoji."""

SCHEMA = {
    "type": "object",
    "properties": {"property_type": {"type": "string"}, "motivation": {"type": "string"},
                   "market": {"type": "string", "enum": ["Miami-Dade", "Broward", "Outside market", "Unknown"]},
                   "status_reason": {"type": "string"}},
    "required": ["property_type", "motivation", "market", "status_reason"],
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
    return {"property_type": "", "motivation": "", "market": "Unknown", "status_reason": why}

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




# ---------------------------------------------------------------- matching

def strip_accents(v):
    return "".join(c for c in unicodedata.normalize("NFKD", v or "") if not unicodedata.combining(c))


def digits(v):
    return re.sub(r"\D", "", v or "")[-10:]


def norm_name(v):
    return re.sub(r"[^a-z]", "", strip_accents(v).lower())


ANSWER_WORDS = [("lo antes posible", "asap"), ("solo tengo curiosidad", "just curious"),
                ("mas de", "more than"), ("anos", "years"), ("meses", "months")]


def norm_answer(v):
    v = re.sub(r"\(.*?\)", "", strip_accents(v).lower().replace("_", " "))  # "... (just curious)"
    v = " ".join(v.split())
    for a, b in ANSWER_WORDS:
        v = v.replace(a, b)
    return {"si": "yes"}.get(v, v)


ADDR_WORDS = {"street": "st", "court": "ct", "terrace": "ter", "terr": "ter", "terra": "ter", "avenue": "ave",
              "drive": "dr", "road": "rd", "lane": "ln", "circle": "cir", "place": "pl", "boulevard": "blvd",
              "southwest": "sw", "northwest": "nw", "northeast": "ne", "southeast": "se", "florida": "fl",
              "fla": "fl", "unit": "", "apt": "", "apartment": "", "ste": "", "suite": ""}
ADDR_FILLER = {"fl", "usa", "us"}  # adding only these is not a better address
PLACEHOLDERS = {"", "not disclosed", "n/a", "na", "unknown", "none", "tbd"}


def addr_tokens(v):
    v = strip_accents(v).lower()
    v = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", v)
    v = re.sub(r"(\d)([a-z])", r"\1 \2", re.sub(r"([a-z])(\d)", r"\1 \2", v))
    return [t for t in (ADDR_WORDS.get(w, w) for w in re.findall(r"[a-z0-9]+", v)) if t]


def usable_address(v):
    return len(re.findall(r"[a-zA-Z]", v or "")) >= 3


def match_rows(theirs, leads):
    """Pair each of their sheet rows with one of our leads: phone, then email, then exact full name."""
    by = {"phone": {}, "email": {}, "name": {}}
    for x in leads:  # oldest first, so the original record wins over a later duplicate
        if x["phone"]:
            by["phone"].setdefault(x["phone"], x)
        if x["email"]:
            by["email"].setdefault(x["email"].strip().lower(), x)
        if len(norm_name(x["name"])) >= 6:
            by["name"].setdefault(norm_name(x["name"]), x)
    pairs = []
    for i, r in theirs:
        keys = [("phone", digits(r[C_PHONE])), ("email", r[C_EMAIL].strip().lower()), ("name", norm_name(r[C_NAME]))]
        how, x = next(((how, by[how][k]) for how, k in keys if k and k in by[how]), (None, None))
        pairs.append((i, r, x, how))
    return pairs


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



def lead_market(x, note):
    guess = note.get("market") if note.get("market") != "Unknown" else ""
    return market_from_address(x["address"]) or guess or "Unknown"


def foreign_phone(raw):
    """Sheets drops the "+" from "+57...", so judge by length: US is 10 digits, or 11 with a leading 1."""
    d = re.sub(r"\D", "", raw or "")
    return len(d) > 11 or (len(d) == 11 and not d.startswith("1"))


def build(theirs, leads, notes):
    """Values for their rows (N onward) plus the three reconciliation sections."""
    synced = dt.datetime.now(ET).strftime("%m/%d/%Y %I:%M %p")
    pairs = match_rows(theirs, leads)
    used, rows, missing_ours, missing_theirs, diffs = set(), {}, [], [], []
    for i, r, x, how in pairs:
        if x is None:
            foreign = foreign_phone(r[C_PHONE])
            mkt = "Outside market" if foreign else (market_from_address(r[C_ADDR]) or "Unknown")
            if foreign:
                why = "Never reached Buying Hero's CRM. Non-US phone number, so the seller is likely outside our area."
                note = "Non-US phone number. Did not come through to our CRM."
            else:
                why = "Never reached Buying Hero's CRM, so nobody has worked this lead yet."
                note = ("Did not come through to our CRM. If it is from today it may still arrive; "
                        "otherwise the Facebook to CRM connection dropped it.")
            rows[i] = ["", "", "Not received", "", "", "", "", "No", why, mkt, synced]
            phone = "+" + r[C_PHONE].lstrip("+") if foreign else r[C_PHONE]
            missing_theirs.append([i + 1, r[C_DATE], r[C_NAME], phone, r[C_ADDR], note])
            continue
        n = notes[x["id"]]
        dup = x["id"] in used
        used.add(x["id"])
        mkt = lead_market(x, n)
        rows[i] = [quality(x, dup), n["motivation"], x["pipeline"], x["status"], n["property_type"],
                   x["calls"], x["texts"], reached(x), n["status_reason"], mkt, synced]
        if not dup:
            diffs += field_diffs(i, r, x, how, mkt)
    matched_phones = {x["phone"] for _, _, x, _ in pairs if x and x["phone"]}
    for x in leads:
        if x["id"] in used or x["phone"] in matched_phones:
            continue  # on their sheet, or a CRM duplicate of a lead that is
        came_in = ("Facebook form, but the row is not on this sheet" if x["answers"]
                   else "Called the ad's phone number (no form submitted)")
        missing_ours.append([dt.datetime.fromtimestamp(x["created"] / 1000, ET).strftime("%m/%d/%Y %I:%M %p"),
                             x["name"], fmt_phone(x["phone"]), x["address"], came_in,
                             "%s / %s" % (x["pipeline"], x["status"]), lead_market(x, notes[x["id"]])])
    return rows, missing_ours, missing_theirs, diffs


def field_diffs(i, r, x, how, mkt):
    out = []

    def add(field, theirs, ours, note):
        out.append([i + 1, r[C_NAME], field, theirs, ours, note])

    if how != "phone" and digits(r[C_PHONE]) != x["phone"]:
        add("Phone", r[C_PHONE], fmt_phone(x["phone"]), "Matched on %s; the seller is reachable on our number." % how)
    if x["email"] and r[C_EMAIL].strip().lower() != x["email"].strip().lower():
        add("Email", r[C_EMAIL], x["email"], "Different email on file.")
    if norm_name(r[C_NAME]) != norm_name(x["name"]):
        add("Name", r[C_NAME], x["name"], "Different name on file.")

    theirs_a, ours_a = r[C_ADDR], x["address"]
    if strip_accents(ours_a).strip().lower() in PLACEHOLDERS:
        if not usable_address(theirs_a):
            add("Address", theirs_a, "Not given yet", "No usable address on the form; the seller has not given one.")
    else:
        t, o = addr_tokens(theirs_a), addr_tokens(ours_a)
        covered = all(w in o for w in t)
        extra = {w for w in o if w not in t}
        if t == o or (covered and extra <= ADDR_FILLER):
            pass  # same address, at most we added the state
        elif covered:
            add("Address", theirs_a, ours_a, "Same address; ours is more complete.")
        elif not usable_address(theirs_a):
            add("Address", theirs_a, ours_a, "No usable address on the form; ours came from the seller.")
        else:
            add("Address", theirs_a, ours_a, "Different address on file; ours is what we confirmed or corrected.")
    if mkt == "Outside market":
        add("Market", theirs_a, ours_a, "Outside Miami-Dade and Broward, where we buy.")

    for field, c, key in [("Listed?", C_LISTED, "Listed"), ("Timeline?", C_TIMELINE, "How Soon"),
                          ("Sell to an investor for cash?", C_CASH, "Investor"),
                          ("How long owned", C_OWNED, "How Long")]:
        ours_v = pick(x["answers"], key)
        if ours_v and r[c] and norm_answer(r[c]) != norm_answer(ours_v):
            add(field, r[c], ours_v, "Form answer differs between the sheet and our CRM.")
    return out


RECON_COLS = 7


def recon_grid(missing_ours, missing_theirs, diffs):
    now = dt.datetime.now(ET).strftime("%m/%d/%Y %I:%M %p")
    grid, bold = [], []

    def line(v=(), b=False):
        if b:
            bold.append(len(grid))
        grid.append(list(v) + [""] * (RECON_COLS - len(v)))

    line(["Buying Hero reconciliation, updated %s ET" % now], True)
    line(["Rebuilt on every sync from Buying Hero's CRM, so edits on this tab are overwritten. "
          "The Meta Lead Sheet's own columns A-M are never changed."])
    sections = [
        ("1. In Buying Hero's CRM under LevelUp, but not on the Meta Lead Sheet",
         ["Date Created (ET)", "Name", "Phone", "Address", "How It Came In", "BH Pipeline / Status", "In Our Market?"],
         missing_ours),
        ("2. On the Meta Lead Sheet, but never received in Buying Hero's CRM",
         ["Sheet Row", "Date Created", "Name", "Phone", "Address", "Note"], missing_theirs),
        ("3. Field differences between the Meta Lead Sheet and Buying Hero's CRM",
         ["Sheet Row", "Name", "Field", "On The Meta Lead Sheet", "In Buying Hero's CRM", "Note"], diffs),
    ]
    for title, header, body in sections:
        line()
        line(["%s (%d)" % (title, len(body))], True)
        line(header, True)
        for v in body:
            line(v)
        if not body:
            line(["None"])
    return grid, bold


def tab_id(api, title, create=False):
    meta = api.get(spreadsheetId=SHEET_ID, fields="sheets(properties(sheetId,title))").execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == title:
            return s["properties"]["sheetId"]
    if not create:
        raise SystemExit("tab %r not found" % title)
    r = api.batchUpdate(spreadsheetId=SHEET_ID,
                        body={"requests": [{"addSheet": {"properties": {"title": title}}}]}).execute()
    return r["replies"][0]["addSheet"]["properties"]["sheetId"]


def read_theirs(api):
    width = OUR_FIRST_COL + len(OUR_HEADERS)
    grid = api.values().get(spreadsheetId=SHEET_ID, range="'%s'!A1:%s" % (TAB, col(width - 1))).execute().get("values", [])
    grid = [r + [""] * (width - len(r)) for r in grid]
    theirs = [(i, r) for i, r in enumerate(grid[1:], start=1) if any(str(c).strip() for c in r[:13])]
    return (grid[0] if grid else []), theirs


def span(sid, r0=0, r1=None, c0=0, c1=None):
    d = {"sheetId": sid, "startRowIndex": r0, "startColumnIndex": c0}
    if r1 is not None:
        d["endRowIndex"] = r1
    if c1 is not None:
        d["endColumnIndex"] = c1
    return d


def width(sid, c, px):
    return {"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": c,
                                                    "endIndex": c + 1},
                                          "properties": {"pixelSize": px}, "fields": "pixelSize"}}


def write(api, header, rows, recon):
    end = OUR_FIRST_COL + len(OUR_HEADERS)
    last = col(end - 1)
    sheet_id = tab_id(api, TAB)
    data = []
    if header[OUR_FIRST_COL:end] != OUR_HEADERS:
        data.append({"range": "'%s'!%s1:%s1" % (TAB, col(OUR_FIRST_COL), last), "values": [OUR_HEADERS]})
    for i, vals in rows.items():  # N onward only; A-M belong to LevelUp
        data.append({"range": "'%s'!N%d:%s%d" % (TAB, i + 1, last, i + 1), "values": [[safe(v) for v in vals]]})
    api.values().batchUpdate(spreadsheetId=SHEET_ID, body={"valueInputOption": "USER_ENTERED", "data": data}).execute()

    grid, bold = recon
    recon_id = tab_id(api, RECON_TAB, create=True)
    api.values().clear(spreadsheetId=SHEET_ID, range="'%s'" % RECON_TAB).execute()
    api.values().update(spreadsheetId=SHEET_ID, range="'%s'!A1" % RECON_TAB, valueInputOption="USER_ENTERED",
                        body={"values": [[safe(v) for v in r] for r in grid]}).execute()

    reqs = [
        # Header style for our columns copied from column O's header; wrap the notes column.
        {"copyPaste": {"source": span(sheet_id, 0, 1, 14, 15), "destination": span(sheet_id, 0, 1, OUR_FIRST_COL, end),
                       "pasteType": "PASTE_FORMAT"}},
        {"repeatCell": {"range": span(sheet_id, 1, None, 14, end),
                        "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP", "verticalAlignment": "TOP"}},
                        "fields": "userEnteredFormat(wrapStrategy,verticalAlignment)"}},
        width(sheet_id, WHY_COL, 420),
        # Reconciliation tab: wrapped text, section titles and column headers in bold.
        {"repeatCell": {"range": span(recon_id),
                        "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP", "verticalAlignment": "TOP",
                                                       "textFormat": {"bold": False}}},
                        "fields": "userEnteredFormat(wrapStrategy,verticalAlignment,textFormat.bold)"}},
    ]
    reqs += [{"repeatCell": {"range": span(recon_id, b, b + 1, 0, RECON_COLS),
                             "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                             "fields": "userEnteredFormat.textFormat.bold"}} for b in bold]
    reqs += [width(recon_id, c, px) for c, px in enumerate([140, 160, 190, 260, 260, 300, 130])]
    api.batchUpdate(spreadsheetId=SHEET_ID, body={"requests": reqs}).execute()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    api = sheets()
    header, theirs = read_theirs(api)
    leads = gather()
    notes, src = summarise(leads)
    log("notes written by: %s" % src)
    rows, missing_ours, missing_theirs, diffs = build(theirs, leads, notes)
    log("sheet rows: %d, matched: %d, not in our CRM: %d, ours not on the sheet: %d, field differences: %d"
        % (len(theirs), len(theirs) - len(missing_theirs), len(missing_theirs), len(missing_ours), len(diffs)))
    if args.dry_run:
        for vals in rows.values():  # masked: quality and our columns only
            print(json.dumps({"quality": vals[0], "status": vals[3], "calls": vals[5],
                              "reached": vals[7], "market": vals[9]}))
        print("field differences by type:", json.dumps(
            {f: sum(1 for d in diffs if d[2] == f) for f in sorted({d[2] for d in diffs})}))
        return
    write(api, header, rows, recon_grid(missing_ours, missing_theirs, diffs))
    log("done")


if __name__ == "__main__":
    main()
