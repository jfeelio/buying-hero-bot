"""
Adds a new tab 'Buyer Cold Call Scripts' to an existing Google Doc
and populates it with extracted lines from the Dean Rogers cold call video.
"""

import json
import requests as req_lib
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build

CREDS_PATH = r"D:\Dropbox\J Feels\Dev\foreclosure-agent\credentials.json"
DOC_ID = "15ywj-ewQuhua4SaACMfbzIeR04kHjNygfdkTktmT5o8"
TAB_TITLE = "Buyer Cold Call Scripts"

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]

CONTENT_SECTIONS = [
    {
        "heading": "OPENING LINES",
        "lines": [
            ("Cold open — buyer found on a platform",
             '"Hey [NAME], my name is [YOUR NAME]. I saw that you were buying properties in [AREA] and I got a new off-market deal. Wanted to see if you might be interested in it."'),
            ("Inbound follow-up — buyer engaged with your listing",
             '"Hey [NAME], this is [YOUR NAME]. I saw you were interested in that property in [AREA]. What questions can I answer for you?"'),
            ("Re-engagement — buyer you already know",
             '"Hey [NAME], what\'s up? I was just seeing if you were still hungry to buy deals."'),
            ("Cold outreach — sourced buyer, no prior contact",
             '"Hey [NAME], I see that you were buying some properties in the area in [AREA] and I got an off-market property right now that\'s pretty hot. Just wanted to reach out — see if you\'re looking to buy more or had any clients."'),
        ],
    },
    {
        "heading": "PRE-QUALIFYING THE BUYER (flip it on them)",
        "lines": [
            ("Let them sell themselves first",
             '"Hey, how many deals have you done out in [AREA]?"'),
            ("Confirm activity level",
             '"You\'re still actively buying in the area, right?"'),
            ("Open the door to their network",
             '"Whether it\'s you or you\'ve got clients — would love to see if we can put a deal together."'),
            ("Warm open with an active buyer",
             '"I\'m just reaching out to the people I know are serious to see if you\'re ready to go."'),
        ],
    },
    {
        "heading": "URGENCY LINES",
        "lines": [
            ("Establish heat early in the call",
             '"There\'s been a whole lot of interest that\'s come in pretty fast here. I\'m just calling everybody to see who\'s serious and who\'s ready to make a move."'),
            ("After sending the deal",
             '"I just sent it out and I\'m getting a whole bunch of crazy interest. I figured I\'d reach out to people I knew were serious."'),
            ("Social proof — inbound volume",
             '"My phone has been ringing nonstop. People are either driving by right now or running their numbers."'),
            ("Hard price expectation",
             '"It looks like it\'s going to go at asking price based on the interest — I haven\'t even had time to check all my messages."'),
            ("Hard deadline — airport close",
             '"I\'m literally about to shut my computer and get in an Uber to the airport. I\'d love to lock something in before I leave."'),
            ("Soft counter when buyer says \'2 hours\'",
             '"You might want to do it quicker — I might be gone before that."'),
            ("51 texts close",
             '"I\'ve got 51 missed texts right now. I think it\'s going to go pretty fast."'),
        ],
    },
    {
        "heading": "GET THEM LOOKING NOW (keep them on the phone)",
        "lines": [
            ("Don't let them hang up and go cold",
             '"Are you in front of your computer right now? Let me send it to you while we\'re talking."'),
            ("Proactive send",
             '"I literally just hit send on it — I\'m doing proactive calls right now. Do you have a few minutes to pull it up?"'),
            ("Time-pressure + look now",
             '"I expect it to move pretty fast. You think you could look at it right now?"'),
            ("Good timing close",
             '"Oh, perfect timing — someone else is actually calling me about it right now. When I hang up I\'ll send it over. Hope to hear back from you quickly."'),
        ],
    },
    {
        "heading": "PROPERTY DESCRIPTION LANGUAGE",
        "lines": [
            ("Spread framing",
             '"There\'s a good spread on this one."'),
            ("Pricing confidence",
             '"It\'s priced to sell."'),
            ("Easy project positioning",
             '"It\'s about as cosmetic as it gets — easy in and out. Floors, paint, kitchen. Once you clear it out, the bones are solid."'),
            ("Speed pitch",
             '"It\'s a really easy in-and-out flip. Cookie cutter house, very straightforward."'),
            ("Vacancy = no friction",
             '"Delivered vacant." / "It\'s vacant — easy to show, easy to close."'),
            ("Reframe the mess",
             '"Yeah, it\'s a hoarder situation — but clear that out for a couple thousand bucks and you\'ve got solid bones. Just needs cosmetic after the junk is gone."'),
        ],
    },
    {
        "heading": "HANDLING OBJECTIONS",
        "lines": [
            ("Price too high — keep the door open",
             '"If that number works for you, great. If not, just tell me what number does and we\'ll see what we can make happen."'),
            ("Repair estimate pushback",
             '"It all depends on your contractors and what finishes you put in. You could come in well under that with mid-grade work."'),
            ("Buyer wants comps",
             '"My partner ran them — he\'s done over a thousand flips and he\'s an agent too. He\'s usually conservative, not pushing the number."'),
            ("Buyer needs to think about it",
             '"I don\'t know if you\'ll get an easier one this year. It\'s about as cosmetic as it gets. But let me know — I just can\'t hold it."'),
            ("Close the gap on price",
             '"We\'re close, man. If you can do [X], I\'d rather not fuss over [Y] dollars. I need to get moving — let\'s just get the contract out."'),
            ("Buyer wants to drive by first",
             '"If they\'ve done their due diligence on the pictures and just want to confirm the inside, we can work on access. But if they\'re ready to lock it up before someone else, that\'s also an option."'),
        ],
    },
    {
        "heading": "CLOSING / GETTING A DECISION",
        "lines": [
            ("Soft close — timing",
             '"If you do want to move on it, how quickly can you give me an answer?"'),
            ("Hard close — urgency + social proof",
             '"I\'m calling back the people I know are serious. See if we can lock in a deal before I head out."'),
            ("FOMO close",
             '"I\'ve got people doing drive-bys right now. If you\'re serious about it, get back to me as soon as you can and let\'s see if we can put a deal together."'),
            ("First come, first served",
             '"It\'s first come, first served. If you\'re ready to move, it could be yours."'),
            ("5-minute close",
             '"I got about 5 minutes. I know you guys can close — you\'re just a little off. Let\'s see if we can bridge it."'),
        ],
    },
    {
        "heading": "VOICEMAIL SCRIPTS",
        "lines": [
            ("Inbound interest voicemail",
             '"Hey [NAME], this is [YOUR NAME] — I saw you had some interest on the property in [AREA]. I think this one\'s going to move really fast today. Shoot me a text or give me a call. Let\'s see if we can put a deal together. Talk soon."'),
            ("Cold outreach voicemail",
             '"Hey [NAME], my name is [YOUR NAME] with Buying Hero. I see you\'ve been buying in [AREA] and I\'ve got an off-market property that just came available — it\'s pretty hot right now. I\'ll shoot you a text too. Give me a call back when you get a chance. Thanks."'),
        ],
    },
    {
        "heading": "META STRATEGY — Coaching Notes from the Video",
        "lines": [
            ("Pre-qualify first, then pitch",
             'Ask "How many deals have you done out there?" before pitching the property. Let the buyer sell themselves on their activity level first — it primes them to prove they\'re serious before you ask anything of them.'),
            ("Create urgency on every call",
             'Reference real or implied buyer activity: "I have a lot of people looking at it right now. I think it\'s going to sell in the next 24 hours. If you want to move on it, how quickly can you give me an answer?"'),
            ("Push for a decision timeline every time",
             'Never end a call without a time commitment. If they say 2 hours, push back — "You might want to do it quicker."'),
            ("Keep them on the phone while they look",
             '"Are you in front of your computer right now? Let me send it to you." Buyers go cold when they hang up. Keep them live while they\'re pulling up the deal.'),
            ("Tag and note every buyer call",
             'Log: cash buyer, fix-and-flip, area, deal type after every call. Your buyer database compounds — every deal makes the next one faster.'),
            ("Update the deal description in real time",
             'Every question a buyer asks on a call = add the answer to the property description immediately. Reduces friction on the next 10 calls.'),
            ("Slight underpricing beats grinding",
             'If no serious movement in 48 hours, price is too high. Renegotiate at the source if possible and re-blast. A motivated buyer at a slightly lower price beats a stalled deal every time.'),
        ],
    },
]


