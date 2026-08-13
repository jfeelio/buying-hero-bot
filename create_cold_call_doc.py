"""
Creates a Google Doc with the best cold calling lines
extracted from the Dean Rogers buyer cold call video.
"""

import os
from google.oauth2 import service_account
from googleapiclient.discovery import build

CREDS_PATH = r"D:\Dropbox\J Feels\Dev\foreclosure-agent\credentials.json"
SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]

DOC_TITLE = "Buying Hero — Buyer Cold Call Scripts (Dean Rogers)"

CONTENT_SECTIONS = [
    {
        "heading": "OPENING LINES",
        "lines": [
            ('Cold open — buyer you found on a platform',
             '"Hey [NAME], my name is [YOUR NAME]. I saw that you were buying properties in [AREA] and I got a new off-market deal. Wanted to see if you might be interested in it."'),
            ('Inbound follow-up — buyer engaged with your listing',
             '"Hey [NAME], this is [YOUR NAME]. I saw you were interested in that property in [AREA]. What questions can I answer for you?"'),
            ('Re-engagement — buyer you already know',
             '"Hey [NAME], what\'s up? I was just seeing if you were still hungry to buy deals."'),
            ('Proactive outreach — cold buyer in target market',
             '"Hey [NAME], I see that you were buying some properties in the area in [AREA] and I got an off-market property right now that\'s pretty hot. Just wanted to reach out — see if you\'re looking to buy more or had any clients."'),
        ],
    },
    {
        "heading": "PRE-QUALIFYING THE BUYER (flip it on them)",
        "lines": [
            ('Let them sell themselves first',
             '"Hey, how many deals have you done out in [AREA]?"'),
            ('Confirm activity level',
             '"You\'re still actively buying in the area, right?"'),
            ('Open the door to their network',
             '"Whether it\'s you or you\'ve got clients — would love to see if we can put a deal together."'),
            ('Warm open with an active buyer',
             '"I just wanted to reach out to people I know are serious and see if you\'re ready to go."'),
        ],
    },
    {
        "heading": "URGENCY LINES",
        "lines": [
            ('Early in the call — establish heat',
             '"There\'s been a whole lot of interest that\'s come in pretty fast here. I\'m just calling everybody to see who\'s serious and who\'s ready to make a move."'),
            ('After sending the deal',
             '"I just sent it out and I\'m getting a whole bunch of crazy interest on it. I think it\'s going to go pretty fast — so I figured I\'d reach out to people I knew were serious."'),
            ('Social proof — inbound volume',
             '"My phone has been ringing nonstop. People are either driving by it right now or running their numbers."'),
            ('Hard clock — price expectation',
             '"It looks like it\'s going to go at asking price. Based on the interest, I haven\'t even had a chance to check all my messages."'),
            ('Airport close — hard deadline',
             '"I\'m literally about to shut my computer and get in an Uber to the airport. I\'d love to lock something in before I leave."'),
            ('Soft pressure — buyer said \'2 hours\'',
             '"You might want to do it quicker — I might be gone before that."'),
        ],
    },
    {
        "heading": "KEEP THEM ON THE PHONE / GET THEM LOOKING NOW",
        "lines": [
            ('Don\'t let them hang up and go cold',
             '"Are you in front of your computer right now? Let me send it to you while we\'re talking."'),
            ('Proactive send',
             '"I literally just hit send on it — I\'m doing proactive calls right now. Do you have a few minutes to pull it up?"'),
            ('Time-pressure + look now',
             '"I expect it to move pretty fast. You think you could look at it right now?"'),
            ('Good timing close',
             '"Oh, perfect — someone else is calling me right now about it. When I hang up I\'ll send it over. Hopefully I can hear back from you quickly."'),
        ],
    },
    {
        "heading": "PROPERTY DESCRIPTION LANGUAGE",
        "lines": [
            ('Spread / value framing',
             '"There\'s a good spread on this one."'),
            ('Pricing confidence',
             '"It\'s priced to sell."'),
            ('Easy project positioning',
             '"It\'s about as cosmetic as it gets — easy in and out. Floors, paint, kitchen. Once you clear it out, the bones are solid."'),
            ('Speed pitch',
             '"It\'s a really easy in-and-out flip. Cookie cutter house, very straightforward."'),
            ('Vacancy = no friction',
             '"Delivered vacant." / "It\'s vacant — easy to show, easy to close."'),
            ('Reframe the mess',
             '"Yeah, it\'s a hoarder situation — but clear that out for a couple thousand bucks and you\'ve got solid bones. It just needs cosmetic after the junk is gone."'),
        ],
    },
    {
        "heading": "HANDLING OBJECTIONS",
        "lines": [
            ('Price too high — keep the door open',
             '"If you feel like that could work, let me know. If not, just tell me what number works and we\'ll see what we can make happen."'),
            ('Repair estimate pushback',
             '"Obviously it all depends on the contractors you use and what finishes you put in. You could go mid-grade and come in under that number."'),
            ('Comps are light',
             '"My partner ran it — he\'s done over a thousand flips and he\'s an agent too. He doesn\'t push numbers. He\'s usually conservative."'),
            ('Buyer needs to think',
             '"I don\'t know if you\'ll get an easier one this year. It\'s about as cosmetic as it gets. But let me know — I just can\'t hold it."'),
            ('Close the gap on price',
             '"We\'re close, man. If you can go [X], I\'d rather not fuss over [Y] dollars. I need to get moving. Let\'s just get the contract out."'),
            ('Buyer wants to drive by first',
             '"If they\'ve done their due diligence on the pictures and just want to confirm the inside — we can work on access. But if they\'re ready to lock it up before someone else, that\'s also an option."'),
        ],
    },
    {
        "heading": "CLOSING / GETTING A DECISION",
        "lines": [
            ('Soft close — timing',
             '"If you do want to move on it, how quickly can you give me an answer?"'),
            ('Hard close — urgency + compliment',
             '"I\'m calling back the people I know are serious. See if we can lock in a deal before I head out."'),
            ('FOMO close',
             '"I\'ve got people doing drive-bys right now. If you\'re serious about it, get back to me as soon as you can and let\'s see if we can put a deal together."'),
            ('First come, first served',
             '"It\'s first come, first served. If you\'re ready to move, it could be yours."'),
            ('5-minute close',
             '"I got about 5 minutes. I know you guys can close — you\'re just a little off. Let\'s see if we can bridge it."'),
        ],
    },
    {
        "heading": "VOICEMAIL SCRIPTS",
        "lines": [
            ('Standard voicemail — inbound interest',
             '"Hey [NAME], this is [YOUR NAME] — I saw you had some interest on the property in [AREA]. I think this one\'s going to move really fast today. Shoot me a text or give me a call. Let\'s see if we can put a deal together. Talk soon."'),
            ('Cold voicemail — sourced buyer',
             '"Hey [NAME], my name is [YOUR NAME] with Buying Hero. I see you\'ve been buying in [AREA] and I\'ve got an off-market property that just came available — it\'s pretty hot right now. I\'ll shoot you a text too so you can see the details. Give me a call back when you get a chance. Thanks."'),
        ],
    },
    {
        "heading": "META STRATEGY (coaching notes from the video)",
        "lines": [
            ('Pre-qualify first, then pitch',
             'Ask "How many deals have you done out there?" before pitching the property. Let the buyer sell themselves on their activity level — it primes them to prove they\'re serious.'),
            ('Create urgency on every call',
             'Reference real or implied buyer activity: "I have a lot of people looking at it right now. I do think it\'s going to sell in the next 24 hours. If you want to move on it, how quickly can you give me an answer?"'),
            ('Push for a decision timeline every time',
             'Never end a call without a time commitment: "How soon can you give me an answer?" If they say 2 hours, push back — "You might want to do it quicker."'),
            ('Keep them on the phone while they look',
             '"Are you in front of your computer right now? Let me send it to you." Buyers go cold when they hang up. Keep them live while they\'re pulling up the deal.'),
            ('Tag and note every buyer call',
             'Log cash buyer, fix-and-flip, area, deal type after every call. Your buyer database compounds — every deal you sell makes the next one faster.'),
            ('Update the deal description in real time',
             'Every question a buyer asks on a call = add the answer to the property description immediately. Reduces friction on the next 10 calls.'),
            ('Slight underpricing beats grinding',
             'If no serious movement in 48 hours, price is too high. Renegotiate at the source if possible and re-blast. A motivated buyer at a slightly lower price beats a stalled deal every time.'),
        ],
    },
]


