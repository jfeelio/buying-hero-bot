#!/usr/bin/env python3
"""Publish Google Ads Strategy to Google Doc with full formatting."""

from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

DOC_ID = "1p5CUcFbjeW5-huEe7rBoE6403Z9snskpU2KkVJoJjsI"
CREDS  = "D:/Dropbox/J Feels/Dev/foreclosure-agent/credentials.json"
SCOPES = ["https://www.googleapis.com/auth/documents"]

# ── Colors ───────────────────────────────────────────────────────────────────
NAVY  = {"red": 0.067, "green": 0.145, "blue": 0.337}
GOLD  = {"red": 0.855, "green": 0.647, "blue": 0.125}
GREEN = {"red": 0.09,  "green": 0.44,  "blue": 0.09}
RED   = {"red": 0.75,  "green": 0.10,  "blue": 0.10}
GRAY  = {"red": 0.40,  "green": 0.40,  "blue": 0.40}
WHITE = {"red": 1.0,   "green": 1.0,   "blue": 1.0}
BLACK = {"red": 0.0,   "green": 0.0,   "blue": 0.0}
LNAVY = {"red": 0.87,  "green": 0.91,  "blue": 0.97}

# ── Segment list ─────────────────────────────────────────────────────────────
# Each tuple: (text, para_style, bold, size, fg, bg, bullet, mono, italic)
SEGS = []

def _add(text, style="NORMAL_TEXT", bold=False, size=11,
         fg=None, bg=None, bullet=False, mono=False, italic=False):
    SEGS.append((text, style, bold, size,
                 fg if fg else BLACK,
                 bg, bullet, mono, italic))

def blank():           _add("")
def h1(t):             _add(t, "HEADING_1", True, 16, WHITE, NAVY)
def h2(t):             _add(t, "HEADING_2", True, 13, NAVY)
def h3(t):             _add(t, "HEADING_3", True, 11, NAVY)
def body(t, **kw):     _add(t, "NORMAL_TEXT", **kw)
def bullet(t, **kw):   _add(t, "NORMAL_TEXT", bullet=True, **kw)
def kw(t):             _add(t, "NORMAL_TEXT", bullet=True, mono=True, size=10)
def callout(t, color=None): _add(t, "NORMAL_TEXT", bold=True, size=13,
                                   fg=color if color else NAVY)

# ════════════════════════════════════════════════════════════════════════════
# DOCUMENT CONTENT
# ════════════════════════════════════════════════════════════════════════════

# Title block
_add("Buying Hero — Google Ads Launch Strategy", "TITLE", True, 26, WHITE, NAVY)
_add("Search Campaigns  ·  Miami-Dade County  ·  Phase 1 Launch Plan",
     "NORMAL_TEXT", False, 12, WHITE, NAVY, italic=True)
blank()

# ── 1. Budget Reality Check ───────────────────────────────────────────────
h1("💰  Budget Reality Check First")
body("Before structure, the math has to work. Miami-Dade is a competitive market.")
blank()
body("Key benchmarks:", bold=True)
bullet("Avg CPC (high-intent): $12–22")
bullet("Landing page CVR on a quality Carrot page: 15–25%")
bullet("Cost per lead: $60–150")
bullet("Lead-to-contract rate on paid traffic: 3–6%")
bullet("Cost per contract: $1,500–4,500", bold=True, fg=NAVY)
blank()
body("At a $20K average assignment fee the math works — but you need volume to optimize. "
     "Too little spend and you are flying blind.")
blank()
callout("✅  Recommended starting budget: $3,000/month", color=GREEN)
blank()
body("That buys ~180 clicks → ~30–40 leads → 1–2 contracts/month at minimum. "
     "Enough data to make real decisions. Do NOT go under $2,000 — "
     "the sample size will be too small.")
blank(); blank()

# ── 2. Campaign Structure ─────────────────────────────────────────────────
h1("🏗  Phase 1 Campaign Structure")
body("Two campaigns. That's it.", bold=True, fg=NAVY)
blank()
body("Don't build 6 campaigns on day one. You'll dilute budget and have no data anywhere. "
     "Keep it tight, gather data, then expand.")
blank()

h2("Campaign 1: Urgent Sellers — $1,800/mo  (60%)")
bullet("Ad Group 1: Sell House Fast")
bullet("Ad Group 2: Cash Home Buyers")
bullet("Ad Group 3: Sell As-Is")
blank()

