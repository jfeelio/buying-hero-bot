"""
Creates a 'Rehab Budget & Project Plan' tab in the Buying Hero spreadsheet.
Spreadsheet: https://docs.google.com/spreadsheets/d/1Slci6swLejIAfu81sVAyx9NCkcPeLEOEVnvXRONdYGk
"""

import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleRequest

CREDS_PATH    = r"D:\Dropbox\J Feels\Dev\foreclosure-agent\credentials.json"
SPREADSHEET_ID = "1Slci6swLejIAfu81sVAyx9NCkcPeLEOEVnvXRONdYGk"
SHEET_TITLE   = "Rehab Budget & Project Plan"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# ── Color palette ────────────────────────────────────────────────────────────
def rgb(r, g, b):
    return {"red": r / 255, "green": g / 255, "blue": b / 255}

DARK_BLUE   = rgb(13,  71, 161)   # section headers
MID_BLUE    = rgb(25, 118, 210)   # column headers
LIGHT_BLUE  = rgb(187, 222, 251)  # category rows
LIGHT_GRAY  = rgb(245, 245, 245)  # alternating rows
WHITE       = rgb(255, 255, 255)
YELLOW      = rgb(255, 249, 196)  # note/open question rows
GREEN_LIGHT = rgb(200, 230, 201)  # totals
ORANGE      = rgb(255, 224, 178)  # project plan header

