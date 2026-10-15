"""Content Tracker sync: D:\\Reels + D:\\Posts  <->  Google Sheet  ->  GHL Social Planner -> Instagram.

Runs every 15 min (Windows Task Scheduler, see install_task.ps1). Each run:
  1. scan   - every reel/post folder on D: gets a row (latest file + caption.txt). Rows that are
              Scheduled/Posted are frozen; Draft/Approved/Failed rows get their file refreshed.
  2. publish- rows with Status=Approved + date (+ time, or Auto = best slot) are uploaded to GHL media and created as a
              scheduled Instagram post (caption from the sheet, BH Properties collab invite,
              optional follow-up comment). Status -> Scheduled. Reels marked "Manual" -> Post Manually.
  1b.unsched- rows moved back to Draft/Skip that still have a GHL post get it deleted from GHL.
  3. track  - Scheduled rows are checked in GHL; once live -> Posted (+ link), errors -> Failed.

  python content_sync.py            # full run
  python content_sync.py --dry-run  # show what would happen, change nothing
"""
import argparse, datetime as dt, glob, json, mimetypes, os, re, sys, traceback
from zoneinfo import ZoneInfo

import gspread
import requests
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SA_KEY = os.path.join(HERE, "..", "foreclosure-agent", "credentials.json")
SHEET_ID = "1wO6LhEfmwL96dnoCTgKda7ck5d2I0yyYchUNgo5a8Co"
TAB = "Content Tracker"
REELS, POSTS = "D:/Reels", "D:/Posts"
TZ = ZoneInfo("America/New_York")

GHL = "https://services.leadconnectorhq.com"
LOCATION = "ib5jEnyqqq06FIEqlVGs"                                   # Buying Hero sub-account
IG_ACCOUNT = "6ad13233873d2c41e704101d_ib5jEnyqqq06FIEqlVGs_17841401750000052"  # @jorgesiverio.rei
USER_ID = "Zr9vmjZQ5YnqQ5dz3HHa"                                     # Jorge (GHL user)
DEFAULT_COLLAB = open(os.path.join(HERE, "collab.txt")).read().strip() if os.path.exists(
    os.path.join(HERE, "collab.txt")) else ""                        # BH Properties IG handle

HEADERS = ["ID", "Type", "Title", "Status", "Post Date", "Post Time (ET)", "Reel Audio", "Collab",
           "Caption", "Follow-up Comment", "File", "Version", "GHL Post ID", "Post Link", "Last Sync / Notes"]
C = {h: i for i, h in enumerate(HEADERS)}
STATUSES = ["Draft", "Approved", "Scheduled", "Posted", "Post Manually", "Failed", "Skip"]
AUDIO = ["Auto-post", "Manual (trending audio)"]
AUTO_TIME = "Auto (best time)"
TIMES = [AUTO_TIME] + [f"{h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}" for h in range(6, 23) for m in (0, 30)]
DATE_FMT = "%a %b %d, %Y"          # how the date picker cells display, e.g. "Fri Oct 16, 2026"
# Default slots (ET) when Post Time is Auto. Jorge wants late morning / lunch (2026-10-15), so
# reels and posts are staggered 11 AM / 12 PM. Tune with his IG insights after ~20 posts.
BEST_TIME = {("Reel", "weekday"): "11:00 AM", ("Reel", "weekend"): "11:00 AM",
             ("Sold Post", "weekday"): "12:00 PM", ("Sold Post", "weekend"): "12:00 PM"}
FROZEN = {"Scheduled", "Posted", "Post Manually", "Skip"}