h2("Campaign 2: Distressed Sellers — $1,200/mo  (40%)")
bullet("Ad Group 1: Foreclosure")
bullet("Ad Group 2: Problem Properties")
bullet("Ad Group 3: Inherited / Probate")
blank()

h3("Campaign Settings — Apply to Both")
bullet("Network: Search only — uncheck Search Partners initially")
bullet("Location: Miami-Dade County — set to Presence (not Presence or interest)")
bullet("Language: English + Spanish")
bullet("Bidding: Manual CPC — do NOT use Smart Bidding until 30+ conversions/month",
       bold=True, fg=RED)
bullet("Ad schedule: Mon–Sat, 7am–9pm — remove Sunday (lower intent, wastes budget)")
bullet("Device: All — monitor mobile vs desktop CVR weekly and adjust bids accordingly")
blank(); blank()

# ── 3. Keyword Strategy ───────────────────────────────────────────────────
h1("🔑  Keyword Strategy")

h2("Campaign 1 — Urgent Sellers")

h3("Ad Group 1: Sell House Fast")
body("Exact match:", bold=True, fg=GRAY)
for k in ["[sell my house fast]","[sell my house fast Miami]",
          "[sell my house fast for cash]","[sell my home fast]",
          "[need to sell my house fast]","[sell house quickly]"]: kw(k)
blank()
body("Phrase match:", bold=True, fg=GRAY)
for k in ['"sell my house fast"','"sell my home fast"','"sell house fast cash"']: kw(k)
blank()

h3("Ad Group 2: Cash Home Buyers")
body("Exact match:", bold=True, fg=GRAY)
for k in ["[cash home buyers Miami]","[cash home buyers near me]",
          "[we buy houses Miami]","[we buy houses for cash]",
          "[buy my house for cash]","[sell house for cash Miami]",
          "[cash offer for my house]"]: kw(k)
blank()
body("Phrase match:", bold=True, fg=GRAY)
for k in ['"cash home buyers"','"we buy houses"',
          '"cash offer my house"','"sell house cash"']: kw(k)
blank()

h3("Ad Group 3: Sell As-Is")
body("Exact match:", bold=True, fg=GRAY)
for k in ["[sell house as is]","[sell house as is Miami]",
          "[sell house no repairs]","[sell house without repairs]",
          "[buy house as is]"]: kw(k)
blank()
body("Phrase match:", bold=True, fg=GRAY)
for k in ['"sell house as is"','"sell home as is"','"buy houses as is"']: kw(k)
blank()

h2("Campaign 2 — Distressed Sellers")

h3("Ad Group 1: Foreclosure")
body("Exact match:", bold=True, fg=GRAY)
for k in ["[sell house in foreclosure]","[sell house before foreclosure]",
          "[stop foreclosure sell house]","[house in foreclosure options]",
          "[sell home foreclosure]"]: kw(k)
blank()
body("Phrase match:", bold=True, fg=GRAY)
for k in ['"sell house foreclosure"','"stop foreclosure"',
          '"behind on mortgage sell house"']: kw(k)
blank()

h3("Ad Group 2: Problem Properties")
body("Exact match:", bold=True, fg=GRAY)
for k in ["[can't sell my house]","[house won't sell]","[sell problem house]",
          "[sell house bad condition]","[sell house no equity]",
          "[house sitting vacant]"]: kw(k)
blank()
body("Phrase match:", bold=True, fg=GRAY)
for k in ['"can\'t sell my house"','"house won\'t sell"',
          '"sell house fast problem"']: kw(k)
blank()

h3("Ad Group 3: Inherited / Probate")
body("Exact match:", bold=True, fg=GRAY)
for k in ["[sell inherited house]","[sell inherited property]",
          "[sell estate house fast]","[inherited house don't want]",
          "[sell probate house]"]: kw(k)
blank()
body("Phrase match:", bold=True, fg=GRAY)
for k in ['"sell inherited house"','"inherited property sell"',
          '"sell estate property fast"']: kw(k)
blank()

h2("⛔  Negative Keywords — Add at Account Level Before Day One")
body("Add every item below before you go live. These prevent wasted spend on non-seller traffic.",
     bold=True, fg=RED)
blank()
for k in ["free","how to sell","tips","advice","DIY","checklist","guide","template",
          "realtor","real estate agent","list my home","MLS listing",
          "Zillow","Redfin","Trulia","Opendoor","Offerpad","Knock","iBuyer",
          "rent","for rent","rental","landlord",
          "buy a house","purchase a home","buying a home","homes for sale",
          "jobs","careers","hiring","school","course","license"]:
    kw(k)