# ── Budget data ──────────────────────────────────────────────────────────────
# Structure: (category, item, low_est, high_est, notes, open_question)
BUDGET_ROWS = [
    # ROOF
    ("ROOF",            "Roof replacement (main structure)",           8000,  14000, "Hiring separate roofing company",              ""),
    ("ROOF",            "Flat roof on addition — convert to sloped?",  3000,   7000, "OPEN: recommend sloped for longevity + resale", "⚠ Decision needed"),
    ("ROOF",            "Fascia & soffit repair/paint",                 500,   1500, "",                                             ""),

    # FLOORS
    ("FLOORS",          "LVP flooring — main structure",              3500,   6000, "Includes quarter-round trim",                  ""),
    ("FLOORS",          "LVP flooring — addition",                     800,   2000, "May have level difference — cosmetic fix OK",  ""),
    ("FLOORS",          "Subfloor repairs (if needed)",                 500,   1500, "Verify after demo",                           ""),

    # BATHROOMS
    ("BATHROOMS",       "Remodel Bath 1 — tile, vanity, shower head, glass door", 4000, 7000, "",  ""),
    ("BATHROOMS",       "Remodel Bath 2 — tile, vanity, shower head, glass door", 4000, 7000, "",  ""),
    ("BATHROOMS",       "Add bathroom in master bedroom closet",       5000,  10000, "Requires plumbing rough-in",                  ""),
    ("BATHROOMS",       "Create master bedroom closet",                1200,   3000, "Framing, drywall, door, shelving",            ""),
    ("BATHROOMS",       "Plumbing rough-in & permits",                 1500,   3500, "Verify permit requirement",                   ""),

    # PAINT
    ("PAINT",           "Interior paint (touch-up or full repaint)",    800,   2500, "Assess on-site — may only need touch-up",     ""),
    ("PAINT",           "Exterior brick paint — white",                1500,   3500, "Elastomeric masonry paint recommended",       ""),
    ("PAINT",           "Shutters & exterior doors — black",            400,    900, "",                                             ""),
    ("PAINT",           "Posts — black",                                150,    400, "",                                             ""),

    # KITCHEN
    ("KITCHEN",         "Resurface & paint cabinets",                   800,   2000, "Sand, prime, paint + new hardware",           ""),
    ("KITCHEN",         "Replace countertops — butcher block",          600,   1500, "DIY-friendly; includes install",              ""),
    ("KITCHEN",         "Dishwasher area repair/re-frame",              300,    800, "Assess rot or water damage",                  ""),
    ("KITCHEN",         "Black hardware — all doors & cabinets",        200,    500, "Consistent with design theme",               ""),
    ("KITCHEN",         "Appliances — fridge, stove, dishwasher, microwave", 2500, 4500, "Builder-grade stainless or black", ""),
    ("KITCHEN",         "Backsplash (recommended add)",                  400,   900, "Peel-and-stick or tile — high visual ROI",   ""),

    # WATER HEATER
    ("WATER HEATER",    "Replace water heater (new unit)",               800,  1500, "50-gal standard tank recommended",           ""),
    ("WATER HEATER",    "Relocate water heater to laundry area",         500,  1200, "Includes new lines & permit if required",    ""),

    # HEATING & COOLING
    ("HEATING & COOLING","Replace interior air handler",               1500,  3500, "Assess unit age first",                       "⚠ Verify before committing"),
    ("HEATING & COOLING","Extend duct to addition OR install mini-split", 800, 2500, "Mini-split ~$1,500 installed; faster/cheaper option", ""),

    # ELECTRICAL
    ("ELECTRICAL",      "Panel inspection & any needed upgrades",        500,  2000, "Required if adding bathroom or HVAC circuit", ""),
    ("ELECTRICAL",      "Add outlets / switches as needed",              300,   800, "",                                             ""),
    ("ELECTRICAL",      "Install light fixtures (all rooms)",            400,  1000, "Budget black fixtures for cohesive look",    ""),

    # DRYWALL & CARPENTRY
    ("DRYWALL & CARPENTRY", "Drywall repairs (holes, cracks, water damage)", 500, 1500, "Assess after demo",                       ""),
    ("DRYWALL & CARPENTRY", "Interior doors (if replacing)",              800,  2000, "Match black hardware theme",               ""),
    ("DRYWALL & CARPENTRY", "Trim & baseboards",                          400,   900, "Replace damaged sections",                 ""),

    # DRIVEWAY
    ("DRIVEWAY",        "Concrete crack repair (patch & seal)",          500,  1200, "Cost-effective vs full replacement",         ""),
    ("DRIVEWAY",        "Full concrete replacement (if needed)",        3000,  7000, "Only if patch not viable",                   "⚠ Decide after inspection"),

    # SHED
    ("SHED",            "Repair, patch, and paint shed",                 300,   800, "",                                            ""),

    # LANDSCAPING
    ("LANDSCAPING",     "Grass cut & trim (initial cleanup)",            150,   400, "",                                            ""),
    ("LANDSCAPING",     "Ongoing maintenance during rehab",              200,   600, "Keep curb appeal during listing prep",       ""),
    ("LANDSCAPING",     "Mulch beds / light landscaping (recommended)",  300,   700, "High visual ROI for listing photos",         ""),

    # MISC / CONTINGENCY
    ("MISC",            "Permits (all applicable trades)",               500,  2000, "Varies by county — budget conservatively",   ""),
    ("MISC",            "Dumpster / debris removal",                     600,  1200, "1–2 pulls depending on scope",              ""),
    ("MISC",            "Cleaning (final detail clean)",                 300,   600, "",                                            ""),
    ("MISC",            "Contingency (10% of mid-estimate)",               0,      0, "Auto-calculated below",                    ""),
]

