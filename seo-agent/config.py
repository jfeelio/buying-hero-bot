import os
from dotenv import load_dotenv

load_dotenv()

# ── Site ──────────────────────────────────────────────────────────────────────
TARGET_URL = os.environ.get("TARGET_URL", "https://www.buyinghero.com")
MAX_CRAWL_PAGES = int(os.environ.get("MAX_CRAWL_PAGES", "50"))

# ── APIs ──────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
PAGESPEED_API_KEY = os.environ.get("PAGESPEED_API_KEY", "")

# ── Google ────────────────────────────────────────────────────────────────────
GOOGLE_CREDS_PATH = os.environ.get("GOOGLE_CREDS_PATH", "../foreclosure-agent/credentials.json")
SEO_GOOGLE_SHEET_ID = os.environ.get("SEO_GOOGLE_SHEET_ID", "")
SEO_BLOG_TAB_NAME = "SEO Blog Plan"

# ── Carrot ────────────────────────────────────────────────────────────────────
CARROT_EMAIL = os.environ.get("CARROT_EMAIL", "")
CARROT_PASSWORD = os.environ.get("CARROT_PASSWORD", "")
CARROT_LOGIN_URL = "https://app.carrot.com/login"

# Populated after first manual inspection of Carrot dashboard URLs.
# Format: {"https://www.buyinghero.com/": "page_id_here", ...}
CARROT_PAGE_IDS: dict[str, str] = {}

# ── Blog plan columns (Google Sheets) ────────────────────────────────────────
BLOG_COLUMNS = [
    "Rank",
    "Keyword",
    "Monthly Searches",
    "Intent",
    "Title",
    "Outline",
    "Priority",
    "Status",
    "Notes",
]

# ── Claude model ──────────────────────────────────────────────────────────────
CLAUDE_MODEL = "claude-sonnet-4-6"

# ── PageSpeed: run these strategies per page ──────────────────────────────────
PAGESPEED_STRATEGIES = ["mobile", "desktop"]

# ── On-page rules thresholds ─────────────────────────────────────────────────
TITLE_MIN = 50
TITLE_MAX = 60
DESC_MIN = 130
DESC_MAX = 160
MIN_WORD_COUNT = 500
MIN_INTERNAL_LINKS = 2
