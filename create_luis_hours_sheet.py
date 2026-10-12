"""
Builds the hourly tracking workbook for Luis (Lead Manager) in the
"Luis Work Hour Tracking" spreadsheet.

Tabs created:
  1. Time Log        - one pre-filled row per work day, Mon-Sat, starting 2026-08-31.
                       Luis fills Time In / Time Out / Break; hours + pay auto-calc.
                       Approved / Paid checkboxes are the internal tracking columns.
  2. Weekly Summary  - per-week rollup: hours, approved, pending, paid, balance owed.
  3. Dashboard       - hourly rate input (C5) + at-a-glance tiles.

Run once. Re-running rebuilds the three tabs from scratch.
"""

import os
import datetime

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

CREDS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "foreclosure-agent", "credentials.json")
SPREADSHEET_ID = "1lbrUg9Oc-Xb8YUcs8vx2BmF9kKdLTcftKr4Nec3HKXo"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

START_DATE = datetime.date(2026, 8, 31)   # Monday
WEEKS = 26                                 # through Sat 2027-02-27
DAYS_PER_WEEK = 6                          # Mon-Sat

LOG_TAB, WEEK_TAB, DASH_TAB = "Time Log", "Weekly Summary", "Dashboard"
FIRST_ROW = 3                              # row 1 banner, row 2 header
LAST_ROW = FIRST_ROW + WEEKS * DAYS_PER_WEEK - 1   # 158

# Sheets' date serial epoch.
EPOCH = datetime.date(1899, 12, 30)

# Time In / Time Out are picked from this list, not typed free-hand: a bare "9"
# typed into a time-formatted cell is stored as the number 9, which silently
# produces negative hours.  5:00 AM through 11:45 PM in 15-minute steps.
TIME_CHOICES = [
    (datetime.datetime(2000, 1, 1, 5, 0) + datetime.timedelta(minutes=15 * i))
    .strftime("%I:%M %p").lstrip("0")
    for i in range(76)
]
BREAK_CHOICES = ["0", "15", "30", "45", "60", "90"]

# every dollar figure in the workbook multiplies by this one cell
RATE = "'Dashboard'!$C$5"


def serial(d):
    return (d - EPOCH).days


# -- palette -----------------------------------------------------------------
def rgb(r, g, b):
    return {"red": r / 255, "green": g / 255, "blue": b / 255}


NAVY = rgb(16, 42, 72)
SLATE = rgb(31, 68, 110)
WHITE = rgb(255, 255, 255)
PALE = rgb(244, 247, 251)
BAND = rgb(238, 243, 249)
GRAY_TXT = rgb(120, 133, 150)
DARK_TXT = rgb(32, 45, 62)
BLUE_FILL = rgb(214, 232, 250)
BLUE_TXT = rgb(21, 71, 132)
GREEN_FILL = rgb(203, 236, 207)
GREEN_TXT = rgb(24, 90, 40)
AMBER_FILL = rgb(255, 241, 204)
AMBER_TXT = rgb(150, 95, 0)
RED_TXT = rgb(168, 45, 45)
YELLOW_IN = rgb(255, 246, 200)
BORDER = rgb(200, 210, 222)

FMT_DATE = {"type": "DATE", "pattern": "mmm d, yyyy"}
FMT_TIME = {"type": "TIME", "pattern": "h:mm am/pm"}
FMT_NUM2 = {"type": "NUMBER", "pattern": "0.00"}
FMT_INT = {"type": "NUMBER", "pattern": "0"}
FMT_USD = {"type": "CURRENCY", "pattern": "$#,##0.00"}