def create_doc():
    creds = service_account.Credentials.from_service_account_file(CREDS_PATH, scopes=SCOPES)
    docs_service = build("docs", "v1", credentials=creds)
    drive_service = build("drive", "v3", credentials=creds)

    # Create blank doc
    doc = docs_service.documents().create(body={"title": DOC_TITLE}).execute()
    doc_id = doc["documentId"]
    print(f"Created doc: https://docs.google.com/document/d/{doc_id}/edit")

    # Share with anyone with link (viewer)
    drive_service.permissions().create(
        fileId=doc_id,
        body={"type": "anyone", "role": "writer"},
    ).execute()

    # Build all the text content first, then insert in one batch
    requests = []
    index = 1  # Google Docs is 1-indexed

    # Title
    title_text = DOC_TITLE + "\n"
    subtitle_text = "Extracted from: Dean Rogers – Buyer Cold Call Live Demo\n\n"

    requests.append({
        "insertText": {
            "location": {"index": index},
            "text": title_text
        }
    })
    index += len(title_text)

    requests.append({
        "insertText": {
            "location": {"index": index},
            "text": subtitle_text
        }
    })
    index += len(subtitle_text)

    for section in CONTENT_SECTIONS:
        heading_text = section["heading"] + "\n"
        requests.append({
            "insertText": {
                "location": {"index": index},
                "text": heading_text
            }
        })
        index += len(heading_text)

        for (label, line) in section["lines"]:
            label_text = f"  {label}\n"
            line_text = f"  {line}\n\n"

            requests.append({
                "insertText": {
                    "location": {"index": index},
                    "text": label_text
                }
            })
            index += len(label_text)

            requests.append({
                "insertText": {
                    "location": {"index": index},
                    "text": line_text
                }
            })
            index += len(line_text)

        requests.append({
            "insertText": {
                "location": {"index": index},
                "text": "\n"
            }
        })
        index += 1

    # Execute all text insertions
    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": requests}
    ).execute()

    # Now apply formatting
    format_requests = []

    # Re-read doc to get actual positions
    doc_content = docs_service.documents().get(documentId=doc_id).execute()
    full_text = ""
    for elem in doc_content.get("body", {}).get("content", []):
        for pe in elem.get("paragraph", {}).get("elements", []):
            full_text += pe.get("textRun", {}).get("content", "")

    # Format title (index 1)
    title_end = len(title_text) + 1
    format_requests.append({
        "updateParagraphStyle": {
            "range": {"startIndex": 1, "endIndex": title_end},
            "paragraphStyle": {"namedStyleType": "HEADING_1"},
            "fields": "namedStyleType"
        }
    })

    # Format subtitle
    subtitle_start = title_end
    subtitle_end = subtitle_start + len(subtitle_text)
    format_requests.append({
        "updateTextStyle": {
            "range": {"startIndex": subtitle_start, "endIndex": subtitle_end},
            "textStyle": {"italic": True, "foregroundColor": {"color": {"rgbColor": {"red": 0.4, "green": 0.4, "blue": 0.4}}}},
            "fields": "italic,foregroundColor"
        }
    })

    # Format section headings
    cursor = subtitle_end
    for section in CONTENT_SECTIONS:
        heading_text = section["heading"] + "\n"
        heading_end = cursor + len(heading_text)
        format_requests.append({
            "updateParagraphStyle": {
                "range": {"startIndex": cursor, "endIndex": heading_end},
                "paragraphStyle": {"namedStyleType": "HEADING_2"},
                "fields": "namedStyleType"
            }
        })
        cursor = heading_end

        for (label, line) in section["lines"]:
            label_text = f"  {label}\n"
            line_text = f"  {line}\n\n"

            label_end = cursor + len(label_text)
            # Bold the label
            format_requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": cursor, "endIndex": label_end},
                    "textStyle": {"bold": True},
                    "fields": "bold"
                }
            })
            cursor = label_end

            line_end = cursor + len(line_text)
            # Style the script line
            format_requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": cursor, "endIndex": line_end},
                    "textStyle": {
                        "foregroundColor": {"color": {"rgbColor": {"red": 0.0, "green": 0.3, "blue": 0.6}}},
                        "fontSize": {"magnitude": 11, "unit": "PT"}
                    },
                    "fields": "foregroundColor,fontSize"
                }
            })
            cursor = line_end

        cursor += 1  # blank line between sections

    docs_service.documents().batchUpdate(
        documentId=doc_id,
        body={"requests": format_requests}
    ).execute()

    print(f"\nDone! Open here:\nhttps://docs.google.com/document/d/{doc_id}/edit")
    return doc_id


if __name__ == "__main__":
    create_doc()
