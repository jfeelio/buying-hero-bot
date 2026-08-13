"""
Replaces 'Rehab Budget & Project Plan' with two separate tabs:
  1. 'Rehab Budget'  — materials + crew-day labor cost per line item
  2. 'Project Plan'  — day-by-day crew schedule (20 days / 4 weeks)

Crew rates: P1 $300/day | P2 $250/day | P3 $120/day
Roof: $10,000 GC flat (no crew days)
"""

import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleRequest

CREDS_PATH     = r"D:\Dropbox\J Feels\Dev\foreclosure-agent\credentials.json"
SPREADSHEET_ID = "1Slci6swLejIAfu81sVAyx9NCkcPeLEOEVnvXRONdYGk"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

RATE_P1 = 300
RATE_P2 = 250
RATE_P3 = 120

# ── Colors ────────────────────────────────────────────────────────────────────
def rgb(r, g, b):
    return {"red": r/255, "green": g/255, "blue": b/255}

DARK_BLUE    = rgb(13,  71, 161)
MID_BLUE     = rgb(25, 118, 210)
LIGHT_BLUE   = rgb(187, 222, 251)
PALE_BLUE    = rgb(225, 245, 254)
LIGHT_GRAY   = rgb(245, 245, 245)
MED_GRAY     = rgb(224, 224, 224)
WHITE        = rgb(255, 255, 255)
YELLOW       = rgb(255, 249, 196)
GREEN_LIGHT  = rgb(200, 230, 201)
GREEN_DARK   = rgb(27, 94, 32)
ORANGE_DARK  = rgb(230, 81, 0)
ORANGE_LIGHT = rgb(255, 224, 178)
RED_LIGHT    = rgb(255, 205, 210)
PURPLE_LIGHT = rgb(237, 231, 246)

