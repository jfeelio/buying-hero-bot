"""
Creates a new Google Sheet: Comparative Market Analysis (CMA) template.
Sections:
  1. Subject Property
  2. Comparable Sales (5 comps)
  3. Comp Summary (min/max/avg/median per key metric)
  4. ARV Estimate (conservative / mid / aggressive + selected)
  5. MAO Calculator (78% rule, repairs, $25K assignment fee)
  6. Deal Decision (spread vs. $12K minimum)

Run once — outputs the sheet URL at the end.
"""

import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleRequest

CREDS_PATH     = r"D:\Dropbox\J Feels\Dev\foreclosure-agent\credentials.json"
SPREADSHEET_ID = "1Slci6swLejIAfu81sVAyx9NCkcPeLEOEVnvXRONdYGk"
TAB_NAME       = "CMA Template"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

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
GREEN_DARK   = rgb(27,  94,  32)
ORANGE_DARK  = rgb(230, 81,   0)
ORANGE_LIGHT = rgb(255, 224, 178)
RED_LIGHT    = rgb(255, 205, 210)
RED_DARK     = rgb(183,  28,  28)

# ── API helpers ───────────────────────────────────────────────────────────────
def get_token(creds):
    creds.refresh(GoogleRequest())
    return creds.token

def sheets_api(creds, method, endpoint, body=None):
    base = "https://sheets.googleapis.com/v4/spreadsheets"
    hdrs = {"Authorization": f"Bearer {get_token(creds)}", "Content-Type": "application/json"}
    resp = getattr(requests, method)(base + endpoint, headers=hdrs, json=body)
    if not resp.ok:
        raise Exception(f"{method.upper()} {endpoint} → {resp.status_code}: {resp.text}")
    return resp.json()

def batch(creds, spread_id, reqs):
    sheets_api(creds, "post", f"/{spread_id}:batchUpdate", {"requests": reqs})

def write_values(creds, spread_id, tab, values):
    rng = f"'{tab}'!A1"
    sheets_api(creds, "put",
               f"/{spread_id}/values/{rng}?valueInputOption=USER_ENTERED",
               {"range": rng, "values": values})

# ── Format helpers (tab_id = integer sheet tab ID used in sheetId fields) ─────
def cell(tab_id, r, c, nr=1, nc=1, bg=None, bold=False, sz=None,
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
        "range": {"sheetId": tab_id, "startRowIndex": r, "endRowIndex": r+nr,
                  "startColumnIndex": c, "endColumnIndex": c+nc},
        "cell": {"userEnteredFormat": fmt},
        "fields": "userEnteredFormat(" + ",".join(fields) + ")"
    }}

def merge(tab_id, r, c, nc):
    return {"mergeCells": {"range": {"sheetId": tab_id,
        "startRowIndex": r, "endRowIndex": r+1,
        "startColumnIndex": c, "endColumnIndex": c+nc},
        "mergeType": "MERGE_ALL"}}

def col_width(tab_id, c, px):
    return {"updateDimensionProperties": {
        "range": {"sheetId": tab_id, "dimension": "COLUMNS",
                  "startIndex": c, "endIndex": c+1},
        "properties": {"pixelSize": px}, "fields": "pixelSize"}}

def row_height(tab_id, r, px):
    return {"updateDimensionProperties": {
        "range": {"sheetId": tab_id, "dimension": "ROWS",
                  "startIndex": r, "endIndex": r+1},
        "properties": {"pixelSize": px}, "fields": "pixelSize"}}

def freeze(tab_id, rows):
    return {"updateSheetProperties": {
        "properties": {"sheetId": tab_id,
                       "gridProperties": {"frozenRowCount": rows}},
        "fields": "gridProperties.frozenRowCount"}}

def currency_fmt(tab_id, r, c, nr=1, nc=1):
    return {"repeatCell": {
        "range": {"sheetId": tab_id, "startRowIndex": r, "endRowIndex": r+nr,
                  "startColumnIndex": c, "endColumnIndex": c+nc},
        "cell": {"userEnteredFormat": {"numberFormat": {"type": "CURRENCY", "pattern": '"$"#,##0'}}},
        "fields": "userEnteredFormat.numberFormat"}}

