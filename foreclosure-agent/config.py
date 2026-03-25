import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_SHEET_ID = os.environ["GOOGLE_SHEET_ID"]
GOOGLE_CREDS_PATH = os.environ.get("GOOGLE_CREDS_PATH", "credentials.json")
SHEET_TAB_NAME = os.environ.get("SHEET_TAB_NAME", "")
PROBATE_GOOGLE_SHEET_ID = os.environ.get("PROBATE_GOOGLE_SHEET_ID", os.environ.get("GOOGLE_SHEET_ID", ""))
PROBATE_SHEET_TAB_NAME = os.environ.get("PROBATE_SHEET_TAB_NAME", "Probate")
PROBATE_DAYS_BACK = int(os.environ.get("PROBATE_DAYS_BACK", "14"))

TAX_DEED_SHEET_TAB_NAME = os.environ.get("TAX_DEED_SHEET_TAB_NAME", "Tax Deed")
TAX_DEED_WEEKS_AHEAD = int(os.environ.get("TAX_DEED_WEEKS_AHEAD", "8"))

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
]

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
]