# ── Budget data ───────────────────────────────────────────────────────────────
# (category, item, materials, p1_days, p2_days, p3_days, notes)
BUDGET = [
    # ── ROOF ─────────────────────────────────────────────────────────────────
    ("ROOF",
     "Full roof replacement — GC contracted separately",
     10000, 0, 0, 0,
     "Fixed GC bid — no crew labor. Schedule Week 1 start."),

    # ── DEMO ─────────────────────────────────────────────────────────────────
    ("DEMO",
     "Full demo: floors, bath tile, kitchen, misc drywall",
     100, 2, 2, 2,
     "Day 1–2, all 3 crew. Haul debris to dumpster."),

    # ── FLOORS ───────────────────────────────────────────────────────────────
    ("FLOORS",
     "Subfloor inspection & repairs",
     250, 0, 0, 1.5,
     "P3 solo Day 3–4. Sistering joists, patching rot if found."),
    ("FLOORS",
     "LVP flooring — main structure (~900 sqft incl. quarter-round)",
     2500, 1.5, 1.5, 0,
     "P1+P2, Days 11–12. ~$2.50/sqft material + trim."),
    ("FLOORS",
     "LVP flooring — addition (~200 sqft incl. quarter-round)",
     600, 0, 0.5, 0,
     "P2 solo, Day 12. Level difference cosmetically OK."),

    # ── BATHROOMS ────────────────────────────────────────────────────────────
    ("BATHROOMS",
     "Bath 1 — tile (floor + walls), vanity, shower head, glass door",
     1350, 1, 2, 1,
     "Tile Days 6–8. Vanity/door Day 8. Tile: P2+P3; fixtures: P1."),
    ("BATHROOMS",
     "Bath 2 — tile (floor + walls), vanity, shower head, glass door",
     1350, 1, 2, 1,
     "Tile Days 8–10. Vanity/door Day 13. Same scope as Bath 1."),
    ("BATHROOMS",
     "Master bathroom addition in closet (plumbing rough-in + finish)",
     1950, 2, 1.5, 0,
     "Rough-in Days 3–4 (P1+P2). Tile Day 10 (P3). P1 finish Day 13."),
    ("BATHROOMS",
     "Master bedroom closet creation (framing, drywall, door, shelving)",
     650, 0.5, 1, 0.5,
     "Days 7–8. Framing P1+P2, shelving P3 Day 15."),

    # ── PAINT ────────────────────────────────────────────────────────────────
    ("PAINT",
     "Interior paint — prime + 2 coats all rooms",
     400, 0, 0, 3,
     "P3 solo Days 11–13. Assess on-site — may reduce if walls clean."),
    ("PAINT",
     "Exterior brick — elastomeric white paint",
     600, 1.5, 1.5, 0,
     "P1+P2 Day 14. Use elastomeric masonry paint for longevity."),
    ("PAINT",
     "Shutters, exterior doors, posts — black",
     80, 0, 0, 0.5,
     "P3 half-day, Day 14."),

    # ── KITCHEN ──────────────────────────────────────────────────────────────
    ("KITCHEN",
     "Resurface & paint kitchen cabinets",
     200, 0.5, 1, 0,
     "Days 9–10. Sand, prime, paint. P1+P2."),
    ("KITCHEN",
     "Butcher block countertops (supply + install)",
     800, 0.5, 0, 0,
     "P1 half-day, Day 10."),
    ("KITCHEN",
     "Dishwasher area fix (re-frame, patch)",
     150, 0, 0.5, 0,
     "P2 half-day, Day 10."),
    ("KITCHEN",
     "Backsplash (peel-and-stick or simple tile)",
     150, 0, 0.5, 0,
     "P2 half-day, Day 10."),
    ("KITCHEN",
     "Black hardware — all cabinet pulls + door handles",
     350, 0, 0, 0.5,
     "P3 half-day, Day 15. ~20–25 pieces."),
    ("KITCHEN",
     "Appliances — fridge, stove, dishwasher, microwave (builder-grade)",
     2500, 0.5, 0.5, 0,
     "P1+P2, Day 16. Coordinate delivery in advance."),

    # ── WATER HEATER ─────────────────────────────────────────────────────────
    ("WATER HEATER",
     "New water heater (50-gal unit, supply + install)",
     650, 0.5, 0, 0,
     "P1 half-day, Day 4."),
    ("WATER HEATER",
     "Relocate water heater to laundry area (new lines)",
     200, 1, 0.5, 0,
     "P1+P2, Day 4. PEX/copper re-run. Permit if required."),

    # ── HVAC ─────────────────────────────────────────────────────────────────
    ("HVAC",
     "Interior air handler replacement (if confirmed needed)",
     1500, 1, 0, 0,
     "⚠ Verify age/condition first. P1, Day 5. Skip if not needed."),
    ("HVAC",
     "Mini-split for addition (supply + install) — preferred over duct run",
     900, 0.5, 1, 0,
     "P2 lead, Day 5. Faster and cheaper than extending ductwork."),

    # ── ELECTRICAL ───────────────────────────────────────────────────────────
    ("ELECTRICAL",
     "Panel inspection + circuit upgrades (bath, HVAC, laundry)",
     600, 1, 0, 0,
     "P1, Day 4. Required before closing walls."),
    ("ELECTRICAL",
     "Additional outlets + switches throughout",
     150, 0.5, 0, 0,
     "P1 half-day, Day 4."),
    ("ELECTRICAL",
     "Light fixtures — all rooms (budget black fixtures)",
     700, 1, 0, 0,
     "P1, Day 15. ~8–10 rooms. Coordinate with paint finish."),

    # ── DRYWALL & CARPENTRY ───────────────────────────────────────────────────
    ("DRYWALL & CARPENTRY",
     "Drywall: close rough-in walls + patch holes/damage",
     350, 1, 1.5, 0,
     "P1+P2, Days 6–7. After all rough-in inspections pass."),
    ("DRYWALL & CARPENTRY",
     "Interior doors (replace damaged/mismatched)",
     800, 0.5, 0.5, 0,
     "P1+P2, Day 17. Match black hardware theme."),
    ("DRYWALL & CARPENTRY",
     "Trim & baseboards (replace damaged sections)",
     350, 0, 0.5, 1,
     "P2 Day 13, P3 Day 15. Quarter-round included in flooring line."),

    # ── DRIVEWAY ─────────────────────────────────────────────────────────────
    ("DRIVEWAY",
     "Concrete crack repair + seal (patch approach)",
     350, 0, 0, 1,
     "P3, Day 16. If cracks are structural → escalate to full pour (~$4k–7k add)."),

    # ── SHED ─────────────────────────────────────────────────────────────────
    ("SHED",
     "Repair, patch, and paint shed",
     150, 0, 0, 1,
     "P3, Day 18."),

    # ── LANDSCAPING ──────────────────────────────────────────────────────────
    ("LANDSCAPING",
     "Cut, edge, trim grass — initial cleanup",
     50, 0, 0, 0.5,
     "P3 half-day, Day 17."),
    ("LANDSCAPING",
     "Mulch beds + light landscaping (curb appeal for listing photos)",
     250, 0, 0, 1,
     "P3, Day 17. High visual ROI before photography."),

    # ── MISC ─────────────────────────────────────────────────────────────────
    ("MISC",
     "Permits (all applicable trades — plumbing, electrical, HVAC)",
     1500, 0, 0, 0,
     "Pull before breaking ground. Varies by county."),
    ("MISC",
     "Dumpster rental — 2 pulls (Day 2 and Day 19)",
     1200, 0, 0, 0,
     "20-yard container recommended."),
    ("MISC",
     "Final detail clean (all 3 crew, Day 20)",
     100, 1, 1, 1,
     "Ready for listing photography."),
]