blank(); blank()

# ── 4. Ad Copy ────────────────────────────────────────────────────────────
h1("✍  Ad Copy — Responsive Search Ads")
body("One RSA per ad group. Google mixes and matches headlines and descriptions. "
     "Give it the best possible combinations to test.", italic=True, fg=GRAY)
callout("Rule: Every headline must stand alone. Every description must close.")
blank()

# — Sell House Fast —
h2("Ad Group: Sell House Fast")
h3("Headlines (15 — ordered by priority)")
for hl in [
    "1.   We Buy Houses Fast In Miami",
    "2.   Sell Your House In 7 Days",
    "3.   Cash Offer Within 24 Hours",
    "4.   No Repairs. No Fees. No Hassle.",
    "5.   Close In As Little As 7 Days",
    "6.   Buying Hero — Local Miami Buyers",
    "7.   Get A Fair Cash Offer Today",
    "8.   Skip The Repairs. Keep The Profit.",
    "9.   We Close On Your Timeline",
    "10.  Sell Fast — Any Condition",
    "11.  No Realtor. No Commission.",
    "12.  Stressed About Selling? We Help.",
    "13.  Miami's Trusted Cash Home Buyers",
    "14.  Sell As-Is For A Fair Price",
    "15.  Free Offer — No Obligation",
]: kw(hl)
blank()
h3("Descriptions (4)")
for d in [
    '1.  Get a no-obligation cash offer in 24 hours. We buy houses in any condition, any situation. Close in as little as 7 days or on your schedule.',
    '2.  Tired of repairs, showings, and waiting? We buy directly from you — no agents, no fees, no surprises. Just a fair offer and a fast close.',
    '3.  We\'ve helped hundreds of Miami homeowners sell fast without the hassle. Call or fill out our form for a free, no-pressure offer today.',
    '4.  Behind on payments? Inherited a property? Just need out fast? We handle complicated situations. Fair cash offer, quick close, zero fees.',
]: bullet(d)
blank()
h3("Pinning Strategy")
bullet('Pin "We Buy Houses Fast In Miami" → Position 1 (establishes who you are)')
bullet('Pin "No Repairs. No Fees. No Hassle." → Position 3 (handles objections)')
bullet("Leave everything else unpinned — let Google test and find winners")
blank()

# — Cash Home Buyers —
h2("Ad Group: Cash Home Buyers")
h3("Headlines (15)")
for hl in [
    "1.   Buying Hero Buys Houses For Cash",
    "2.   Fair Cash Offer — Miami Area",
    "3.   We Pay Cash. You Pick The Date.",
    "4.   No Banks. No Delays. Cash Close.",
    "5.   Sell Your Home Without An Agent",
    "6.   100% Cash Buyers — No Financing",
    "7.   Cash In Hand — 7 to 30 Days",
    "8.   No Showings. No Open Houses.",
    "9.   Any Situation. Any Condition.",
    "10.  Get Your Cash Offer In 24 Hours",
    "11.  We Buy Inherited Homes Too",
    "12.  Foreclosure? We Can Help.",
    "13.  Local Buyers. Real Offers.",
    "14.  Skip The MLS. Sell Direct.",
    "15.  Close When You're Ready",
]: kw(hl)
blank()
h3("Descriptions (4)")
for d in [
    "1.  Buying Hero pays cash for Miami homes in any condition. Get an offer in 24 hours and close in as little as 7 days. No fees, no repairs, no agents.",
    "2.  Why list with an agent when you can sell directly? We make fair cash offers on Miami-Dade homes — any situation, any condition, fast close.",
    "3.  Cash buyer with a track record in South Florida. We close fast, pay fair, and handle the details so you don't have to. Free offer, no pressure.",
    "4.  Selling to us means no commissions, no repair costs, no fall-through risk. Just a fair cash price and a close on your timeline.",
]: bullet(d)
blank()