def log(msg):
    line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    try:
        print(line)          # no console under pythonw (scheduled task) - log file is the record
    except Exception:
        pass
    with open(os.path.join(HERE, "sync.log"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------- local content ----------
def latest_reel_file(folder):
    out = os.path.join(folder, "output")
    finals = sorted(glob.glob(os.path.join(out, "final*.mp4")), key=os.path.getmtime)
    if finals:
        return finals[-1], "final"
    vs = []
    for f in glob.glob(os.path.join(out, "v*.mp4")):
        m = re.match(r"v(\d+)", os.path.basename(f))
        if m:
            vs.append((int(m.group(1)), f))
    if vs:
        n, f = max(vs)
        return f, f"v{n}"
    return None, None


def scan():
    items = []
    for d in sorted(glob.glob(os.path.join(REELS, "*"))):
        f, ver = latest_reel_file(d)
        if f:
            items.append({"id": os.path.basename(d), "type": "Reel", "dir": d, "file": f, "version": ver})
    for d in sorted(glob.glob(os.path.join(POSTS, "*"))):
        f = os.path.join(d, "sold_post.png")
        if os.path.exists(f):
            ver = dt.datetime.fromtimestamp(os.path.getmtime(f)).strftime("%m/%d %H:%M")
            items.append({"id": os.path.basename(d), "type": "Sold Post", "dir": d, "file": f, "version": ver})
    for it in items:
        cap = os.path.join(it["dir"], "caption.txt")
        it["caption"] = open(cap, encoding="utf-8").read().strip() if os.path.exists(cap) else ""
        first = it["caption"].splitlines()[0] if it["caption"] else it["id"]
        it["title"] = first[:70]
    return items


# ---------- sheet ----------
def open_tab(gc):
    sh = gc.open_by_key(SHEET_ID)
    try:
        return sh, sh.worksheet(TAB)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(TAB, rows=200, cols=len(HEADERS))
        setup_tab(sh, ws)
        return sh, ws


def refresh_dropdowns(sh, ws):
    """Post Date = Google's date picker (double-click a cell); Post Time = list with Auto first."""
    sid = ws.id
    col = lambda c: {"sheetId": sid, "startRowIndex": 1, "endRowIndex": 1000, "startColumnIndex": c, "endColumnIndex": c + 1}
    sh.batch_update({"requests": [
        {"setDataValidation": {"range": col(C["Post Date"]),
                               "rule": {"condition": {"type": "DATE_IS_VALID"}, "strict": True}}},
        {"repeatCell": {"range": col(C["Post Date"]),
                        "cell": {"userEnteredFormat": {"numberFormat": {"type": "DATE", "pattern": "ddd mmm d, yyyy"}}},
                        "fields": "userEnteredFormat.numberFormat"}},
        {"setDataValidation": {"range": col(C["Post Time (ET)"]),
                               "rule": {"condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": v} for v in TIMES]},
                                        "showCustomUi": True, "strict": True}}},
    ]})


def setup_tab(sh, ws):
    ws.update([HEADERS], "A1")
    sid = ws.id

    def dv(col, values):
        return {"setDataValidation": {
            "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": 1000, "startColumnIndex": col, "endColumnIndex": col + 1},
            "rule": {"condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": v} for v in values]},
                     "showCustomUi": True, "strict": True}}}

    widths = [200, 90, 260, 120, 110, 120, 190, 150, 420, 260, 300, 70, 210, 220, 300]
    reqs = [
        {"updateSheetProperties": {"properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 1}},
                                   "fields": "gridProperties.frozenRowCount"}},
        {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
                        "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0, "green": 0.514, "blue": 0.792},
                                                       "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                                                       "wrapStrategy": "WRAP", "verticalAlignment": "MIDDLE"}},
                        "fields": "userEnteredFormat"}},
        {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": 1000},
                        "cell": {"userEnteredFormat": {"verticalAlignment": "TOP", "wrapStrategy": "CLIP"}},
                        "fields": "userEnteredFormat(verticalAlignment,wrapStrategy)"}},
        dv(C["Status"], STATUSES), dv(C["Reel Audio"], AUDIO),
    ]
    for i, w in enumerate(widths):
        reqs.append({"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
                                                   "properties": {"pixelSize": w}, "fields": "pixelSize"}})
    colours = {"Approved": (1.0, 0.95, 0.70), "Scheduled": (0.80, 0.90, 1.0), "Posted": (0.80, 0.94, 0.80),
               "Failed": (1.0, 0.80, 0.80), "Post Manually": (0.95, 0.85, 1.0)}
    for st, (r, g, b) in colours.items():
        reqs.append({"addConditionalFormatRule": {"index": 0, "rule": {
            "ranges": [{"sheetId": sid, "startRowIndex": 1, "endRowIndex": 1000, "startColumnIndex": 0, "endColumnIndex": len(HEADERS)}],
            "booleanRule": {"condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": f'=$D2="{st}"'}]},
                            "format": {"backgroundColor": {"red": r, "green": g, "blue": b}}}}}})
    sh.batch_update({"requests": reqs})