def pct_fmt(tab_id, r, c, nr=1, nc=1):
    return {"repeatCell": {
        "range": {"sheetId": tab_id, "startRowIndex": r, "endRowIndex": r+nr,
                  "startColumnIndex": c, "endColumnIndex": c+nc},
        "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "0.0%"}}},
        "fields": "userEnteredFormat.numberFormat"}}

def number_fmt(tab_id, r, c, nr=1, nc=1, pattern="#,##0"):
    return {"repeatCell": {
        "range": {"sheetId": tab_id, "startRowIndex": r, "endRowIndex": r+nr,
                  "startColumnIndex": c, "endColumnIndex": c+nc},
        "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": pattern}}},
        "fields": "userEnteredFormat.numberFormat"}}

def border_bottom(tab_id, r, c, nc, style="SOLID_MEDIUM"):
    return {"updateBorders": {
        "range": {"sheetId": tab_id, "startRowIndex": r, "endRowIndex": r+1,
                  "startColumnIndex": c, "endColumnIndex": c+nc},
        "bottom": {"style": style, "color": rgb(66, 66, 66)}}}

def border_all(tab_id, r, c, nr, nc, style="SOLID"):
    return {"updateBorders": {
        "range": {"sheetId": tab_id, "startRowIndex": r, "endRowIndex": r+nr,
                  "startColumnIndex": c, "endColumnIndex": c+nc},
        "top":    {"style": style, "color": rgb(189, 189, 189)},
        "bottom": {"style": style, "color": rgb(189, 189, 189)},
        "left":   {"style": style, "color": rgb(189, 189, 189)},
        "right":  {"style": style, "color": rgb(189, 189, 189)},
        "innerHorizontal": {"style": style, "color": rgb(189, 189, 189)},
        "innerVertical":   {"style": style, "color": rgb(189, 189, 189)},
    }}

def dropdown(tab_id, r, c, options):
    values = [{"userEnteredValue": o} for o in options]
    return {"setDataValidation": {
        "range": {"sheetId": tab_id, "startRowIndex": r, "endRowIndex": r+1,
                  "startColumnIndex": c, "endColumnIndex": c+1},
        "rule": {"condition": {"type": "ONE_OF_LIST", "values": values},
                 "showCustomUi": True, "strict": False}
    }}

# ── CMA Tab ───────────────────────────────────────────────────────────────────
# Column layout (A=0 … K=10):
#   A : Field label
#   B : Subject property value / formula result / input
#   C–G: Comp 1–5
#   H : MIN summary
#   I : MAX summary
#   J : AVG summary
#   K : MEDIAN summary

NC_TOTAL = 12   # columns A–L

def col_letter(i):
    return chr(ord("A") + i)

def comp_range(row_1idx):
    """Returns e.g. C10:G10 for the 5 comp cells in a row."""
    return f"C{row_1idx}:G{row_1idx}"


