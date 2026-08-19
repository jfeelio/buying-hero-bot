"""Build the GHL import plan from the live `MAIN Dispo Tab`.

  python build_import.py            # writes the review tab, touches nothing else
  python build_import.py --push     # writes the review tab AND imports to GHL

Reads the live sheet, re-keys the hand-reviewed extraction onto buyer identity
(see rekey.py — row numbers moved on 2026-08-18), writes `GHL Import Plan` for
review, and on --push creates/merges contacts in GoHighLevel.

MERGE POLICY, identical to the InvestorBase capture (W12): a re-run may only
ADD. It never overwrites a tier, a status, an excl_ rule, or a name a human set
in GHL. Running this twice is safe; running it after the dispo team has curated
records in GHL is also safe.
"""
import argparse, json, os, re, sys, time
import urllib.request, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extraction as E
import rekey

from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

CREDS = r"D:\Dropbox\J Feels\Dev\foreclosure-agent\credentials.json"
SID = "1wHg_2vIvhBYTJTIFebPzvvAbxzmuhtpt4oh62wRAYY0"
SRC_TAB = "MAIN Dispo Tab"
FROZEN_TAB = "GHL Import Dry Run"   # frozen snapshot: row -> identity
OUT_TAB = "GHL Import Plan"

LOCATION = "ib5jEnyqqq06FIEqlVGs"
API = "https://services.leadconnectorhq.com"

FIELD = {
    "record_type": "vGlkrrrRFNhDn4S7Exlv", "buy_tier": "6LvZFW4TVSaFYDx60Yaj",
    "buy_type": "O145PqkYqXQ02Vu4Ue4z", "buy_source": "kmikehE2YPSxJILEMzmb",
    "buy_status": "lU8dcFyBnnvoAy9DHQ5o", "buy_counties": "ao4ItInAMbgFCaTMJ7QB",
    "buy_neighborhoods": "IWKqbPeAYwQi2jSzEimE", "buy_price_min": "MxZpTpwOnVOrjsuUBZ4Q",
    "buy_price_max": "0pi1duru4xCRriQLyVjM", "buy_sqft_min": "ZDyvlo0q7KZIgDiDqM8n",
    "buy_prop_types": "J3NloYAipqQjSZU6Ecmp", "buy_rehab_appetite": "C9sDttAKLClZzQ9LSxa2",
    "buy_out_of_state": "H1rXvKXSIf4FSZYGUDnQ", "buy_high_end": "DhOLxmI6tr41VoNlVd4q",
    "buy_relationship_building": "4OrHPvzysyhD0rY5zPUE",
    "buy_consent_status": "5ml7I8irq1JpVPriEPbp", "buy_consent_source": "8cNibmRNgVOW5JbeRA8l",
    "buy_extract_confidence": "GE9QndHEZ7sUT8svaudA", "buy_notes": "gCQaugkGmCMR3DrRj93P",
    "buy_entity_name": "ai41CygrKK7nLDlhrrq3", "excl_all_blasts": "zKxjOzGcLfMNiCUPvw5n",
    "excl_notes": "8q8gTIPW2FNNm51Y8r7H",
}
MULTI = {"record_type", "buy_type", "buy_source", "buy_counties",
         "buy_neighborhoods", "buy_prop_types"}

# Same policy as W12's "Merge into Existing Buyer": these UNION, these are the
# human's and never touched, everything else fills blanks only.
UNION = {"buy_source", "record_type", "buy_type", "buy_prop_types"}
KEEP = {"buy_status", "buy_tier", "excl_all_blasts", "excl_notes"}


# ----------------------------------------------------------------- GHL client
# The token file lives in the user profile, NOT in this repo: the repo is a
# Dropbox-synced git working tree, so a secret written here is both committed
# and uploaded. ~/.ghl_pit is neither.
TOKEN_FILE = os.path.join(os.path.expanduser("~"), ".ghl_pit")
_TOKEN = []