# Project plan: (week, day_range, crew, task, category, dependencies)
PROJECT_PLAN = [
    # WEEK 1 — Demo, rough-in, structural
    (1, "Day 1–2",   "All 3",  "Full demo: tear out floors, bathroom tile, kitchen cabinets demo, drywall removal (as needed), shed cleanup", "Demo"),
    (1, "Day 1–2",   "All 3",  "Dumpster pull #1",                               "Logistics"),
    (1, "Day 2–3",   "P1+P2",  "Plumbing rough-in: master bath addition, water heater relocation", "Plumbing"),
    (1, "Day 3–4",   "P1+P2",  "Electrical rough-in: panel check, new circuits for bath/HVAC, outlet adds", "Electrical"),
    (1, "Day 4–5",   "P3",     "Subfloor repairs & leveling",                    "Floors"),
    (1, "Day 5",     "All 3",  "HVAC decision: extend duct vs mini-split install starts", "HVAC"),

    # WEEK 2 — Drywall, bathrooms, kitchen structure
    (2, "Day 6–7",   "P1+P2",  "Drywall: close walls after rough-in, patch all areas",  "Drywall"),
    (2, "Day 6–8",   "P3",     "Bathroom tile: both baths, floor and walls",     "Bathrooms"),
    (2, "Day 8",     "P1",     "Water heater install (new unit, new location)",  "Plumbing"),
    (2, "Day 8–9",   "P2+P3",  "Master closet framing and drywall",             "Carpentry"),
    (2, "Day 9–10",  "P1",     "Air handler replacement (if confirmed needed)",  "HVAC"),
    (2, "Day 9–10",  "P2+P3",  "Kitchen: cabinet resurface/paint, butcher block counters, dishwasher area fix", "Kitchen"),

    # WEEK 3 — Finishes, flooring, paint
    (3, "Day 11–12", "P1+P2",  "LVP flooring install — main structure + addition", "Floors"),
    (3, "Day 11–13", "P3",     "Interior paint: prime + 2 coats all rooms",      "Paint"),
    (3, "Day 12–13", "P1",     "Bathroom vanities, shower heads, glass doors, fixtures install", "Bathrooms"),
    (3, "Day 13",    "P2",     "Kitchen backsplash, hardware, appliance prep",   "Kitchen"),
    (3, "Day 14",    "P2+P3",  "Exterior paint: brick white, shutters/doors/posts black", "Paint"),
    (3, "Day 14–15", "P1",     "Light fixtures, outlet covers, switch plates (all rooms)", "Electrical"),

    # WEEK 4 — Punch list, exterior, final
    (4, "Day 16",    "All 3",  "Appliance delivery & install (fridge, stove, dishwasher, microwave)", "Kitchen"),
    (4, "Day 16",    "P3",     "Driveway: crack repair & seal",                  "Driveway"),
    (4, "Day 16–17", "P1+P2",  "Trim, baseboards, quarter-round flooring finish, interior doors/hardware", "Carpentry"),
    (4, "Day 17",    "P3",     "Landscaping: cut, trim, mulch beds",             "Landscaping"),
    (4, "Day 18",    "P1",     "Shed: patch, repair, paint",                    "Shed"),
    (4, "Day 18–19", "All 3",  "Punch list walkthrough — fix all open items",   "Punch List"),
    (4, "Day 19",    "P2",     "Dumpster pull #2 / final debris removal",       "Logistics"),
    (4, "Day 20",    "All 3",  "Final detail clean — ready for photos",         "Cleanup"),
    (4, "Day 20",    "Owner",  "Photography / listing prep",                    "Disposition"),
]

NOTE_ROWS = {
    "MISC": True,
    "DRIVEWAY": True,
    "HEATING & COOLING": True,
}

# ── Sheets API helpers ────────────────────────────────────────────────────────

def get_token(creds):
    creds.refresh(GoogleRequest())
    return creds.token

def sheets_request(creds, method, endpoint, body=None):
    base = "https://sheets.googleapis.com/v4/spreadsheets"
    url  = f"{base}/{SPREADSHEET_ID}{endpoint}"
    hdrs = {"Authorization": f"Bearer {get_token(creds)}", "Content-Type": "application/json"}
    fn   = getattr(requests, method)
    resp = fn(url, headers=hdrs, json=body)
    if not resp.ok:
        raise Exception(f"{method.upper()} {endpoint} failed {resp.status_code}: {resp.text}")
    return resp.json()


