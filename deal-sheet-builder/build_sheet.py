"""
Buying Hero — Deal Sheet Builder

Creates the Google Sheet structure for the per-deal-tab workflow:
  Config (defaults, editable MAO%, etc.)
  Deals Index (pipeline rollup)
  Template (hidden master, every deal tab is copied from this)
  Archive (dead deals)

Run once to set up the sheet. Re-running rebuilds Config/Index/Template
without touching existing deal tabs (those are user data).

Usage:
  python build_sheet.py
"""

import os
import sys
import logging
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

SHEET_ID = "16of8fZhqeYlF_UzBWX3GoYiIOZJKT6F57JhzvKV5s0g"
CREDS_PATH = os.path.join(os.path.dirname(__file__), "..", "foreclosure-agent", "credentials.json")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

CONFIG_TAB = "⚙️ Config"
CALC_TAB = "🏠 Deal Calculator"

NAVY = {"red": 0.06, "green": 0.16, "blue": 0.27}
WHITE = {"red": 1, "green": 1, "blue": 1}
YELLOW = {"red": 1, "green": 0.976, "blue": 0.902}
GREEN_LIGHT = {"red": 0.83, "green": 0.93, "blue": 0.83}
GREEN_DARK = {"red": 0.18, "green": 0.56, "blue": 0.32}
AMBER = {"red": 0.99, "green": 0.84, "blue": 0.51}
AMBER_DARK = {"red": 0.85, "green": 0.47, "blue": 0.04}
RED_LIGHT = {"red": 0.96, "green": 0.78, "blue": 0.78}
RED_DARK = {"red": 0.76, "green": 0.16, "blue": 0.16}
GREY_LIGHT = {"red": 0.95, "green": 0.95, "blue": 0.95}
GREY_MID = {"red": 0.85, "green": 0.85, "blue": 0.87}
GREY_TEXT = {"red": 0.42, "green": 0.45, "blue": 0.50}
SECTION_BG = {"red": 0.18, "green": 0.28, "blue": 0.42}
BG_PAGE = {"red": 0.95, "green": 0.96, "blue": 0.97}
BANNER_BG = {"red": 1.00, "green": 0.97, "blue": 0.85}
CARD_BG = {"red": 1, "green": 1, "blue": 1}
BLUE_HEADER = {"red": 0.12, "green": 0.25, "blue": 0.69}
BLUE_LINK = {"red": 0.07, "green": 0.34, "blue": 0.74}
TOTAL_BG = {"red": 0.93, "green": 0.96, "blue": 1.00}


def get_service():
    creds = Credentials.from_service_account_file(CREDS_PATH, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


# ─────────────────────────────────────────────────────────────────────────────
# Tab management
# ─────────────────────────────────────────────────────────────────────────────

def get_sheet_meta(svc):
    return svc.spreadsheets().get(spreadsheetId=SHEET_ID).execute()


def find_tab_id(meta, title):
    for s in meta.get("sheets", []):
        if s["properties"]["title"] == title:
            return s["properties"]["sheetId"]
    return None


def ensure_tab(svc, meta, title, hidden=False):
    """Create tab if missing. Returns (sheetId, was_created)."""
    sid = find_tab_id(meta, title)
    if sid is not None:
        return sid, False
    body = {
        "requests": [{
            "addSheet": {
                "properties": {
                    "title": title,
                    "hidden": hidden,
                    "gridProperties": {"rowCount": 200, "columnCount": 20},
                }
            }
        }]
    }
    resp = svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body=body).execute()
    new_sid = resp["replies"][0]["addSheet"]["properties"]["sheetId"]
    log.info(f"  + Created tab: {title}")
    return new_sid, True


def clear_tab(svc, sheet_id):
    """Clear all cells (preserves the tab itself)."""
    svc.spreadsheets().values().clear(
        spreadsheetId=SHEET_ID, range=f"{sheet_id}", body={}
    ).execute()


def clear_tab_by_name(svc, tab_name):
    svc.spreadsheets().values().clear(
        spreadsheetId=SHEET_ID, range=f"'{tab_name}'", body={}
    ).execute()


# ─────────────────────────────────────────────────────────────────────────────
# Request builders
# ─────────────────────────────────────────────────────────────────────────────

def req_merge(sheet_id, r1, r2, c1, c2):
    return {"mergeCells": {
        "range": {"sheetId": sheet_id, "startRowIndex": r1, "endRowIndex": r2,
                  "startColumnIndex": c1, "endColumnIndex": c2},
        "mergeType": "MERGE_ALL",
    }}


def req_format(sheet_id, r1, r2, c1, c2, fmt):
    return {"repeatCell": {
        "range": {"sheetId": sheet_id, "startRowIndex": r1, "endRowIndex": r2,
                  "startColumnIndex": c1, "endColumnIndex": c2},
        "cell": {"userEnteredFormat": fmt},
        "fields": "userEnteredFormat(" + ",".join(fmt.keys()) + ")",
    }}


def req_col_width(sheet_id, col_idx, width):
    return {"updateDimensionProperties": {
        "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                  "startIndex": col_idx, "endIndex": col_idx + 1},
        "properties": {"pixelSize": width},
        "fields": "pixelSize",
    }}


def req_row_height(sheet_id, row_idx, height):
    return {"updateDimensionProperties": {
        "range": {"sheetId": sheet_id, "dimension": "ROWS",
                  "startIndex": row_idx, "endIndex": row_idx + 1},
        "properties": {"pixelSize": height},
        "fields": "pixelSize",
    }}


def req_freeze(sheet_id, rows=0, cols=0):
    return {"updateSheetProperties": {
        "properties": {"sheetId": sheet_id,
                       "gridProperties": {"frozenRowCount": rows, "frozenColumnCount": cols}},
        "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
    }}


def req_hide_tab(sheet_id, hidden=True):
    return {"updateSheetProperties": {
        "properties": {"sheetId": sheet_id, "hidden": hidden},
        "fields": "hidden",
    }}


def req_data_validation(sheet_id, r1, r2, c1, c2, values):
    return {"setDataValidation": {
        "range": {"sheetId": sheet_id, "startRowIndex": r1, "endRowIndex": r2,
                  "startColumnIndex": c1, "endColumnIndex": c2},
        "rule": {
            "condition": {"type": "ONE_OF_LIST",
                          "values": [{"userEnteredValue": v} for v in values]},
            "showCustomUi": True,
            "strict": False,
        },
    }}


def req_conditional_format(sheet_id, r1, r2, c1, c2, condition, fmt, index=0):
    return {"addConditionalFormatRule": {
        "rule": {
            "ranges": [{"sheetId": sheet_id, "startRowIndex": r1, "endRowIndex": r2,
                        "startColumnIndex": c1, "endColumnIndex": c2}],
            "booleanRule": {"condition": condition, "format": fmt},
        },
        "index": index,
    }}


def req_named_range(name, sheet_id, r1, r2, c1, c2):
    return {"addNamedRange": {
        "namedRange": {"name": name,
                       "range": {"sheetId": sheet_id, "startRowIndex": r1, "endRowIndex": r2,
                                 "startColumnIndex": c1, "endColumnIndex": c2}}
    }}


def req_delete_named_range(named_range_id):
    return {"deleteNamedRange": {"namedRangeId": named_range_id}}


def req_border_section(sheet_id, r1, r2, c1, c2):
    border = {"style": "SOLID", "width": 1, "color": GREY_MID}
    return {"updateBorders": {
        "range": {"sheetId": sheet_id, "startRowIndex": r1, "endRowIndex": r2,
                  "startColumnIndex": c1, "endColumnIndex": c2},
        "top": border, "bottom": border, "left": border, "right": border,
        "innerHorizontal": border, "innerVertical": border,
    }}