# — Foreclosure —
h2("Ad Group: Foreclosure")
h3("Headlines (15)")
for hl in [
    "1.   Stop Foreclosure — Sell Fast",
    "2.   Facing Foreclosure In Miami?",
    "3.   Sell Before The Bank Takes Over",
    "4.   We Buy Houses In Foreclosure",
    "5.   Cash Offer — Close Before Auction",
    "6.   Options To Stop Foreclosure",
    "7.   Sell Your Home. Save Your Credit.",
    "8.   Behind On Payments? We Can Help.",
    "9.   Fast Sale Before Foreclosure Date",
    "10.  Get Out From Under — Sell Fast",
    "11.  No Judgment. Just Solutions.",
    "12.  Local Buyers Who Understand",
    "13.  Fair Offer Even In Foreclosure",
    "14.  Act Now — Protect What You Have",
    "15.  Free Consultation — No Obligation",
]: kw(hl)
blank()
h3("Descriptions (4)")
for d in [
    "1.  If you're facing foreclosure, time matters. We can make a cash offer quickly and close before your auction date. Free consultation — no pressure.",
    "2.  Selling your home before foreclosure can protect your credit and put cash in your pocket. We've helped Miami homeowners do it — we can help you too.",
    "3.  You have more options than you think. Get a fair cash offer from a local buyer who understands your situation. Fast, private, no fees.",
    "4.  Don't let the bank make the decision for you. Call Buying Hero today for a no-obligation offer. We move fast on distressed situations.",
]: bullet(d)
blank(); blank()

# ── 5. Landing Page Blueprint ─────────────────────────────────────────────
h1("🖥  Landing Page Blueprint")
callout("This is where most campaigns fail. A perfect ad sending traffic to a weak "
        "page is money thrown away.", color=RED)
blank()
_add("Do NOT send traffic to your homepage.",
     "NORMAL_TEXT", True, 14, RED)
body("Build a dedicated page per campaign — Carrot supports this natively. "
     "Minimum: one for Sell Fast, one for Foreclosure.")
blank()

h2("Page Structure — Top to Bottom")

h3("Section 1: Hero  (the only thing that truly matters)")
bullet('Headline: "Sell Your Miami Home Fast — Get A Cash Offer In 24 Hours"', bold=True)
bullet('Subheadline: "No Repairs. No Fees. No Agents. Close In As Little As 7 Days."')
bullet('CTA Button: [Get My Free Cash Offer →] — large, high-contrast, above the fold')
bullet('Trust line below button: "Hundreds of Miami homeowners helped since [year]"')
_add("No navigation menu. No outbound links. Nothing that gives them a reason to leave.",
     "NORMAL_TEXT", True, 11, RED)
blank()

h3("Section 2: Lead Form")
bullet("3 fields maximum: Name, Phone, Property Address")
bullet("Do NOT ask for email upfront — it increases abandonment")
bullet('Button text: "Get My Free Offer" — never "Submit"')
bullet('"No obligation. We never share your info." — directly below the button')
blank()

h3("Section 3: How It Works — 3 Steps Only")
bullet("Step 1: Tell Us About Your Property  (2 minutes — online or by phone)", bold=True)
bullet("Step 2: Receive Your Cash Offer  (within 24 hours, no obligation)", bold=True)
bullet("Step 3: Pick Your Closing Date  (we work around your schedule)", bold=True)
blank()

h3("Section 4: Who We Help — The 'That's Me' Moment")
body("This section is critical. It triggers seller self-identification.", italic=True, fg=GRAY)
bullet("Behind on payments or facing foreclosure")
bullet("Inherited a property you don't want to deal with")
bullet("Going through divorce")
bullet("Property needs major repairs you can't afford")
bullet("Tired of being a landlord")
bullet("Just need to sell fast without the hassle")
blank()

h3("Section 5: Buying Hero vs. Listing With an Agent")
for row in [
    ("Closing timeline",        "7–30 days ✓",  "60–90+ days"),
    ("Repairs required",        "None ✓",         "Usually yes"),
    ("Agent commissions",       "$0 ✓",           "5–6%"),
    ("Showings / open houses",  "None ✓",         "Many"),
    ("Deal fall-through risk",  "None ✓",         "Common"),
]:
    bullet(f"{row[0]}:  Buying Hero → {row[1]}   |   Agent → {row[2]}")
blank()

h3("Section 6: Social Proof")
bullet("2–3 short testimonials — first name and neighborhood only, no stock photos")
bullet("Google review star rating if you have one")
bullet("Authenticity converts better than polish here")
blank()

h3("Section 7: Second CTA at Bottom")
bullet("Repeat the same form OR display your phone number only")
bullet("Some sellers scroll the full page before committing — make it easy to act at the bottom")
blank()