def build_content_requests(tab_id):
    """Build all insertText and formatting requests for the new tab."""
    requests = []
    index = 1  # Docs are 1-indexed

    title_text = "Buyer Cold Call Scripts — Buying Hero\n"
    subtitle_text = "Extracted from: Dean Rogers – Buyer Cold Call Live Demo (YouTube)\n\n"

    # Insert title
    requests.append({"insertText": {"location": {"index": index, "tabId": tab_id}, "text": title_text}})
    index += len(title_text)

    requests.append({"insertText": {"location": {"index": index, "tabId": tab_id}, "text": subtitle_text}})
    index += len(subtitle_text)

    section_positions = []

    for section in CONTENT_SECTIONS:
        heading_text = section["heading"] + "\n"
        section_positions.append({"type": "heading", "start": index, "end": index + len(heading_text)})
        requests.append({"insertText": {"location": {"index": index, "tabId": tab_id}, "text": heading_text}})
        index += len(heading_text)

        for (label, line) in section["lines"]:
            label_text = f"  {label}\n"
            line_text = f"  {line}\n\n"

            section_positions.append({"type": "label", "start": index, "end": index + len(label_text)})
            requests.append({"insertText": {"location": {"index": index, "tabId": tab_id}, "text": label_text}})
            index += len(label_text)

            section_positions.append({"type": "line", "start": index, "end": index + len(line_text)})
            requests.append({"insertText": {"location": {"index": index, "tabId": tab_id}, "text": line_text}})
            index += len(line_text)

        requests.append({"insertText": {"location": {"index": index, "tabId": tab_id}, "text": "\n"}})
        index += 1

    return requests, index, title_text, subtitle_text, section_positions