def token():
    if _TOKEN:
        return _TOKEN[0]
    t = os.environ.get("GHL_PIT", "")
    if not t and os.path.exists(TOKEN_FILE):
        # utf-8-sig: Notepad writes a BOM, which would ride along in the token.
        with open(TOKEN_FILE, encoding="utf-8-sig") as f:
            t = f.read().strip()
    if not t:
        sys.exit(
            "No GoHighLevel token found.\n\n"
            "Put the Private Integration Token in %s (one line, nothing else):\n"
            "    Settings -> Private Integrations -> your integration -> copy token\n\n"
            "That path is in your user profile, not the Dropbox-synced repo, so "
            "it is never committed or uploaded." % TOKEN_FILE)
    _TOKEN.append(t)
    return t


def call(method, path, body=None, tries=4):
    req = urllib.request.Request(
        API + path, method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + token(), "Version": "2021-07-28",
                 "Content-Type": "application/json", "Accept": "application/json",
                 # Cloudflare sits in front of the LeadConnector API and rejects
                 # urllib's default agent with a 1010 that reads like an auth
                 # failure. It is not one.
                 "User-Agent": "buying-hero-import/1.0"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:400]
            # 429/5xx are worth waiting out; a 4xx is our bug and retrying it
            # just writes the same wrong thing three more times.
            if e.code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError("%s %s -> %s %s" % (method, path, e.code, detail))
        except urllib.error.URLError:
            if attempt < tries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
    raise RuntimeError("unreachable")


def find_by_phone(phone):
    res = call("POST", "/contacts/search", {
        "locationId": LOCATION, "pageLimit": 5,
        "filters": [{"field": "phone", "operator": "eq", "value": phone}]})
    return (res.get("contacts") or [])


def existing_values(contact):
    out = {}
    for c in contact.get("customFields") or []:
        v = c.get("value", c.get("fieldValue"))
        for name, fid in FIELD.items():
            if c.get("id") == fid:
                out[name] = v
    return out


def split_multi(v):
    if v is None or v == "":
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return [s.strip() for s in str(v).split(";") if s.strip()]