# ── Project Plan data ─────────────────────────────────────────────────────────
# (week, day, p1_task, p2_task, p3_task, notes)
# 6 days/week — Day 6/12/18/24 are Saturdays (lighter/catch-up days)
PLAN = [
    # WEEK 1 — Demo, Rough-in, Structure
    (1,"Day 1 (Mon)",  "Demo: floors, bath tile, kitchen",                   "Demo: floors, bath tile, kitchen",              "Demo: floors, bath tile, kitchen",               "Full tear-out. Fill dumpster."),
    (1,"Day 2 (Tue)",  "Demo cont. + assess subfloor/walls",                 "Demo cont. + assess subfloor/walls",            "Demo cont. + dumpster pull #1",                  "Document all findings with photos."),
    (1,"Day 3 (Wed)",  "Plumbing rough-in: master bath addition + WH lines", "Plumbing rough-in assist",                      "Subfloor inspection + sistering/repairs",        "Rough-in before closing walls."),
    (1,"Day 4 (Thu)",  "WH relocate + new install; electrical panel + circuits", "WH relocation assist; outlet rough-in",     "Subfloor repairs cont.",                         "Coordinate permit inspections."),
    (1,"Day 5 (Fri)",  "HVAC: air handler (if needed); electrical finish",   "HVAC: mini-split install for addition",         "Drywall demo patch prep; misc framing",          "HVAC complete before drywall close."),
    (1,"Day 6 (SAT)",  "Permit inspection coordination; rough-in punch list","Any open rough-in items; material order review","General cleanup + organize materials on-site",   "Lighter day. Confirm all inspections pass before Week 2."),

    # WEEK 2 — Drywall, Baths, Kitchen Structure
    (2,"Day 7 (Mon)",  "Drywall: close rough-in walls",                      "Drywall: close rough-in walls",                 "Bath 1: tile floor + walls start",               "Drywall only after rough-in inspection clears."),
    (2,"Day 8 (Tue)",  "Drywall cont.; master closet framing",               "Master closet drywall + tape/mud",              "Bath 1: tile cont.",                             ""),
    (2,"Day 9 (Wed)",  "Bath 1: vanity, plumbing fixtures, glass door",      "Bath 2: tile floor + walls start",              "Bath 2: tile cont.",                             ""),
    (2,"Day 10 (Thu)", "Kitchen: cabinet resurface + paint",                  "Kitchen: cabinet paint",                        "Bath 2: tile finish",                            "⚠ Order appliances this week — confirm delivery Day 19."),
    (2,"Day 11 (Fri)", "Butcher block countertop measure + install",          "Dishwasher area fix; backsplash",               "Master bath addition: tile start",               ""),
    (2,"Day 12 (SAT)", "Kitchen hardware + final cabinet touch-up",           "Kitchen punch items; backsplash grout finish",  "Master bath addition: tile finish",              "Lighter day. Kitchen and master bath wrapped by end of day."),

    # WEEK 3 — Flooring, Paint, Finishes
    (3,"Day 13 (Mon)", "LVP flooring: main living areas",                    "LVP flooring: main living areas",               "Interior paint: prime all rooms",                "Flooring before vanities and trim."),
    (3,"Day 14 (Tue)", "LVP flooring cont.",                                 "LVP flooring cont.",                            "Interior paint: coat 1",                         ""),
    (3,"Day 15 (Wed)", "Bath 1 + 2: vanity install, glass door, fixtures",   "Trim + baseboards",                             "Interior paint: coat 2 + touch-up",              ""),
    (3,"Day 16 (Thu)", "Exterior brick paint — white (elastomeric)",          "Exterior brick paint — white",                  "Shutters, exterior doors, posts — black",        "Paint shutters after brick dries."),
    (3,"Day 17 (Fri)", "Electrical: light fixtures all rooms",                "Black hardware: all doors + cabinets",          "Master closet: shelving, door, trim",            ""),
    (3,"Day 18 (SAT)", "LVP addition + quarter-round finish",                 "Exterior paint touch-up; any missed areas",     "Interior paint touch-up throughout",             "Lighter day. Use to close out any Week 3 open items."),

    # WEEK 4 — Punch List, Exterior, Final
    (4,"Day 19 (Mon)", "Appliance delivery + install (fridge, stove, DW, microwave)", "Appliance install assist",             "Driveway: crack repair + seal",                  "Confirm delivery window day before."),
    (4,"Day 20 (Tue)", "Interior door install",                               "Interior door install + trim touch-up",         "Landscaping: cut, edge, mulch beds",             ""),
    (4,"Day 21 (Wed)", "Punch list walkthrough — all 3 document issues",      "Punch list fixes",                              "Shed: repair, patch, paint",                     "Photo document every punch list item."),
    (4,"Day 22 (Thu)", "Punch list fixes cont.",                              "Punch list fixes cont.",                        "Dumpster pull #2 + final debris removal",        ""),
    (4,"Day 23 (Fri)", "Final walk-through with owner/partners",              "Remaining punch list items",                    "Exterior final touch-up + curb appeal check",    "Partners sign off before final clean."),
    (4,"Day 24 (SAT)", "Final detail clean",                                  "Final detail clean",                            "Final detail clean",                             "Ready for listing photography."),
]

