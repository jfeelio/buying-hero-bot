"""
SEO Agent — Pipeline Orchestrator for buyinghero.com

Phases:
  1. Site crawl (Playwright)
  2. PageSpeed Insights API
  3. On-page rules analysis
  4. Claude AI analysis + blog plan
  5. Output (Google Docs, Sheets, Markdown)
  6. [Optional] Carrot dashboard automation (--implement flag)

Usage:
  python main.py                  # Full run (no Carrot edits)
  python main.py --implement      # Full run + apply meta changes in Carrot
  python main.py --audit-only     # Crawl + rules only (no Claude AI)
  python main.py --blog-plan-only # Claude blog plan only (no crawl)
"""

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

import config
from scrapers.site_crawler import crawl_site
from scrapers.pagespeed import run_pagespeed_for_pages
from analyzers.onpage import analyze_pages
from outputs.markdown import write_audit_report, write_blog_plan

# ── Logging setup (same pattern as foreclosure-agent) ─────────────────────────
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
log_file = LOG_DIR / f"run_{date.today().isoformat()}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# ── Browser launcher (reused from foreclosure-agent pattern) ─────────────────

def launch_browser(playwright, headless: bool = True):
    browser = playwright.chromium.launch(
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
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
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    page = context.new_page()
    return browser, context, page


# ── Phase runners ─────────────────────────────────────────────────────────────

def phase1_crawl() -> list[dict]:
    logger.info("=" * 60)
    logger.info(f"Phase 1: Crawling {config.TARGET_URL}")
    logger.info("=" * 60)
    with sync_playwright() as pw:
        browser, context, page = launch_browser(pw, headless=True)
        try:
            return crawl_site(page)
        finally:
            browser.close()


def phase2_pagespeed(crawl_data: list[dict]) -> list[dict]:
    logger.info("=" * 60)
    logger.info("Phase 2: PageSpeed Insights")
    logger.info("=" * 60)
    return run_pagespeed_for_pages(crawl_data)


def phase3_onpage(crawl_data: list[dict]) -> list[dict]:
    logger.info("=" * 60)
    logger.info("Phase 3: On-page analysis")
    logger.info("=" * 60)
    return analyze_pages(crawl_data)


def phase4_claude(crawl_data: list[dict], pagespeed_data: list[dict], issues: list[dict]) -> tuple[dict, dict]:
    logger.info("=" * 60)
    logger.info("Phase 4: Claude AI analysis")
    logger.info("=" * 60)
    from agent import analyze_audit, generate_blog_plan

    audit_result = analyze_audit(crawl_data, pagespeed_data, issues)
    logger.info(f"  Priority fixes: {len(audit_result.get('priority_fixes', []))}")
    logger.info(f"  Revised meta entries: {len(audit_result.get('revised_meta', []))}")

    blog_plan = generate_blog_plan(audit_result, crawl_data)
    logger.info(f"  Blog posts generated: {len(blog_plan.get('blog_posts', []))}")

    return audit_result, blog_plan


def phase5_output(
    audit_result: dict,
    pagespeed_data: list[dict],
    issues: list[dict],
    crawl_data: list[dict],
    blog_plan: dict,
) -> dict:
    logger.info("=" * 60)
    logger.info("Phase 5: Writing outputs")
    logger.info("=" * 60)

    output_paths = {}

    # Markdown (always)
    audit_path = write_audit_report(audit_result, pagespeed_data, issues, crawl_data)
    blog_path = write_blog_plan(blog_plan.get("blog_posts", []))
    output_paths["audit_md"] = str(audit_path)
    output_paths["blog_md"] = str(blog_path)
    logger.info(f"  Audit report: {audit_path}")
    logger.info(f"  Blog plan:    {blog_path}")

    # Google Sheets (blog plan)
    if config.SEO_GOOGLE_SHEET_ID:
        from outputs.google_sheets import write_blog_plan as sheets_write
        ok = sheets_write(blog_plan.get("blog_posts", []))
        if ok:
            output_paths["sheets"] = f"https://docs.google.com/spreadsheets/d/{config.SEO_GOOGLE_SHEET_ID}"
            logger.info(f"  Blog plan written to Google Sheets")
    else:
        logger.warning("  SEO_GOOGLE_SHEET_ID not set — skipping Sheets output")

    # Google Docs (audit report)
    if config.GOOGLE_CREDS_PATH and Path(config.GOOGLE_CREDS_PATH).exists():
        try:
            from outputs.google_docs import create_audit_doc
            doc_url = create_audit_doc(audit_result, pagespeed_data, issues, crawl_data)
            if doc_url:
                output_paths["google_doc"] = doc_url
                logger.info(f"  Audit doc: {doc_url}")
        except Exception as e:
            logger.warning(f"  Google Docs failed: {e}")
    else:
        logger.warning("  Google credentials not found — skipping Docs output")

    return output_paths


def phase6_implement(audit_result: dict) -> None:
    logger.info("=" * 60)
    logger.info("Phase 6: Carrot Dashboard Implementation")
    logger.info("=" * 60)

    revised_meta = audit_result.get("revised_meta", [])
    if not revised_meta:
        logger.info("No revised meta entries — nothing to implement")
        return

    print("\n" + "=" * 60)
    print(f"PLANNED CHANGES ({len(revised_meta)} pages):")
    print("=" * 60)
    for i, item in enumerate(revised_meta, 1):
        print(f"\n[{i}] {item.get('page_url', '')}")
        print(f"    Title:       {item.get('new_title', '')}")
        print(f"    Description: {item.get('new_description', '')}")

    print("\n" + "=" * 60)
    confirm = input(f"Proceed with implementing {len(revised_meta)} change(s) in Carrot? (y/N): ").strip().lower()

    if confirm != "y":
        logger.info("Implementation cancelled by user")
        print("Implementation cancelled.")
        return

    from scrapers.carrot_editor import apply_meta_changes
    changes_log = Path(__file__).parent / "reports" / f"changes_applied_{date.today().isoformat()}.md"
    results = apply_meta_changes(revised_meta, changes_log)

    success = sum(1 for r in results if r.get("success"))
    failed = len(results) - success
    logger.info(f"Implementation complete: {success} succeeded, {failed} failed/skipped")
    print(f"\nDone. {success}/{len(results)} changes applied. Log: {changes_log}")


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="Buying Hero SEO Agent")
    parser.add_argument("--implement", action="store_true",
                        help="Apply meta changes to Carrot dashboard after analysis")
    parser.add_argument("--audit-only", action="store_true",
                        help="Run crawl + on-page rules only (no Claude AI)")
    parser.add_argument("--blog-plan-only", action="store_true",
                        help="Generate blog content calendar only (skips crawl)")
    return parser.parse_args()