# ------------------------------------------------------------------ the build
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true",
                    help="actually create/merge contacts in GHL")
    ap.add_argument("--limit", type=int, default=0, help="push only the first N")
    args = ap.parse_args()

    creds = Credentials.from_service_account_file(
        CREDS, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    svc = build("sheets", "v4", credentials=creds)
    read = lambda rng: svc.spreadsheets().values().get(
        spreadsheetId=SID, range=rng).execute().get("values", [])

    frozen = read("'%s'!A:E" % FROZEN_TAB)[1:]
    by_identity, orphans = rekey.build_map(frozen, E.EXTRACT)
    print("extraction re-keyed onto identity: %d of %d entries"
          % (len(by_identity), len(E.EXTRACT)))
    for row, why in orphans:
        print("  ORPHANED extraction for original row %s: %s" % (row, why))

    vals = read("'%s'!A:AC" % SRC_TAB)
    hdr, data = vals[0], vals[1:]
    matched = set()

    seen, out = {}, []
    stats = dict(create=0, dupe=0, nophone=0, suppress_nophone=0, dnc=0, blacklist=0)

    for i, raw in enumerate(data, start=2):
        raw = raw + [""] * (len(hdr) - len(raw))
        r = {h: (raw[j] or "").strip() for j, h in enumerate(hdr)}
        if not (r["First Name"] or r["Last Name"] or r["Phone"]):
            continue

        phone = E.norm_phone(r["Phone"])
        ex = rekey.resolve(by_identity, phone, r["First Name"], r["Last Name"])
        if ex:
            matched.add(id(ex))
        notes = r["Overall Notes"]

        tier, col_type, src = E.TYPE_MAP.get(r["Type"], ("", "", ""))
        src = E.source_from_notes(notes, src)

        # record_type is Buyer, full stop. An earlier version added Seller for
        # JV partners on the theory that they "sit on both sides of the table" -
        # Jorge corrected that on 2026-08-18: none of these people are sellers.
        # It is not a cosmetic label either. record_type is the field EVERY
        # workflow and smart list filters on, so a stray Seller would pull JV
        # partners into seller nurture sequences the moment the REsimpli
        # migration lands. That they partner on deals is what buy_type = JV
        # already records.
        rec = ["Buyer"]
        btypes = E.clean_types(ex.get("btype"))
        if col_type and col_type not in btypes:
            btypes.insert(0, col_type)

        banned = r["Type"] == "BANNED"
        dnc = ex.get("dnc", False)
        if banned:
            status = "Blacklist"; stats["blacklist"] += 1
        elif dnc:
            status = "DNC"; stats["dnc"] += 1
        else:
            status = "Active"

        aoi = E.AOI.get(r["Areas of Interest"].strip().lower(), ("", ""))
        counties = aoi[0] or ex.get("counties", "")
        hoods = aoi[1] or ex.get("hoods", "")

        # Consent records HOW THEY REACHED US. It is evidence, not a switch;
        # outreach policy is set separately and this stays truthful either way.
        if src == "InvestorBase":
            consent, csrc = "Not Opted In", ""
        elif src == "InvestorLift":
            consent, csrc = "Opted In", "InvestorLift"
        else:
            consent, csrc = "Opted In", "Master List"

        # The sheet's Email column is free text and sometimes holds prose or a
        # second phone number. GHL 422s on those. Do not silently drop the
        # value - "646-966-2358" is a real second number and "another
        # wholesaler" is a vetting signal. Move it into the notes instead.
        email, bad_email = r["Email"], ""
        if email and not re.match(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$", email):
            bad_email, email = email, ""
        # The same string often appears in BOTH columns (someone pasted a
        # WhatsApp remark into each). Do not echo it twice into the notes.
        if bad_email and bad_email not in notes:
            notes = ((notes + "\n") if notes else "") + \
                    "Sheet Email column (not an address): " + bad_email

        warn = []
        if bad_email:
            warn.append("EMAIL COLUMN WAS NOT AN EMAIL - kept in notes")
        if not phone:
            warn.append("NO PHONE")
        if phone and phone in seen:
            warn.append("DUPLICATE of sheet row %d" % seen[phone])
        if banned or dnc:
            warn.append("SUPPRESS - do not blast")
        if ex.get("note_flag"):
            warn.append(ex["note_flag"])

        if not phone and (banned or dnc):
            # A suppression record is worth keeping even with nothing to text.
            # Without it, the ban lives only in a spreadsheet: the day this
            # person turns up in an InvestorBase or InvestorLift pull WITH a
            # phone, they land as a clean active buyer and get blasted. The
            # record will not auto-merge (the merge key is phone), but a dispo
            # agent searching the name finds the ban - which is the whole point
            # of not deleting a snake.
            action = "CREATE - suppression record, no phone"
            stats["suppress_nophone"] += 1
        elif not phone:
            action = "REVIEW - no phone" if email else "SKIP - no phone/email"
            stats["nophone"] += 1
        elif phone in seen:
            action = "MERGE into earlier row"
            stats["dupe"] += 1
        else:
            action = "CREATE"; stats["create"] += 1; seen[phone] = i

        out.append(dict(
            row=i, action=action, first=r["First Name"], last=r["Last Name"],
            phone=phone, email=email, company=r["Company"],
            record_type=rec, buy_tier=tier, buy_type=btypes, buy_source=[src] if src else [],
            buy_status=status, buy_counties=split_multi(counties),
            buy_neighborhoods=split_multi(hoods),
            buy_price_min=ex.get("pmin", ""), buy_price_max=ex.get("pmax", ""),
            buy_sqft_min=ex.get("sqft_min", ""),
            buy_prop_types=split_multi(ex.get("types", "")),
            buy_rehab_appetite=ex.get("rehab", ""),
            buy_out_of_state="Yes" if r["Out of State?"] == "TRUE" else ex.get("oos", ""),
            buy_high_end="Yes" if r["High End Flips"] == "TRUE" else ex.get("high_end", ""),
            buy_relationship_building="Yes" if r["Building Relationship"] == "TRUE" else "",
            buy_consent_status=consent, buy_consent_source=csrc,
            buy_extract_confidence=ex.get("conf", "" if not notes else "Needs Review"),
            date_added=r["Date Added"], buy_notes=notes, warn=" | ".join(warn),
            # An explicit DNC in the source is a person who told us to stop.
            # buy_status alone is honoured by the engines, but excl_all_blasts
            # is the field a human reads on the contact card.
            excl_all_blasts="Yes" if (banned or dnc) else "",
            # A suppression with no stated reason is nearly useless six months
            # later - somebody reinstates the buyer because nobody remembers
            # why. Always say something, even when the sheet only had the
            # Type column to go on.
            excl_notes=(
                ("Imported from the master sheet: " + ex["note_flag"])
                if ex.get("note_flag") else
                ("Imported from the master sheet: Type column said BANNED - "
                 "reason not recorded in the source" if banned else
                 "Imported from the master sheet: explicit DNC in the source")
            ) if (banned or dnc) else "",
        ))

    unmatched = [row for row, ex in E.EXTRACT.items() if id(ex) not in matched]
    if unmatched:
        print("\n!! %d curated extractions found NO buyer in the live sheet: %s"
              % (len(unmatched), unmatched))

    write_review(svc, out)
    print("\n" + json.dumps(stats, indent=1))
    print("distinct contacts to create:", stats["create"])

    if not args.push:
        print("\nDry run only. Re-run with --push to write to GHL.")
        return
    push(out, args.limit)


HEADERS = ["src row", "action", "first_name", "last_name", "phone", "email",
           "buy_entity_name", "record_type", "buy_tier", "buy_type", "buy_source",
           "buy_status", "buy_counties", "buy_neighborhoods", "buy_price_min",
           "buy_price_max", "buy_sqft_min", "buy_prop_types", "buy_rehab_appetite",
           "buy_out_of_state", "buy_high_end", "buy_relationship_building",
           "buy_consent_status", "buy_consent_source", "buy_extract_confidence",
           "excl_all_blasts", "date_added", "buy_notes", "WARNINGS"]


def write_review(svc, out):
    j = lambda v: "; ".join(v) if isinstance(v, list) else v
    rows = [[r["row"], r["action"], r["first"], r["last"], r["phone"], r["email"],
             r["company"], j(r["record_type"]), r["buy_tier"], j(r["buy_type"]),
             j(r["buy_source"]), r["buy_status"], j(r["buy_counties"]),
             j(r["buy_neighborhoods"]), r["buy_price_min"], r["buy_price_max"],
             r["buy_sqft_min"], j(r["buy_prop_types"]), r["buy_rehab_appetite"],
             r["buy_out_of_state"], r["buy_high_end"], r["buy_relationship_building"],
             r["buy_consent_status"], r["buy_consent_source"],
             r["buy_extract_confidence"], r["excl_all_blasts"], r["date_added"],
             r["buy_notes"], r["warn"]] for r in out]

    meta = svc.spreadsheets().get(spreadsheetId=SID).execute()
    titles = [s["properties"]["title"] for s in meta["sheets"]]
    if OUT_TAB not in titles:
        svc.spreadsheets().batchUpdate(spreadsheetId=SID, body={"requests": [
            {"addSheet": {"properties": {"title": OUT_TAB, "gridProperties":
             {"rowCount": max(200, len(rows) + 10), "columnCount": 32}}}}]}).execute()
        print("created tab %r" % OUT_TAB)
    else:
        svc.spreadsheets().values().clear(
            spreadsheetId=SID, range="'%s'!A:AF" % OUT_TAB).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=SID, range="'%s'!A1" % OUT_TAB, valueInputOption="RAW",
        body={"values": [HEADERS] + rows}).execute()
    print("wrote %d rows to %r" % (len(rows), OUT_TAB))


# --------------------------------------------------------------------- push
def push(out, limit):
    todo = [r for r in out if r["action"].startswith("CREATE")]
    if limit:
        todo = todo[:limit]
    print("\npushing %d contacts to GHL...\n" % len(todo))
    created = updated = failed = 0
    log = []

    for i, r in enumerate(todo, 1):
        try:
            hits = find_by_phone(r["phone"]) if r["phone"] else find_by_name(r)
            if hits:
                verb, cid = merge(hits[0], r)
                updated += 1
            else:
                verb, cid = create(r)
                created += 1
            log.append((r["phone"], r["first"] + " " + r["last"], verb, cid, ""))
        except Exception as ex:                                   # noqa: BLE001
            failed += 1
            log.append((r["phone"], r["first"] + " " + r["last"], "FAILED", "", str(ex)[:200]))
            print("  FAILED %-24s %s" % (r["first"] + " " + r["last"], str(ex)[:160]))
        if i % 20 == 0:
            print("  ... %d/%d" % (i, len(todo)))

    print("\ncreated %d | merged into existing %d | failed %d" % (created, updated, failed))
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "import-log.tsv")
    with open(path, "w", encoding="utf-8") as f:
        f.write("phone\tname\tresult\tcontactId\terror\n")
        for row in log:
            f.write("\t".join(str(x) for x in row) + "\n")
    print("log: %s" % path)
    if failed:
        sys.exit(1)


