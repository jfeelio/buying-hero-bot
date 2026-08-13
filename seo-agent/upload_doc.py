"""
Write audit_2026-03-09.md into an existing Google Doc with full formatting.
Handles: H1/H2/H3 headings, bold inline text, bullet lists, code spans, tables.
"""

import re
from pathlib import Path
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

CREDS_PATH = "../foreclosure-agent/credentials.json"
MD_FILE = Path(__file__).parent / "reports" / "audit_2026-03-09.md"
DOC_ID = "1Pig9xknYXbVvG3WmgUjZjhoDhfDfQpBtdlWjhgkWVqw"
DOC_URL = f"https://docs.google.com/document/d/{DOC_ID}/edit"
SCOPES = ["https://www.googleapis.com/auth/documents"]
BATCH_SIZE = 150


# ── Inline markdown parser ─────────────────────────────────────────────────────

def strip_inline(text):
    """
    Strip ** and ` markers from text.
    Returns (clean_text, bold_ranges, code_ranges) where ranges are (start, end) char offsets.
    """
    result = []
    bold_ranges = []
    code_ranges = []
    i = 0
    pos = 0

    while i < len(text):
        if text[i:i+2] == '**':
            j = text.find('**', i + 2)
            if j != -1:
                start = pos
                content = text[i+2:j]
                result.append(content)
                pos += len(content)
                bold_ranges.append((start, pos))
                i = j + 2
            else:
                result.append(text[i])
                pos += 1
                i += 1
        elif text[i] == '`':
            j = text.find('`', i + 1)
            if j != -1:
                start = pos
                content = text[i+1:j]
                result.append(content)
                pos += len(content)
                code_ranges.append((start, pos))
                i = j + 1
            else:
                result.append(text[i])
                pos += 1
                i += 1
        else:
            result.append(text[i])
            pos += 1
            i += 1

    return ''.join(result), bold_ranges, code_ranges


# ── Markdown parser ────────────────────────────────────────────────────────────

def parse_table(lines):
    """Parse markdown table lines into list of rows (each row = list of cell strings)."""
    rows = []
    for line in lines:
        if re.match(r'^\|[\s\-:|]+\|$', line.strip()):
            continue  # separator row
        cells = [c.strip() for c in line.strip().split('|')]
        cells = [c for c in cells if c or cells.index(c) not in (0, len(cells)-1)]
        rows.append(cells)
    return rows


def parse_markdown(content):
    """
    Parse markdown content into a list of segment dicts.
    Each segment has: type, text (optional), bold_ranges, code_ranges, rows (for tables).
    """
    segments = []
    lines = content.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i]

        # ── Table ──────────────────────────────────────────────────────────────
        if line.startswith('|'):
            table_lines = []
            while i < len(lines) and lines[i].startswith('|'):
                table_lines.append(lines[i])
                i += 1
            rows = parse_table(table_lines)
            if rows:
                segments.append({'type': 'table', 'rows': rows})
            continue

        # ── Horizontal rule ────────────────────────────────────────────────────
        if line.strip() == '---':
            segments.append({'type': 'hr'})
            i += 1
            continue

        # ── Headings ───────────────────────────────────────────────────────────
        if line.startswith('### '):
            text, bold, code = strip_inline(line[4:].strip())
            segments.append({'type': 'heading3', 'text': text, 'bold_ranges': bold, 'code_ranges': code})
        elif line.startswith('## '):
            text, bold, code = strip_inline(line[3:].strip())
            segments.append({'type': 'heading2', 'text': text, 'bold_ranges': bold, 'code_ranges': code})
        elif line.startswith('# '):
            text, bold, code = strip_inline(line[2:].strip())
            segments.append({'type': 'heading1', 'text': text, 'bold_ranges': bold, 'code_ranges': code})

        # ── Bullet list ────────────────────────────────────────────────────────
        elif line.startswith('- '):
            text, bold, code = strip_inline(line[2:].strip())
            segments.append({'type': 'bullet', 'text': text, 'bold_ranges': bold, 'code_ranges': code})

        # ── Numbered list ──────────────────────────────────────────────────────
        elif re.match(r'^\d+\. ', line):
            # Strip outer number; also strip inner duplicate number if present (e.g. "1. 1. TEXT")
            content = re.sub(r'^\d+\. ', '', line).strip()
            content = re.sub(r'^\d+\. ', '', content).strip()
            text, bold, code = strip_inline(content)
            segments.append({'type': 'numbered', 'text': text, 'bold_ranges': bold, 'code_ranges': code})

        # ── Blank line ─────────────────────────────────────────────────────────
        elif line.strip() == '':
            segments.append({'type': 'blank'})

        # ── Normal text ────────────────────────────────────────────────────────
        else:
            text, bold, code = strip_inline(line.strip())
            if text:
                segments.append({'type': 'normal', 'text': text, 'bold_ranges': bold, 'code_ranges': code})
            else:
                segments.append({'type': 'blank'})

        i += 1

    return segments


# ── Request builder ────────────────────────────────────────────────────────────

HEADING_STYLES = {
    'heading1': 'HEADING_1',
    'heading2': 'HEADING_2',
    'heading3': 'HEADING_3',
}


