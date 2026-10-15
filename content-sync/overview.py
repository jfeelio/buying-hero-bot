"""Builds the "Overview" tab: status counts, posting KPIs, and a 4-week calendar with gap highlighting.

Everything is live Google Sheets formulas over the Content Tracker tab, so it updates the moment a row
changes (no sync needed). content_sync.py calls build_overview() only if the tab doesn't exist;
run `python overview.py --rebuild` after changing the layout here.
"""
import sys

import gspread

T = "'Content Tracker'"
ID, TYPE, TITLE, STATUS, DATE = f"{T}!$A$2:$A", f"{T}!$B$2:$B", f"{T}!$C$2:$C", f"{T}!$D$2:$D", f"{T}!$E$2:$E"
LIVE = '{"Approved","Scheduled","Posted","Post Manually"}'          # statuses that count as "on the calendar"
ON_CAL = f'ISNUMBER(MATCH({STATUS},{LIVE},0))'
STATUSES = ["Draft", "Approved", "Scheduled", "Posted", "Post Manually", "Failed", "Skip"]
BLUE = {"red": 0, "green": 0.514, "blue": 0.792}
WEEKS = 4
CAL_TOP = 12          # 1-based row where the calendar header starts


def build_overview(sh, rebuild=False):
    try:
        ws = sh.worksheet("Overview")
        if not rebuild:
            return ws
        sh.del_worksheet(ws)
    except gspread.WorksheetNotFound:
        pass
    ws = sh.add_worksheet("Overview", rows=40, cols=9, index=0)
    sid = ws.id

    cells = [
        ("A1", "CONTENT OVERVIEW"),
        ("A2", '="Updated live from the Content Tracker tab · today is "&TEXT(TODAY(),"ddd mmm d")'),
        # status counts
        ("A4", "STATUS"), ("B4", "COUNT"),
    ]
    for k, st in enumerate(STATUSES):
        cells += [(f"A{5 + k}", st), (f"B{5 + k}", f'=COUNTIF({STATUS},"{st}")')]
    # KPIs
    nxt_date = f'MINIFS({DATE},{DATE},">="&TODAY(),{STATUS},"<>Draft",{STATUS},"<>Skip",{STATUS},"<>Failed")'
    cells += [
        ("D4", "POSTING PACE"), ("E4", ""),
        ("D5", "Target posts / week"), ("E5", 4),
        ("D6", "Next post"),
        ("E6", f'=IFERROR(IF({nxt_date}=0,"nothing lined up",TEXT({nxt_date},"ddd mmm d")&" · "&'
               f'INDEX(FILTER({TITLE},{DATE}={nxt_date},{ON_CAL}),1)),"nothing lined up")'),
        ("D7", "Lined up · next 7 days"),
        ("E7", f'=COUNTIFS({DATE},">="&TODAY(),{DATE},"<"&TODAY()+7,{STATUS},"Approved")'
               f'+COUNTIFS({DATE},">="&TODAY(),{DATE},"<"&TODAY()+7,{STATUS},"Scheduled")'
               f'+COUNTIFS({DATE},">="&TODAY(),{DATE},"<"&TODAY()+7,{STATUS},"Post Manually")'),
        ("D8", "Days with no post · next 14"),
        ("E8", f'=SUMPRODUCT(--(COUNTIFS({DATE},TODAY()+SEQUENCE(14,1,0),{STATUS},"Approved")'
               f'+COUNTIFS({DATE},TODAY()+SEQUENCE(14,1,0),{STATUS},"Scheduled")'
               f'+COUNTIFS({DATE},TODAY()+SEQUENCE(14,1,0),{STATUS},"Post Manually")=0))'),
        ("D9", "Pace vs target · next 7 days"),
        ("E9", '=IF(E7>=E5,"✅ on pace ("&E7&"/"&E5&")","⚠️ short by "&(E5-E7)&" ("&E7&"/"&E5&")")'),
        ("D10", "Last posted"),
        ("E10", f'=IF(MAXIFS({DATE},{STATUS},"Posted")=0,"nothing posted yet",'
                f'TEXT(MAXIFS({DATE},{STATUS},"Posted"),"ddd mmm d")&" · "&'
                f'(TODAY()-MAXIFS({DATE},{STATUS},"Posted"))&" days ago")'),
        (f"A{CAL_TOP}", "NEXT 4 WEEKS"),
        (f"A{CAL_TOP + 1}", "Red = open day (no post lined up) · counts Approved, Scheduled, Post Manually and Posted rows"),
    ]
    days = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
    hdr = CAL_TOP + 2
    for c, dname in enumerate(days):
        cells.append((f"{chr(65 + c)}{hdr}", dname))
    for w in range(WEEKS):
        date_row, body_row = hdr + 1 + 2 * w, hdr + 2 + 2 * w
        for c in range(7):
            col = chr(65 + c)
            off = 7 * w + c
            cells.append((f"{col}{date_row}", f"=TODAY()-WEEKDAY(TODAY(),3)+{off}"))
            d = f"{col}{date_row}"
            cells.append((f"{col}{body_row}",
                          f'=IFERROR(TEXTJOIN(CHAR(10),TRUE,FILTER(IF({TYPE}="Reel","🎬 ","🏠 ")&LEFT({TITLE},34)'
                          f'&IF({STATUS}="Posted"," ✓",""),{DATE}={d},{ON_CAL})),"—")'))

    ws.batch_update([{"range": a, "values": [[v]]} for a, v in cells], value_input_option="USER_ENTERED")

    first_body = hdr + 2
    last_row = hdr + 2 * WEEKS
    reqs = [
        {"updateSheetProperties": {"properties": {"sheetId": sid, "gridProperties": {"hideGridlines": True}},
                                   "fields": "gridProperties.hideGridlines"}},
        {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
                        "cell": {"userEnteredFormat": {"textFormat": {"bold": True, "fontSize": 18, "foregroundColor": BLUE}}},
                        "fields": "userEnteredFormat.textFormat"}},
        {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": 2},
                        "cell": {"userEnteredFormat": {"textFormat": {"italic": True, "foregroundColor": {"red": .45, "green": .45, "blue": .45}}}},
                        "fields": "userEnteredFormat.textFormat"}},
    ]
    # section headers (blue bar)
    for r0, c0, c1 in [(3, 0, 2), (3, 3, 5), (CAL_TOP - 1, 0, 7), (hdr - 1, 0, 7)]:
        reqs.append({"repeatCell": {"range": {"sheetId": sid, "startRowIndex": r0, "endRowIndex": r0 + 1, "startColumnIndex": c0, "endColumnIndex": c1},
                                    "cell": {"userEnteredFormat": {"backgroundColor": BLUE, "horizontalAlignment": "CENTER" if r0 == hdr - 1 else "LEFT",
                                                                   "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}}},
                                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"}})
    reqs.append({"repeatCell": {"range": {"sheetId": sid, "startRowIndex": CAL_TOP, "endRowIndex": CAL_TOP + 1},
                                "cell": {"userEnteredFormat": {"textFormat": {"italic": True, "fontSize": 9, "foregroundColor": {"red": .45, "green": .45, "blue": .45}}}},
                                "fields": "userEnteredFormat.textFormat"}})
    # KPI values bold, target editable (light yellow)
    reqs.append({"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 4, "endRowIndex": 10, "startColumnIndex": 4, "endColumnIndex": 5},
                                "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}}, "fields": "userEnteredFormat.textFormat"}})
    reqs.append({"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 4, "endRowIndex": 5, "startColumnIndex": 4, "endColumnIndex": 5},
                                "cell": {"userEnteredFormat": {"backgroundColor": {"red": 1, "green": .97, "blue": .8}, "horizontalAlignment": "LEFT"}},
                                "fields": "userEnteredFormat(backgroundColor,horizontalAlignment)"}})
    reqs.append({"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 4, "endRowIndex": 4 + len(STATUSES), "startColumnIndex": 1, "endColumnIndex": 2},
                                "cell": {"userEnteredFormat": {"horizontalAlignment": "CENTER", "textFormat": {"bold": True}}},
                                "fields": "userEnteredFormat(horizontalAlignment,textFormat)"}})
    # calendar: date rows formatted + bold; body rows wrap, tall
    for w in range(WEEKS):
        dr, br = hdr + 2 * w, hdr + 1 + 2 * w        # 0-based
        reqs.append({"repeatCell": {"range": {"sheetId": sid, "startRowIndex": dr, "endRowIndex": dr + 1, "startColumnIndex": 0, "endColumnIndex": 7},
                                    "cell": {"userEnteredFormat": {"numberFormat": {"type": "DATE", "pattern": "mmm d"}, "textFormat": {"bold": True},
                                                                   "backgroundColor": {"red": .93, "green": .95, "blue": .97}}},
                                    "fields": "userEnteredFormat(numberFormat,textFormat,backgroundColor)"}})
        reqs.append({"repeatCell": {"range": {"sheetId": sid, "startRowIndex": br, "endRowIndex": br + 1, "startColumnIndex": 0, "endColumnIndex": 7},
                                    "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP", "verticalAlignment": "TOP", "textFormat": {"fontSize": 9}}},
                                    "fields": "userEnteredFormat(wrapStrategy,verticalAlignment,textFormat)"}})
        reqs.append({"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "ROWS", "startIndex": br, "endIndex": br + 1},
                                                   "properties": {"pixelSize": 64}, "fields": "pixelSize"}})
    cal = {"sheetId": sid, "startRowIndex": hdr, "endRowIndex": last_row, "startColumnIndex": 0, "endColumnIndex": 7}
    reqs += [
        # past days: grey date + body
        {"addConditionalFormatRule": {"index": 0, "rule": {"ranges": [cal], "booleanRule": {
            "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": f"=AND(ISODD(ROW()-{hdr}),A{hdr + 1}<TODAY())"}]},
            "format": {"textFormat": {"foregroundColor": {"red": .6, "green": .6, "blue": .6}}}}}}},
        {"addConditionalFormatRule": {"index": 0, "rule": {"ranges": [cal], "booleanRule": {
            "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": f"=AND(ISEVEN(ROW()-{hdr}),INDIRECT(ADDRESS(ROW()-1,COLUMN()))<TODAY())"}]},
            "format": {"textFormat": {"foregroundColor": {"red": .6, "green": .6, "blue": .6}}}}}}},
        # open future days: red
        {"addConditionalFormatRule": {"index": 0, "rule": {"ranges": [cal], "booleanRule": {
            "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": f'=AND(ISEVEN(ROW()-{hdr}),A{hdr + 1}="—",INDIRECT(ADDRESS(ROW()-1,COLUMN()))>=TODAY())'}]},
            "format": {"backgroundColor": {"red": 1, "green": .87, "blue": .87}, "textFormat": {"foregroundColor": {"red": .75, "green": .2, "blue": .2}}}}}}},
        # today: blue border-ish highlight on date cell
        {"addConditionalFormatRule": {"index": 0, "rule": {"ranges": [cal], "booleanRule": {
            "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": f"=AND(ISODD(ROW()-{hdr}),A{hdr + 1}=TODAY())"}]},
            "format": {"backgroundColor": BLUE, "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}}}}}},
        # status counts: highlight Failed > 0
        {"addConditionalFormatRule": {"index": 0, "rule": {"ranges": [{"sheetId": sid, "startRowIndex": 9, "endRowIndex": 10, "startColumnIndex": 0, "endColumnIndex": 2}],
            "booleanRule": {"condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": "=$B$10>0"}]},
                            "format": {"backgroundColor": {"red": 1, "green": .8, "blue": .8}}}}}},
    ]
    for c, wpx in enumerate([150, 150, 150, 210, 260, 150, 150]):
        reqs.append({"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": c, "endIndex": c + 1},
                                                   "properties": {"pixelSize": wpx}, "fields": "pixelSize"}})
    sh.batch_update({"requests": reqs})
    return ws


if __name__ == "__main__":
    sys.path.insert(0, ".")
    from content_sync import SA_KEY, SHEET_ID
    sh = gspread.service_account(filename=SA_KEY).open_by_key(SHEET_ID)
    build_overview(sh, rebuild="--rebuild" in sys.argv)
    print("Overview ready")