# ── API helpers ───────────────────────────────────────────────────────────────
def get_token(creds):
    creds.refresh(GoogleRequest())
    return creds.token

def api(creds, method, endpoint, body=None):
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}"
    hdrs = {"Authorization": f"Bearer {get_token(creds)}", "Content-Type": "application/json"}
    resp = getattr(requests, method)(base + endpoint, headers=hdrs, json=body)
    if not resp.ok:
        raise Exception(f"{method.upper()} {endpoint} → {resp.status_code}: {resp.text}")
    return resp.json()

def batch(creds, reqs):
    api(creds, "post", ":batchUpdate", {"requests": reqs})

def write_values(creds, tab, values):
    rng = f"'{tab}'!A1"
    api(creds, "put", f"/values/{rng}?valueInputOption=USER_ENTERED",
        {"range": rng, "values": values})

def get_sheet_list(creds):
    info = api(creds, "get", "")
    return {s["properties"]["title"]: s["properties"]["sheetId"]
            for s in info["sheets"]}

# ── Format helpers ────────────────────────────────────────────────────────────
def cell(sid, r, c, nr=1, nc=1, bg=None, bold=False, sz=None,
         align=None, tc=None, wrap=None, italic=False):
    fmt, fields = {}, []
    if bg:
        fmt["backgroundColor"] = bg; fields.append("backgroundColor")
    tf = {}
    if bold:   tf["bold"] = True
    if sz:     tf["fontSize"] = sz
    if tc:     tf["foregroundColor"] = tc
    if italic: tf["italic"] = True
    if tf:
        fmt["textFormat"] = tf; fields.append("textFormat")
    if align:
        fmt["horizontalAlignment"] = align; fields.append("horizontalAlignment")
    if wrap:
        fmt["wrapStrategy"] = wrap; fields.append("wrapStrategy")
    return {"repeatCell": {
        "range": {"sheetId": sid, "startRowIndex": r, "endRowIndex": r+nr,
                  "startColumnIndex": c, "endColumnIndex": c+nc},
        "cell": {"userEnteredFormat": fmt},
        "fields": "userEnteredFormat(" + ",".join(fields) + ")"
    }}

def merge(sid, r, c, nc):
    return {"mergeCells": {"range": {"sheetId": sid,
        "startRowIndex": r, "endRowIndex": r+1,
        "startColumnIndex": c, "endColumnIndex": c+nc},
        "mergeType": "MERGE_ALL"}}

