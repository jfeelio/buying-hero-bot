"""
Google Sheets output — Blog Content Calendar.

Writes blog plan to "SEO Blog Plan" tab in the configured Google Sheet.
Reuses the same append_rows pattern as foreclosure-agent/sheets.py.
"""

import logging

from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

import config

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
TAB_NAME = config.SEO_BLOG_TAB_NAME


def _get_service():
    creds = Credentials.from_service_account_file(config.GOOGLE_CREDS_PATH, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def _range(cell: str) -> str:
    return f"'{TAB_NAME}'!{cell}"


def _ensure_tab(svc, sheet_id: str) -> None:
    """Create the SEO Blog Plan tab if it doesn't exist."""
    try:
        meta = svc.spreadsheets().get(spreadsheetId=sheet_id).execute()
        existing_tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]
        if TAB_NAME not in existing_tabs:
            svc.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": TAB_NAME}}}]},
            ).execute()
            logger.info(f"Created tab: {TAB_NAME}")
    except Exception as e:
        logger.warning(f"Tab check failed: {e}")


def _ensure_header(svc, sheet_id: str) -> None:
    """Write header row if the tab is empty."""
    try:
        result = (
            svc.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range=_range("A1:I1"))
            .execute()
        )
        existing = result.get("values", [[]])[0] if result.get("values") else []
        if not existing:
            svc.spreadsheets().values().update(
                spreadsheetId=sheet_id,
                range=_range("A1"),
                valueInputOption="RAW",
                body={"values": [config.BLOG_COLUMNS]},
            ).execute()
            logger.info("Blog plan header row written")
    except Exception as e:
        logger.warning(f"Header check failed: {e}")


def write_blog_plan(blog_posts: list[dict]) -> bool:
    """
    Write 50 blog post rows to the SEO Blog Plan tab.
    Clears existing data first, then writes fresh.
    """
    if not blog_posts:
        logger.info("No blog posts to write")
        return True

    sheet_id = config.SEO_GOOGLE_SHEET_ID
    if not sheet_id:
        logger.error("SEO_GOOGLE_SHEET_ID not set in .env")
        return False

    svc = _get_service()

    try:
        _ensure_tab(svc, sheet_id)
        _ensure_header(svc, sheet_id)

        # Clear existing data rows (keep header)
        svc.spreadsheets().values().clear(
            spreadsheetId=sheet_id,
            range=_range("A2:I1000"),
        ).execute()

        # Build rows
        rows = []
        for post in blog_posts:
            outline = post.get("outline", [])
            outline_str = " | ".join(outline) if isinstance(outline, list) else str(outline)
            rows.append([
                post.get("rank", ""),
                post.get("keyword", ""),
                post.get("monthly_searches", ""),
                post.get("search_intent", ""),
                post.get("title", ""),
                outline_str,
                post.get("priority", ""),
                "Pending",          # Status — default
                post.get("notes", ""),
            ])

        svc.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range=_range("A2"),
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        ).execute()

        logger.info(f"Blog plan written: {len(rows)} posts to '{TAB_NAME}' tab")
        return True

    except Exception as e:
        logger.error(f"Failed to write blog plan to Sheets: {e}")
        return False
