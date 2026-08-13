"""
On-Page SEO Rules Engine.

Input: list of page dicts from site_crawler.py
Output: list of issue dicts with severity (critical / warning / info)
"""

import logging
from collections import Counter

import config

logger = logging.getLogger(__name__)

CRITICAL = "critical"
WARNING = "warning"
INFO = "info"


def _issue(page_url: str, check: str, severity: str, detail: str, current: str = "") -> dict:
    return {
        "url": page_url,
        "check": check,
        "severity": severity,
        "detail": detail,
        "current_value": current,
    }


def analyze_pages(pages: list[dict]) -> list[dict]:
    """
    Run all on-page SEO rules against the crawled pages.
    Returns a flat list of issue dicts.
    """
    issues: list[dict] = []

    # Pre-compute duplicate detection
    title_counter = Counter(
        p.get("title", "").strip()
        for p in pages
        if p.get("title", "").strip()
    )
    desc_counter = Counter(
        p.get("meta_description", "").strip()
        for p in pages
        if p.get("meta_description", "").strip()
    )

    # Count how many times each URL is linked to internally
    inbound_link_counts: dict[str, int] = {}
    base = config.TARGET_URL.rstrip("/")
    for page in pages:
        for link in page.get("internal_links", []):
            href = link["href"].rstrip("/")
            inbound_link_counts[href] = inbound_link_counts.get(href, 0) + 1

    for page in pages:
        url = page.get("url", "")
        status = page.get("status", 200)

        # Skip error pages (treat as separate issue class)
        if status == 0 or status >= 400:
            issues.append(_issue(url, "HTTP Error", CRITICAL,
                                 f"Page returned HTTP {status}", str(status)))
            continue

        title = page.get("title", "").strip()
        description = page.get("meta_description", "").strip()
        h1_list = page.get("h1", [])
        word_count = page.get("word_count", 0)
        images_missing_alt = page.get("images_missing_alt", [])
        schema = page.get("schema", [])
        internal_links_out = page.get("internal_links", [])

        # ── Meta title checks ──────────────────────────────────────────────
        if not title:
            issues.append(_issue(url, "Meta title missing", CRITICAL,
                                 "Page has no <title> tag"))
        else:
            tlen = len(title)
            if tlen < config.TITLE_MIN:
                issues.append(_issue(url, "Meta title too short", WARNING,
                                     f"Title is {tlen} chars (min {config.TITLE_MIN})", title))
            elif tlen > config.TITLE_MAX:
                issues.append(_issue(url, "Meta title too long", WARNING,
                                     f"Title is {tlen} chars (max {config.TITLE_MAX})", title))

            if title_counter[title] > 1:
                issues.append(_issue(url, "Duplicate meta title", CRITICAL,
                                     f"Same title used on {title_counter[title]} pages", title))

        # ── Meta description checks ────────────────────────────────────────
        if not description:
            issues.append(_issue(url, "Meta description missing", CRITICAL,
                                 "Page has no meta description"))
        else:
            dlen = len(description)
            if dlen < config.DESC_MIN:
                issues.append(_issue(url, "Meta description too short", WARNING,
                                     f"Description is {dlen} chars (min {config.DESC_MIN})", description))
            elif dlen > config.DESC_MAX:
                issues.append(_issue(url, "Meta description too long", WARNING,
                                     f"Description is {dlen} chars (max {config.DESC_MAX})", description))

            if desc_counter[description] > 1:
                issues.append(_issue(url, "Duplicate meta description", CRITICAL,
                                     f"Same description used on {desc_counter[description]} pages",
                                     description))

        # ── H1 checks ─────────────────────────────────────────────────────
        h1_count = len(h1_list)
        if h1_count == 0:
            issues.append(_issue(url, "H1 missing", CRITICAL,
                                 "Page has no H1 tag"))
        elif h1_count > 1:
            issues.append(_issue(url, "Multiple H1 tags", CRITICAL,
                                 f"Page has {h1_count} H1 tags (should have exactly 1)",
                                 " | ".join(h1_list)))

        # ── Word count ─────────────────────────────────────────────────────
        if word_count < config.MIN_WORD_COUNT:
            issues.append(_issue(url, "Thin content", WARNING,
                                 f"Page has only {word_count} words (min {config.MIN_WORD_COUNT})",
                                 str(word_count)))

        # ── Images missing alt ─────────────────────────────────────────────
        missing = len(images_missing_alt)
        if missing > 0:
            issues.append(_issue(url, "Images missing alt text", WARNING,
                                 f"{missing} image(s) have no alt attribute",
                                 "; ".join(images_missing_alt[:3])))

        # ── Schema markup (homepage only) ──────────────────────────────────
        if url.rstrip("/") == base and not schema:
            issues.append(_issue(url, "Schema markup missing", WARNING,
                                 "Homepage has no JSON-LD schema markup"))

        # ── Inbound internal links ─────────────────────────────────────────
        norm_url = url.rstrip("/")
        inbound = inbound_link_counts.get(norm_url, 0)
        if norm_url != base and inbound < config.MIN_INTERNAL_LINKS:
            issues.append(_issue(url, "Low internal link count", INFO,
                                 f"Only {inbound} internal link(s) point to this page "
                                 f"(min {config.MIN_INTERNAL_LINKS})",
                                 str(inbound)))

        # ── Robots meta blocking indexing ──────────────────────────────────
        robots = page.get("robots_meta", "").lower()
        if "noindex" in robots:
            issues.append(_issue(url, "Page set to noindex", CRITICAL,
                                 f"robots meta contains 'noindex': {robots}", robots))

    # Summary log
    counts = Counter(i["severity"] for i in issues)
    logger.info(
        f"On-page analysis: {len(issues)} issue(s) — "
        f"{counts.get(CRITICAL,0)} critical, "
        f"{counts.get(WARNING,0)} warnings, "
        f"{counts.get(INFO,0)} info"
    )
    return issues