def add_sheet(creds):
    """Add new sheet tab, return sheet_id."""
    body = {"requests": [{"addSheet": {"properties": {"title": SHEET_TITLE}}}]}
    res  = sheets_request(creds, "post", ":batchUpdate", body)
    return res["replies"][0]["addSheet"]["properties"]["sheetId"]


def batch_update(creds, requests_body):
    sheets_request(creds, "post", ":batchUpdate", {"requests": requests_body})


def write_values(creds, range_name, values):
    sheets_request(creds, "put",
        f"/values/{range_name}?valueInputOption=USER_ENTERED",
        {"range": range_name, "values": values})


# ── Build all data rows ───────────────────────────────────────────────────────

def build_budget_values():
    rows = []
    rows.append(["REHAB BUDGET ESTIMATE", "", "", "", "", ""])
    rows.append(["Property:", "", "", "", "Date:", "2026-03-30"])
    rows.append(["", "", "", "", "", ""])
    rows.append(["CATEGORY", "LINE ITEM", "LOW EST ($)", "HIGH EST ($)", "MID EST ($)", "NOTES / FLAGS"])

    categories_seen = set()
    mid_total = 0
    row_meta = []  # track row index → type

    # header rows = 4 (0-indexed rows 0–3)
    data_start = 4

    current_cat = None
    for (cat, item, low, high, note, flag) in BUDGET_ROWS:
        if cat != current_cat:
            row_meta.append(("cat_header", cat))
            rows.append([cat, "", "", "", "", ""])
            current_cat = cat

        mid = (low + high) // 2
        if low > 0 or high > 0:
            mid_total += mid
        note_full = note + (f"  {flag}" if flag else "")
        row_meta.append(("item", cat, low, high, mid))
        rows.append(["", item, low if low else "", high if high else "", f"=(C{len(rows)+1}+D{len(rows)+1})/2" if low else "", note_full])

    # Contingency row (10%)
    contingency_mid = round(mid_total * 0.10, -2)
    row_meta.append(("contingency",))
    rows.append(["", "Contingency (10% of mid-estimate)", "", "", int(contingency_mid), "Budget for unknowns discovered during demo"])

    # Totals
    rows.append(["", "", "", "", "", ""])
    rows.append(["TOTALS", "", f'=SUMIF(B5:B{len(rows)},\"<>\",C5:C{len(rows)})',
                 f'=SUMIF(B5:B{len(rows)},\"<>\",D5:D{len(rows)})',
                 f'=SUMIF(B5:B{len(rows)},\"<>\",E5:E{len(rows)})', ""])

    rows.append(["", "* Roof handled by separate company — include in total budget", "", "", "", ""])
    rows.append(["", "", "", "", "", ""])

    return rows, row_meta, data_start


def build_project_plan_values(start_row):
    rows = []
    rows.append(["", "", "", "", "", ""])
    rows.append(["PROJECT PLAN — 4 WEEKS / 3-PERSON CREW", "", "", "", "", ""])
    rows.append(["", "Roof: contracted separately (schedule Week 1–2 ideally)", "", "", "", ""])
    rows.append(["WEEK", "DAYS", "CREW", "TASK", "CATEGORY", ""])

    for (week, days, crew, task, category) in PROJECT_PLAN:
        rows.append([f"Week {week}", days, crew, task, category, ""])

    return rows


# ── Formatting requests ───────────────────────────────────────────────────────

def cell_fmt(sheet_id, r, c, num_rows=1, num_cols=1,
             bg=None, bold=False, font_size=None, h_align=None,
             text_color=None, borders=None, wrap=None):
    """Build a repeatCell format request."""
    fmt = {}
    if bg:
        fmt["backgroundColor"] = bg
    if text_color:
        fmt["textFormat"] = {"foregroundColor": text_color}
    if bold or font_size:
        tf = fmt.get("textFormat", {})
        if bold:
            tf["bold"] = True
        if font_size:
            tf["fontSize"] = font_size
        fmt["textFormat"] = tf
    if h_align:
        fmt["horizontalAlignment"] = h_align
    if wrap:
        fmt["wrapStrategy"] = wrap

    fields = []
    if bg:             fields.append("backgroundColor")
    if "textFormat" in fmt: fields.append("textFormat")
    if h_align:        fields.append("horizontalAlignment")
    if wrap:           fields.append("wrapStrategy")

    req = {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": r,
                "endRowIndex": r + num_rows,
                "startColumnIndex": c,
                "endColumnIndex": c + num_cols,
            },
            "cell": {"userEnteredFormat": fmt},
            "fields": "userEnteredFormat(" + ",".join(fields) + ")",
        }
    }
    return req


