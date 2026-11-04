"""Write D:/Carousels/pipeline.json into the "Carousel Pipeline" tab of the Content Ideas sheet.

Re-runnable: keeps whatever Status/Folder Jorge already set per idea #.
Usage: python pipeline_tab.py [path/to/pipeline.json]
"""
import json, os, sys
import gspread

HERE = os.path.dirname(os.path.abspath(__file__))
SA_KEY = os.path.join(HERE, "..", "foreclosure-agent", "credentials.json")
SHEET_ID = "1wO6LhEfmwL96dnoCTgKda7ck5d2I0yyYchUNgo5a8Co"
TAB = "Carousel Pipeline"
SRC = sys.argv[1] if len(sys.argv) > 1 else "D:/Carousels/pipeline.json"

HEADERS = ["#", "Status", "Hook (slide 1)", "Format", "Slide Outline", "AI Scenes",
           "Needs From Jorge", "Caption", "Folder"]
STATUSES = ["Idea", "Building", "Ready", "Posted", "Skip"]
WIDTHS = [40, 90, 260, 140, 380, 260, 220, 420, 200]


def main():
    ideas = json.load(open(SRC, encoding="utf-8"))
    sh = gspread.service_account(filename=SA_KEY).open_by_key(SHEET_ID)
    try:
        ws = sh.worksheet(TAB)
        old = {r[0]: r for r in ws.get_all_values()[1:] if r}
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(TAB, rows=100, cols=len(HEADERS))
        old = {}

    rows = [HEADERS]
    for it in ideas:
        prev = old.get(str(it["n"]), [])
        status = prev[1] if len(prev) > 1 and prev[1] else "Idea"
        folder = prev[8] if len(prev) > 8 and prev[8] else ""
        rows.append([it["n"], status, it["hook"], it["format"], it["slides"], it["scenes"],
                     it["needs"], it["caption"], folder])
    ws.clear()
    ws.update(rows, "A1")

    sid = ws.id
    reqs = [
        {"updateSheetProperties": {"properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 1}},
                                   "fields": "gridProperties.frozenRowCount"}},
        {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
                        "cell": {"userEnteredFormat": {"textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                                                       "backgroundColor": {"red": 0, "green": 0.514, "blue": 0.792}}},
                        "fields": "userEnteredFormat(textFormat,backgroundColor)"}},
        {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": len(rows)},
                        "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP", "verticalAlignment": "TOP"}},
                        "fields": "userEnteredFormat(wrapStrategy,verticalAlignment)"}},
        {"setDataValidation": {"range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": len(rows),
                                         "startColumnIndex": 1, "endColumnIndex": 2},
                               "rule": {"condition": {"type": "ONE_OF_LIST",
                                                      "values": [{"userEnteredValue": s} for s in STATUSES]},
                                        "showCustomUi": True, "strict": True}}},
    ]
    for i, w in enumerate(WIDTHS):
        reqs.append({"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
                                                   "properties": {"pixelSize": w}, "fields": "pixelSize"}})
    sh.batch_update({"requests": reqs})
    print(f"wrote {len(rows) - 1} ideas to '{TAB}'  https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid={sid}")


if __name__ == "__main__":
    main()