def resolve_time(kind, date_s, time_s):
    """Blank or Auto -> best slot for this content type and day of week."""
    time_s = (time_s or "").strip()
    if time_s and time_s != AUTO_TIME:
        return time_s
    d = parse_date(date_s)
    if not d:
        return ""
    return BEST_TIME[(kind, "weekend" if d.weekday() >= 5 else "weekday")]


def parse_date(date_s):
    for fmt in (DATE_FMT, "%a %b %d, %Y", "%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return dt.datetime.strptime((date_s or "").strip(), fmt).date()
        except ValueError:
            pass
    return None


def parse_when(date_s, time_s):
    date_s, time_s = (date_s or "").strip(), (time_s or "").strip()
    if not date_s or not time_s:
        return None
    d = None
    for fmt in ("%a %b %d, %Y", "%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%b %d, %Y"):
        try:
            d = dt.datetime.strptime(date_s, fmt).date()
            break
        except ValueError:
            pass
    t = dt.datetime.strptime(time_s.upper().replace(".", ""), "%I:%M %p").time()
    return dt.datetime.combine(d, t, TZ) if d else None


# ---------- GHL ----------
def ghl_token():
    p = os.path.join(HERE, ".ghl_token")
    return open(p).read().strip() if os.path.exists(p) else None


def ghl(method, path, token, **kw):
    h = {"Authorization": f"Bearer {token}", "Version": "2021-07-28", "Accept": "application/json"}
    r = requests.request(method, GHL + path, headers=h, timeout=600, **kw)
    if r.status_code >= 300:
        raise RuntimeError(f"GHL {method} {path} -> {r.status_code}: {r.text[:400]}")
    return r.json() if r.text else {}


def upload_media(path, token):
    send = path
    if path.lower().endswith(".png"):           # Instagram feed posts must be JPEG
        send = os.path.splitext(path)[0] + "_ig.jpg"
        Image.open(path).convert("RGB").save(send, "JPEG", quality=95)
    mime = mimetypes.guess_type(send)[0] or "application/octet-stream"
    with open(send, "rb") as f:
        res = ghl("POST", "/medias/upload-file", token,
                  files={"file": (os.path.basename(send), f, mime)}, data={"hosted": "false", "name": os.path.basename(send)})
    url = res.get("url") or res.get("fileUrl")
    if not url:
        raise RuntimeError(f"media upload returned no url: {json.dumps(res)[:300]}")
    return url, ("video/mp4" if mime.startswith("video") else "image/jpeg")


def find_key(obj, *keys):
    """Depth-first search for the first non-empty value under any of `keys` (GHL nests responses)."""
    if isinstance(obj, dict):
        for k in keys:
            if obj.get(k):
                return obj[k]
        for v in obj.values():
            hit = find_key(v, *keys)
            if hit:
                return hit
    elif isinstance(obj, list):
        for v in obj:
            hit = find_key(v, *keys)
            if hit:
                return hit
    return None


def schedule(row, when, token):
    is_reel = row[C["Type"]] == "Reel"
    url, mtype = upload_media(row[C["File"]], token)
    ig = {"type": "reel" if is_reel else "post"}
    if is_reel:
        ig["showOnFeed"] = True
    collab = row[C["Collab"]].strip().lstrip("@")
    if collab:
        ig["collaborators"] = {IG_ACCOUNT: [collab]}
    body = {"accountIds": [IG_ACCOUNT], "summary": row[C["Caption"]], "media": [{"url": url, "type": mtype}],
            "status": "scheduled", "scheduleDate": when.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "type": "reel" if is_reel else "post", "userId": USER_ID, "createdBy": USER_ID,
            "instagramPostDetails": ig}
    if row[C["Follow-up Comment"]].strip():
        body["followUpComment"] = row[C["Follow-up Comment"]].strip()
    res = ghl("POST", f"/social-media-posting/{LOCATION}/posts", token, json=body)
    pid = find_key(res, "_id", "id", "postId")
    if not pid:
        raise RuntimeError(f"create post returned no id: {json.dumps(res)[:300]}")
    return pid


def check(pid, token):
    res = ghl("GET", f"/social-media-posting/{LOCATION}/posts/{pid}", token)
    post = find_key(res, "post") or res
    status = (post.get("status") if isinstance(post, dict) else None) or find_key(res, "status")
    link = find_key(res, "permalink", "postUrl", "publishedUrl", "publishedPostUrl")
    err = find_key(res, "error", "errorMessage", "failedReason")
    return status, link, err


# ---------- main ----------
def validate(row, when):
    cap = row[C["Caption"]]
    if not row[C["File"]] or not os.path.exists(row[C["File"]]):
        return "File not found on D: (is the drive connected?)"
    if when is None:
        return "Pick a Post Date, then set Approved again"
    if when < dt.datetime.now(TZ) + dt.timedelta(minutes=10):
        return "Post date/time is in the past (or <10 min away) - pick a later time"
    if not cap.strip():
        return "Caption is empty"
    if len(cap) > 2200:
        return f"Caption is {len(cap)} chars - Instagram max is 2,200"
    if len(re.findall(r"#\w", cap)) > 30:
        return "More than 30 hashtags - Instagram will reject it"
    return None


def run(dry):
    gc = gspread.service_account(filename=SA_KEY)
    sh, ws = open_tab(gc)
    if not dry:
        refresh_dropdowns(sh, ws)
        from overview import build_overview
        build_overview(sh)                      # no-op if the Overview tab already exists
    rows = ws.get_all_values()[1:]
    rows = [r + [""] * (len(HEADERS) - len(r)) for r in rows]
    by_id = {r[C["ID"]]: i for i, r in enumerate(rows) if r[C["ID"]]}
    now = f"{dt.datetime.now(TZ):%m/%d %I:%M %p}"
    updates, appends = {}, []

    def setcell(i, col, val):
        if rows[i][C[col]] != val:
            rows[i][C[col]] = val
            updates[(i, C[col])] = val

    # 1. scan
    for it in scan():
        if it["id"] not in by_id:
            r = [""] * len(HEADERS)
            r[C["ID"]], r[C["Type"]], r[C["Title"]], r[C["Status"]] = it["id"], it["type"], it["title"], "Draft"
            r[C["Reel Audio"]] = "Auto-post" if it["type"] == "Reel" else ""
            r[C["Post Time (ET)"]] = AUTO_TIME
            r[C["Collab"]], r[C["Caption"]] = DEFAULT_COLLAB, it["caption"]
            r[C["File"]], r[C["Version"]], r[C["Last Sync / Notes"]] = it["file"].replace("\\", "/"), it["version"], f"Added {now}"
            appends.append(r)
            log(f"new row {it['id']} ({it['type']}, {it['version']})")
            continue
        i = by_id[it["id"]]
        if rows[i][C["Status"]] in FROZEN:
            continue
        setcell(i, "File", it["file"].replace("\\", "/"))
        setcell(i, "Version", it["version"])
        if not rows[i][C["Post Time (ET)"]].strip():
            setcell(i, "Post Time (ET)", AUTO_TIME)
        if not rows[i][C["Caption"]].strip() and it["caption"]:
            setcell(i, "Caption", it["caption"])

    token = ghl_token()
    # 1b. unschedule: a row moved back to Draft/Skip pulls its pending post out of GHL
    for i, r in enumerate(rows):
        pid = r[C["GHL Post ID"]]
        if r[C["Status"]] not in ("Draft", "Skip") or not pid or not token:
            continue
        if dry:
            log(f"[dry-run] would unschedule {r[C['ID']]} ({pid})")
            continue
        try:
            post = ghl("GET", f"/social-media-posting/{LOCATION}/posts/{pid}", token)["results"]["post"]
            if post.get("status") == "published":
                setcell(i, "Last Sync / Notes", f"{now}: already posted on Instagram - delete it in the IG app if needed")
                continue
            if not post.get("deleted"):
                ghl("POST", f"/social-media-posting/{LOCATION}/posts/bulk-delete", token, json={"postIds": [pid]})
            setcell(i, "GHL Post ID", "")
            setcell(i, "Last Sync / Notes", f"{now}: pulled from the GHL schedule (set Approved again to reschedule)")
            log(f"unscheduled {r[C['ID']]} ({pid})")
        except Exception as e:
            log(f"unschedule {r[C['ID']]} failed: {e}")

    # 2. publish approved
    for i, r in enumerate(rows):
        if r[C["Status"]] != "Approved":
            continue
        if r[C["Type"]] == "Reel" and r[C["Reel Audio"]].startswith("Manual"):
            setcell(i, "Status", "Post Manually")
            setcell(i, "Last Sync / Notes", f"{now}: post from your phone on {r[C['Post Date']]} {r[C['Post Time (ET)']]} (trending audio)")
            continue
        slot = resolve_time(r[C["Type"]], r[C["Post Date"]], r[C["Post Time (ET)"]])
        try:
            when = parse_when(r[C["Post Date"]], slot)
        except ValueError:
            when = None
        problem = validate(r, when)
        if problem:
            setcell(i, "Last Sync / Notes", f"{now}: NOT scheduled - {problem}")
            continue
        if not token:
            setcell(i, "Last Sync / Notes", f"{now}: NOT scheduled - GHL token missing (content-sync/.ghl_token)")
            continue
        if dry:
            log(f"[dry-run] would schedule {r[C['ID']]} for {when:%a %b %d %I:%M %p} ET")
            continue
        try:
            if r[C["GHL Post ID"]]:   # re-approved after a change: replace the old scheduled post
                ghl("POST", f"/social-media-posting/{LOCATION}/posts/bulk-delete", token, json={"postIds": [r[C["GHL Post ID"]]]})
            pid = schedule(r, when, token)
            setcell(i, "GHL Post ID", pid)
            setcell(i, "Status", "Scheduled")
            same_day = [x[C["ID"]] for j, x in enumerate(rows) if j != i and x[C["Status"]] in ("Scheduled", "Posted")
                        and parse_date(x[C["Post Date"]]) == when.date()]
            setcell(i, "Last Sync / Notes", f"{now}: scheduled for {when:%a %b %d %I:%M %p} ET"
                    + (" (auto best time)" if slot != r[C["Post Time (ET)"]].strip() else "")
                    + (f" - heads-up: {', '.join(same_day)} also posts that day" if same_day else "")
                    + (f" - collab invite to @{r[C['Collab']].lstrip('@')} (accept it from that account)" if r[C["Collab"]].strip() else ""))
            log(f"scheduled {r[C['ID']]} -> {pid}")
        except Exception as e:
            setcell(i, "Status", "Failed")
            setcell(i, "Last Sync / Notes", f"{now}: {str(e)[:300]}")
            log(f"FAILED {r[C['ID']]}: {e}")

    # 3. track scheduled
    if token:
        for i, r in enumerate(rows):
            if r[C["Status"]] != "Scheduled" or not r[C["GHL Post ID"]]:
                continue
            try:
                status, link, err = check(r[C["GHL Post ID"]], token)
            except Exception as e:
                log(f"check {r[C['ID']]} failed: {e}")
                continue
            if status == "published":
                setcell(i, "Status", "Posted")
                setcell(i, "Post Link", link or "")
                setcell(i, "Last Sync / Notes", f"{now}: live on Instagram")
                log(f"posted {r[C['ID']]}")
            elif status == "failed":
                setcell(i, "Status", "Failed")
                setcell(i, "Last Sync / Notes", f"{now}: GHL failed - {str(err)[:250]}")

    # write back
    if dry:
        log(f"[dry-run] {len(appends)} new rows, {len(updates)} cell updates")
        return
    if updates:
        ws.batch_update([{"range": gspread.utils.rowcol_to_a1(i + 2, c + 1), "values": [[v]]} for (i, c), v in updates.items()])
    if appends:
        ws.append_rows(appends, value_input_option="RAW")
    log(f"sync ok: {len(appends)} new, {len(updates)} updated")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    try:
        run(ap.parse_args().dry_run)
    except Exception:
        log("ERROR " + traceback.format_exc())
        sys.exit(1)
