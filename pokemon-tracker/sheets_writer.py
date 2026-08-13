"""Write the Pokemon Sealed tab — full-replace each run since prices update in place."""
import logging

from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

from config import POKEMON_SHEET_ID, GOOGLE_CREDS_PATH, SHEET_TAB_NAME, SHEET_COLUMNS

logger = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _service():
    creds = Credentials.from_service_account_file(GOOGLE_CREDS_PATH, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def _ensure_tab(svc, sheet_id: str, tab_name: str) -> None:
    meta = svc.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if tab_name in existing:
        return
    svc.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
    ).execute()
    logger.info(f"Created tab '{tab_name}'")


def _col_letter(n: int) -> str:
    s = ""
    while n:
        n, rem = divmod(n - 1, 26)
        s = chr(65 + rem) + s
    return s


def write_full_replace(rows: list[list]) -> None:
    svc = _service()
    _ensure_tab(svc, POKEMON_SHEET_ID, SHEET_TAB_NAME)

    last_col = _col_letter(len(SHEET_COLUMNS))
    tab = f"'{SHEET_TAB_NAME}'"

    svc.spreadsheets().values().clear(
        spreadsheetId=POKEMON_SHEET_ID,
        range=f"{tab}!A:{last_col}",
        body={},
    ).execute()

    svc.spreadsheets().values().update(
        spreadsheetId=POKEMON_SHEET_ID,
        range=f"{tab}!A1",
        valueInputOption="RAW",
        body={"values": [SHEET_COLUMNS] + rows},
    ).execute()
    logger.info(f"Wrote {len(rows)} rows to '{SHEET_TAB_NAME}'")


def _sheet_id_for_tab(svc, sheet_id: str, tab_name: str) -> int | None:
    meta = svc.spreadsheets().get(spreadsheetId=sheet_id).execute()
    for s in meta.get("sheets", []):
        if s["properties"]["title"] == tab_name:
            return s["properties"]["sheetId"]
    return None


# Investment Rating column D (index 3). Sheets formula refs use 1-indexed cols
# but the format-rule range startColumnIndex is 0-indexed. Whole-row coloring is
# triggered by a CUSTOM_FORMULA that references $D2 etc.
_RATING_COLORS = [
    ("Strong Buy", {"red": 0.58, "green": 0.88, "blue": 0.58}),  # darker green
    ("Buy",        {"red": 0.82, "green": 0.95, "blue": 0.82}),  # light green
    ("Pre-Release",{"red": 0.90, "green": 0.92, "blue": 1.00}),  # light blue
    ("Wholesale",  {"red": 1.00, "green": 0.95, "blue": 0.80}),  # light amber
    ("Pass",       {"red": 0.98, "green": 0.86, "blue": 0.86}),  # light red
]


def apply_conditional_formatting() -> None:
    """Color rows by Investment Rating. Idempotent: clears existing rules first."""
    svc = _service()
    gid = _sheet_id_for_tab(svc, POKEMON_SHEET_ID, SHEET_TAB_NAME)
    if gid is None:
        logger.warning(f"Tab '{SHEET_TAB_NAME}' not found for formatting")
        return

    # Fetch existing rules so we can delete them by index (must delete high → low)
    meta = svc.spreadsheets().get(
        spreadsheetId=POKEMON_SHEET_ID,
        ranges=[f"'{SHEET_TAB_NAME}'"],
        fields="sheets(properties.sheetId,conditionalFormats)",
    ).execute()
    target_sheet = next(
        (s for s in meta.get("sheets", []) if s["properties"]["sheetId"] == gid), {}
    )
    existing_count = len(target_sheet.get("conditionalFormats", []))

    requests = []
    for i in range(existing_count - 1, -1, -1):
        requests.append({
            "deleteConditionalFormatRule": {"sheetId": gid, "index": i}
        })

    for idx, (label, color) in enumerate(_RATING_COLORS):
        requests.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [{
                        "sheetId": gid,
                        "startRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(SHEET_COLUMNS),
                    }],
                    "booleanRule": {
                        "condition": {
                            "type": "CUSTOM_FORMULA",
                            "values": [{"userEnteredValue": f'=$E2="{label}"'}],
                        },
                        "format": {"backgroundColor": color},
                    },
                },
                "index": idx,
            }
        })

    if not requests:
        return
    svc.spreadsheets().batchUpdate(
        spreadsheetId=POKEMON_SHEET_ID,
        body={"requests": requests},
    ).execute()
    logger.info(f"Applied {len(_RATING_COLORS)} conditional-format rules")