def fmt_text(bg=None, fg=None, size=None, bold=False, italic=False, h_align="LEFT",
             v_align="MIDDLE", wrap=True, number_format=None):
    f = {"horizontalAlignment": h_align, "verticalAlignment": v_align}
    if wrap:
        f["wrapStrategy"] = "WRAP"
    if bg:
        f["backgroundColor"] = bg
    text_fmt = {}
    if fg:
        text_fmt["foregroundColor"] = fg
    if size:
        text_fmt["fontSize"] = size
    if bold:
        text_fmt["bold"] = True
    if italic:
        text_fmt["italic"] = True
    if text_fmt:
        f["textFormat"] = text_fmt
    if number_format:
        f["numberFormat"] = number_format
    return f


CURRENCY_FMT = {"type": "CURRENCY", "pattern": "$#,##0"}
CURRENCY_FMT_2 = {"type": "CURRENCY", "pattern": "$#,##0.00"}
PERCENT_FMT = {"type": "PERCENT", "pattern": "0.00%"}
NUMBER_FMT = {"type": "NUMBER", "pattern": "#,##0"}


# ─────────────────────────────────────────────────────────────────────────────
# Values writer
# ─────────────────────────────────────────────────────────────────────────────

def write_values(svc, tab_name, rows, start_cell="A1", raw=False):
    svc.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range=f"'{tab_name}'!{start_cell}",
        valueInputOption="RAW" if raw else "USER_ENTERED",
        body={"values": rows},
    ).execute()


def write_formulas(svc, tab_name, rows, start_cell="A1"):
    """Same as write_values but uses USER_ENTERED so formulas are parsed."""
    write_values(svc, tab_name, rows, start_cell, raw=False)


# ─────────────────────────────────────────────────────────────────────────────
# Named ranges cleanup
# ─────────────────────────────────────────────────────────────────────────────

def clear_named_ranges_with_prefix(svc, meta, prefix):
    """Delete any named ranges that start with prefix (so we can rebuild cleanly)."""
    requests = []
    for nr in meta.get("namedRanges", []):
        if nr.get("name", "").startswith(prefix):
            requests.append(req_delete_named_range(nr["namedRangeId"]))
    if requests:
        svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": requests}).execute()
        log.info(f"  - Cleared {len(requests)} named range(s) starting with '{prefix}'")


# ─────────────────────────────────────────────────────────────────────────────
# Config tab builder
# ─────────────────────────────────────────────────────────────────────────────

CONFIG_LAYOUT = [
    # (label, value, named_range, number_format, section_header)
    ("⚙️  Buying Hero — Global Config", None, None, None, "title"),
    ("Edit yellow cells. Changes cascade to every deal tab automatically.", None, None, None, "subtitle"),
    ("", None, None, None, None),
    ("UNDERWRITING THRESHOLDS", None, None, None, "section"),
    ("MAO %", 0.78, "cfg_mao_pct", PERCENT_FMT, None),
    ("Assignment Fee Target", 25000, "cfg_assign_target", CURRENCY_FMT, None),
    ("Min Spread Threshold", 12000, "cfg_min_spread", CURRENCY_FMT, None),
    ("Default Hold (months)", 5, "cfg_hold_months", NUMBER_FMT, None),
    ("Rehab $/sqft minimum (sanity)", 20, "cfg_rehab_per_sqft", CURRENCY_FMT, None),
    ("", None, None, None, None),
    ("HARD MONEY LOAN DEFAULTS", None, None, None, "section"),
    ("APR", 0.1124, "cfg_apr", PERCENT_FMT, None),
    ("Origination Points", 0.0175, "cfg_orig_pts", PERCENT_FMT, None),
    ("Down Payment %", 0.10, "cfg_down_pct", PERCENT_FMT, None),
    ("Appraisal", 0, "cfg_appraisal", CURRENCY_FMT, None),
    ("Other Lender Fees", 0, "cfg_other_lend", CURRENCY_FMT, None),
    ("", None, None, None, None),
    ("PURCHASE CLOSING DEFAULTS", None, None, None, "section"),
    ("Title Fees (flat)", 1400, "cfg_title_fees", CURRENCY_FMT, None),
    ("Title Insurance %", 0.0055, "cfg_title_ins_pct", PERCENT_FMT, None),
    ("Gov Recording %", 0.0065, "cfg_gov_rec_pct", PERCENT_FMT, None),
    ("Home Inspection", 275, "cfg_home_insp", CURRENCY_FMT, None),
    ("Mobile Notary", 250, "cfg_notary", CURRENCY_FMT, None),
    ("Survey", 545, "cfg_survey", CURRENCY_FMT, None),
    ("Transaction Coordination", 0, "cfg_trans_coord", CURRENCY_FMT, None),
    ("Other Purchase Costs", 0, "cfg_other_purch", CURRENCY_FMT, None),
    ("", None, None, None, None),
    ("HOLDING COSTS (per month)", None, None, None, "section"),
    ("Utilities", 100, "cfg_utilities", CURRENCY_FMT, None),
    ("Builders Insurance", 500, "cfg_bldg_ins", CURRENCY_FMT, None),
    ("HOA", 0, "cfg_hoa", CURRENCY_FMT, None),
    ("", None, None, None, None),
    ("SALE CLOSING DEFAULTS", None, None, None, "section"),
    ("Buyers Agent %", 0.03, "cfg_buyers_agt", PERCENT_FMT, None),
    ("Sellers Agent %", 0.03, "cfg_sellers_agt", PERCENT_FMT, None),
    ("Doc Stamps % (FL transfer tax)", 0.007, "cfg_doc_stamps_pct", PERCENT_FMT, None),
    ("Sale Title Insurance %", 0.0038, "cfg_sale_title_ins", PERCENT_FMT, None),
    ("Sale Title Fee (flat)", 400, "cfg_sale_title_fee", CURRENCY_FMT, None),
]


def build_config_tab(svc, sheet_id):
    log.info(f"Building {CONFIG_TAB}…")
    clear_tab_by_name(svc, CONFIG_TAB)

    # Write values
    values = []
    formats_requests = []
    named_range_requests = []

    for i, (label, value, named, num_fmt, kind) in enumerate(CONFIG_LAYOUT):
        if kind == "title":
            values.append([label, ""])
        elif kind == "subtitle":
            values.append([label, ""])
        elif kind == "section":
            values.append([label, ""])
        else:
            values.append([label, value if value is not None else ""])

    write_values(svc, CONFIG_TAB, values, "A1", raw=False)

    # Formatting pass
    requests = []
    requests.append(req_col_width(sheet_id, 0, 260))
    requests.append(req_col_width(sheet_id, 1, 140))
    requests.append(req_col_width(sheet_id, 2, 200))

    for i, (label, value, named, num_fmt, kind) in enumerate(CONFIG_LAYOUT):
        row = i  # 0-indexed

        if kind == "title":
            requests.append(req_merge(sheet_id, row, row + 1, 0, 3))
            requests.append(req_format(sheet_id, row, row + 1, 0, 3,
                fmt_text(bg=NAVY, fg=WHITE, size=18, bold=True, h_align="CENTER")))
            requests.append(req_row_height(sheet_id, row, 44))
        elif kind == "subtitle":
            requests.append(req_merge(sheet_id, row, row + 1, 0, 3))
            requests.append(req_format(sheet_id, row, row + 1, 0, 3,
                fmt_text(bg=GREY_LIGHT, fg={"red":0.4,"green":0.4,"blue":0.4}, size=10, italic=True, h_align="CENTER")))
        elif kind == "section":
            requests.append(req_merge(sheet_id, row, row + 1, 0, 3))
            requests.append(req_format(sheet_id, row, row + 1, 0, 3,
                fmt_text(bg=SECTION_BG, fg=WHITE, size=11, bold=True, h_align="LEFT")))
            requests.append(req_row_height(sheet_id, row, 28))
        elif label:
            # Label cell
            requests.append(req_format(sheet_id, row, row + 1, 0, 1,
                fmt_text(bg=WHITE, fg=NAVY, size=10, bold=False)))
            # Value cell (yellow editable)
            value_fmt = fmt_text(bg=YELLOW, fg=NAVY, size=11, bold=True, h_align="RIGHT", number_format=num_fmt)
            requests.append(req_format(sheet_id, row, row + 1, 1, 2, value_fmt))

            # Named range for the value cell
            if named:
                named_range_requests.append(req_named_range(named, sheet_id, row, row + 1, 1, 2))

    # Apply all formatting
    if requests:
        svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": requests}).execute()

    # Apply named ranges separately
    if named_range_requests:
        svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": named_range_requests}).execute()
        log.info(f"  + {len(named_range_requests)} named ranges set")