def build_requests(segments):
    requests = []
    idx = 1  # Docs content starts at index 1

    for seg in segments:
        t = seg['type']

        # ── Blank / HR ─────────────────────────────────────────────────────────
        if t in ('blank', 'hr'):
            requests.append({'insertText': {'location': {'index': idx}, 'text': '\n'}})
            idx += 1
            continue

        # ── Table ──────────────────────────────────────────────────────────────
        if t == 'table':
            rows = seg['rows']
            for row_i, row in enumerate(rows):
                row_text = '  │  '.join(row) + '\n'
                requests.append({'insertText': {'location': {'index': idx}, 'text': row_text}})
                end = idx + len(row_text)

                # Bold header row
                if row_i == 0:
                    requests.append({
                        'updateTextStyle': {
                            'range': {'startIndex': idx, 'endIndex': end - 1},
                            'textStyle': {'bold': True},
                            'fields': 'bold',
                        }
                    })

                # Monospace font for all table rows
                requests.append({
                    'updateTextStyle': {
                        'range': {'startIndex': idx, 'endIndex': end - 1},
                        'textStyle': {'weightedFontFamily': {'fontFamily': 'Courier New'}, 'fontSize': {'magnitude': 9, 'unit': 'PT'}},
                        'fields': 'weightedFontFamily,fontSize',
                    }
                })

                idx = end

            # Blank line after table
            requests.append({'insertText': {'location': {'index': idx}, 'text': '\n'}})
            idx += 1
            continue

        # ── Text-based segments ────────────────────────────────────────────────
        text = seg.get('text', '')
        if not text:
            requests.append({'insertText': {'location': {'index': idx}, 'text': '\n'}})
            idx += 1
            continue

        full_text = text + '\n'
        requests.append({'insertText': {'location': {'index': idx}, 'text': full_text}})
        end_idx = idx + len(full_text)

        # Paragraph style (headings)
        if t in HEADING_STYLES:
            requests.append({
                'updateParagraphStyle': {
                    'range': {'startIndex': idx, 'endIndex': end_idx},
                    'paragraphStyle': {'namedStyleType': HEADING_STYLES[t]},
                    'fields': 'namedStyleType',
                }
            })

        # Bullet list
        if t == 'bullet':
            requests.append({
                'createParagraphBullets': {
                    'range': {'startIndex': idx, 'endIndex': end_idx},
                    'bulletPreset': 'BULLET_DISC_CIRCLE_SQUARE',
                }
            })

        # Numbered list
        if t == 'numbered':
            requests.append({
                'createParagraphBullets': {
                    'range': {'startIndex': idx, 'endIndex': end_idx},
                    'bulletPreset': 'NUMBERED_DECIMAL_ALPHA_ROMAN',
                }
            })

        # Inline bold
        for start, end in seg.get('bold_ranges', []):
            abs_start = idx + start
            abs_end = idx + end
            if abs_start < abs_end <= end_idx:
                requests.append({
                    'updateTextStyle': {
                        'range': {'startIndex': abs_start, 'endIndex': abs_end},
                        'textStyle': {'bold': True},
                        'fields': 'bold',
                    }
                })

        # Inline code (monospace)
        for start, end in seg.get('code_ranges', []):
            abs_start = idx + start
            abs_end = idx + end
            if abs_start < abs_end <= end_idx:
                requests.append({
                    'updateTextStyle': {
                        'range': {'startIndex': abs_start, 'endIndex': abs_end},
                        'textStyle': {
                            'weightedFontFamily': {'fontFamily': 'Courier New'},
                            'backgroundColor': {'color': {'rgbColor': {'red': 0.95, 'green': 0.95, 'blue': 0.95}}},
                        },
                        'fields': 'weightedFontFamily,backgroundColor',
                    }
                })

        idx = end_idx

    return requests


# ── Main ──────────────────────────────────────────────────────────────────────

def send_batches(docs, doc_id, requests):
    total = len(requests)
    for i in range(0, total, BATCH_SIZE):
        batch = requests[i:i+BATCH_SIZE]
        docs.documents().batchUpdate(
            documentId=doc_id,
            body={'requests': batch},
        ).execute()
        print(f"  Batch {i//BATCH_SIZE + 1}/{-(-total//BATCH_SIZE)} sent ({len(batch)} requests)")


def main():
    content = MD_FILE.read_text(encoding='utf-8')
    creds = Credentials.from_service_account_file(CREDS_PATH, scopes=SCOPES)
    docs = build('docs', 'v1', credentials=creds)

    # Clear existing doc content
    print("Reading current doc...")
    doc = docs.documents().get(documentId=DOC_ID).execute()
    body_content = doc.get('body', {}).get('content', [])
    end_index = body_content[-1].get('endIndex', 2) - 1 if body_content else 1

    clear_requests = []
    if end_index > 1:
        clear_requests.append({
            'deleteContentRange': {
                'range': {'startIndex': 1, 'endIndex': end_index}
            }
        })
        docs.documents().batchUpdate(
            documentId=DOC_ID,
            body={'requests': clear_requests},
        ).execute()
        print("Cleared existing content.")

    # Parse and build
    print("Parsing markdown...")
    segments = parse_markdown(content)
    print(f"  {len(segments)} segments parsed.")

    print("Building requests...")
    requests = build_requests(segments)
    print(f"  {len(requests)} API requests built.")

    print("Writing to Google Doc...")
    send_batches(docs, DOC_ID, requests)

    print(f"\nDone. URL: {DOC_URL}")


if __name__ == '__main__':
    main()