def col_width(sid, c, px):
    return {"updateDimensionProperties": {
        "range": {"sheetId": sid, "dimension": "COLUMNS",
                  "startIndex": c, "endIndex": c+1},
        "properties": {"pixelSize": px}, "fields": "pixelSize"}}

def row_height(sid, r, px):
    return {"updateDimensionProperties": {
        "range": {"sheetId": sid, "dimension": "ROWS",
                  "startIndex": r, "endIndex": r+1},
        "properties": {"pixelSize": px}, "fields": "pixelSize"}}

def freeze(sid, rows):
    return {"updateSheetProperties": {
        "properties": {"sheetId": sid,
                       "gridProperties": {"frozenRowCount": rows}},
        "fields": "gridProperties.frozenRowCount"}}

def num_fmt(sid, r, c, pattern='"$"#,##0'):
    return {"repeatCell": {
        "range": {"sheetId": sid, "startRowIndex": r, "endRowIndex": r+1,
                  "startColumnIndex": c, "endColumnIndex": c+1},
        "cell": {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": pattern}}},
        "fields": "userEnteredFormat.numberFormat"}}

def border_bottom(sid, r, c, nc, style="SOLID_MEDIUM"):
    return {"updateBorders": {
        "range": {"sheetId": sid, "startRowIndex": r, "endRowIndex": r+1,
                  "startColumnIndex": c, "endColumnIndex": c+nc},
        "bottom": {"style": style, "color": rgb(66, 66, 66)}}}

# ── BUILD BUDGET TAB ──────────────────────────────────────────────────────────
# Labor is driven by actual project plan days (24 days × each crew rate)
# not per-task estimates, so the two tabs stay in sync.
PLAN_DAYS   = 24
LABOR_P1    = PLAN_DAYS * RATE_P1   # 24 × $300 = $7,200
LABOR_P2    = PLAN_DAYS * RATE_P2   # 24 × $250 = $6,000
LABOR_P3    = PLAN_DAYS * RATE_P3   # 24 × $120 = $2,880
TOTAL_LABOR = LABOR_P1 + LABOR_P2 + LABOR_P3  # $16,080

def build_budget(creds, sid):
    rows = []
    NC = 5  # number of columns: Cat | Item | Materials | Total | Notes

    # ── Row 0: Title ──────────────────────────────────────────────────────────
    rows.append(["REHAB BUDGET ESTIMATE", "", "", "", ""])

    # ── Row 1: Property / date ────────────────────────────────────────────────
    rows.append(["Property:", "", "Date:", "2026-03-30", ""])

    # ── Row 2: blank ─────────────────────────────────────────────────────────
    rows.append(["", "", "", "", ""])

    # ── Row 3: Column headers ─────────────────────────────────────────────────
    rows.append(["CATEGORY", "LINE ITEM", "MATERIALS ($)", "TOTAL ($)", "NOTES"])

    # ── Materials line items ──────────────────────────────────────────────────
    DATA_START = 4
    current_cat = None
    row_meta = []

    for (cat, item, mat, p1, p2, p3, note) in BUDGET:
        # Skip roof from materials — it goes in the summary section
        if cat == "ROOF":
            continue
        if cat != current_cat:
            rows.append([cat, "", "", "", ""])
            row_meta.append(("cat", cat))
            current_cat = cat

        rows.append(["", item, mat if mat else "", mat if mat else "", note])
        row_meta.append(("item",))

    # ── Blank separator ───────────────────────────────────────────────────────
    rows.append(["", "", "", "", ""])
    row_meta.append(("space",))

    # ── Materials subtotal ────────────────────────────────────────────────────
    mat_last = len(rows)  # 1-indexed last data row
    mat_sub_r = len(rows) + 1
    rows.append(["", "TOTAL MATERIALS (ex-roof)",
                 f"=SUM(C{DATA_START+1}:C{mat_last})",
                 f"=SUM(C{DATA_START+1}:C{mat_last})", ""])
    row_meta.append(("subtotal",))

    # ── Blank separator ───────────────────────────────────────────────────────
    rows.append(["", "", "", "", ""])
    row_meta.append(("space",))

    # ── Labor section header ──────────────────────────────────────────────────
    rows.append(["CREW LABOR", "", "", "", ""])
    row_meta.append(("section_header", "CREW LABOR"))

    labor_note = f"24 working days (Mon–Sat × 4 weeks) — matches Project Plan tab"
    rows.append(["", "P1 — Main Guy", f"$300/day × {PLAN_DAYS} days", LABOR_P1, labor_note])
    row_meta.append(("labor_item",))
    rows.append(["", "P2 — Second",   f"$250/day × {PLAN_DAYS} days", LABOR_P2, ""])
    row_meta.append(("labor_item",))
    rows.append(["", "P3 — Helper",   f"$120/day × {PLAN_DAYS} days", LABOR_P3, ""])
    row_meta.append(("labor_item",))

    labor_r = len(rows) + 1
    rows.append(["", "TOTAL CREW LABOR", "", TOTAL_LABOR, ""])
    row_meta.append(("subtotal",))

    # ── Blank separator ───────────────────────────────────────────────────────
    rows.append(["", "", "", "", ""])
    row_meta.append(("space",))

    # ── Roof section ──────────────────────────────────────────────────────────
    rows.append(["ROOF", "", "", "", ""])
    row_meta.append(("section_header", "ROOF"))
    rows.append(["", "Full roof replacement — GC contracted separately",
                 "$10,000 fixed bid", 10000,
                 "Separate company. Schedule Week 1 start."])
    row_meta.append(("labor_item",))

    # ── Blank separator ───────────────────────────────────────────────────────
    rows.append(["", "", "", "", ""])
    row_meta.append(("space",))

    # ── Contingency ───────────────────────────────────────────────────────────
    sub_r = len(rows) + 1
    # Contingency = 10% of (materials + labor), excluding roof
    mat_total_ref  = f"C{mat_sub_r}"
    rows.append(["", "Contingency — 10% of materials + labor (ex-roof)",
                 "", f"=ROUND(({mat_total_ref}+{TOTAL_LABOR})*0.10,-2)",
                 "Buffer for unknowns found during demo"])
    row_meta.append(("contingency",))

    # ── Grand total ───────────────────────────────────────────────────────────
    rows.append(["", "", "", "", ""])
    row_meta.append(("space",))

    last_r = len(rows)
    rows.append(["GRAND TOTAL", "",
                 "",
                 f"=SUM(D{mat_sub_r},D{labor_r},{last_r-1},D{last_r})",
                 "Materials + Labor + Roof + Contingency"])
    row_meta.append(("grand_total",))

    # ── Write values ──────────────────────────────────────────────────────────
    write_values(creds, "Rehab Budget", rows)

    # ── Formatting ────────────────────────────────────────────────────────────
    fmt = []

    # Title
    fmt.append(merge(sid, 0, 0, NC))
    fmt.append(cell(sid, 0, 0, nc=NC, bg=DARK_BLUE, bold=True, sz=16,
                    tc=WHITE, align="CENTER"))
    fmt.append(row_height(sid, 0, 45))

    # Property row
    fmt.append(cell(sid, 1, 0, nc=NC, bg=LIGHT_GRAY, bold=True))

    # Column headers (row 3)
    fmt.append(cell(sid, 3, 0, nc=NC, bg=MID_BLUE, bold=True, sz=11,
                    tc=WHITE, align="CENTER"))
    fmt.append(row_height(sid, 3, 32))

    # Column widths: Cat | Item | Materials detail | Total $ | Notes
    widths = [160, 360, 180, 110, 280]
    for i, w in enumerate(widths):
        fmt.append(col_width(sid, i, w))

    # Freeze top 4 rows
    fmt.append(freeze(sid, 4))

    # Data rows
    current_row = DATA_START
    alt = 0
    for meta in row_meta:
        kind = meta[0]
        if kind == "cat":
            fmt.append(merge(sid, current_row, 0, NC))
            fmt.append(cell(sid, current_row, 0, nc=NC,
                            bg=LIGHT_BLUE, bold=True, sz=11))
            fmt.append(border_bottom(sid, current_row, 0, NC, "SOLID_MEDIUM"))
            alt = 0
        elif kind == "item":
            bg = WHITE if alt % 2 == 0 else LIGHT_GRAY
            fmt.append(cell(sid, current_row, 0, nc=NC, bg=bg, wrap="WRAP"))
            fmt.append(num_fmt(sid, current_row, 2))
            fmt.append(num_fmt(sid, current_row, 3))
            alt += 1
        elif kind == "section_header":
            fmt.append(merge(sid, current_row, 0, NC))
            fmt.append(cell(sid, current_row, 0, nc=NC,
                            bg=LIGHT_BLUE, bold=True, sz=11))
            fmt.append(border_bottom(sid, current_row, 0, NC, "SOLID_MEDIUM"))
            alt = 0
        elif kind == "labor_item":
            bg = WHITE if alt % 2 == 0 else LIGHT_GRAY
            fmt.append(cell(sid, current_row, 0, nc=NC, bg=bg, wrap="WRAP"))
            fmt.append(num_fmt(sid, current_row, 3))
            alt += 1
        elif kind == "subtotal":
            fmt.append(cell(sid, current_row, 0, nc=NC,
                            bg=MED_GRAY, bold=True))
            fmt.append(border_bottom(sid, current_row, 0, NC))
            fmt.append(num_fmt(sid, current_row, 2))
            fmt.append(num_fmt(sid, current_row, 3))
        elif kind == "contingency":
            fmt.append(cell(sid, current_row, 0, nc=NC, bg=YELLOW, bold=True))
            fmt.append(num_fmt(sid, current_row, 3))
        elif kind == "grand_total":
            fmt.append(merge(sid, current_row, 0, 2))
            fmt.append(cell(sid, current_row, 0, nc=NC,
                            bg=GREEN_LIGHT, bold=True, sz=13))
            fmt.append(border_bottom(sid, current_row, 0, NC, "SOLID_MEDIUM"))
            fmt.append(num_fmt(sid, current_row, 3))

        current_row += 1

    batch(creds, fmt)
    print(f"  Budget tab: {current_row} rows, {len(fmt)} format ops")


# ── BUILD PROJECT PLAN TAB ────────────────────────────────────────────────────
def build_plan(creds, sid):
    rows = []

    # ── Row 0: Title ──────────────────────────────────────────────────────────
    rows.append(["PROJECT PLAN — 4 WEEKS / 3-PERSON CREW", "", "", "", "", ""])

    # ── Row 1: Sub-header ─────────────────────────────────────────────────────
    rows.append(["Roof: contracted separately — target start Week 1",
                 "", "", "", "", ""])

    # ── Row 2: Rates ─────────────────────────────────────────────────────────
    rows.append(["P1 (Main) = $300/day", "P2 (Second) = $250/day",
                 "P3 (Helper) = $120/day", "All 3 = $670/day", "", ""])

    # ── Row 3: blank ─────────────────────────────────────────────────────────
    rows.append(["", "", "", "", "", ""])

    # ── Row 4: Column headers ─────────────────────────────────────────────────
    rows.append(["WEEK / DAY", "P1 — Main ($300/day)",
                 "P2 — Second ($250/day)", "P3 — Helper ($120/day)",
                 "DAILY LABOR ($)", "NOTES / DEPENDENCIES"])

    current_week = None
    for (week, day, p1t, p2t, p3t, note) in PLAN:
        if week != current_week:
            label = f"WEEK {week}"
            if week == 1:   label += " — Demo, Rough-in, Structure"
            elif week == 2: label += " — Drywall, Baths, Kitchen Structure"
            elif week == 3: label += " — Flooring, Paint, Finishes"
            elif week == 4: label += " — Punch List, Exterior, Final"
            rows.append([label, "", "", "", "", ""])
            current_week = week

        # Calculate daily labor (assumes each person works full day when assigned a non-blank task)
        def has_task(t): return bool(t.strip())
        p1_pay = RATE_P1 if has_task(p1t) else 0
        p2_pay = RATE_P2 if has_task(p2t) else 0
        p3_pay = RATE_P3 if has_task(p3t) else 0
        daily  = p1_pay + p2_pay + p3_pay

        rows.append([day, p1t, p2t, p3t, daily, note])

    # ── Total labor row ───────────────────────────────────────────────────────
    rows.append(["", "", "", "", "", ""])
    n_data = len(rows)
    rows.append(["TOTAL CREW LABOR", "", "", "",
                 f"=SUM(E6:E{n_data})",
                 "Materials + permits + roof billed separately"])

    write_values(creds, "Project Plan", rows)

    # ── Formatting ────────────────────────────────────────────────────────────
    fmt = []

    # Title
    fmt.append(merge(sid, 0, 0, 6))
    fmt.append(cell(sid, 0, 0, nc=6, bg=ORANGE_DARK, bold=True, sz=16,
                    tc=WHITE, align="CENTER"))
    fmt.append(row_height(sid, 0, 45))

    # Sub-header
    fmt.append(merge(sid, 1, 0, 6))
    fmt.append(cell(sid, 1, 0, nc=6, bg=YELLOW, italic=True))

    # Rates row
    fmt.append(cell(sid, 2, 0, nc=6, bg=PALE_BLUE, bold=True))

    # Column headers
    fmt.append(cell(sid, 4, 0, nc=6, bg=DARK_BLUE, bold=True, sz=11,
                    tc=WHITE, align="CENTER"))
    fmt.append(row_height(sid, 4, 32))

    # Column widths: Day | P1 task | P2 task | P3 task | Daily $ | Notes
    widths = [100, 260, 260, 260, 100, 240]
    for i, w in enumerate(widths):
        fmt.append(col_width(sid, i, w))

    fmt.append(freeze(sid, 5))

    WEEK_COLORS = [
        rgb(232, 245, 233),  # Week 1 — light green
        rgb(225, 245, 254),  # Week 2 — light blue
        rgb(243, 229, 245),  # Week 3 — light purple
        rgb(255, 243, 224),  # Week 4 — light orange
    ]

    r = 5  # 0-indexed row after headers
    current_week = None
    alt = 0
    for (week, day, p1t, p2t, p3t, note) in PLAN:
        if week != current_week:
            # Week header row
            fmt.append(merge(sid, r, 0, 6))
            wc = WEEK_COLORS[week - 1]
            fmt.append(cell(sid, r, 0, nc=6, bg=wc, bold=True, sz=12))
            fmt.append(border_bottom(sid, r, 0, 6, "SOLID_MEDIUM"))
            current_week = week
            alt = 0
            r += 1

        wc = WEEK_COLORS[week - 1]
        # Slightly tint alternating rows
        row_bg = wc if alt % 2 == 0 else WHITE
        fmt.append(cell(sid, r, 0, nc=6, bg=row_bg, wrap="WRAP"))
        fmt.append(cell(sid, r, 0, bold=True, align="CENTER"))  # day # bold
        fmt.append(num_fmt(sid, r, 4, '"$"#,##0'))  # daily labor currency
        alt += 1
        r += 1

    # Totals
    fmt.append(cell(sid, r + 1, 0, nc=6, bg=GREEN_LIGHT, bold=True, sz=12))
    fmt.append(num_fmt(sid, r + 1, 4, '"$"#,##0'))

    batch(creds, fmt)
    print(f"  Project Plan tab: {len(rows)} rows written, {len(fmt)} format ops applied")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    creds = service_account.Credentials.from_service_account_file(
        CREDS_PATH, scopes=SCOPES)

    print("Reading existing sheets...")
    sheets = get_sheet_list(creds)
    print(f"  Found: {list(sheets.keys())}")

    delete_reqs = []
    for title in ["Rehab Budget & Project Plan", "Rehab Budget", "Project Plan"]:
        if title in sheets:
            delete_reqs.append({"deleteSheet": {"sheetId": sheets[title]}})
            print(f"  Queued delete: '{title}'")

    add_reqs = [
        {"addSheet": {"properties": {"title": "Rehab Budget",   "index": 0}}},
        {"addSheet": {"properties": {"title": "Project Plan",   "index": 1}}},
    ]

    print("Replacing tabs...")
    result = api(creds, "post", ":batchUpdate",
                 {"requests": delete_reqs + add_reqs})

    new_ids = {}
    for reply in result.get("replies", []):
        if "addSheet" in reply:
            props = reply["addSheet"]["properties"]
            new_ids[props["title"]] = props["sheetId"]
    print(f"  New sheet IDs: {new_ids}")

    print("\nBuilding Rehab Budget tab...")
    build_budget(creds, new_ids["Rehab Budget"])

    print("\nBuilding Project Plan tab...")
    build_plan(creds, new_ids["Project Plan"])

    print(f"\nDone! Open here:")
    print(f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit")


if __name__ == "__main__":
    main()
