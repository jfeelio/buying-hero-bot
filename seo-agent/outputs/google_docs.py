"""
Google Docs output — SEO Audit Report.

Creates a new Google Doc with the full audit report.
Uses Google Docs API v1 with the same service account as Sheets.
"""

import logging
from datetime import date

from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

import config

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]


def _get_services():
    creds = Credentials.from_service_account_file(config.GOOGLE_CREDS_PATH, scopes=SCOPES)
    docs_svc = build("docs", "v1", credentials=creds)
    drive_svc = build("drive", "v3", credentials=creds)
    return docs_svc, drive_svc


def _text_request(text: str, idx: int) -> dict:
    return {"insertText": {"location": {"index": idx}, "text": text}}


def _style_request(style: str, start: int, end: int) -> dict:
    return {
        "updateParagraphStyle": {
            "range": {"startIndex": start, "endIndex": end},
            "paragraphStyle": {"namedStyleType": style},
            "fields": "namedStyleType",
        }
    }


def create_audit_doc(
    audit_result: dict,
    pagespeed_data: list[dict],
    issues: list[dict],
    crawl_data: list[dict],
) -> str:
    """
    Create a Google Doc with the full audit report.
    Returns the document URL.
    """
    if not config.GOOGLE_CREDS_PATH:
        logger.error("GOOGLE_CREDS_PATH not set")
        return ""

    docs_svc, drive_svc = _get_services()
    title = f"Buying Hero SEO Audit — {date.today().isoformat()}"

    try:
        # Create blank document
        doc = docs_svc.documents().create(body={"title": title}).execute()
        doc_id = doc["documentId"]
        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        logger.info(f"Created Google Doc: {doc_url}")

        # Build content as a list of (text, style) tuples
        sections = _build_doc_sections(audit_result, pagespeed_data, issues, crawl_data)

        # Insert all text in reverse order (Docs API inserts at index, shifting content)
        # Simpler: build full text first, then batch insert with styles
        requests = _build_requests(sections)

        if requests:
            docs_svc.documents().batchUpdate(
                documentId=doc_id,
                body={"requests": requests},
            ).execute()

        # Share with anyone who has the link (viewer) — or make editor if you prefer
        drive_svc.permissions().create(
            fileId=doc_id,
            body={"role": "writer", "type": "anyone"},
        ).execute()

        logger.info(f"Audit report available at: {doc_url}")
        return doc_url

    except Exception as e:
        logger.error(f"Failed to create Google Doc: {e}")
        return ""


def _build_doc_sections(
    audit_result: dict,
    pagespeed_data: list[dict],
    issues: list[dict],
    crawl_data: list[dict],
) -> list[tuple[str, str]]:
    """
    Build list of (text, style) pairs.
    style: 'HEADING_1', 'HEADING_2', 'NORMAL_TEXT'
    """
    sections = []

    def h1(text): sections.append((text + "\n", "HEADING_1"))
    def h2(text): sections.append((text + "\n", "HEADING_2"))
    def body(text): sections.append((text + "\n", "NORMAL_TEXT"))

    # ── Executive Summary ──────────────────────────────────────────────────
    h1("Executive Summary")
    body(audit_result.get("executive_summary", "No summary available."))

    # ── Critical Issues ────────────────────────────────────────────────────
    h1("Critical Issues")
    for i, issue in enumerate(audit_result.get("critical_issues", []), 1):
        body(f"{i}. {issue}")

    # ── PageSpeed Scores ───────────────────────────────────────────────────
    h1("PageSpeed Insights Scores")
    if pagespeed_data:
        # Homepage scores
        home_scores = [r for r in pagespeed_data if r.get("url", "").rstrip("/") == config.TARGET_URL.rstrip("/")]
        if home_scores:
            h2("Homepage")
            for r in home_scores:
                strat = r.get("strategy", "").upper()
                body(
                    f"{strat} — Performance: {r.get('performance', 'n/a')} | "
                    f"SEO: {r.get('seo', 'n/a')} | "
                    f"Accessibility: {r.get('accessibility', 'n/a')} | "
                    f"LCP: {r.get('LCP', 'n/a')} | "
                    f"CLS: {r.get('CLS', 'n/a')}"
                )
    else:
        body("PageSpeed data not available (check PAGESPEED_API_KEY).")

    # ── Priority Fixes ─────────────────────────────────────────────────────
    h1("Priority Fixes")
    for fix in audit_result.get("priority_fixes", []):
        h2(f"{fix.get('issue', '')} — {fix.get('page_url', '')}")
        body(f"Current: {fix.get('current_value', 'n/a')}")
        body(f"Recommended: {fix.get('recommended_value', 'n/a')}")
        body(f"Notes: {fix.get('implementation_notes', '')}")

    # ── Revised Meta Titles & Descriptions ───────────────────────────────
    h1("Revised Meta Titles & Descriptions")
    for meta in audit_result.get("revised_meta", []):
        h2(meta.get("page_url", ""))
        body(f"New Title ({len(meta.get('new_title',''))} chars): {meta.get('new_title','')}")
        body(f"New Description ({len(meta.get('new_description',''))} chars): {meta.get('new_description','')}")

    # ── On-Page Issues Summary ────────────────────────────────────────────
    h1("On-Page Issues Summary")
    critical = [i for i in issues if i["severity"] == "critical"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    info = [i for i in issues if i["severity"] == "info"]
    body(f"Total issues found: {len(issues)} — Critical: {len(critical)}, Warnings: {len(warnings)}, Info: {len(info)}")

    h2("Critical")
    for issue in critical[:20]:
        body(f"• [{issue['check']}] {issue['url']} — {issue['detail']}")

    h2("Warnings")
    for issue in warnings[:20]:
        body(f"• [{issue['check']}] {issue['url']} — {issue['detail']}")

    # ── Pages Crawled ──────────────────────────────────────────────────────
    h1("Pages Crawled")
    body(f"Total pages crawled: {len(crawl_data)}")
    for p in crawl_data:
        status = p.get("status", "?")
        title = p.get("title", "(no title)")
        wc = p.get("word_count", 0)
        body(f"• [{status}] {p.get('url','')} | Title: {title[:50]} | Words: {wc}")

    return sections


def _build_requests(sections: list[tuple[str, str]]) -> list[dict]:
    """
    Convert sections to Docs API batchUpdate requests.
    Inserts text sequentially and applies heading styles.
    """
    requests = []
    current_index = 1  # Docs start at index 1

    for text, style in sections:
        requests.append({
            "insertText": {
                "location": {"index": current_index},
                "text": text,
            }
        })

        end_index = current_index + len(text)

        if style != "NORMAL_TEXT":
            requests.append({
                "updateParagraphStyle": {
                    "range": {
                        "startIndex": current_index,
                        "endIndex": end_index,
                    },
                    "paragraphStyle": {"namedStyleType": style},
                    "fields": "namedStyleType",
                }
            })

        current_index = end_index

    return requests