# ─────────────────────────────────────────────────────────────────────────────
# Deal Calculator tab builder — card-based layout matching jfeelio bot
# ─────────────────────────────────────────────────────────────────────────────


def build_template_tab(svc, sheet_id):
    log.info(f"Building {CALC_TAB}…")
    clear_tab_by_name(svc, CALC_TAB)
    # Unmerge any leftover merges from previous builds BEFORE writing values
    # (otherwise old merges eat the new values)
    try:
        svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": [{
            "unmergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 200,
                                       "startColumnIndex": 0, "endColumnIndex": 20}}
        }]}).execute()
    except Exception:
        pass  # No existing merges → fine

    # ════════════════════════════════════════════════════════════════════════
    # VALUES — 12-column-wide layout
    # ════════════════════════════════════════════════════════════════════════
    rows = []

    # Row 1: Address bar (merged A1:L1)
    rows.append(["🏠  [DEAL ADDRESS WILL APPEAR HERE]"] + [""] * 11)
    # Row 2: thin spacer
    rows.append([""] * 12)
    # Row 3: small labels in banner
    rows.append(["ASSIGNMENT CONTRACT MAO"] + [""] * 5 + ["NET PROFIT — HARD MONEY"] + [""] * 5)
    # Row 4: huge MAO and Net Profit values
    rows.append([
        "=IF(J9=0,0,J9*cfg_mao_pct - D9 - B12)", "", "", "", "", "",
        "=IF(J9=0,0,(J9-K27)-(A9+D9+D23+H20)-L19)", "", "", "", "", ""
    ])
    # Row 5: formula explanation / verdict badge
    rows.append([
        '=IF(J9=0,"Enter ARV, rehab, and target to calculate",CONCATENATE("(",TEXT(cfg_mao_pct,"0%")," × ",TEXT(J9,"$#,##0"),") − ",TEXT(D9,"$#,##0")," repairs − ",TEXT(B12,"$#,##0")," target"))',
        "", "", "", "", "",
        '=IF(OR(J9=0,A9=0),"Enter deal info",IF(G4>=25000,"✅  GO",IF(G4>=12000,"⚠️  MARGINAL","❌  NO GO")))',
        "", "", "", "", ""
    ])
    # Row 6: spacer
    rows.append([""] * 12)
    # Row 7: DEAL INPUTS header with Kiavi link
    rows.append(["DEAL INPUTS"] + [""] * 10 + ['=HYPERLINK("https://app.kiavi.com/property-search","Kiavi ARV Estimator ↗")'])
    # Row 8: sub-labels
    rows.append(["PURCHASE PRICE", "", "", "REHAB ESTIMATE", "", "", "HOLD MO.", "", "", "ARV — AFTER REPAIR VALUE", "", ""])
    # Row 9: input values
    rows.append([0, "", "", 0, "", "", "=cfg_hold_months", "", "", 0, "", ""])
    # Row 10: spacer
    rows.append([""] * 12)
    # Row 11: PARAMETERS header
    rows.append(["PARAMETERS"] + [""] * 11)
    # Row 12: 4 inline parameters
    rows.append([
        "ASSIGNMENT TARGET", "=cfg_assign_target", "",
        "ORIG POINTS", "=cfg_orig_pts", "",
        "APR", "=cfg_apr", "",
        "DOWN PAYMENT", "=cfg_down_pct", "",
    ])
    # Row 13: spacer
    rows.append([""] * 12)
    # Row 14: 3 card headers
    rows.append([
        "PURCHASE CLOSING COSTS", "", "", "",
        "HARD MONEY LENDING", "", "", "",
        "HOLDING COSTS", "", "", "",
    ])
    # Row 15
    rows.append([
        "Title Fees", "", "", "=cfg_title_fees",
        "Loan Amount", "", "", "=A9*(1-K12) + D9",
        "Utilities / month", "", "", "=cfg_utilities",
    ])
    # Row 16
    rows.append([
        "Title Insurance", "", "=cfg_title_ins_pct", "=A9*C16",
        "Interest Cost", "", "", "=H15*(H12/12)*G9",
        "Builder's Insurance / mo", "", "", "=cfg_bldg_ins",
    ])
    # Row 17
    rows.append([
        "Gov Recording", "", "=cfg_gov_rec_pct", "=A9*C17",
        "Origination Fee", "", "", "=H15*E12",
        "HOA / month", "", "", "=cfg_hoa",
    ])
    # Row 18
    rows.append([
        "Home Inspection", "", "", "=cfg_home_insp",
        "Appraisal", "", "", "=cfg_appraisal",
        "Property Tax (auto)", "", "", "=A9*0.01/12*G9",
    ])
    # Row 19 — HML "Other Fees" + Holding Total
    rows.append([
        "Mobile Notary", "", "", "=cfg_notary",
        "Other Fees", "", "", "=cfg_other_lend",
        "Total", "", "", "=(L15+L16+L17)*G9 + L18",
    ])
    # Row 20 — HML Total
    rows.append([
        "Survey", "", "", "=cfg_survey",
        "Total", "", "", "=H16+H17+H18+H19",
        "", "", "", "",
    ])
    # Row 21
    rows.append([
        "Transaction Coord", "", "", "=cfg_trans_coord",
        "", "", "", "",
        "", "", "", "",
    ])
    # Row 22
    rows.append([
        "Other", "", "", "=cfg_other_purch",
        "", "", "", "",
        "", "", "", "",
    ])
    # Row 23 — Purchase Closing Total
    rows.append([
        "Total", "", "", "=D15+D16+D17+D18+D19+D20+D21+D22",
        "", "", "", "",
        "", "", "", "",
    ])
    # Row 24 spacer
    rows.append([""] * 12)
    # Row 25 — SALE CLOSING header
    rows.append(["SALE CLOSING COSTS"] + [""] * 11)
    # Row 26 — 6 sub-labels (Doc Stamps label embeds %)
    rows.append([
        "BUYERS AGENT", "",
        "SELLERS AGENT", "",
        '=CONCATENATE("DOC STAMPS (",TEXT(cfg_doc_stamps_pct,"0.00%"),")")', "",
        "TITLE FEE", "",
        "TITLE INSURANCE", "",
        "TOTAL SALE CLOSING", "",
    ])
    # Row 27 — 6 values
    rows.append([
        "=cfg_buyers_agt", "",
        "=cfg_sellers_agt", "",
        "=J9*cfg_doc_stamps_pct", "",
        "=cfg_sale_title_fee", "",
        "=cfg_sale_title_ins", "",
        "=J9*(A27+C27+cfg_doc_stamps_pct+I27) + G27", "",
    ])
    # Row 28 — 6 sub-sub-labels
    rows.append([
        "% of ARV", "",
        "% of ARV", "",
        "", "",
        "", "",
        "% of ARV", "",
        "", "",
    ])
    # Row 29 spacer
    rows.append([""] * 12)
    # ── EXTRAS ──
    # Row 30 — Underwriting Gate
    rows.append(["🛡️  UNDERWRITING GATE (CLAUDE.md rules)"] + [""] * 11)
    # Rows 31-35: 5 checks
    rows.append(["Spread ≥ Min Threshold ($12K default)"] + [""] * 5 + ['=IF(J9=0,"—",IF(G4>=cfg_min_spread,"✅ PASS","❌ FAIL"))'] + [""] * 5)
    rows.append(["Net Profit ≥ Assignment Target"] + [""] * 5 + ['=IF(J9=0,"—",IF(G4>=B12,"✅ PASS","❌ FAIL"))'] + [""] * 5)
    rows.append(["Purchase Price ≤ MAO"] + [""] * 5 + ['=IF(OR(A9=0,J9=0),"—",IF(A9<=A4,"✅ PASS","❌ FAIL"))'] + [""] * 5)
    rows.append(["Rehab $/sqft ≥ minimum (set in Config)"] + [""] * 5 + ['=IF(OR(G39=0,D9=0),"—",IF(D9/G39>=cfg_rehab_per_sqft,"✅ PASS","⚠️ LOW — verify scope"))'] + [""] * 5)
    rows.append(["ARV Verified (Kiavi/comps/external)"] + [""] * 5 + ["Not Verified"] + [""] * 5)
    # Row 36 — Overall verdict
    rows.append(["OVERALL VERDICT"] + [""] * 5 + ['=IF(J9=0,"⚪ Enter Deal",IF(COUNTIF(G31:G35,"*✅*")=5,"🟢 GO",IF(COUNTIF(G31:G35,"*❌*")>=2,"🔴 NO-GO","🟡 TIGHT")))'] + [""] * 5)
    # Row 37 spacer
    rows.append([""] * 12)
    # Row 38 — Square Footage section
    rows.append(["📐  SQUARE FOOTAGE (optional — enables rehab $/sqft sanity check)"] + [""] * 11)
    # Row 39
    rows.append(["Square Footage"] + [""] * 5 + [0] + [""] * 5)
    # Row 40 spacer
    rows.append([""] * 12)
    # Row 41 — MAO Sensitivity
    rows.append(["📊  MAO SENSITIVITY (different % assumptions)"] + [""] * 11)
    # Row 42
    rows.append(["70%", "", "72%", "", "74%", "", "76%", "", "78%", "", "80%", ""])
    # Row 43
    rows.append([
        "=J9*0.70-D9-B12", "",
        "=J9*0.72-D9-B12", "",
        "=J9*0.74-D9-B12", "",
        "=J9*0.76-D9-B12", "",
        "=J9*0.78-D9-B12", "",
        "=J9*0.80-D9-B12", "",
    ])
    # Row 44 spacer
    rows.append([""] * 12)
    # Row 45 — Rehab Stress
    rows.append(["⚠️  REHAB OVERAGE STRESS TEST (net profit if rehab runs over)"] + [""] * 11)
    # Row 46
    rows.append(["Rehab +$0", "", "+$5K", "", "+$10K", "", "+$15K", "", "+$20K", "", "", ""])
    # Row 47
    rows.append(["=G4", "", "=G4-5000", "", "=G4-10000", "", "=G4-15000", "", "=G4-20000", "", "", ""])
    # Row 48 spacer
    rows.append([""] * 12)
    # Row 49 — Buyer Log header
    rows.append(["📞  BUYER INTEREST LOG (48-hour velocity rule)"] + [""] * 11)
    # Row 50
    rows.append(["Date", "", "Buyer Name", "", "Phone", "", "Offer", "", "Status", "", "Notes", ""])
    # Rows 51-57
    for _ in range(7):
        rows.append([""] * 12)
    # Row 58 spacer
    rows.append([""] * 12)
    # Row 59 — DD header
    rows.append(["🔍  DUE DILIGENCE CHECKLIST"] + [""] * 11)
    # Rows 60-65
    rows.append(["Title Status"] + [""] * 5 + ["Unknown"] + [""] * 4 + ["Clear / Cleanup Needed / Issue / Unknown"])
    rows.append(["Permits"] + [""] * 5 + ["Unknown"] + [""] * 4 + ["Clear / Open / Unknown"])
    rows.append(["Code Violations"] + [""] * 5 + ["Unknown"] + [""] * 4 + ["None / Pending / Issued / Unknown"])
    rows.append(["Property Taxes"] + [""] * 5 + ["Unknown"] + [""] * 4 + ["Current / Delinquent / Unknown"])
    rows.append(["HOA Status"] + [""] * 5 + ["Unknown"] + [""] * 4 + ["None / Current / Delinquent / Unknown"])
    rows.append(["Occupancy"] + [""] * 5 + ["Unknown"] + [""] * 4 + ["Vacant / Owner-Occupied / Tenant / Unknown"])
    # Row 66 spacer
    rows.append([""] * 12)
    # Row 67 — Comp Links
    rows.append(["🔗  COMP LINKS (search this address)"] + [""] * 11)
    rows.append(["Kiavi ARV Estimator"] + [""] * 5 + ['=HYPERLINK("https://app.kiavi.com/property-search","Open Kiavi ↗")'] + [""] * 5)
    rows.append(["Zillow"] + [""] * 5 + ['=HYPERLINK("https://www.zillow.com/homes/" & SUBSTITUTE(A1," ","-") & "_rb/","Search Zillow ↗")'] + [""] * 5)
    rows.append(["Redfin"] + [""] * 5 + ['=HYPERLINK("https://www.redfin.com/stingray/do/location-autocomplete?location=" & A1,"Search Redfin ↗")'] + [""] * 5)
    rows.append(["Miami-Dade Property Appraiser"] + [""] * 5 + ['=HYPERLINK("https://www.miamidade.gov/Apps/PA/propertysearch/","Open MDC PA ↗")'] + [""] * 5)
    rows.append(["Public Records Search"] + [""] * 5 + ['=HYPERLINK("https://www.google.com/search?q=" & SUBSTITUTE(A1," ","+") & "+property+records","Google Search ↗")'] + [""] * 5)
    # Row 73 spacer
    rows.append([""] * 12)
    # Row 74 — Notes header
    rows.append(["📝  NOTES + DEAL INFO"] + [""] * 11)
    # Rows 75-78: deal info inputs
    rows.append(["Seller Name"] + [""] * 11)
    rows.append(["Seller Phone"] + [""] * 11)
    rows.append(["Lead Source"] + [""] * 11)
    rows.append(["Date Added"] + [""] * 11)
    # Rows 79-89: free notes
    for _ in range(11):
        rows.append([""] * 12)

    # Write everything
    write_values(svc, CALC_TAB, rows, "A1", raw=False)

    # ════════════════════════════════════════════════════════════════════════
    # FORMATTING
    # ════════════════════════════════════════════════════════════════════════
    requests = []

    # Unmerge any previous merges in this tab so re-runs work cleanly
    requests.append({"unmergeCells": {
        "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 200,
                  "startColumnIndex": 0, "endColumnIndex": 20}
    }})

    # Column widths (12 columns)
    for c in range(12):
        requests.append(req_col_width(sheet_id, c, 125))

    # Row 1: Address bar
    requests.append(req_merge(sheet_id, 0, 1, 0, 12))
    requests.append(req_format(sheet_id, 0, 1, 0, 12,
        fmt_text(bg=NAVY, fg=WHITE, size=22, bold=True, h_align="CENTER")))
    requests.append(req_row_height(sheet_id, 0, 56))

    # Row 2: spacer
    requests.append(req_row_height(sheet_id, 1, 12))
    requests.append(req_format(sheet_id, 1, 2, 0, 12, fmt_text(bg=BG_PAGE)))

    # Rows 3-5: Yellow banner
    requests.append(req_merge(sheet_id, 2, 3, 0, 6))
    requests.append(req_merge(sheet_id, 2, 3, 6, 12))
    requests.append(req_format(sheet_id, 2, 3, 0, 12,
        fmt_text(bg=BANNER_BG, fg=GREY_TEXT, size=10, bold=True, h_align="LEFT")))
    requests.append(req_row_height(sheet_id, 2, 32))

    requests.append(req_merge(sheet_id, 3, 4, 0, 6))
    requests.append(req_merge(sheet_id, 3, 4, 6, 12))
    requests.append(req_format(sheet_id, 3, 4, 0, 12,
        fmt_text(bg=BANNER_BG, fg=NAVY, size=32, bold=True, h_align="LEFT", number_format=CURRENCY_FMT)))
    requests.append(req_row_height(sheet_id, 3, 64))

    requests.append(req_merge(sheet_id, 4, 5, 0, 6))
    requests.append(req_merge(sheet_id, 4, 5, 6, 12))
    requests.append(req_format(sheet_id, 4, 5, 0, 6,
        fmt_text(bg=BANNER_BG, fg=GREY_TEXT, size=10, h_align="LEFT")))
    requests.append(req_format(sheet_id, 4, 5, 6, 12,
        fmt_text(bg=BANNER_BG, fg=NAVY, size=12, bold=True, h_align="LEFT")))
    requests.append(req_row_height(sheet_id, 4, 36))

    # Row 6: spacer
    requests.append(req_row_height(sheet_id, 5, 16))
    requests.append(req_format(sheet_id, 5, 6, 0, 12, fmt_text(bg=BG_PAGE)))

    # Row 7: DEAL INPUTS header
    requests.append(req_merge(sheet_id, 6, 7, 0, 11))
    requests.append(req_format(sheet_id, 6, 7, 0, 11,
        fmt_text(bg=CARD_BG, fg=BLUE_HEADER, size=12, bold=True, h_align="LEFT")))
    requests.append(req_format(sheet_id, 6, 7, 11, 12,
        fmt_text(bg=CARD_BG, fg=BLUE_LINK, size=10, h_align="RIGHT")))
    requests.append(req_row_height(sheet_id, 6, 32))

    # Row 8: sub-labels
    for start in [0, 3, 6, 9]:
        requests.append(req_merge(sheet_id, 7, 8, start, start + 3))
    requests.append(req_format(sheet_id, 7, 8, 0, 12,
        fmt_text(bg=CARD_BG, fg=GREY_TEXT, size=9, bold=True, h_align="LEFT")))
    requests.append(req_row_height(sheet_id, 7, 22))

    # Row 9: input values (merged groups of 3)
    for start in [0, 3, 6, 9]:
        requests.append(req_merge(sheet_id, 8, 9, start, start + 3))
    requests.append(req_format(sheet_id, 8, 9, 0, 3,
        fmt_text(bg=YELLOW, fg=NAVY, size=18, bold=True, h_align="LEFT", number_format=CURRENCY_FMT)))
    requests.append(req_format(sheet_id, 8, 9, 3, 6,
        fmt_text(bg=YELLOW, fg=NAVY, size=18, bold=True, h_align="LEFT", number_format=CURRENCY_FMT)))
    requests.append(req_format(sheet_id, 8, 9, 6, 9,
        fmt_text(bg=YELLOW, fg=NAVY, size=18, bold=True, h_align="LEFT", number_format=NUMBER_FMT)))
    requests.append(req_format(sheet_id, 8, 9, 9, 12,
        fmt_text(bg=YELLOW, fg=NAVY, size=18, bold=True, h_align="LEFT", number_format=CURRENCY_FMT)))
    requests.append(req_row_height(sheet_id, 8, 44))

    # Row 10: spacer
    requests.append(req_row_height(sheet_id, 9, 16))
    requests.append(req_format(sheet_id, 9, 10, 0, 12, fmt_text(bg=BG_PAGE)))

    # Row 11: PARAMETERS header
    requests.append(req_merge(sheet_id, 10, 11, 0, 12))
    requests.append(req_format(sheet_id, 10, 11, 0, 12,
        fmt_text(bg=CARD_BG, fg=BLUE_HEADER, size=12, bold=True, h_align="LEFT")))
    requests.append(req_row_height(sheet_id, 10, 32))

    # Row 12: 4 inline parameters
    for start in [0, 3, 6, 9]:
        requests.append(req_format(sheet_id, 11, 12, start, start + 1,
            fmt_text(bg=CARD_BG, fg=GREY_TEXT, size=9, bold=True, h_align="LEFT")))
        requests.append(req_merge(sheet_id, 11, 12, start + 1, start + 3))
    # Currency for target
    requests.append(req_format(sheet_id, 11, 12, 1, 3,
        fmt_text(bg=YELLOW, fg=NAVY, size=14, bold=True, h_align="RIGHT", number_format=CURRENCY_FMT)))
    # Percent for the other three
    for start in [4, 7, 10]:
        requests.append(req_format(sheet_id, 11, 12, start, start + 2,
            fmt_text(bg=YELLOW, fg=NAVY, size=14, bold=True, h_align="RIGHT", number_format=PERCENT_FMT)))
    requests.append(req_row_height(sheet_id, 11, 40))

    # Row 13: spacer
    requests.append(req_row_height(sheet_id, 12, 16))
    requests.append(req_format(sheet_id, 12, 13, 0, 12, fmt_text(bg=BG_PAGE)))

    # Row 14: 3 card headers
    requests.append(req_merge(sheet_id, 13, 14, 0, 4))
    requests.append(req_merge(sheet_id, 13, 14, 4, 8))
    requests.append(req_merge(sheet_id, 13, 14, 8, 12))
    requests.append(req_format(sheet_id, 13, 14, 0, 12,
        fmt_text(bg=CARD_BG, fg=BLUE_HEADER, size=12, bold=True, h_align="LEFT")))
    requests.append(req_row_height(sheet_id, 13, 32))

    # Base background for card content area (rows 15-23)
    requests.append(req_format(sheet_id, 14, 23, 0, 12,
        fmt_text(bg=CARD_BG, fg=NAVY, size=11)))

    # Purchase Closing card (cols 0-3): label merges
    # Row 15 (Title Fees), 18 (Home Insp), 19 (Notary), 20 (Survey), 21 (Trans Coord), 22 (Other), 23 (Total): label spans 0-2
    for r in [14, 17, 18, 19, 20, 21, 22]:
        requests.append(req_merge(sheet_id, r, r + 1, 0, 3))
    # Row 16 (Title Insurance), 17 (Gov Recording): label spans 0-1 (col 2 is the pct input)
    for r in [15, 16]:
        requests.append(req_merge(sheet_id, r, r + 1, 0, 2))
    # Pct column (col 2 for rows 15-16) — yellow editable percent
    requests.append(req_format(sheet_id, 15, 17, 2, 3,
        fmt_text(bg=YELLOW, fg=NAVY, size=11, bold=True, h_align="RIGHT", number_format=PERCENT_FMT)))
    # $$ column (col 3) currency, right-aligned
    requests.append(req_format(sheet_id, 14, 23, 3, 4,
        fmt_text(bg=CARD_BG, fg=NAVY, size=11, bold=True, h_align="RIGHT", number_format=CURRENCY_FMT)))
    # Yellow inputs in col 3 for editable rows (15, 18-22 inclusive)
    for r in [14, 17, 18, 19, 20, 21]:
        requests.append(req_format(sheet_id, r, r + 1, 3, 4,
            fmt_text(bg=YELLOW, fg=NAVY, size=11, bold=True, h_align="RIGHT", number_format=CURRENCY_FMT)))
    # Row 23 — Purchase Closing Total (blue)
    requests.append(req_format(sheet_id, 22, 23, 0, 4,
        fmt_text(bg=TOTAL_BG, fg=BLUE_HEADER, size=11, bold=True, h_align="LEFT")))
    requests.append(req_format(sheet_id, 22, 23, 3, 4,
        fmt_text(bg=TOTAL_BG, fg=BLUE_HEADER, size=11, bold=True, h_align="RIGHT", number_format=CURRENCY_FMT)))

    # HML card (cols 4-7): label merges for rows 15-20
    for r in [14, 15, 16, 17, 18, 19]:
        requests.append(req_merge(sheet_id, r, r + 1, 4, 7))
    # $$ column (col 7) currency
    requests.append(req_format(sheet_id, 14, 20, 7, 8,
        fmt_text(bg=CARD_BG, fg=NAVY, size=11, bold=True, h_align="RIGHT", number_format=CURRENCY_FMT)))
    # Yellow inputs for H18 (Appraisal) and H19 (Other Fees) — rows 17-18 zero-indexed
    for r in [17, 18]:
        requests.append(req_format(sheet_id, r, r + 1, 7, 8,
            fmt_text(bg=YELLOW, fg=NAVY, size=11, bold=True, h_align="RIGHT", number_format=CURRENCY_FMT)))
    # Row 20 — HML Total (blue)
    requests.append(req_format(sheet_id, 19, 20, 4, 8,
        fmt_text(bg=TOTAL_BG, fg=BLUE_HEADER, size=11, bold=True, h_align="LEFT")))
    requests.append(req_format(sheet_id, 19, 20, 7, 8,
        fmt_text(bg=TOTAL_BG, fg=BLUE_HEADER, size=11, bold=True, h_align="RIGHT", number_format=CURRENCY_FMT)))

    # Holding card (cols 8-11): label merges for rows 15-19
    for r in [14, 15, 16, 17, 18]:
        requests.append(req_merge(sheet_id, r, r + 1, 8, 11))
    # $$ column (col 11) currency
    requests.append(req_format(sheet_id, 14, 19, 11, 12,
        fmt_text(bg=CARD_BG, fg=NAVY, size=11, bold=True, h_align="RIGHT", number_format=CURRENCY_FMT)))
    # Yellow inputs for L15, L16, L17 (Utilities, Builders Ins, HOA) — rows 14-16 zero-indexed
    for r in [14, 15, 16]:
        requests.append(req_format(sheet_id, r, r + 1, 11, 12,
            fmt_text(bg=YELLOW, fg=NAVY, size=11, bold=True, h_align="RIGHT", number_format=CURRENCY_FMT)))
    # Row 19 — Holding Total (blue)
    requests.append(req_format(sheet_id, 18, 19, 8, 12,
        fmt_text(bg=TOTAL_BG, fg=BLUE_HEADER, size=11, bold=True, h_align="LEFT")))
    requests.append(req_format(sheet_id, 18, 19, 11, 12,
        fmt_text(bg=TOTAL_BG, fg=BLUE_HEADER, size=11, bold=True, h_align="RIGHT", number_format=CURRENCY_FMT)))

    # Clear unused HML cells (rows 20-22) and Holding cells (rows 19-22)
    requests.append(req_format(sheet_id, 20, 23, 4, 8, fmt_text(bg=BG_PAGE)))
    requests.append(req_format(sheet_id, 19, 23, 8, 12, fmt_text(bg=BG_PAGE)))

    # Card row heights
    for r in range(14, 23):
        requests.append(req_row_height(sheet_id, r, 26))

    # Row 24: spacer
    requests.append(req_row_height(sheet_id, 23, 16))
    requests.append(req_format(sheet_id, 23, 24, 0, 12, fmt_text(bg=BG_PAGE)))

    # Row 25: SALE CLOSING header
    requests.append(req_merge(sheet_id, 24, 25, 0, 12))
    requests.append(req_format(sheet_id, 24, 25, 0, 12,
        fmt_text(bg=CARD_BG, fg=BLUE_HEADER, size=12, bold=True, h_align="LEFT")))
    requests.append(req_row_height(sheet_id, 24, 32))

    # Row 26: 6 sub-labels
    for start in [0, 2, 4, 6, 8, 10]:
        requests.append(req_merge(sheet_id, 25, 26, start, start + 2))
    requests.append(req_format(sheet_id, 25, 26, 0, 10,
        fmt_text(bg=CARD_BG, fg=GREY_TEXT, size=9, bold=True, h_align="LEFT")))
    requests.append(req_format(sheet_id, 25, 26, 10, 12,
        fmt_text(bg=TOTAL_BG, fg=BLUE_HEADER, size=9, bold=True, h_align="LEFT")))
    requests.append(req_row_height(sheet_id, 25, 22))

    # Row 27: 6 values
    for start in [0, 2, 4, 6, 8, 10]:
        requests.append(req_merge(sheet_id, 26, 27, start, start + 2))
    # Buyers/Sellers Agt: percent yellow input
    requests.append(req_format(sheet_id, 26, 27, 0, 2,
        fmt_text(bg=YELLOW, fg=NAVY, size=18, bold=True, h_align="LEFT", number_format=PERCENT_FMT)))
    requests.append(req_format(sheet_id, 26, 27, 2, 4,
        fmt_text(bg=YELLOW, fg=NAVY, size=18, bold=True, h_align="LEFT", number_format=PERCENT_FMT)))
    # Doc Stamps: calculated $$ (grey, read-only)
    requests.append(req_format(sheet_id, 26, 27, 4, 6,
        fmt_text(bg=CARD_BG, fg=GREY_TEXT, size=18, bold=True, h_align="LEFT", number_format=CURRENCY_FMT)))
    # Title Fee: currency yellow input
    requests.append(req_format(sheet_id, 26, 27, 6, 8,
        fmt_text(bg=YELLOW, fg=NAVY, size=18, bold=True, h_align="LEFT", number_format=CURRENCY_FMT)))
    # Title Insurance: percent yellow input
    requests.append(req_format(sheet_id, 26, 27, 8, 10,
        fmt_text(bg=YELLOW, fg=NAVY, size=18, bold=True, h_align="LEFT", number_format=PERCENT_FMT)))
    # Total Sale Closing: calculated, blue
    requests.append(req_format(sheet_id, 26, 27, 10, 12,
        fmt_text(bg=TOTAL_BG, fg=BLUE_HEADER, size=18, bold=True, h_align="LEFT", number_format=CURRENCY_FMT)))
    requests.append(req_row_height(sheet_id, 26, 44))

    # Row 28: 6 sub-sub-labels
    for start in [0, 2, 4, 6, 8, 10]:
        requests.append(req_merge(sheet_id, 27, 28, start, start + 2))
    requests.append(req_format(sheet_id, 27, 28, 0, 10,
        fmt_text(bg=CARD_BG, fg=GREY_TEXT, size=9, h_align="LEFT")))
    requests.append(req_format(sheet_id, 27, 28, 10, 12,
        fmt_text(bg=TOTAL_BG, fg=BLUE_HEADER, size=9, h_align="LEFT")))
    requests.append(req_row_height(sheet_id, 27, 20))

    # ══ EXTRAS BELOW ══

    # Row 29 spacer
    requests.append(req_row_height(sheet_id, 28, 24))
    requests.append(req_format(sheet_id, 28, 29, 0, 12, fmt_text(bg=BG_PAGE)))

    # Row 30: Underwriting Gate
    requests.append(req_merge(sheet_id, 29, 30, 0, 12))
    requests.append(req_format(sheet_id, 29, 30, 0, 12,
        fmt_text(bg=SECTION_BG, fg=WHITE, size=12, bold=True, h_align="LEFT")))
    requests.append(req_row_height(sheet_id, 29, 32))

    # Rows 31-35: 5 check rows
    for r in range(30, 35):
        requests.append(req_merge(sheet_id, r, r + 1, 0, 6))
        requests.append(req_merge(sheet_id, r, r + 1, 6, 12))
        requests.append(req_format(sheet_id, r, r + 1, 0, 6,
            fmt_text(bg=CARD_BG, fg=NAVY, size=11)))
        requests.append(req_format(sheet_id, r, r + 1, 6, 12,
            fmt_text(bg=CARD_BG, fg=NAVY, size=11, bold=True, h_align="CENTER")))

    # Row 35 (ARV Verified) — yellow dropdown
    requests.append(req_format(sheet_id, 34, 35, 6, 12,
        fmt_text(bg=YELLOW, fg=NAVY, size=11, bold=True, h_align="CENTER")))
    requests.append(req_data_validation(sheet_id, 34, 35, 6, 12, ["✅ Verified", "Not Verified"]))

    # Row 36: OVERALL VERDICT
    requests.append(req_merge(sheet_id, 35, 36, 0, 6))
    requests.append(req_merge(sheet_id, 35, 36, 6, 12))
    requests.append(req_format(sheet_id, 35, 36, 0, 6,
        fmt_text(bg=CARD_BG, fg=NAVY, size=12, bold=True)))
    requests.append(req_format(sheet_id, 35, 36, 6, 12,
        fmt_text(bg=CARD_BG, fg=NAVY, size=18, bold=True, h_align="CENTER")))
    requests.append(req_row_height(sheet_id, 35, 44))

    # Row 37 spacer
    requests.append(req_row_height(sheet_id, 36, 20))
    requests.append(req_format(sheet_id, 36, 37, 0, 12, fmt_text(bg=BG_PAGE)))

    # Row 38: Square Footage header
    requests.append(req_merge(sheet_id, 37, 38, 0, 12))
    requests.append(req_format(sheet_id, 37, 38, 0, 12,
        fmt_text(bg=SECTION_BG, fg=WHITE, size=12, bold=True)))
    requests.append(req_row_height(sheet_id, 37, 28))

    # Row 39: Square Footage input
    requests.append(req_merge(sheet_id, 38, 39, 0, 6))
    requests.append(req_merge(sheet_id, 38, 39, 6, 12))
    requests.append(req_format(sheet_id, 38, 39, 0, 6,
        fmt_text(bg=CARD_BG, fg=NAVY, size=11)))
    requests.append(req_format(sheet_id, 38, 39, 6, 12,
        fmt_text(bg=YELLOW, fg=NAVY, size=14, bold=True, h_align="CENTER", number_format=NUMBER_FMT)))

    # Row 40 spacer
    requests.append(req_row_height(sheet_id, 39, 20))
    requests.append(req_format(sheet_id, 39, 40, 0, 12, fmt_text(bg=BG_PAGE)))

    # Row 41: MAO Sensitivity header
    requests.append(req_merge(sheet_id, 40, 41, 0, 12))
    requests.append(req_format(sheet_id, 40, 41, 0, 12,
        fmt_text(bg=SECTION_BG, fg=WHITE, size=12, bold=True)))
    requests.append(req_row_height(sheet_id, 40, 28))

    # Row 42 headers, Row 43 values
    for start in [0, 2, 4, 6, 8, 10]:
        requests.append(req_merge(sheet_id, 41, 42, start, start + 2))
        requests.append(req_merge(sheet_id, 42, 43, start, start + 2))
    requests.append(req_format(sheet_id, 41, 42, 0, 12,
        fmt_text(bg=GREY_LIGHT, fg=NAVY, size=11, bold=True, h_align="CENTER")))
    requests.append(req_format(sheet_id, 42, 43, 0, 12,
        fmt_text(bg=CARD_BG, fg=NAVY, size=13, bold=True, h_align="CENTER", number_format=CURRENCY_FMT)))
    requests.append(req_row_height(sheet_id, 42, 32))

    # Row 44 spacer
    requests.append(req_row_height(sheet_id, 43, 20))
    requests.append(req_format(sheet_id, 43, 44, 0, 12, fmt_text(bg=BG_PAGE)))

    # Row 45: Rehab Stress header
    requests.append(req_merge(sheet_id, 44, 45, 0, 12))
    requests.append(req_format(sheet_id, 44, 45, 0, 12,
        fmt_text(bg=SECTION_BG, fg=WHITE, size=12, bold=True)))
    requests.append(req_row_height(sheet_id, 44, 28))

    # Row 46/47
    for start in [0, 2, 4, 6, 8, 10]:
        requests.append(req_merge(sheet_id, 45, 46, start, start + 2))
        requests.append(req_merge(sheet_id, 46, 47, start, start + 2))
    requests.append(req_format(sheet_id, 45, 46, 0, 12,
        fmt_text(bg=GREY_LIGHT, fg=NAVY, size=11, bold=True, h_align="CENTER")))
    requests.append(req_format(sheet_id, 46, 47, 0, 12,
        fmt_text(bg=CARD_BG, fg=NAVY, size=13, bold=True, h_align="CENTER", number_format=CURRENCY_FMT)))
    requests.append(req_row_height(sheet_id, 46, 32))

    # Row 48 spacer
    requests.append(req_row_height(sheet_id, 47, 20))
    requests.append(req_format(sheet_id, 47, 48, 0, 12, fmt_text(bg=BG_PAGE)))

    # Row 49: Buyer Log header
    requests.append(req_merge(sheet_id, 48, 49, 0, 12))
    requests.append(req_format(sheet_id, 48, 49, 0, 12,
        fmt_text(bg=SECTION_BG, fg=WHITE, size=12, bold=True)))
    requests.append(req_row_height(sheet_id, 48, 28))

    # Row 50 (headers) + rows 51-57 (entries)
    for r in range(49, 57):
        for start in [0, 2, 4, 6, 8, 10]:
            requests.append(req_merge(sheet_id, r, r + 1, start, start + 2))
    requests.append(req_format(sheet_id, 49, 50, 0, 12,
        fmt_text(bg=GREY_MID, fg=NAVY, size=10, bold=True, h_align="LEFT")))
    requests.append(req_format(sheet_id, 50, 57, 0, 12,
        fmt_text(bg=CARD_BG, fg=NAVY, size=10)))
    requests.append(req_format(sheet_id, 50, 57, 6, 8,
        fmt_text(bg=CARD_BG, fg=NAVY, size=10, h_align="RIGHT", number_format=CURRENCY_FMT)))

    # Row 58 spacer
    requests.append(req_row_height(sheet_id, 57, 20))
    requests.append(req_format(sheet_id, 57, 58, 0, 12, fmt_text(bg=BG_PAGE)))

    # Row 59: DD header
    requests.append(req_merge(sheet_id, 58, 59, 0, 12))
    requests.append(req_format(sheet_id, 58, 59, 0, 12,
        fmt_text(bg=SECTION_BG, fg=WHITE, size=12, bold=True)))
    requests.append(req_row_height(sheet_id, 58, 28))

    # Rows 60-65: 6 dropdowns
    dd_options = [
        ["Clear", "Cleanup Needed", "Issue", "Unknown"],
        ["Clear", "Open", "Unknown"],
        ["None", "Pending", "Issued", "Unknown"],
        ["Current", "Delinquent", "Unknown"],
        ["None", "Current", "Delinquent", "Unknown"],
        ["Vacant", "Owner-Occupied", "Tenant", "Unknown"],
    ]
    for i in range(6):
        r = 59 + i
        requests.append(req_merge(sheet_id, r, r + 1, 0, 6))
        requests.append(req_merge(sheet_id, r, r + 1, 6, 11))
        requests.append(req_format(sheet_id, r, r + 1, 0, 6,
            fmt_text(bg=CARD_BG, fg=NAVY, size=11)))
        requests.append(req_format(sheet_id, r, r + 1, 6, 11,
            fmt_text(bg=YELLOW, fg=NAVY, size=11, bold=True, h_align="CENTER")))
        requests.append(req_format(sheet_id, r, r + 1, 11, 12,
            fmt_text(bg=CARD_BG, fg=GREY_TEXT, size=9, italic=True)))
        requests.append(req_data_validation(sheet_id, r, r + 1, 6, 11, dd_options[i]))

    # Row 66 spacer
    requests.append(req_row_height(sheet_id, 65, 20))
    requests.append(req_format(sheet_id, 65, 66, 0, 12, fmt_text(bg=BG_PAGE)))

    # Row 67: Comp Links header
    requests.append(req_merge(sheet_id, 66, 67, 0, 12))
    requests.append(req_format(sheet_id, 66, 67, 0, 12,
        fmt_text(bg=SECTION_BG, fg=WHITE, size=12, bold=True)))
    requests.append(req_row_height(sheet_id, 66, 28))

    # Rows 68-72: 5 links
    for r in range(67, 72):
        requests.append(req_merge(sheet_id, r, r + 1, 0, 6))
        requests.append(req_merge(sheet_id, r, r + 1, 6, 12))
        requests.append(req_format(sheet_id, r, r + 1, 0, 6,
            fmt_text(bg=CARD_BG, fg=NAVY, size=11)))
        requests.append(req_format(sheet_id, r, r + 1, 6, 12,
            fmt_text(bg=CARD_BG, fg=BLUE_LINK, size=11, bold=True)))

    # Row 73 spacer
    requests.append(req_row_height(sheet_id, 72, 20))
    requests.append(req_format(sheet_id, 72, 73, 0, 12, fmt_text(bg=BG_PAGE)))

    # Row 74: Notes header
    requests.append(req_merge(sheet_id, 73, 74, 0, 12))
    requests.append(req_format(sheet_id, 73, 74, 0, 12,
        fmt_text(bg=SECTION_BG, fg=WHITE, size=12, bold=True)))
    requests.append(req_row_height(sheet_id, 73, 28))

    # Rows 75-78: deal info
    for r in range(74, 78):
        requests.append(req_merge(sheet_id, r, r + 1, 0, 4))
        requests.append(req_merge(sheet_id, r, r + 1, 4, 12))
        requests.append(req_format(sheet_id, r, r + 1, 0, 4,
            fmt_text(bg=CARD_BG, fg=NAVY, size=11)))
        requests.append(req_format(sheet_id, r, r + 1, 4, 12,
            fmt_text(bg=YELLOW, fg=NAVY, size=11, bold=True, h_align="LEFT")))

    # Rows 79-89: free notes
    for r in range(78, 89):
        requests.append(req_merge(sheet_id, r, r + 1, 0, 12))
        requests.append(req_format(sheet_id, r, r + 1, 0, 12,
            fmt_text(bg=YELLOW, fg=NAVY, size=11, wrap=True)))
        requests.append(req_row_height(sheet_id, r, 24))

    # ════════════════════════════════════════════════════════════════════════
    # CONDITIONAL FORMATTING
    # ════════════════════════════════════════════════════════════════════════

    # Verdict badge row 5, cols 6-12 — order matters: more specific first
    requests.append(req_conditional_format(
        sheet_id, 4, 5, 6, 12,
        {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "❌"}]},
        {"backgroundColor": RED_DARK, "textFormat": {"bold": True, "foregroundColor": WHITE}},
    ))
    requests.append(req_conditional_format(
        sheet_id, 4, 5, 6, 12,
        {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "⚠️"}]},
        {"backgroundColor": AMBER_DARK, "textFormat": {"bold": True, "foregroundColor": WHITE}},
    ))
    requests.append(req_conditional_format(
        sheet_id, 4, 5, 6, 12,
        {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "✅"}]},
        {"backgroundColor": GREEN_DARK, "textFormat": {"bold": True, "foregroundColor": WHITE}},
    ))

    # Net Profit big number (row 4, cols 6-12) — by value
    requests.append(req_conditional_format(
        sheet_id, 3, 4, 6, 12,
        {"type": "NUMBER_GREATER_THAN_EQ", "values": [{"userEnteredValue": "25000"}]},
        {"textFormat": {"bold": True, "foregroundColor": GREEN_DARK}},
    ))
    requests.append(req_conditional_format(
        sheet_id, 3, 4, 6, 12,
        {"type": "NUMBER_BETWEEN", "values": [{"userEnteredValue": "12000"}, {"userEnteredValue": "25000"}]},
        {"textFormat": {"bold": True, "foregroundColor": AMBER_DARK}},
    ))
    requests.append(req_conditional_format(
        sheet_id, 3, 4, 6, 12,
        {"type": "NUMBER_LESS", "values": [{"userEnteredValue": "12000"}]},
        {"textFormat": {"bold": True, "foregroundColor": RED_DARK}},
    ))

    # Underwriting check cells (rows 31-35 zero-indexed 30-34, cols 6-12)
    requests.append(req_conditional_format(
        sheet_id, 30, 35, 6, 12,
        {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "PASS"}]},
        {"backgroundColor": GREEN_LIGHT, "textFormat": {"bold": True, "foregroundColor": GREEN_DARK}},
    ))
    requests.append(req_conditional_format(
        sheet_id, 30, 35, 6, 12,
        {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "FAIL"}]},
        {"backgroundColor": RED_LIGHT, "textFormat": {"bold": True, "foregroundColor": RED_DARK}},
    ))
    requests.append(req_conditional_format(
        sheet_id, 30, 35, 6, 12,
        {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "LOW"}]},
        {"backgroundColor": AMBER, "textFormat": {"bold": True, "foregroundColor": NAVY}},
    ))
    requests.append(req_conditional_format(
        sheet_id, 30, 35, 6, 12,
        {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "Verified"}]},
        {"backgroundColor": GREEN_LIGHT, "textFormat": {"bold": True, "foregroundColor": GREEN_DARK}},
    ))

    # OVERALL verdict (row 36 zero-indexed 35)
    requests.append(req_conditional_format(
        sheet_id, 35, 36, 6, 12,
        {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "🟢"}]},
        {"backgroundColor": GREEN_LIGHT, "textFormat": {"bold": True, "foregroundColor": GREEN_DARK}},
    ))
    requests.append(req_conditional_format(
        sheet_id, 35, 36, 6, 12,
        {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "🟡"}]},
        {"backgroundColor": AMBER, "textFormat": {"bold": True, "foregroundColor": NAVY}},
    ))
    requests.append(req_conditional_format(
        sheet_id, 35, 36, 6, 12,
        {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": "🔴"}]},
        {"backgroundColor": RED_LIGHT, "textFormat": {"bold": True, "foregroundColor": RED_DARK}},
    ))

    # Freeze rows 1-5 (address bar + banner stays visible while scrolling)
    requests.append(req_freeze(sheet_id, rows=5))

    # Push it
    svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={"requests": requests}).execute()
    log.info(f"  ✓ {CALC_TAB} built ({len(rows)} rows, {len(requests)} formatting requests)")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    if not os.path.exists(CREDS_PATH):
        log.error(f"❌ Credentials not found at: {CREDS_PATH}")
        sys.exit(1)

    svc = get_service()
    log.info(f"🔗 Connected to sheet: {SHEET_ID}")

    meta = get_sheet_meta(svc)
    clear_named_ranges_with_prefix(svc, meta, "cfg_")

    config_id, _ = ensure_tab(svc, meta, CONFIG_TAB, hidden=False)
    meta = get_sheet_meta(svc)
    calc_id, _ = ensure_tab(svc, meta, CALC_TAB, hidden=False)

    build_config_tab(svc, config_id)
    build_template_tab(svc, calc_id)

    log.info("")
    log.info("✅ Sheet structure built successfully.")
    log.info("")
    log.info("Next steps:")
    log.info(f"  1. Open: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")
    log.info(f"  2. Install apps_script.gs (Extensions → Apps Script → paste → save)")
    log.info(f"  3. Use the '🏠 Buying Hero → New Deal from Address' menu for each new deal")


if __name__ == "__main__":
    main()
