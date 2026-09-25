import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_SHEET_ID = os.environ["GOOGLE_SHEET_ID"]
GOOGLE_CREDS_PATH = os.environ.get("GOOGLE_CREDS_PATH", "credentials.json")
# Legacy Airmail tab. Airmail is no longer used; this stays only because
# probate falls back to GOOGLE_SHEET_ID and sheets.py defaults to this tab.
SHEET_TAB_NAME = os.environ.get("SHEET_TAB_NAME") or "272. Pre-foreclosure, Buying Hero, (3 steps)"
PROBATE_GOOGLE_SHEET_ID = os.environ.get("PROBATE_GOOGLE_SHEET_ID", os.environ.get("GOOGLE_SHEET_ID", ""))
PROBATE_SHEET_TAB_NAME = os.environ.get("PROBATE_SHEET_TAB_NAME", "Probate")
PROBATE_DAYS_BACK = int(os.environ.get("PROBATE_DAYS_BACK", "14"))

TAX_DEED_SHEET_TAB_NAME = os.environ.get("TAX_DEED_SHEET_TAB_NAME", "Tax Deed")
TAX_DEED_WEEKS_AHEAD = int(os.environ.get("TAX_DEED_WEEKS_AHEAD", "8"))

# Foreclosures AND tax deeds both land here ("ALL Foreclosures and Tax
# Auctions"), which feeds daily Open Letter Connect mailings. New env var names
# on purpose: the old SHEET_TAB_NAME secret still points at the Airmail tab.
MAIL_SHEET_ID = os.environ.get("MAIL_SHEET_ID") or "1Wt83XMAnt-PR66a3AQVspj7LJ1xnHdOXMKQM589VsmA"
MAIL_SHEET_TAB = os.environ.get("MAIL_SHEET_TAB") or "Sheet1"

# How many weeks ahead to scrape
WEEKS_AHEAD = 8

TAX_DEED_COLUMNS = [
    "Sent",
    "Company",
    "Owner First Name",
    "Owner Last Name",
    "Mailing Address",
    "Mailing City",
    "Mailing State",
    "Mailing Zip",
    "Address",
    "City",
    "State",
    "Zip",
    "Certificate #",
    "Opening Bid",
    "Assessed Value",
    "Auction Date",
    "Case Number",
]

# Layout of the mail sheet. main.py / main_tax_deed.py build rows in this
# order; "Sent" is left blank for the Open Letter step to fill in.
MAIL_COLUMNS = [
    "Sent",
    "Type",
    "Owner First Name",
    "Owner Last Name",
    "Mailing Address",
    "Mailing City",
    "Mailing State",
    "Mailing Zip",
    "Address",
    "City",
    "State",
    "Zip",
    "Value",
    "Auction Date",
    "Case Number",
    "Date Added",
]
MAIL_CASE_COL = "O"  # Case Number (dedup key)

SHEET_COLUMNS = [
    "Sent",
    "Company",
    "Owner First Name",
    "Owner Last Name",
    "Mailing Address",
    "Mailing City",
    "Mailing State",
    "Mailing Zip",
    "Address",
    "City",
    "State",
    "Zip",
    "Value",
    "Case Number",
]