h2("What NOT to Include on the Landing Page")
body("Every item below actively reduces conversion rate:", bold=True, fg=RED)
for item in [
    "Site navigation that links elsewhere",
    "Blog posts or content links",
    "Long-form About Us section",
    "Autoplay video — kills mobile load speed",
    "Multiple competing CTAs or offers",
    "Anything that gives them a reason to leave before submitting",
]: bullet(item, fg=RED)
blank(); blank()

# ── 6. Conversion Tracking ────────────────────────────────────────────────
h1("📊  Conversion Tracking Setup")
callout("Set this up before you spend a single dollar. "
        "Without it you are optimizing blindly.", color=RED)
blank()

h2("1. Form Submission  (Primary — set this first)")
bullet("Trigger: Thank-you page load after form submit  (/thank-you)")
bullet("Goal type: Page view")
bullet("Value: $150 placeholder — adjust as you learn actual CPL")
bullet("Count: Every")
blank()

h2("2. Phone Call From Ad  (Primary)")
bullet("Enable Google forwarding numbers inside Google Ads")
bullet("Trigger: Call duration > 60 seconds")
bullet("Value: $150")
bullet("Captures sellers who call directly from the ad without visiting the page")
blank()

h2("3. Phone Call From Website")
bullet("Install Google tag on your Carrot site")
bullet("Track clicks on your phone number (tel: links)")
bullet("Duration threshold: 90 seconds minimum")
blank()

h2("Do NOT Track These as Conversions")
body("These corrupt your bidding data:", bold=True, fg=RED)
for item in ["Page views", "Time on site", "Scroll depth",
             "Any engagement metric that doesn't indicate intent to sell"]:
    bullet(item, fg=RED)
blank()

h2("Future State: Optimize for Deals, Not Leads")
body("Once you have deal data flowing, import offline conversions from your CRM:")
bullet("Tag every lead that becomes a contract — include deal value")
bullet("Trace each back to its campaign and ad group via UTM parameters")
bullet("This trains Google's algorithm to find more people who actually close")
callout("Set your CRM to capture UTM parameters from day one — "
        "retrofit is painful and you lose history.")
blank(); blank()

# ── 7. Launch Checklist ───────────────────────────────────────────────────
h1("✅  Week-by-Week Launch Checklist")

h2("Week 1: Setup")
for item in [
    "Create Google Ads account — link to Google Analytics",
    "Install conversion tracking (form submit + phone call) — verify both fire",
    "Build Campaign 1 (Urgent Sellers): 3 ad groups, keywords loaded, RSAs written",
    "Add all negative keywords at account level before any traffic runs",
    "Build dedicated landing pages in Carrot — one per campaign minimum",
    "Set manual CPC bids: start at $8–12, adjust after first week of data",
]: bullet(item)
blank()

h2("Week 2: Launch Campaign 1 Only")
bullet("Go live with $1,800/mo on Campaign 1")
bullet("Check search terms report after 3 days — add negatives immediately")
_add("Do NOT touch bids for the first 7 days. Let it gather data.",
     "NORMAL_TEXT", True, 11, RED, None, True)
blank()

h2("Week 3: Analyze + Launch Campaign 2")
bullet("Review CPL, search terms, and device split (mobile vs desktop)")
bullet("Add new negatives identified from search terms report")
bullet("Launch Campaign 2 (Distressed) at $1,200/mo")
bullet("Compare CVR between ad groups — pause the weakest after 50+ clicks with no conversion")
blank()

h2("Week 4+: Ongoing Optimization Cycle")
bullet("Pull search terms weekly → add negatives aggressively")
bullet("Pause any ad group with 50+ clicks and zero conversions — don't keep feeding it")
bullet("Test one new headline variation per RSA per month — not more")
bullet("Never change bids more than 15–20% in a single adjustment")
bullet("Bring performance data weekly — I will return specific next actions")
blank(); blank()

# ── 8. Weekly Reporting ───────────────────────────────────────────────────
h1("📥  What to Bring Me Each Week")
body("Send me the following and I'll return exact actions — no guessing:")
blank()
bullet("Screenshot of campaign performance: impressions, clicks, conversions, cost")
bullet("Search terms report exported from Google Ads")
bullet("Lead count for the week and how many were qualified")
blank()
body("I will return:", bold=True, fg=NAVY)
bullet("Specific bid adjustments with exact percentages")
bullet("New negatives to add based on your search terms")
bullet("Headline and description variations to test")
bullet("Budget reallocation recommendations if one campaign outperforms")
blank()
callout("The only metric that matters: Cost per contract. "
        "Not CTR. Not impressions. Not leads.")
