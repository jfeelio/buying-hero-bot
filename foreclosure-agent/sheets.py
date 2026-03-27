import logging
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from config import GOOGLE_SHEET_ID, GOOGLE_CREDS_PATH, SHEET_COLUMNS, SHEET_TAB_NAME

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _range(cell: str, tab_name: str = "") -> str:
    """Prefix a cell/range with a tab name (explicit > config > none)."""
    tab = tab_name or SHEET_TAB_NAME
    if tab:
        return f"'{tab}'!{cell}"
    return cell


def _get_service():
    creds = Credentials.from_service_account_file(GOOGLE_CREDS_PATH, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def _create_tab(svc, sid: str, tab_name: str) -> None:
    """Add a new sheet tab if it doesn't already exist."""
    spreadsheet = svc.spreadsheets().get(spreadsheetId=sid).execute()
    existing = [s["properties"]["title"] for s in spreadsheet.get("sheets", [])]
    if tab_name in existing:
        return
    svc.spreadsheets().batchUpdate(
        spreadsheetId=sid,
        body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
    ).execute()
    logger.info(f"Created new sheet tab: '{tab_name}'")


def ensure_header_row(tab_name: str = "", sheet_id: str = "", columns: list = None) -> None:
    sid = sheet_id or GOOGLE_SHEET_ID
    cols = columns or SHEET_COLUMNS
    svc = _get_service()

    if tab_name:
        _create_tab(svc, sid, tab_name)

    last_col = chr(ord("A") + len(cols) - 1)
    result = (
        svc.spreadsheets()
        .values()
        .get(spreadsheetId=sid, range=_range(f"A1:{last_col}1", tab_name))
        .execute()
    )
    existing = result.get("values", [[]])[0] if result.get("values") else []
    if not existing:
        svc.spreadsheets().values().update(
            spreadsheetId=sid,
            range=_range("A1", tab_name),
            valueInputOption="RAW",
            body={"values": [cols]},
        ).execute()
        logger.info("Header row written to sheet.")
    else:
        num_existing = len(existing)
        if num_existing < len(cols):
            extra = cols[num_existing:]
            start_col = chr(ord("A") + num_existing)
            svc.spreadsheets().values().update(
                spreadsheetId=sid,
                range=_range(f"{start_col}1", tab_name),
                valueInputOption="RAW",
                body={"values": [extra]},
            ).execute()
            logger.info(f"Extended header with: {extra}")
        else:
            logger.info("Header row already present.")


def get_existing_case_numbers(tab_name: str = "", sheet_id: str = "", col: str = "N") -> set:
    """Read case numbers already in the sheet to guard against duplicate writes.

    col defaults to 'N' (14th column = index 13, standard SHEET_COLUMNS).
    Pass col='R' for the Tax Deed tab which has 17 columns before Case Number.
    """
    sid = sheet_id or GOOGLE_SHEET_ID
    svc = _get_service()
    try:
        range_str = _range(f"{col}2:{col}", tab_name)
        result = (
            svc.spreadsheets()
            .values()
            .get(spreadsheetId=sid, range=range_str)
            .execute()
        )
        values = result.get("values", [])
        return {row[0].strip() for row in values if row and row[0].strip()}
    except Exception as e:
        logger.warning(f"Could not read sheet case numbers: {e}")
        return set()


def append_rows(rows: list, tab_name: str = "", sheet_id: str = "") -> bool:
    if not rows:
        logger.info("No rows to append.")
        return True
    sid = sheet_id or GOOGLE_SHEET_ID
    svc = _get_service()
    try:
        svc.spreadsheets().values().append(
            spreadsheetId=sid,
            range=_range("A1", tab_name),
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        ).execute()
        logger.info(f"Appended {len(rows)} row(s) to sheet.")
        return True
    except Exception as e:
        logger.error(f"Failed to append rows to sheet: {e}")
        return False