def cell(value=None, formula=None, bold=False, size=10, color=DARK_TXT,
         bg=None, halign=None, valign="MIDDLE", fmt=None, wrap=None,
         italic=False, borders=None):
    fmtd = {
        "textFormat": {"bold": bold, "fontSize": size, "foregroundColor": color,
                       "italic": italic},
        "verticalAlignment": valign,
    }
    if bg:
        fmtd["backgroundColor"] = bg
    if halign:
        fmtd["horizontalAlignment"] = halign
    if fmt:
        fmtd["numberFormat"] = fmt
    if wrap:
        fmtd["wrapStrategy"] = wrap
    if borders:
        fmtd["borders"] = borders
    c = {"userEnteredFormat": fmtd}
    if formula is not None:
        c["userEnteredValue"] = {"formulaValue": formula}
    elif isinstance(value, bool):
        c["userEnteredValue"] = {"boolValue": value}
    elif isinstance(value, str):
        c["userEnteredValue"] = {"stringValue": value}
    elif isinstance(value, (int, float)):
        c["userEnteredValue"] = {"numberValue": value}
    return c


def row(cells):
    return {"values": cells}


def rows_request(sheet_id, start_row, start_col, data):
    return {"updateCells": {
        "rows": data,
        "fields": "userEnteredValue,userEnteredFormat",
        "start": {"sheetId": sheet_id, "rowIndex": start_row, "columnIndex": start_col},
    }}


def grid(sheet_id, r1, r2, c1, c2):
    return {"sheetId": sheet_id, "startRowIndex": r1, "endRowIndex": r2,
            "startColumnIndex": c1, "endColumnIndex": c2}


def cf_rule(sheet_id, ranges, formula, bg=None, txt=None, bold=False, index=0):
    fmt = {}
    if bg:
        fmt["backgroundColor"] = bg
    tf = {}
    if txt:
        tf["foregroundColor"] = txt
    if bold:
        tf["bold"] = True
    if tf:
        fmt["textFormat"] = tf
    return {"addConditionalFormatRule": {"index": index, "rule": {
        "ranges": ranges,
        "booleanRule": {
            "condition": {"type": "CUSTOM_FORMULA",
                          "values": [{"userEnteredValue": formula}]},
            "format": fmt,
        }}}}