blank(); blank()

# Footer
_add("Buying Hero  ·  Google Ads Launch Strategy  ·  Confidential",
     "NORMAL_TEXT", False, 9, GRAY)


# ════════════════════════════════════════════════════════════════════════════
# BUILD + PUBLISH
# ════════════════════════════════════════════════════════════════════════════

def publish():
    creds   = Credentials.from_service_account_file(CREDS, scopes=SCOPES)
    service = build("docs", "v1", credentials=creds)

    # ── 1. Clear existing content ────────────────────────────────────────
    doc     = service.documents().get(documentId=DOC_ID).execute()
    end_idx = doc["body"]["content"][-1]["endIndex"]
    if end_idx > 2:
        service.documents().batchUpdate(
            documentId=DOC_ID,
            body={"requests": [{"deleteContentRange": {
                "range": {"startIndex": 1, "endIndex": end_idx - 1}
            }}]}
        ).execute()
        print("Cleared existing content.")

    # ── 2. Insert all text at once ───────────────────────────────────────
    full_text = "\n".join(seg[0] for seg in SEGS) + "\n"
    service.documents().batchUpdate(
        documentId=DOC_ID,
        body={"requests": [{"insertText": {
            "location": {"index": 1},
            "text": full_text
        }}]}
    ).execute()
    print(f"Inserted {len(full_text):,} characters.")

    # ── 3. Calculate positions ────────────────────────────────────────────
    positions = []
    pos = 1
    for seg in SEGS:
        text   = seg[0]
        length = len(text) + 1  # +1 for \n
        positions.append((pos, pos + length))
        pos += length

    # ── 4. Build formatting requests ─────────────────────────────────────
    reqs = []
    for i, seg in enumerate(SEGS):
        text, style, bold, size, fg, bg, is_bullet, mono, italic = seg
        start, end = positions[i]
        if not text:
            continue

        # Paragraph style
        if style != "NORMAL_TEXT":
            reqs.append({"updateParagraphStyle": {
                "range":          {"startIndex": start, "endIndex": end},
                "paragraphStyle": {"namedStyleType": style},
                "fields":         "namedStyleType",
            }})

        # Paragraph background
        if bg:
            reqs.append({"updateParagraphStyle": {
                "range":          {"startIndex": start, "endIndex": end},
                "paragraphStyle": {"shading": {"backgroundColor": {"color": {"rgbColor": bg}}}},
                "fields":         "shading",
            }})

        # Bullet
        if is_bullet:
            reqs.append({"createParagraphBullets": {
                "range":        {"startIndex": start, "endIndex": end},
                "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
            }})

        # Text style (applied to text only, not trailing \n)
        text_end = start + len(text)
        ts, fields = {}, []

        if bold:
            ts["bold"] = True;      fields.append("bold")
        if italic:
            ts["italic"] = True;    fields.append("italic")
        if fg and fg != BLACK:
            ts["foregroundColor"] = {"color": {"rgbColor": fg}}
            fields.append("foregroundColor")
        if bg and style in ("NORMAL_TEXT",):
            ts["backgroundColor"] = {"color": {"rgbColor": bg}}
            fields.append("backgroundColor")
        if size != 11:
            ts["fontSize"] = {"magnitude": size, "unit": "PT"}
            fields.append("fontSize")
        if mono:
            ts["weightedFontFamily"] = {"fontFamily": "Courier New"}
            fields.append("weightedFontFamily")

        if ts:
            reqs.append({"updateTextStyle": {
                "range":     {"startIndex": start, "endIndex": text_end},
                "textStyle": ts,
                "fields":    ",".join(fields),
            }})

    # ── 5. Execute formatting in batches of 40 ───────────────────────────
    total = 0
    for i in range(0, len(reqs), 40):
        batch = reqs[i:i + 40]
        service.documents().batchUpdate(
            documentId=DOC_ID,
            body={"requests": batch}
        ).execute()
        total += len(batch)
        print(f"  Formatting: {total}/{len(reqs)} requests applied...")

    print(f"\nDone. {len(SEGS)} paragraphs, {len(reqs)} formatting ops.")
    print(f"https://docs.google.com/document/d/{DOC_ID}/edit")


if __name__ == "__main__":
    publish()