def payload_fields(r, skip=()):
    cf = []
    for name, fid in FIELD.items():
        if name in skip:
            continue
        v = r.get(name, "")
        if isinstance(v, list):
            if v:
                cf.append({"id": fid, "value": v})
        elif v not in ("", None):
            cf.append({"id": fid, "value": str(v)})
    return cf


def find_by_name(r):
    """Only for the phoneless suppression records. Name matching is far too
    loose to merge real buyers on - two different people share a name all the
    time - but here it exists purely to stop a re-run creating the same ban
    twice, and a false positive costs nothing because the record carries no
    contactable data anyway."""
    name = (r["first"] + " " + r["last"]).strip()
    if not name:
        return []
    res = call("POST", "/contacts/search", {
        "locationId": LOCATION, "pageLimit": 20,
        "filters": [{"field": "firstNameLowerCase", "operator": "eq",
                     "value": r["first"].lower()}]})
    return [c for c in (res.get("contacts") or [])
            if not c.get("phone")
            and (c.get("lastName") or "").lower() == r["last"].lower()]


def create(r):
    body = {"locationId": LOCATION,
            "firstName": r["first"], "lastName": r["last"],
            "source": "Master buyer sheet import",
            "customFields": payload_fields(r)}
    if r["phone"]:
        body["phone"] = r["phone"]
    if r["email"]:
        body["email"] = r["email"]
    if r["company"]:
        body["companyName"] = r["company"]
    res = call("POST", "/contacts/", body)
    return "created", (res.get("contact") or {}).get("id", "")


def merge(existing, r):
    """ADD ONLY. A tier, status, or excl_ rule already in GHL is a human's
    decision and outranks anything this sheet says."""
    prior = existing_values(existing)
    cf = []
    for name, fid in FIELD.items():
        v = r.get(name, "")
        have = prior.get(name)
        if name in KEEP and have not in (None, ""):
            continue
        if name in UNION:
            merged = split_multi(have)
            for x in (v if isinstance(v, list) else split_multi(v)):
                if x not in merged:
                    merged.append(x)
            if merged and merged != split_multi(have):
                cf.append({"id": fid, "value": merged})
            continue
        if have not in (None, ""):          # fill blanks only
            continue
        if isinstance(v, list):
            if v:
                cf.append({"id": fid, "value": v})
        elif v not in ("", None):
            cf.append({"id": fid, "value": str(v)})

    body = {}
    if cf:
        body["customFields"] = cf
    for key, val in (("firstName", r["first"]), ("lastName", r["last"]),
                     ("email", r["email"]), ("companyName", r["company"])):
        if val and not existing.get(key):
            body[key] = val
    if not body:
        return "already complete", existing["id"]
    call("PUT", "/contacts/" + existing["id"], body)
    return "merged", existing["id"]


if __name__ == "__main__":
    main()
