"""
Reusable script — appends a new video's cold call lines to the
'Buyer Cold Call Scripts' tab in the Buying Hero Google Doc.

Usage:
    Edit SECTIONS and VIDEO_TITLE below, then run:
    python append_to_cold_call_tab.py
"""

import requests as req_lib
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleRequest

CREDS_PATH = r"D:\Dropbox\J Feels\Dev\foreclosure-agent\credentials.json"
DOC_ID     = "15ywj-ewQuhua4SaACMfbzIeR04kHjNygfdkTktmT5o8"
TAB_ID     = "t.4992fw1lln6w"

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]

# ─── EDIT THESE FOR EACH NEW VIDEO ──────────────────────────────────────────

VIDEO_TITLE = "Video Title — Author Name"
VIDEO_URL   = "https://www.youtube.com/watch?v=XXXXXXXXXXX"

SECTIONS = [
    {
        "heading": "SECTION HEADING",
        "lines": [
            ("Label / context", '"Script line goes here."'),
        ],
    },
]

# ────────────────────────────────────────────────────────────────────────────


def get_doc_end_index(creds):
    """Get the last character index of the tab so we can append after it."""
    creds.refresh(GoogleRequest())
    url = f"https://docs.googleapis.com/v1/documents/{DOC_ID}?includeTabsContent=true"
    resp = req_lib.get(url, headers={"Authorization": f"Bearer {creds.token}"})
    resp.raise_for_status()
    data = resp.json()

    for tab in data.get("tabs", []):
        props = tab.get("documentTab", {}).get("tabProperties", {})
        if props.get("tabId") == TAB_ID:
            body = tab.get("documentTab", {}).get("body", {})
            content = body.get("content", [])
            if content:
                return content[-1].get("endIndex", 1) - 1
    return 1


def batch_update(creds, requests_body):
    creds.refresh(GoogleRequest())
    url = f"https://docs.googleapis.com/v1/documents/{DOC_ID}:batchUpdate"
    resp = req_lib.post(
        url,
        headers={"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"},
        json={"requests": requests_body},
    )
    if not resp.ok:
        raise Exception(f"batchUpdate failed {resp.status_code}: {resp.text}")
    return resp.json()


def build_append_requests(start_index):
    """Build insertText + formatting requests starting at start_index."""
    insert_reqs  = []
    format_reqs  = []
    idx = start_index

    def ins(text):
        nonlocal idx
        insert_reqs.append({
            "insertText": {
                "location": {"index": idx, "tabId": TAB_ID},
                "text": text,
            }
        })
        idx += len(text)

    # ── Page break + video header ────────────────────────────────────────────
    page_break_start = idx
    ins("\n")  # newline before page break
    insert_reqs.append({
        "insertPageBreak": {
            "location": {"index": idx, "tabId": TAB_ID}
        }
    })
    idx += 1  # page break is 1 character

    header_start = idx
    header_text  = f"{VIDEO_TITLE}\n"
    ins(header_text)

    source_start = idx
    source_text  = f"Source: {VIDEO_URL}\n\n"
    ins(source_text)

    # ── Sections ─────────────────────────────────────────────────────────────
    section_positions = []

    for section in SECTIONS:
        h_text = section["heading"] + "\n"
        section_positions.append({"type": "heading", "start": idx, "end": idx + len(h_text)})
        ins(h_text)

        for (label, line) in section["lines"]:
            label_text = f"  {label}\n"
            line_text  = f"  {line}\n\n"

            section_positions.append({"type": "label", "start": idx, "end": idx + len(label_text)})
            ins(label_text)

            section_positions.append({"type": "line", "start": idx, "end": idx + len(line_text)})
            ins(line_text)

        ins("\n")

    # ── Formatting ────────────────────────────────────────────────────────────
    # Video title — Heading 1
    format_reqs.append({
        "updateParagraphStyle": {
            "range": {"startIndex": header_start, "endIndex": header_start + len(header_text), "tabId": TAB_ID},
            "paragraphStyle": {"namedStyleType": "HEADING_1"},
            "fields": "namedStyleType",
        }
    })
    # Source URL — italic gray
    format_reqs.append({
        "updateTextStyle": {
            "range": {"startIndex": source_start, "endIndex": source_start + len(source_text), "tabId": TAB_ID},
            "textStyle": {
                "italic": True,
                "foregroundColor": {"color": {"rgbColor": {"red": 0.4, "green": 0.4, "blue": 0.4}}},
            },
            "fields": "italic,foregroundColor",
        }
    })
    # Section headings, labels, script lines
    for pos in section_positions:
        if pos["type"] == "heading":
            format_reqs.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": pos["start"], "endIndex": pos["end"], "tabId": TAB_ID},
                    "paragraphStyle": {"namedStyleType": "HEADING_2"},
                    "fields": "namedStyleType",
                }
            })
        elif pos["type"] == "label":
            format_reqs.append({
                "updateTextStyle": {
                    "range": {"startIndex": pos["start"], "endIndex": pos["end"], "tabId": TAB_ID},
                    "textStyle": {"bold": True},
                    "fields": "bold",
                }
            })
        elif pos["type"] == "line":
            format_reqs.append({
                "updateTextStyle": {
                    "range": {"startIndex": pos["start"], "endIndex": pos["end"], "tabId": TAB_ID},
                    "textStyle": {
                        "foregroundColor": {"color": {"rgbColor": {"red": 0.05, "green": 0.27, "blue": 0.55}}},
                        "fontSize": {"magnitude": 11, "unit": "PT"},
                    },
                    "fields": "foregroundColor,fontSize",
                }
            })

    return insert_reqs, format_reqs


def main():
    creds = service_account.Credentials.from_service_account_file(CREDS_PATH, scopes=SCOPES)

    print("Finding end of tab...")
    end_index = get_doc_end_index(creds)
    print(f"Appending after index {end_index}")

    insert_reqs, format_reqs = build_append_requests(end_index)

    print(f"Inserting {len(insert_reqs)} text blocks...")
    chunk_size = 50
    for i in range(0, len(insert_reqs), chunk_size):
        batch_update(creds, insert_reqs[i:i + chunk_size])

    print(f"Applying {len(format_reqs)} format rules...")
    for i in range(0, len(format_reqs), chunk_size):
        batch_update(creds, format_reqs[i:i + chunk_size])

    print(f"\nDone! View the tab here:")
    print(f"https://docs.google.com/document/d/{DOC_ID}/edit?tab={TAB_ID}")


if __name__ == "__main__":
    main()
