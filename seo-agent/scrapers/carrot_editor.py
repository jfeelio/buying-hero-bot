"""
Carrot Dashboard Automation — Playwright (headful).

Applies revised meta titles and descriptions to buyinghero.com pages
via the Carrot.com admin dashboard.

IMPORTANT: This module is gated behind an explicit user confirmation prompt
in main.py before any changes are made.
"""

import logging
import time
from datetime import date
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

import config

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).parent.parent / "reports"


def launch_browser_headful(playwright):
    """Launch visible Chromium so the user can intervene if needed."""
    browser = playwright.chromium.launch(
        headless=False,
        args=[
            "--no-sandbox",
            "--disable-infobars",
            "--start-maximized",
        ],
    )
    context = browser.new_context(
        viewport={"width": 1440, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    )
    page = context.new_page()
    return browser, context, page


def _login(page: Page) -> bool:
    """Log in to Carrot dashboard. Returns True on success."""
    if not config.CARROT_EMAIL or not config.CARROT_PASSWORD:
        logger.error("CARROT_EMAIL / CARROT_PASSWORD not set in .env")
        return False

    logger.info(f"Logging in to Carrot as {config.CARROT_EMAIL}")
    try:
        page.goto(config.CARROT_LOGIN_URL, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # Fill login form
        email_input = page.locator('input[type="email"], input[name="email"], #email').first
        email_input.fill(config.CARROT_EMAIL)

        password_input = page.locator('input[type="password"], input[name="password"], #password').first
        password_input.fill(config.CARROT_PASSWORD)

        # Submit
        submit = page.locator('button[type="submit"], input[type="submit"]').first
        submit.click()

        page.wait_for_load_state("networkidle", timeout=15000)
        page.wait_for_timeout(2000)

        # Verify login by checking URL changed away from login page
        current_url = page.url
        if "login" in current_url.lower():
            logger.error("Login may have failed — still on login page")
            return False

        logger.info("Login successful")
        return True

    except Exception as e:
        logger.error(f"Login failed: {e}")
        return False


def _find_page_editor(page: Page, site_url: str) -> bool:
    """
    Navigate to the Carrot page editor for a given site URL.

    Strategy:
    1. Check config.CARROT_PAGE_IDS for a known page ID.
    2. If not found, search the pages list in Carrot dashboard.
    3. Return True if editor is open, False if page not found.
    """
    page_id = config.CARROT_PAGE_IDS.get(site_url)

    if page_id:
        # Direct navigation using known page ID
        # Carrot URL pattern: https://app.carrot.com/sites/{site_id}/pages/{page_id}
        # site_id needs to be discovered — for now navigate via pages list
        editor_url = f"https://app.carrot.com/pages/{page_id}/edit"
        logger.info(f"Navigating directly to editor: {editor_url}")
        page.goto(editor_url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        return True

    # Fallback: navigate to pages list and search for matching page
    logger.info(f"No page ID for {site_url} — searching Carrot pages list")
    try:
        page.goto("https://app.carrot.com/pages", timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # Try to find the page by its URL/slug in the list
        slug = site_url.rstrip("/").rsplit("/", 1)[-1] or "home"
        logger.info(f"Looking for page with slug: {slug}")

        # Look for a link or button containing the slug or "Home"
        search_term = slug if slug != config.TARGET_URL.rstrip("/") else "home"
        match = page.locator(f'text="{search_term}"').first
        if match.count() > 0:
            match.click()
            page.wait_for_load_state("networkidle", timeout=10000)
            return True

        logger.warning(f"Could not locate editor for {site_url}")
        return False

    except Exception as e:
        logger.warning(f"Editor navigation failed for {site_url}: {e}")
        return False


def _update_meta_fields(page: Page, new_title: str, new_description: str) -> bool:
    """
    Find and update meta title + description in the Carrot editor.
    Tries common Carrot SEO tab patterns.
    """
    try:
        # Look for SEO tab
        seo_tab = page.locator('a:has-text("SEO"), button:has-text("SEO"), [data-tab="seo"]').first
        if seo_tab.count() > 0:
            seo_tab.click()
            page.wait_for_timeout(1000)

        # Meta title — try common field names/labels
        title_selectors = [
            'input[name="seo_title"]',
            'input[id="seo_title"]',
            'input[placeholder*="title" i]',
            'input[name*="meta_title" i]',
            'input[name*="seo_title" i]',
        ]
        title_input = None
        for sel in title_selectors:
            el = page.locator(sel).first
            if el.count() > 0:
                title_input = el
                break

        if title_input:
            title_input.triple_click()
            title_input.fill(new_title)
            logger.info(f"  Title updated: {new_title}")
        else:
            logger.warning("  Could not locate meta title field")

        # Meta description
        desc_selectors = [
            'textarea[name="seo_description"]',
            'textarea[id="seo_description"]',
            'textarea[placeholder*="description" i]',
            'textarea[name*="meta_description" i]',
            'textarea[name*="seo_description" i]',
        ]
        desc_input = None
        for sel in desc_selectors:
            el = page.locator(sel).first
            if el.count() > 0:
                desc_input = el
                break

        if desc_input:
            desc_input.triple_click()
            desc_input.fill(new_description)
            logger.info(f"  Description updated: {new_description[:60]}...")
        else:
            logger.warning("  Could not locate meta description field")

        # Save
        save_btn = page.locator('button:has-text("Save"), button:has-text("Update"), input[value="Save"]').first
        if save_btn.count() > 0:
            save_btn.click()
            page.wait_for_timeout(2000)
            logger.info("  Saved")
            return True
        else:
            logger.warning("  Could not find Save button")
            return False

    except Exception as e:
        logger.error(f"  Meta field update failed: {e}")
        return False


def apply_meta_changes(revised_meta: list[dict], changes_log_path: Path) -> list[dict]:
    """
    Apply all revised meta titles and descriptions via Carrot dashboard.

    revised_meta: list of {page_url, new_title, new_description} dicts
    Returns list of result dicts with success/failure per page.
    """
    results = []
    REPORTS_DIR.mkdir(exist_ok=True)

    with sync_playwright() as pw:
        browser, context, page = launch_browser_headful(pw)
        try:
            if not _login(page):
                logger.error("Aborting — Carrot login failed")
                return []

            for item in revised_meta:
                site_url = item.get("page_url", "")
                new_title = item.get("new_title", "")
                new_description = item.get("new_description", "")

                logger.info(f"Processing: {site_url}")

                found = _find_page_editor(page, site_url)
                if not found:
                    results.append({
                        "url": site_url,
                        "success": False,
                        "reason": "Page editor not found — manual action required",
                    })
                    continue

                success = _update_meta_fields(page, new_title, new_description)
                results.append({
                    "url": site_url,
                    "new_title": new_title,
                    "new_description": new_description,
                    "success": success,
                    "reason": "OK" if success else "Field update failed",
                })
                time.sleep(2)

        finally:
            browser.close()

    # Write changes log
    _write_changes_log(results, changes_log_path)
    return results


def _write_changes_log(results: list[dict], path: Path) -> None:
    success = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]

    lines = [
        f"# Carrot Changes Applied — {date.today().isoformat()}\n",
        f"**Applied:** {len(success)}  |  **Failed/Skipped:** {len(failed)}\n\n",
        "## Successfully Applied\n",
    ]
    for r in success:
        lines.append(f"- **{r['url']}**")
        lines.append(f"  - Title: `{r.get('new_title', '')}`")
        lines.append(f"  - Description: `{r.get('new_description', '')}`\n")

    if failed:
        lines.append("\n## Failed / Skipped (Manual Action Required)\n")
        for r in failed:
            lines.append(f"- **{r['url']}** — {r.get('reason', 'unknown')}")

    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"Changes log written to {path}")