def main():
    creds = Credentials.from_service_account_file(CREDS_PATH, scopes=SCOPES)
    svc = build("sheets", "v4", credentials=creds).spreadsheets()

    meta = svc.get(spreadsheetId=SPREADSHEET_ID).execute()
    existing = {s["properties"]["title"]: s["properties"]["sheetId"]
                for s in meta["sheets"]}

    # ---- 1. structural pass: drop old versions, create the three tabs -------
    reqs = [{"updateSpreadsheetProperties": {
        "properties": {"timeZone": "America/New_York"},
        "fields": "timeZone"}}]
    # Rename any previous version out of the way rather than deleting it up
    # front: once the default Sheet1 is gone, deleting all three tabs before the
    # replacements exist would momentarily empty the document, which Sheets
    # rejects. Rename -> add -> delete always leaves at least one tab alive.
    stale = [existing[n] for n in (LOG_TAB, WEEK_TAB, DASH_TAB) if n in existing]
    for i, old_id in enumerate(stale):
        reqs.append({"updateSheetProperties": {
            "properties": {"sheetId": old_id, "title": "_replaced_%d" % i},
            "fields": "title"}})
    specs = [
        (LOG_TAB, 0, LAST_ROW + 1, 13, 2, 2),
        (WEEK_TAB, 1, WEEKS + 4, 11, 2, 3),
        (DASH_TAB, 2, 36, 10, 0, 0),
    ]
    for title, idx, nrows, ncols, frows, fcols in specs:
        reqs.append({"addSheet": {"properties": {
            "title": title, "index": idx,
            "gridProperties": {"rowCount": nrows, "columnCount": ncols,
                               "frozenRowCount": frows, "frozenColumnCount": fcols},
            "tabColor": NAVY if title == LOG_TAB else SLATE,
        }}})
    for old_id in stale:
        reqs.append({"deleteSheet": {"sheetId": old_id}})
    res = svc.batchUpdate(spreadsheetId=SPREADSHEET_ID,
                          body={"requests": reqs}).execute()
    ids = {}
    for r in res.get("replies", []):
        if "addSheet" in r:
            p = r["addSheet"]["properties"]
            ids[p["title"]] = p["sheetId"]
    log_id, week_id, dash_id = ids[LOG_TAB], ids[WEEK_TAB], ids[DASH_TAB]

    reqs = []

    # =====================================================================
    # TIME LOG
    # =====================================================================
    banner = [cell("LUIS  \u00b7  DAILY TIME LOG", bold=True, size=14, color=WHITE,
                   bg=NAVY, halign="LEFT")] + \
             [cell(None, bg=NAVY) for _ in range(12)]
    reqs.append(rows_request(log_id, 0, 0, [row(banner)]))
    # banner is merged either side of the frozen-column boundary (col 2);
    # Sheets refuses a single merge that straddles it.
    for c1, c2 in ((0, 2), (2, 13)):
        reqs.append({"mergeCells": {"range": grid(log_id, 0, 1, c1, c2),
                                    "mergeType": "MERGE_ALL"}})

    headers = ["Date", "Day", "Time In", "Time Out", "Break (min)", "Hours",
               "Notes \u2014 what I worked on", "Approved", "Approved By",
               "Paid", "Pay Date", "Pay ($)", "Week Of"]
    hdr = [cell(h, bold=True, size=10, color=WHITE, bg=SLATE,
                halign="CENTER" if i not in (0, 6, 8) else "LEFT",
                wrap="WRAP") for i, h in enumerate(headers)]
    reqs.append(rows_request(log_id, 1, 0, [row(hdr)]))

    data = []
    for w in range(WEEKS):
        for d in range(DAYS_PER_WEEK):
            date = START_DATE + datetime.timedelta(days=w * 7 + d)
            r = len(data) + FIRST_ROW  # 1-based sheet row
            data.append(row([
                cell(serial(date), fmt=FMT_DATE, halign="LEFT"),
                cell(formula='=IF($A{r}="","",TEXT($A{r},"dddd"))'.format(r=r),
                     color=GRAY_TXT, halign="LEFT"),
                cell(fmt=FMT_TIME, halign="CENTER"),
                cell(fmt=FMT_TIME, halign="CENTER"),
                cell(fmt=FMT_INT, halign="CENTER"),
                # IFERROR(TIMEVALUE(x), x) accepts either a text time picked from
                # the dropdown ("9:00 AM") or a real time value typed by hand.
                cell(formula=('=IF(OR($C{r}="",$D{r}=""),"",'
                              'ROUND(MOD(IFERROR(TIMEVALUE($D{r}),$D{r})'
                              '-IFERROR(TIMEVALUE($C{r}),$C{r}),1)*24'
                              '-IF($E{r}="",0,$E{r})/60,2))'
                              ).format(r=r),
                     fmt=FMT_NUM2, halign="CENTER", bold=True),
                cell(wrap="CLIP", halign="LEFT"),
                cell(False, halign="CENTER"),
                cell(halign="LEFT", size=9),
                cell(False, halign="CENTER"),
                cell(fmt=FMT_DATE, halign="CENTER", size=9),
                cell(formula=('=IF(OR($F{r}="",{rate}=""),"",'
                              'ROUND($F{r}*{rate},2))').format(r=r, rate=RATE),
                     fmt=FMT_USD, halign="RIGHT"),
                cell(formula="=$A{r}-WEEKDAY($A{r},3)".format(r=r), fmt=FMT_DATE,
                     color=GRAY_TXT, size=9, halign="CENTER"),
            ]))
    reqs.append(rows_request(log_id, FIRST_ROW - 1, 0, data))

    # checkboxes on Approved / Paid
    for col in (7, 9):
        reqs.append({"setDataValidation": {
            "range": grid(log_id, FIRST_ROW - 1, LAST_ROW, col, col + 1),
            "rule": {"condition": {"type": "BOOLEAN"}, "showCustomUi": True}}})

    # Time In / Time Out: strict dropdown, so a bare number can't get through.
    for col in (2, 3):
        reqs.append({"setDataValidation": {
            "range": grid(log_id, FIRST_ROW - 1, LAST_ROW, col, col + 1),
            "rule": {
                "condition": {"type": "ONE_OF_LIST",
                              "values": [{"userEnteredValue": t}
                                         for t in TIME_CHOICES]},
                "inputMessage": ("Pick a time from the list (15-minute steps), "
                                 "or type it in full: 9:00 AM, 5:30 PM. "
                                 "A bare 9 is not a time."),
                "showCustomUi": True, "strict": True}}})

    # Break offers the usual values but still accepts any typed number.
    reqs.append({"setDataValidation": {
        "range": grid(log_id, FIRST_ROW - 1, LAST_ROW, 4, 5),
        "rule": {
            "condition": {"type": "ONE_OF_LIST",
                          "values": [{"userEnteredValue": b}
                                     for b in BREAK_CHOICES]},
            "inputMessage": ("Unpaid break in minutes. Pick one or type any "
                             "number. Leave blank for no break."),
            "showCustomUi": True, "strict": False}}})

    # header notes, so the format is discoverable without asking anyone
    header_notes = {
        2: ("Click the cell and pick a start time from the dropdown.\n"
            "15-minute steps. Enter it in full: 9:00 AM. A bare 9 is not a time."),
        3: ("Click the cell and pick an end time from the dropdown.\n"
            "Use PM for the afternoon: 5:30 PM, not 5:30."),
        4: ("Total UNPAID break in minutes, e.g. 30 or 60.\n"
            "Subtracted from the day's hours. Blank means no break."),
        5: "Calculated for you: (Time Out - Time In) - Break. Nothing to type here.",
    }
    for col, note in header_notes.items():
        reqs.append({"updateCells": {
            "rows": [{"values": [{"note": note}]}],
            "fields": "note",
            "start": {"sheetId": log_id, "rowIndex": 1, "columnIndex": col}}})

    body = [grid(log_id, FIRST_ROW - 1, LAST_ROW, 0, 13)]
    reqs.append(cf_rule(log_id, [grid(log_id, FIRST_ROW - 1, LAST_ROW, 5, 6)],
                        '=AND($F3<>"",$F3>10)', bg=AMBER_FILL, txt=AMBER_TXT,
                        bold=True, index=0))
    reqs.append(cf_rule(log_id, body, "=$J3=TRUE", bg=GREEN_FILL, txt=GREEN_TXT,
                        index=1))
    reqs.append(cf_rule(log_id, body, "=$H3=TRUE", bg=BLUE_FILL, txt=BLUE_TXT,
                        index=2))
    reqs.append(cf_rule(log_id, body, "=ISODD(ISOWEEKNUM($A3))", bg=BAND, index=3))

    widths = [(0, 105), (1, 95), (2, 85), (3, 85), (4, 80), (5, 70),
              (6, 320), (7, 80), (8, 110), (9, 60), (10, 100), (11, 90), (12, 85)]
    for c, px in widths:
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": log_id, "dimension": "COLUMNS",
                      "startIndex": c, "endIndex": c + 1},
            "properties": {"pixelSize": px}, "fields": "pixelSize"}})
    reqs.append({"updateDimensionProperties": {
        "range": {"sheetId": log_id, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
        "properties": {"pixelSize": 40}, "fields": "pixelSize"}})

    # a heavier line at the top of every Monday so weeks read as blocks
    for w in range(WEEKS):
        r0 = FIRST_ROW - 1 + w * DAYS_PER_WEEK
        reqs.append({"updateBorders": {
            "range": grid(log_id, r0, r0 + 1, 0, 13),
            "top": {"style": "SOLID_MEDIUM", "color": SLATE}}})
    reqs.append({"updateBorders": {
        "range": grid(log_id, FIRST_ROW - 1, LAST_ROW, 0, 13),
        "innerVertical": {"style": "SOLID", "color": BORDER}}})

    reqs.append({"setBasicFilter": {"filter": {
        "range": grid(log_id, 1, LAST_ROW, 0, 13)}}})

    # No protected range here. A warning-only protection on the approval columns
    # nags every editor, partners included, on every edit -- more friction than
    # the accident it guards against. Lock it to specific partner accounts later
    # if that becomes worth doing.

    # =====================================================================
    # WEEKLY SUMMARY
    # =====================================================================
    wbanner = [cell("WEEKLY SUMMARY  \u00b7  approval & payroll rollup", bold=True,
                    size=14, color=WHITE, bg=NAVY, halign="LEFT")] + \
              [cell(None, bg=NAVY) for _ in range(10)]
    reqs.append(rows_request(week_id, 0, 0, [row(wbanner)]))
    for c1, c2 in ((0, 3), (3, 11)):
        reqs.append({"mergeCells": {"range": grid(week_id, 0, 1, c1, c2),
                                    "mergeType": "MERGE_ALL"}})
    wheaders = ["Week #", "Week Of (Mon)", "Week Ending (Sat)", "Hours Logged",
                "Approved Hrs", "Pending Hrs", "Paid Hrs", "Approved $",
                "Paid $", "Balance Owed", "Status"]
    reqs.append(rows_request(week_id, 1, 0, [row(
        [cell(h, bold=True, color=WHITE, bg=SLATE, halign="CENTER", wrap="WRAP")
         for h in wheaders])]))

    L = "'{}'".format(LOG_TAB)
    wdata = []
    for w in range(WEEKS):
        mon = START_DATE + datetime.timedelta(days=w * 7)
        r = w + 3
        sumifs = "SUMIFS({L}!$F:$F,{L}!$M:$M,$B{r}".format(L=L, r=r)
        wdata.append(row([
            cell(w + 1, halign="CENTER", color=GRAY_TXT),
            cell(serial(mon), fmt=FMT_DATE, halign="CENTER", bold=True),
            cell(formula="=$B{r}+5".format(r=r), fmt=FMT_DATE, halign="CENTER",
                 color=GRAY_TXT),
            cell(formula="={})".format(sumifs), fmt=FMT_NUM2, halign="CENTER",
                 bold=True),
            cell(formula="={},{L}!$H:$H,TRUE)".format(sumifs, L=L), fmt=FMT_NUM2,
                 halign="CENTER"),
            cell(formula="=$D{r}-$E{r}".format(r=r), fmt=FMT_NUM2, halign="CENTER"),
            cell(formula="={},{L}!$J:$J,TRUE)".format(sumifs, L=L), fmt=FMT_NUM2,
                 halign="CENTER"),
            cell(formula='=IF({rate}="","",$E{r}*{rate})'.format(r=r, rate=RATE),
                 fmt=FMT_USD),
            cell(formula='=IF({rate}="","",$G{r}*{rate})'.format(r=r, rate=RATE),
                 fmt=FMT_USD),
            cell(formula='=IF({rate}="","",($E{r}-$G{r})*{rate})'.format(r=r, rate=RATE),
                 fmt=FMT_USD, bold=True),
            cell(formula=('=IF($D{r}=0,"\u2014",IF($G{r}>=$D{r},"Paid in full",'
                          'IF($E{r}=0,"Awaiting approval",'
                          'IF($G{r}>0,"Partly paid","Approved \u00b7 unpaid"))))'
                          ).format(r=r),
                 halign="CENTER", bold=True),
        ]))
    reqs.append(rows_request(week_id, 2, 0, wdata))

    tot = WEEKS + 3  # 1-based totals row
    top_border = {"top": {"style": "SOLID_MEDIUM", "color": SLATE}}
    totals = [cell("TOTAL", bold=True, bg=PALE, borders=top_border),
              cell(None, bg=PALE, borders=top_border),
              cell(None, bg=PALE, borders=top_border)]
    for col in "DEFGHIJ":
        f = FMT_USD if col in "HIJ" else FMT_NUM2
        totals.append(cell(formula="=SUM({c}3:{c}{last})".format(c=col, last=tot - 1),
                           bold=True, bg=PALE, fmt=f,
                           halign="CENTER" if col in "DEFG" else "RIGHT",
                           borders=top_border))
    totals.append(cell(None, bg=PALE, borders=top_border))
    reqs.append(rows_request(week_id, tot - 1, 0, [row(totals)]))

    krange = [grid(week_id, 2, tot - 1, 10, 11)]
    reqs.append(cf_rule(week_id, krange, '=$K3="Paid in full"',
                        bg=GREEN_FILL, txt=GREEN_TXT, bold=True, index=0))
    reqs.append(cf_rule(week_id, krange, '=$K3="Approved \u00b7 unpaid"',
                        bg=AMBER_FILL, txt=AMBER_TXT, bold=True, index=1))
    reqs.append(cf_rule(week_id, krange, '=$K3="Partly paid"',
                        bg=AMBER_FILL, txt=AMBER_TXT, bold=True, index=2))
    reqs.append(cf_rule(week_id, krange, '=$K3="Awaiting approval"',
                        bg=BLUE_FILL, txt=BLUE_TXT, bold=True, index=3))
    reqs.append(cf_rule(week_id, [grid(week_id, 2, tot - 1, 9, 10)],
                        "=$J3>0", txt=RED_TXT, bold=True, index=4))
    reqs.append(cf_rule(week_id, [grid(week_id, 2, tot - 1, 0, 11)],
                        "=ISEVEN($A3)", bg=BAND, index=5))

    for c, px in [(0, 65), (1, 120), (2, 130), (3, 95), (4, 95), (5, 95),
                  (6, 85), (7, 105), (8, 105), (9, 115), (10, 150)]:
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": week_id, "dimension": "COLUMNS",
                      "startIndex": c, "endIndex": c + 1},
            "properties": {"pixelSize": px}, "fields": "pixelSize"}})
    reqs.append({"updateDimensionProperties": {
        "range": {"sheetId": week_id, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
        "properties": {"pixelSize": 40}, "fields": "pixelSize"}})

    # =====================================================================
    # DASHBOARD
    # =====================================================================
    dbanner = [cell("LUIS  \u00b7  HOURS & PAY DASHBOARD", bold=True, size=14,
                    color=WHITE, bg=NAVY, halign="LEFT")] + \
              [cell(None, bg=NAVY) for _ in range(9)]
    reqs.append(rows_request(dash_id, 0, 0, [row(dbanner)]))
    reqs.append({"mergeCells": {"range": grid(dash_id, 0, 1, 0, 10),
                                "mergeType": "MERGE_ALL"}})

    def label(t):
        return cell(t, bold=True, size=9, color=GRAY_TXT)

    setup = [
        ("Hourly Rate", None, True),
        ("Start Date", serial(START_DATE), False),
        ("Schedule", "Monday \u2013 Saturday", False),
        ("Pay Period", "Weekly (Mon\u2013Sat), paid after approval", False),
    ]
    reqs.append(rows_request(dash_id, 2, 1, [row([
        cell("SETUP", bold=True, size=11, color=SLATE)])]))
    for i, (lab, val, is_input) in enumerate(setup):
        r = 4 + i  # 0-based
        c_val = cell(val,
                     fmt=FMT_USD if is_input else (FMT_DATE if lab == "Start Date" else None),
                     bg=YELLOW_IN if is_input else None,
                     bold=is_input, halign="LEFT")
        cells = [label(lab), c_val]
        if is_input:
            cells.append(cell("\u2190  enter Luis's hourly rate here", italic=True,
                              size=9, color=AMBER_TXT))
        reqs.append(rows_request(dash_id, r, 1, [row(cells)]))

    # tiles
    F = "'{}'".format(LOG_TAB)
    tiles = [
        ("TOTAL HOURS LOGGED", "=SUM({F}!$F:$F)".format(F=F), FMT_NUM2, SLATE),
        ("APPROVED HOURS", "=SUMIF({F}!$H:$H,TRUE,{F}!$F:$F)".format(F=F),
         FMT_NUM2, BLUE_TXT),
        ("HOURS PENDING APPROVAL",
         "=SUM({F}!$F:$F)-SUMIF({F}!$H:$H,TRUE,{F}!$F:$F)".format(F=F),
         FMT_NUM2, AMBER_TXT),
        ("APPROVED $ TO DATE",
         '=IF({rate}="","",SUMIF({F}!$H:$H,TRUE,{F}!$F:$F)*{rate})'.format(F=F, rate=RATE),
         FMT_USD, SLATE),
        ("PAID TO DATE",
         '=IF({rate}="","",SUMIF({F}!$J:$J,TRUE,{F}!$F:$F)*{rate})'.format(F=F, rate=RATE),
         FMT_USD, GREEN_TXT),
        ("BALANCE OWED",
         '=IF({rate}="","",(SUMIF({F}!$H:$H,TRUE,{F}!$F:$F)'
         '-SUMIF({F}!$J:$J,TRUE,{F}!$F:$F))*{rate})'.format(F=F, rate=RATE),
         FMT_USD, RED_TXT),
    ]
    reqs.append(rows_request(dash_id, 9, 1, [row([
        cell("AT A GLANCE", bold=True, size=11, color=SLATE)])]))
    box = {s: {"style": "SOLID", "color": BORDER}
           for s in ("top", "bottom", "left", "right")}
    for i, (lab, formula, fmt, color) in enumerate(tiles):
        band, slot = divmod(i, 3)
        r_lab = 11 + band * 4
        c0 = 1 + slot * 3
        reqs.append(rows_request(dash_id, r_lab, c0, [row([
            cell(lab, bold=True, size=9, color=GRAY_TXT, bg=PALE,
                 halign="CENTER", borders=box),
            cell(None, bg=PALE, borders=box)])]))
        reqs.append(rows_request(dash_id, r_lab + 1, c0, [row([
            cell(formula=formula, bold=True, size=18, color=color, bg=PALE,
                 halign="CENTER", fmt=fmt, valign="TOP", borders=box),
            cell(None, bg=PALE, borders=box)])]))
        reqs.append({"mergeCells": {"range": grid(dash_id, r_lab, r_lab + 1, c0, c0 + 2),
                                    "mergeType": "MERGE_ALL"}})
        reqs.append({"mergeCells": {
            "range": grid(dash_id, r_lab + 1, r_lab + 2, c0, c0 + 2),
            "mergeType": "MERGE_ALL"}})

    reqs.append(rows_request(dash_id, 19, 1, [row([
        cell("THIS WEEK", bold=True, size=11, color=SLATE)])]))
    this_mon = "TODAY()-WEEKDAY(TODAY(),3)"
    reqs.append(rows_request(dash_id, 20, 1, [row([
        label("Week of"),
        cell(formula="={}".format(this_mon), fmt=FMT_DATE, bold=True,
             halign="LEFT")])]))
    reqs.append(rows_request(dash_id, 21, 1, [row([
        label("Hours logged this week"),
        cell(formula="=SUMIFS({F}!$F:$F,{F}!$M:$M,{m})".format(F=F, m=this_mon),
             fmt=FMT_NUM2, bold=True, halign="LEFT")])]))
    reqs.append(rows_request(dash_id, 22, 1, [row([
        label("Hours awaiting approval this week"),
        cell(formula=("=SUMIFS({F}!$F:$F,{F}!$M:$M,{m})"
                      "-SUMIFS({F}!$F:$F,{F}!$M:$M,{m},{F}!$H:$H,TRUE)"
                      ).format(F=F, m=this_mon),
             fmt=FMT_NUM2, bold=True, halign="LEFT")])]))

    how = [
        "HOW THIS WORKS",
        "Luis \u00b7 every day: open the Time Log tab, find today's date, then click "
        "Time In, Time Out and Break and pick from the dropdown in each cell. "
        "Hours calculate themselves. Times must be full \u2014 9:00 AM, not 9.",
        "Luis \u00b7 use the Notes column for what you worked on that day \u2014 it is "
        "what the approval is based on.",
        "Partners \u00b7 end of each week, review the rows, tick Approved and put your "
        "name in Approved By.",
        "Partners \u00b7 when payment goes out, tick Paid and enter the Pay Date. Rows "
        "turn green once paid.",
        "Weekly Summary shows every week's hours, what is approved, and what is still "
        "owed. Balance Owed in red = approved but not yet paid.",
        "Days off / no work: just leave the row blank \u2014 blank rows count as zero.",
        "Dates are pre-filled Mon\u2013Sat from Aug 31, 2026 through Feb 27, 2027.",
    ]
    for i, line in enumerate(how):
        r = 25 + i
        first = i == 0
        reqs.append(rows_request(dash_id, r, 1, [row([
            cell(line, bold=first, size=11 if first else 9,
                 color=SLATE if first else DARK_TXT, wrap="WRAP")])]))
        if not first:
            reqs.append({"mergeCells": {"range": grid(dash_id, r, r + 1, 1, 10),
                                        "mergeType": "MERGE_ALL"}})

    for c, px in [(0, 30), (1, 210), (2, 130), (3, 40), (4, 210), (5, 130),
                  (6, 40), (7, 210), (8, 130), (9, 40)]:
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": dash_id, "dimension": "COLUMNS",
                      "startIndex": c, "endIndex": c + 1},
            "properties": {"pixelSize": px}, "fields": "pixelSize"}})
    reqs.append({"updateDimensionProperties": {
        "range": {"sheetId": dash_id, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
        "properties": {"pixelSize": 40}, "fields": "pixelSize"}})
    for band in range(2):
        r = 12 + band * 4
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": dash_id, "dimension": "ROWS",
                      "startIndex": r, "endIndex": r + 1},
            "properties": {"pixelSize": 44}, "fields": "pixelSize"}})
    reqs.append({"updateSheetProperties": {
        "properties": {"sheetId": dash_id, "gridProperties": {"hideGridlines": True}},
        "fields": "gridProperties.hideGridlines"}})

    svc.batchUpdate(spreadsheetId=SPREADSHEET_ID, body={"requests": reqs}).execute()

    # drop the leftover default tab, if it is still there and empty
    meta = svc.get(spreadsheetId=SPREADSHEET_ID, includeGridData=False).execute()
    for s in meta["sheets"]:
        if s["properties"]["title"] == "Sheet1":
            vals = svc.values().get(spreadsheetId=SPREADSHEET_ID,
                                    range="Sheet1!A1:Z50").execute().get("values", [])
            if not vals:
                svc.batchUpdate(spreadsheetId=SPREADSHEET_ID, body={"requests": [
                    {"deleteSheet": {"sheetId": s["properties"]["sheetId"]}}]}).execute()
                print("Removed empty default 'Sheet1'.")
            else:
                print("Left 'Sheet1' in place - it has content.")

    print("Done: https://docs.google.com/spreadsheets/d/%s/edit" % SPREADSHEET_ID)
    print("Time Log rows %d-%d (%s through %s)" % (
        FIRST_ROW, LAST_ROW, START_DATE,
        START_DATE + datetime.timedelta(days=WEEKS * 7 - 2)))


if __name__ == "__main__":
    main()