def merge_cells(sheet_id, r, c, num_cols):
    return {
        "mergeCells": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": r,
                "endRowIndex": r + 1,
                "startColumnIndex": c,
                "endColumnIndex": c + num_cols,
            },
            "mergeType": "MERGE_ALL",
        }
    }


def set_col_widths(sheet_id):
    widths = [160, 340, 100, 100, 100, 280]
    reqs = []
    for i, w in enumerate(widths):
        reqs.append({
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                          "startIndex": i, "endIndex": i + 1},
                "properties": {"pixelSize": w},
                "fields": "pixelSize",
            }
        })
    return reqs


def freeze_rows(sheet_id, num_rows):
    return {
        "updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": num_rows}},
            "fields": "gridProperties.frozenRowCount",
        }
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    creds = service_account.Credentials.from_service_account_file(CREDS_PATH, scopes=SCOPES)

    print("Creating new sheet tab...")
    sheet_id = add_sheet(creds)
    print(f"Sheet ID: {sheet_id}")

    print("Building data...")
    budget_rows, row_meta, data_start = build_budget_values()
    plan_start_offset = len(budget_rows)
    plan_rows = build_project_plan_values(plan_start_offset + 1)

    all_rows = budget_rows + plan_rows

    print(f"Writing {len(all_rows)} rows...")
    range_name = f"'{SHEET_TITLE}'!A1"
    write_values(creds, range_name, all_rows)

    print("Applying formatting...")
    fmt_reqs = []

    # ── Title row ─────────────────────────────────────────────────────────────
    fmt_reqs.append(merge_cells(sheet_id, 0, 0, 6))
    fmt_reqs.append(cell_fmt(sheet_id, 0, 0, 1, 6, bg=DARK_BLUE,
                             bold=True, font_size=16,
                             text_color=WHITE, h_align="CENTER"))

    # ── Property / date row ───────────────────────────────────────────────────
    fmt_reqs.append(cell_fmt(sheet_id, 1, 0, 1, 6, bg=LIGHT_GRAY, bold=True))

    # ── Column header row (row 3, index 3) ───────────────────────────────────
    fmt_reqs.append(cell_fmt(sheet_id, 3, 0, 1, 6, bg=MID_BLUE,
                             bold=True, font_size=11,
                             text_color=WHITE, h_align="CENTER"))

    # ── Budget data rows ──────────────────────────────────────────────────────
    current_row = data_start  # row index 4
    current_cat = None
    alternator  = 0

    for meta in row_meta:
        if meta[0] == "cat_header":
            cat = meta[1]
            fmt_reqs.append(merge_cells(sheet_id, current_row, 0, 6))
            fmt_reqs.append(cell_fmt(sheet_id, current_row, 0, 1, 6,
                                     bg=LIGHT_BLUE, bold=True, font_size=11))
            current_cat = cat
            alternator  = 0
            current_row += 1
        elif meta[0] == "item":
            cat = meta[1]
            bg  = WHITE if alternator % 2 == 0 else LIGHT_GRAY
            fmt_reqs.append(cell_fmt(sheet_id, current_row, 0, 1, 6, bg=bg, wrap="WRAP"))
            # Number format for cost columns
            for col in [2, 3, 4]:
                fmt_reqs.append({
                    "repeatCell": {
                        "range": {"sheetId": sheet_id,
                                  "startRowIndex": current_row, "endRowIndex": current_row + 1,
                                  "startColumnIndex": col, "endColumnIndex": col + 1},
                        "cell": {"userEnteredFormat": {
                            "numberFormat": {"type": "CURRENCY", "pattern": '"$"#,##0'},
                        }},
                        "fields": "userEnteredFormat.numberFormat",
                    }
                })
            alternator += 1
            current_row += 1
        elif meta[0] == "contingency":
            fmt_reqs.append(cell_fmt(sheet_id, current_row, 0, 1, 6,
                                     bg=YELLOW, bold=True))
            fmt_reqs.append({
                "repeatCell": {
                    "range": {"sheetId": sheet_id,
                              "startRowIndex": current_row, "endRowIndex": current_row + 1,
                              "startColumnIndex": 4, "endColumnIndex": 5},
                    "cell": {"userEnteredFormat": {
                        "numberFormat": {"type": "CURRENCY", "pattern": '"$"#,##0'},
                    }},
                    "fields": "userEnteredFormat.numberFormat",
                }
            })
            current_row += 1

    # ── Totals row ────────────────────────────────────────────────────────────
    totals_row = current_row + 1  # blank row then totals
    fmt_reqs.append(cell_fmt(sheet_id, totals_row, 0, 1, 6,
                             bg=GREEN_LIGHT, bold=True, font_size=12))
    for col in [2, 3, 4]:
        fmt_reqs.append({
            "repeatCell": {
                "range": {"sheetId": sheet_id,
                          "startRowIndex": totals_row, "endRowIndex": totals_row + 1,
                          "startColumnIndex": col, "endColumnIndex": col + 1},
                "cell": {"userEnteredFormat": {
                    "numberFormat": {"type": "CURRENCY", "pattern": '"$"#,##0'},
                }},
                "fields": "userEnteredFormat.numberFormat",
            }
        })

    # ── Project plan section ──────────────────────────────────────────────────
    plan_base = plan_start_offset   # row index where plan starts
    # Plan title
    fmt_reqs.append(merge_cells(sheet_id, plan_base + 1, 0, 6))
    fmt_reqs.append(cell_fmt(sheet_id, plan_base + 1, 0, 1, 6,
                             bg=ORANGE, bold=True, font_size=14, h_align="CENTER"))
    # Plan sub-note
    fmt_reqs.append(cell_fmt(sheet_id, plan_base + 2, 0, 1, 6,
                             bg=YELLOW, bold=False))
    # Plan column headers
    fmt_reqs.append(cell_fmt(sheet_id, plan_base + 3, 0, 1, 6,
                             bg=MID_BLUE, bold=True, text_color=WHITE, h_align="CENTER"))

    # Plan data rows — alternate + week banding
    current_week = None
    for i, row in enumerate(PROJECT_PLAN):
        week = row[0]
        ri   = plan_base + 4 + i
        if week != current_week:
            current_week = week
            bg = LIGHT_BLUE if week % 2 == 1 else rgb(225, 245, 254)
        else:
            bg = WHITE if i % 2 == 0 else LIGHT_GRAY
        fmt_reqs.append(cell_fmt(sheet_id, ri, 0, 1, 6, bg=bg, wrap="WRAP"))

    # ── Freeze top 4 rows, set col widths ────────────────────────────────────
    fmt_reqs.append(freeze_rows(sheet_id, 4))
    fmt_reqs.extend(set_col_widths(sheet_id))

    # Send in chunks of 50
    chunk = 50
    for i in range(0, len(fmt_reqs), chunk):
        batch_update(creds, fmt_reqs[i:i + chunk])
        print(f"  Formatting batch {i//chunk + 1}/{(len(fmt_reqs)-1)//chunk + 1} done")

    print(f"\nDone! Open the tab here:")
    print(f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit")


if __name__ == "__main__":
    main()