def run():
    args = parse_args()

    logger.info("=" * 60)
    logger.info("Buying Hero SEO Agent starting")
    logger.info(f"Target: {config.TARGET_URL}")
    logger.info("=" * 60)

    # ── Blog-plan-only shortcut ────────────────────────────────────────────
    if args.blog_plan_only:
        audit_result: dict = {}
        crawl_data: list = []
        blog_plan, _ = phase4_claude([], [], [])
        write_blog_plan(blog_plan.get("blog_posts", []))
        if config.SEO_GOOGLE_SHEET_ID:
            from outputs.google_sheets import write_blog_plan as sheets_write
            sheets_write(blog_plan.get("blog_posts", []))
        logger.info("Blog plan complete.")
        return

    # ── Phase 1: Crawl ─────────────────────────────────────────────────────
    crawl_data = phase1_crawl()
    if not crawl_data:
        logger.error("Crawl returned no pages — aborting")
        sys.exit(1)

    # Save crawl data locally for debugging
    crawl_cache = Path(__file__).parent / "reports" / f"crawl_{date.today().isoformat()}.json"
    crawl_cache.parent.mkdir(exist_ok=True)
    crawl_cache.write_text(json.dumps(crawl_data, indent=2), encoding="utf-8")
    logger.info(f"Crawl data saved: {crawl_cache}")

    # ── Phase 2: PageSpeed ─────────────────────────────────────────────────
    pagespeed_data = phase2_pagespeed(crawl_data)

    # ── Phase 3: On-page analysis ──────────────────────────────────────────
    issues = phase3_onpage(crawl_data)

    # ── Audit-only shortcut ────────────────────────────────────────────────
    if args.audit_only:
        audit_path = write_audit_report({}, pagespeed_data, issues, crawl_data)
        logger.info(f"Audit-only complete: {audit_path}")
        return

    # ── Phase 4: Claude AI ─────────────────────────────────────────────────
    audit_result, blog_plan = phase4_claude(crawl_data, pagespeed_data, issues)

    # ── Phase 5: Output ────────────────────────────────────────────────────
    output_paths = phase5_output(audit_result, pagespeed_data, issues, crawl_data, blog_plan)

    # ── Phase 6: Implement (optional) ─────────────────────────────────────
    if args.implement:
        phase6_implement(audit_result)

    logger.info("=" * 60)
    logger.info("SEO Agent pipeline complete")
    for key, val in output_paths.items():
        logger.info(f"  {key}: {val}")
    logger.info("=" * 60)


if __name__ == "__main__":
    run()