def build_cma(creds, spread_id, tab_id):
    """
    spread_id : string spreadsheet ID (for API calls)
    tab_id    : integer sheet tab ID (for format range sheetId fields)
    """
    T = tab_id   # short alias used in all format helper calls
    fmt    = []
    values = []

    def R():
        return len(values) + 1  # next 1-indexed row number (before appending)

    def add(row):
        values.append(row)
        return len(values)  # returns 1-indexed row just added

    def pad(row, total=NC_TOTAL):
        return row + [""] * (total - len(row))

    # ──────────────────────────────────────────────────────────────────────────
    # ROW 1 — Main Title
    # ──────────────────────────────────────────────────────────────────────────
    TITLE_ROW = add(pad(["COMPARATIVE MARKET ANALYSIS (CMA)"]))
    fmt += [
        merge(T, TITLE_ROW-1, 0, NC_TOTAL),
        cell(T, TITLE_ROW-1, 0, nc=NC_TOTAL, bg=DARK_BLUE, bold=True, sz=18,
             tc=WHITE, align="CENTER"),
        row_height(T, TITLE_ROW-1, 50),
    ]

    # ── ROW 2 — Meta: address / date / analyst ────────────────────────────────
    META_ROW = add(pad(["Property Address:", "", "Date:", "", "Analyst:", ""]))
    fmt += [
        cell(T, META_ROW-1, 0, nc=NC_TOTAL, bg=PALE_BLUE),
        cell(T, META_ROW-1, 0, bold=True),
        cell(T, META_ROW-1, 2, bold=True),
        cell(T, META_ROW-1, 4, bold=True),
        row_height(T, META_ROW-1, 28),
    ]

    add(pad([""]))  # spacer

    # ──────────────────────────────────────────────────────────────────────────
    # SECTION: SUBJECT PROPERTY
    # ──────────────────────────────────────────────────────────────────────────
    SUBJ_HDR = add(pad(["SUBJECT PROPERTY"]))
    fmt += [
        merge(T, SUBJ_HDR-1, 0, NC_TOTAL),
        cell(T, SUBJ_HDR-1, 0, nc=NC_TOTAL, bg=MID_BLUE, bold=True, sz=12, tc=WHITE),
        border_bottom(T, SUBJ_HDR-1, 0, NC_TOTAL),
        row_height(T, SUBJ_HDR-1, 32),
    ]

    SUBJ_HEAD = add(pad(["Field", "Value"]))
    fmt += [
        cell(T, SUBJ_HEAD-1, 0, nc=NC_TOTAL, bg=LIGHT_BLUE, bold=True),
        row_height(T, SUBJ_HEAD-1, 26),
    ]

    subj_fields = [
        ("Address",         ""),
        ("City / Zip",      ""),
        ("Beds",            ""),
        ("Baths",           ""),
        ("Sqft (Living)",   ""),
        ("Lot Size",        ""),
        ("Year Built",      ""),
        ("Condition",       ""),
        ("Asking Price",    ""),
        ("Last Sale Price", ""),
        ("Last Sale Date",  ""),
        ("Notes",           ""),
    ]

    SUBJ_DATA_START = R()
    for i, (field, val) in enumerate(subj_fields):
        r_idx = add(pad([field, val]))
        bg = WHITE if i % 2 == 0 else LIGHT_GRAY
        fmt += [
            cell(T, r_idx-1, 0, nc=NC_TOTAL, bg=bg, wrap="WRAP"),
            cell(T, r_idx-1, 0, bold=True),
        ]
        if "Price" in field:
            fmt.append(currency_fmt(T, r_idx-1, 1))

    # Condition dropdown (8th field = index 7, row SUBJ_DATA_START+7)
    SUBJ_COND_ROW = SUBJ_DATA_START + 7 - 1  # 0-indexed
    fmt.append(dropdown(T, SUBJ_COND_ROW, 1,
                        ["Excellent", "Good", "Fair", "Poor", "Distressed"]))

    add(pad([""]))  # spacer

    # ──────────────────────────────────────────────────────────────────────────
    # SECTION: COMPARABLE SALES
    # ──────────────────────────────────────────────────────────────────────────
    COMP_HDR = add(pad(["COMPARABLE SALES  (5 MAX)"]))
    fmt += [
        merge(T, COMP_HDR-1, 0, NC_TOTAL),
        cell(T, COMP_HDR-1, 0, nc=NC_TOTAL, bg=ORANGE_DARK, bold=True,
             sz=12, tc=WHITE),
        border_bottom(T, COMP_HDR-1, 0, NC_TOTAL),
        row_height(T, COMP_HDR-1, 32),
    ]

    NOTE_ROW = add(pad(["Conservative underwriting: closed sales ≤90 days, "
                         "≤0.5 mi, similar sqft ±15%, same condition or adjusted."]))
    fmt += [
        merge(T, NOTE_ROW-1, 0, NC_TOTAL),
        cell(T, NOTE_ROW-1, 0, nc=NC_TOTAL, bg=YELLOW, italic=True),
    ]

    # Comp column headers
    COMP_COL_HDR = add(pad([
        "Field", "Subject",
        "Comp 1", "Comp 2", "Comp 3", "Comp 4", "Comp 5",
        "MIN", "MAX", "AVG", "MEDIAN", ""
    ]))
    fmt += [
        cell(T, COMP_COL_HDR-1, 0, nc=NC_TOTAL, bg=DARK_BLUE, bold=True,
             sz=10, tc=WHITE, align="CENTER"),
        row_height(T, COMP_COL_HDR-1, 30),
    ]

    comp_rows_meta = []  # (label, row_1indexed, type)

    # ── Address ───────────────────────────────────────────────────────────────
    comp_rows_meta.append(("address", R(), "text"))
    r_idx = add(pad(["Address", ""] + [""] * 5))
    fmt += [cell(T, r_idx-1, 0, nc=NC_TOTAL, bg=PALE_BLUE, bold=True, wrap="WRAP")]

    # ── Sold Date ─────────────────────────────────────────────────────────────
    comp_rows_meta.append(("sold_date", R(), "text"))
    r_idx = add(pad(["Sold Date", ""] + [""] * 5))
    fmt += [cell(T, r_idx-1, 0, nc=NC_TOTAL, bg=WHITE, wrap="WRAP")]

    # ── List Price ────────────────────────────────────────────────────────────
    LIST_ROW = R()
    comp_rows_meta.append(("list_price", LIST_ROW, "currency"))
    r_idx = add(pad(["List Price ($)", ""] + [""] * 5))
    fmt += [cell(T, r_idx-1, 0, nc=NC_TOTAL, bg=LIGHT_GRAY, wrap="WRAP")]

    # ── Sold Price ────────────────────────────────────────────────────────────
    SOLD_ROW = R()
    comp_rows_meta.append(("sold_price", SOLD_ROW, "currency"))
    r_idx = add(pad(["Sold Price ($)", ""] + [""] * 5))
    fmt += [cell(T, r_idx-1, 0, nc=NC_TOTAL, bg=WHITE, wrap="WRAP")]

    # ── Sale/List % ───────────────────────────────────────────────────────────
    SL_ROW = R()
    comp_rows_meta.append(("sl_pct", SL_ROW, "pct"))
    sl_formulas = [f'=IFERROR({col_letter(2+i)}{SOLD_ROW}/{col_letter(2+i)}{LIST_ROW},"")'
                   for i in range(5)]
    r_idx = add(pad(["Sale/List %", ""] + sl_formulas))
    fmt += [cell(T, r_idx-1, 0, nc=NC_TOTAL, bg=LIGHT_GRAY, wrap="WRAP")]

    # ── Beds ──────────────────────────────────────────────────────────────────
    BEDS_ROW = R()
    comp_rows_meta.append(("beds", BEDS_ROW, "number"))
    r_idx = add(pad(["Beds", ""] + [""] * 5))
    fmt += [cell(T, r_idx-1, 0, nc=NC_TOTAL, bg=WHITE, wrap="WRAP")]

    # ── Baths ─────────────────────────────────────────────────────────────────
    BATHS_ROW = R()
    comp_rows_meta.append(("baths", BATHS_ROW, "number"))
    r_idx = add(pad(["Baths", ""] + [""] * 5))
    fmt += [cell(T, r_idx-1, 0, nc=NC_TOTAL, bg=LIGHT_GRAY, wrap="WRAP")]

    # ── Sqft ──────────────────────────────────────────────────────────────────
    SQFT_ROW = R()
    comp_rows_meta.append(("sqft", SQFT_ROW, "number"))
    r_idx = add(pad(["Sqft (Living)", ""] + [""] * 5))
    fmt += [cell(T, r_idx-1, 0, nc=NC_TOTAL, bg=WHITE, wrap="WRAP")]

    # ── $/Sqft (computed) ─────────────────────────────────────────────────────
    PPSF_ROW = R()
    comp_rows_meta.append(("ppsf", PPSF_ROW, "currency"))
    ppsf_formulas = [f'=IFERROR({col_letter(2+i)}{SOLD_ROW}/{col_letter(2+i)}{SQFT_ROW},"")'
                     for i in range(5)]
    r_idx = add(pad(["$/Sqft", ""] + ppsf_formulas))
    fmt += [cell(T, r_idx-1, 0, nc=NC_TOTAL, bg=LIGHT_GRAY, wrap="WRAP")]

    # ── Year Built ────────────────────────────────────────────────────────────
    comp_rows_meta.append(("yr_built", R(), "number"))
    r_idx = add(pad(["Year Built", ""] + [""] * 5))
    fmt += [cell(T, r_idx-1, 0, nc=NC_TOTAL, bg=WHITE, wrap="WRAP")]

    # ── Condition ─────────────────────────────────────────────────────────────
    COND_ROW = R()
    comp_rows_meta.append(("condition", COND_ROW, "text"))
    r_idx = add(pad(["Condition", ""] + [""] * 5))
    fmt += [cell(T, r_idx-1, 0, nc=NC_TOTAL, bg=LIGHT_GRAY, wrap="WRAP")]
    for i in range(5):
        fmt.append(dropdown(T, r_idx-1, 2+i,
                            ["Excellent", "Good", "Fair", "Poor", "Distressed"]))

    # ── Distance ──────────────────────────────────────────────────────────────
    DIST_ROW = R()
    comp_rows_meta.append(("distance", DIST_ROW, "number"))
    r_idx = add(pad(["Distance (mi)", ""] + [""] * 5))
    fmt += [cell(T, r_idx-1, 0, nc=NC_TOTAL, bg=WHITE, wrap="WRAP")]

    # ── DOM ───────────────────────────────────────────────────────────────────
    DOM_ROW = R()
    comp_rows_meta.append(("dom", DOM_ROW, "number"))
    r_idx = add(pad(["DOM", ""] + [""] * 5))
    fmt += [cell(T, r_idx-1, 0, nc=NC_TOTAL, bg=LIGHT_GRAY, wrap="WRAP")]

    # ── Notes ─────────────────────────────────────────────────────────────────
    comp_rows_meta.append(("notes", R(), "text"))
    r_idx = add(pad(["Notes", ""] + [""] * 5))
    fmt += [cell(T, r_idx-1, 0, nc=NC_TOTAL, bg=PALE_BLUE, wrap="WRAP")]

    # ── Back-fill summary formulas (MIN/MAX/AVG/MEDIAN) for numeric rows ──────
    summary_targets = {
        "list_price": LIST_ROW,
        "sold_price": SOLD_ROW,
        "ppsf":       PPSF_ROW,
        "beds":       BEDS_ROW,
        "baths":      BATHS_ROW,
        "sqft":       SQFT_ROW,
        "distance":   DIST_ROW,
        "dom":        DOM_ROW,
    }
    for key, row_num in summary_targets.items():
        rng = comp_range(row_num)
        row = values[row_num - 1]
        row[7]  = f'=IFERROR(MIN({rng}),"")'
        row[8]  = f'=IFERROR(MAX({rng}),"")'
        row[9]  = f'=IFERROR(AVERAGE({rng}),"")'
        row[10] = f'=IFERROR(MEDIAN({rng}),"")'

    # ── Format all comp rows ──────────────────────────────────────────────────
    for label, row_num, rtype in comp_rows_meta:
        r0 = row_num - 1
        fmt.append(cell(T, r0, 0, bold=True))
        if rtype == "currency":
            fmt += [currency_fmt(T, r0, 2, nc=5), currency_fmt(T, r0, 7, nc=4)]
        elif rtype == "pct":
            fmt += [pct_fmt(T, r0, 2, nc=5), pct_fmt(T, r0, 7, nc=4)]
        elif rtype == "number":
            fmt += [number_fmt(T, r0, 2, nc=5), number_fmt(T, r0, 7, nc=4)]

    fmt.append(border_all(T, COMP_COL_HDR-1, 0, len(comp_rows_meta)+1, NC_TOTAL))

    add(pad([""]))  # spacer

    # ──────────────────────────────────────────────────────────────────────────
    # SECTION: ARV ESTIMATE
    # ──────────────────────────────────────────────────────────────────────────
    ARV_HDR = add(pad(["ARV ESTIMATE"]))
    fmt += [
        merge(T, ARV_HDR-1, 0, NC_TOTAL),
        cell(T, ARV_HDR-1, 0, nc=NC_TOTAL, bg=MID_BLUE, bold=True, sz=12, tc=WHITE),
        border_bottom(T, ARV_HDR-1, 0, NC_TOTAL),
        row_height(T, ARV_HDR-1, 32),
    ]

    note_row = add(pad(["Sold price comps only. Prefer closed ≤90 days. "
                         "Conservative ARV = median $/sqft × subj sqft × 0.95."]))
    fmt += [
        merge(T, note_row-1, 0, NC_TOTAL),
        cell(T, note_row-1, 0, nc=NC_TOTAL, bg=YELLOW, italic=True),
    ]

    # Median $/sqft
    PPSF_MEDIAN_ROW = R()
    ppsf_rng = comp_range(PPSF_ROW)
    r_idx = add(pad(["Median $/Sqft (comps)", f'=IFERROR(MEDIAN({ppsf_rng}),"")']))
    fmt += [
        cell(T, r_idx-1, 0, nc=2, bg=LIGHT_GRAY, bold=True),
        currency_fmt(T, r_idx-1, 1),
    ]

    # Subject sqft reference (5th field in subject data section)
    SUBJ_SQFT_REF = f"B{SUBJ_DATA_START + 4}"

    ARV_CONS_ROW = R()
    r_idx = add(pad([
        "Conservative ARV",
        f'=IFERROR(ROUND(B{PPSF_MEDIAN_ROW}*{SUBJ_SQFT_REF}*0.95,-3),"")',
        "(median $/sqft × sqft × 0.95)"
    ]))
    fmt += [
        cell(T, r_idx-1, 0, nc=3, bg=ORANGE_LIGHT, bold=True),
        currency_fmt(T, r_idx-1, 1),
    ]

    ARV_MID_ROW = R()
    r_idx = add(pad([
        "Mid ARV",
        f'=IFERROR(ROUND(B{PPSF_MEDIAN_ROW}*{SUBJ_SQFT_REF},-3),"")',
        "(median $/sqft × sqft)"
    ]))
    fmt += [
        cell(T, r_idx-1, 0, nc=3, bg=LIGHT_GRAY, bold=True),
        currency_fmt(T, r_idx-1, 1),
    ]

    ARV_AGG_ROW = R()
    r_idx = add(pad([
        "Aggressive ARV",
        f'=IFERROR(ROUND(B{PPSF_MEDIAN_ROW}*{SUBJ_SQFT_REF}*1.05,-3),"")',
        "(median $/sqft × sqft × 1.05)"
    ]))
    fmt += [
        cell(T, r_idx-1, 0, nc=3, bg=GREEN_LIGHT, bold=True),
        currency_fmt(T, r_idx-1, 1),
    ]

    SELECTED_ARV_ROW = R()
    r_idx = add(pad([
        "→ SELECTED ARV  (override here)",
        f"=B{ARV_CONS_ROW}",
        "⬅  Yellow = input cell — override if needed"
    ]))
    fmt += [
        cell(T, r_idx-1, 0, bold=True, sz=12, bg=YELLOW),
        cell(T, r_idx-1, 1, bold=True, sz=12, bg=YELLOW, align="RIGHT"),
        cell(T, r_idx-1, 2, italic=True, bg=YELLOW),
        currency_fmt(T, r_idx-1, 1),
        border_bottom(T, r_idx-1, 0, NC_TOTAL, "SOLID_MEDIUM"),
        row_height(T, r_idx-1, 36),
    ]

    add(pad([""]))  # spacer

    # ──────────────────────────────────────────────────────────────────────────
    # SECTION: MAO CALCULATOR
    # ──────────────────────────────────────────────────────────────────────────
    MAO_HDR = add(pad(["MAO CALCULATOR  (78% Rule)"]))
    fmt += [
        merge(T, MAO_HDR-1, 0, NC_TOTAL),
        cell(T, MAO_HDR-1, 0, nc=NC_TOTAL, bg=DARK_BLUE, bold=True, sz=12, tc=WHITE),
        border_bottom(T, MAO_HDR-1, 0, NC_TOTAL),
        row_height(T, MAO_HDR-1, 32),
    ]

    r_idx = add(pad(["Selected ARV", f"=B{SELECTED_ARV_ROW}", "", "from above"]))
    fmt += [
        cell(T, r_idx-1, 0, nc=4, bg=PALE_BLUE),
        cell(T, r_idx-1, 0, bold=True),
        currency_fmt(T, r_idx-1, 1),
    ]

    PCT_ROW = R()
    r_idx = add(pad(["× 78%", f"=ROUND(B{r_idx}*0.78,-2)"]))
    fmt += [
        cell(T, r_idx-1, 0, nc=4, bg=LIGHT_GRAY),
        cell(T, r_idx-1, 0, bold=True),
        currency_fmt(T, r_idx-1, 1),
    ]
    PCT_ROW = r_idx

    REPAIRS_ROW = R()
    r_idx = add(pad(["− Estimated Repairs", "", "", "⬅  Enter repair estimate"]))
    fmt += [
        cell(T, r_idx-1, 0, nc=4, bg=YELLOW),
        cell(T, r_idx-1, 0, bold=True),
        cell(T, r_idx-1, 3, italic=True),
        currency_fmt(T, r_idx-1, 1),
    ]
    REPAIRS_ROW = r_idx

    ASSIGN_ROW = R()
    r_idx = add(pad(["− Assignment Fee", 25000]))
    fmt += [
        cell(T, r_idx-1, 0, nc=4, bg=LIGHT_GRAY),
        cell(T, r_idx-1, 0, bold=True),
        currency_fmt(T, r_idx-1, 1),
    ]
    ASSIGN_ROW = r_idx

    MAO_ROW = R()
    r_idx = add(pad([
        "= MAO  (Max Allowable Offer)",
        f"=IFERROR(B{PCT_ROW}-B{REPAIRS_ROW}-B{ASSIGN_ROW},\"\")",
    ]))
    fmt += [
        cell(T, r_idx-1, 0, nc=2, bold=True, sz=13, bg=GREEN_LIGHT),
        currency_fmt(T, r_idx-1, 1),
        border_bottom(T, r_idx-1, 0, NC_TOTAL, "SOLID_MEDIUM"),
        row_height(T, r_idx-1, 36),
    ]
    MAO_ROW = r_idx

    add(pad([""]))  # spacer

    # ──────────────────────────────────────────────────────────────────────────
    # SECTION: DEAL DECISION
    # ──────────────────────────────────────────────────────────────────────────
    DEC_HDR = add(pad(["DEAL DECISION"]))
    fmt += [
        merge(T, DEC_HDR-1, 0, NC_TOTAL),
        cell(T, DEC_HDR-1, 0, nc=NC_TOTAL, bg=ORANGE_DARK, bold=True, sz=12, tc=WHITE),
        border_bottom(T, DEC_HDR-1, 0, NC_TOTAL),
        row_height(T, DEC_HDR-1, 32),
    ]

    SELLER_ROW = R()
    r_idx = add(pad(["Seller Asking Price", "", "", "⬅  Enter seller's number"]))
    fmt += [
        cell(T, r_idx-1, 0, nc=4, bg=YELLOW),
        cell(T, r_idx-1, 0, bold=True),
        cell(T, r_idx-1, 3, italic=True),
        currency_fmt(T, r_idx-1, 1),
    ]
    SELLER_ROW = r_idx

    r_idx = add(pad(["MAO", f"=B{MAO_ROW}"]))
    fmt += [
        cell(T, r_idx-1, 0, nc=2, bg=LIGHT_GRAY, bold=True),
        currency_fmt(T, r_idx-1, 1),
    ]

    SPREAD_ROW = R()
    r_idx = add(pad([
        "Spread  (MAO − Asking)",
        f'=IFERROR(B{MAO_ROW}-B{SELLER_ROW},"")',
    ]))
    fmt += [
        cell(T, r_idx-1, 0, nc=2, bold=True, bg=PALE_BLUE),
        currency_fmt(T, r_idx-1, 1),
    ]
    SPREAD_ROW = r_idx

    MIN_SPREAD_ROW = R()
    r_idx = add(pad(["Minimum Viable Spread", 12000]))
    fmt += [
        cell(T, r_idx-1, 0, nc=2, bg=LIGHT_GRAY, bold=True),
        currency_fmt(T, r_idx-1, 1),
    ]
    MIN_SPREAD_ROW = r_idx

    DECISION_ROW = R()
    r_idx = add(pad([
        "DECISION",
        f'=IFERROR(IF(B{SPREAD_ROW}>=B{MIN_SPREAD_ROW},"GO — OFFER","NO-GO — PASS"),"")',
    ]))
    fmt += [
        cell(T, r_idx-1, 0, nc=2, bold=True, sz=14, align="CENTER"),
        border_bottom(T, r_idx-1, 0, NC_TOTAL, "SOLID_MEDIUM"),
        row_height(T, r_idx-1, 40),
    ]
    DECISION_ROW = r_idx

    # Conditional formatting: green if GO, red if NO-GO
    fmt += [
        {"addConditionalFormatRule": {
            "rule": {
                "ranges": [{"sheetId": T,
                            "startRowIndex": DECISION_ROW-1, "endRowIndex": DECISION_ROW,
                            "startColumnIndex": 1, "endColumnIndex": 2}],
                "booleanRule": {
                    "condition": {"type": "TEXT_CONTAINS",
                                  "values": [{"userEnteredValue": "GO — OFFER"}]},
                    "format": {"backgroundColor": GREEN_LIGHT,
                               "textFormat": {"foregroundColor": GREEN_DARK, "bold": True}}
                }
            }, "index": 0}},
        {"addConditionalFormatRule": {
            "rule": {
                "ranges": [{"sheetId": T,
                            "startRowIndex": DECISION_ROW-1, "endRowIndex": DECISION_ROW,
                            "startColumnIndex": 1, "endColumnIndex": 2}],
                "booleanRule": {
                    "condition": {"type": "TEXT_CONTAINS",
                                  "values": [{"userEnteredValue": "NO-GO"}]},
                    "format": {"backgroundColor": RED_LIGHT,
                               "textFormat": {"foregroundColor": RED_DARK, "bold": True}}
                }
            }, "index": 1}},
    ]

    # ── Footer ────────────────────────────────────────────────────────────────
    add(pad([""]))
    FOOTER_ROW = add(pad([
        "Always verify: title, liens, permits, violations, HOA, taxes, occupancy. "
        "Conservative ARV > optimistic ARV. Margin over ego."
    ]))
    fmt += [
        merge(T, FOOTER_ROW-1, 0, NC_TOTAL),
        cell(T, FOOTER_ROW-1, 0, nc=NC_TOTAL, bg=YELLOW, italic=True, sz=9),
    ]

    # ── Column widths ─────────────────────────────────────────────────────────
    widths = [200, 150, 130, 130, 130, 130, 130, 90, 90, 90, 90, 90]
    for i, w in enumerate(widths):
        fmt.append(col_width(T, i, w))

    # ── Freeze top 2 rows ─────────────────────────────────────────────────────
    fmt.append(freeze(T, 2))

    # ── Write data + formatting ───────────────────────────────────────────────
    write_values(creds, spread_id, TAB_NAME, values)
    batch(creds, spread_id, fmt)
    print(f"  CMA tab: {len(values)} rows, {len(fmt)} format ops")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    creds = service_account.Credentials.from_service_account_file(
        CREDS_PATH, scopes=SCOPES)

    spread_id = SPREADSHEET_ID

    # ── Get existing tabs ──────────────────────────────────────────────────────
    print(f"Opening spreadsheet {spread_id}...")
    info = sheets_api(creds, "get", f"/{spread_id}")
    existing = {s["properties"]["title"]: s["properties"]["sheetId"]
                for s in info["sheets"]}
    print(f"  Existing tabs: {list(existing.keys())}")

    # ── Delete old CMA Template tab if present ─────────────────────────────────
    delete_reqs = []
    if TAB_NAME in existing:
        delete_reqs.append({"deleteSheet": {"sheetId": existing[TAB_NAME]}})
        print(f"  Queued delete: '{TAB_NAME}'")

    # ── Create fresh CMA Template tab ─────────────────────────────────────────
    add_req = [{"addSheet": {"properties": {"title": TAB_NAME}}}]
    result = sheets_api(creds, "post", f"/{spread_id}:batchUpdate",
                        {"requests": delete_reqs + add_req})

    tab_id = None
    for reply in result.get("replies", []):
        if "addSheet" in reply:
            tab_id = reply["addSheet"]["properties"]["sheetId"]

    print(f"  Created tab '{TAB_NAME}' (sheetId={tab_id})")

    # ── Build template ─────────────────────────────────────────────────────────
    print("\nBuilding CMA tab...")
    build_cma(creds, spread_id, tab_id)

    url = (f"https://docs.google.com/spreadsheets/d/{spread_id}"
           f"/edit#gid={tab_id}")
    print(f"\nDone! Open here:\n{url}")


if __name__ == "__main__":
    main()
