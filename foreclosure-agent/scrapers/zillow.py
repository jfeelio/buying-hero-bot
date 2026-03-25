"""
Zillow Zestimate extractor via Playwright (headful Chromium).

Strategy:
  1. Navigate to zillow.com/homes/{slug}_rb/
  2. Parse __NEXT_DATA__ JSON blob → find zestimate field
  3. Fallback: regex scan of page text for "$NNN,NNN Zestimate" pattern

The browser instance is created ONCE in main.py and reused across all lookups.
Pass the Playwright `page` object into get_zestimate().
"""

import json
import logging
import re
import time
import random

logger = logging.getLogger(__name__)

ZILLOW_BASE = "https://www.zillow.com/homes/"


def _address_to_slug(address: str, city: str = "", state: str = "FL", zip_code: str = "") -> str:
    """Convert a property address to a Zillow URL slug."""
    parts = [address]
    if city:
        parts.append(city)
    parts.append(state)
    if zip_code:
        parts.append(zip_code)
    full = " ".join(parts)
    # Replace non-alphanumeric (except spaces) with nothing, then spaces with hyphens
    slug = re.sub(r"[^a-zA-Z0-9 ]", "", full)
    slug = re.sub(r"\s+", "-", slug.strip())
    return slug


def _extract_from_next_data(page) -> str:
    """Parse __NEXT_DATA__ script tag for zestimate value."""
    try:
        content = page.evaluate("""
            () => {
                const el = document.getElementById('__NEXT_DATA__');
                return el ? el.textContent : null;
            }
        """)
        if not content:
            return ""
        data = json.loads(content)
        # Walk the nested structure to find zestimate
        # Path varies by page layout; we do a deep search
        zestimate = _deep_find_zestimate(data)
        if zestimate:
            return f"${zestimate:,}"
    except Exception as e:
        logger.debug(f"__NEXT_DATA__ parse error: {e}")
    return ""


def _deep_find_zestimate(obj, depth: int = 0) -> int | None:
    """Recursively search a JSON object for a 'zestimate' integer field."""
    if depth > 12:
        return None
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key.lower() == "zestimate" and isinstance(val, (int, float)) and val > 0:
                return int(val)
            result = _deep_find_zestimate(val, depth + 1)
            if result:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = _deep_find_zestimate(item, depth + 1)
            if result:
                return result
    return None


def _extract_from_page_text(page) -> str:
    """Fallback: regex scan of visible page text for Zestimate pattern."""
    try:
        text = page.evaluate("() => document.body.innerText")
        # Pattern: $NNN,NNN or $N,NNN,NNN followed by "Zestimate"
        match = re.search(r"\$[\d,]+(?=\s*Zestimate)", text, re.IGNORECASE)
        if match:
            return match.group(0)
    except Exception as e:
        logger.debug(f"Page text regex error: {e}")
    return ""


def get_zestimate(
    page,
    address: str,
    city: str = "",
    state: str = "FL",
    zip_code: str = "",
) -> str:
    """
    Navigate to Zillow and extract Zestimate. Returns formatted string like "$350,000"
    or empty string on failure/CAPTCHA.

    `page` is a Playwright Page object (reused across calls).
    """
    if not address:
        return ""

    slug = _address_to_slug(address, city, state, zip_code)
    url = f"{ZILLOW_BASE}{slug}_rb/"
    logger.info(f"Zillow lookup: {url}")

    try:
        response = page.goto(url, timeout=30000, wait_until="domcontentloaded")

        if response and response.status == 403:
            logger.warning(f"Zillow 403 for {address} — skipping")
            return ""

        # Wait a moment for JS to hydrate
        page.wait_for_timeout(2000)

        # Check for CAPTCHA
        page_title = page.title()
        if "captcha" in page_title.lower() or "robot" in page_title.lower():
            logger.warning(f"Zillow CAPTCHA detected for {address}")
            return ""

        # Primary extraction
        zestimate = _extract_from_next_data(page)
        if zestimate:
            logger.info(f"Zestimate (JSON): {zestimate} for {address}")
            return zestimate

        # Fallback extraction
        zestimate = _extract_from_page_text(page)
        if zestimate:
            logger.info(f"Zestimate (text): {zestimate} for {address}")
            return zestimate

        logger.info(f"No Zestimate found for {address}")
        return ""

    except Exception as e:
        logger.warning(f"Zillow error for '{address}': {e}")
        return ""


def launch_browser(playwright):
    """
    Launch a headful Chromium browser with anti-detection flags.
    Called once from main.py. Returns (browser, context, page).
    """
    browser = playwright.chromium.launch(
        headless=False,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--start-maximized",
        ],
    )
    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="en-US",
    )
    # Remove navigator.webdriver flag
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    page = context.new_page()
    return browser, context, page


def random_delay(min_sec: float = 2.5, max_sec: float = 4.5) -> None:
    delay = random.uniform(min_sec, max_sec)
    logger.debug(f"Zillow delay: {delay:.1f}s")
    time.sleep(delay)