def build_format_requests(tab_id, title_text, subtitle_text, section_positions):
    """Build formatting requests after all text is inserted."""
    fmt = []

    # Title — Heading 1
    fmt.append({
        "updateParagraphStyle": {
            "range": {"startIndex": 1, "endIndex": len(title_text) + 1, "tabId": tab_id},
            "paragraphStyle": {"namedStyleType": "HEADING_1"},
            "fields": "namedStyleType"
        }
    })

    # Subtitle — italic gray
    sub_start = len(title_text) + 1
    sub_end = sub_start + len(subtitle_text)
    fmt.append({
        "updateTextStyle": {
            "range": {"startIndex": sub_start, "endIndex": sub_end, "tabId": tab_id},
            "textStyle": {
                "italic": True,
                "foregroundColor": {"color": {"rgbColor": {"red": 0.4, "green": 0.4, "blue": 0.4}}}
            },
            "fields": "italic,foregroundColor"
        }
    })

    for pos in section_positions:
        if pos["type"] == "heading":
            fmt.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": pos["start"], "endIndex": pos["end"], "tabId": tab_id},
                    "paragraphStyle": {"namedStyleType": "HEADING_2"},
                    "fields": "namedStyleType"
                }
            })
        elif pos["type"] == "label":
            fmt.append({
                "updateTextStyle": {
                    "range": {"startIndex": pos["start"], "endIndex": pos["end"], "tabId": tab_id},
                    "textStyle": {"bold": True},
                    "fields": "bold"
                }
            })
        elif pos["type"] == "line":
            fmt.append({
                "updateTextStyle": {
                    "range": {"startIndex": pos["start"], "endIndex": pos["end"], "tabId": tab_id},
                    "textStyle": {
                        "foregroundColor": {"color": {"rgbColor": {"red": 0.05, "green": 0.27, "blue": 0.55}}},
                        "fontSize": {"magnitude": 11, "unit": "PT"},
                    },
                    "fields": "foregroundColor,fontSize"
                }
            })

    return fmt


def docs_batch_update(creds, doc_id, requests_body):
    """Make a batchUpdate call directly via REST, bypassing discovery schema validation."""
    auth_req = GoogleRequest()
    creds.refresh(auth_req)
    token = creds.token

    url = f"https://docs.googleapis.com/v1/documents/{doc_id}:batchUpdate"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    resp = req_lib.post(url, headers=headers, json={"requests": requests_body})
    if not resp.ok:
        raise Exception(f"batchUpdate failed {resp.status_code}: {resp.text}")
    return resp.json()


def main():
    creds = service_account.Credentials.from_service_account_file(CREDS_PATH, scopes=SCOPES)

    # Use the existing tab ID from the URL: ?tab=t.u1cm59ew9171
    tab_id = "t.4992fw1lln6w"
    print(f"Writing to existing tab ID: {tab_id}")

    # Step 2: Insert all text
    print("Inserting content...")
    content_requests, _, title_text, subtitle_text, section_positions = build_content_requests(tab_id)

    chunk_size = 50
    for i in range(0, len(content_requests), chunk_size):
        chunk = content_requests[i:i + chunk_size]
        docs_batch_update(creds, DOC_ID, chunk)
    print(f"Inserted {len(content_requests)} text blocks.")

    # Step 3: Apply formatting
    print("Applying formatting...")
    fmt_requests = build_format_requests(tab_id, title_text, subtitle_text, section_positions)
    for i in range(0, len(fmt_requests), chunk_size):
        chunk = fmt_requests[i:i + chunk_size]
        docs_batch_update(creds, DOC_ID, chunk)
    print(f"Applied {len(fmt_requests)} format rules.")

    print(f"\nDone! Open the doc and click the '{TAB_TITLE}' tab:")
    print(f"https://docs.google.com/document/d/{DOC_ID}/edit")


if __name__ == "__main__":
    main()
