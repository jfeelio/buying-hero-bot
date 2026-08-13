"""
Google PageSpeed Insights API client.

Runs mobile + desktop audits for each key page (homepage + top pages by
internal link count) and returns structured metric dicts.
"""

import logging
import time

import requests

import config

MAX_RETRIES = 3
RETRY_BACKOFF = [5, 15, 30]  # seconds between retries

logger = logging.getLogger(__name__)

PAGESPEED_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

# Lighthouse categories we care about
CATEGORIES = ["performance", "seo", "accessibility", "best-practices"]

# Core Web Vitals audit IDs → friendly names
CWV_AUDITS = {
    "largest-contentful-paint": "LCP",
    "first-contentful-paint": "FCP",
    "cumulative-layout-shift": "CLS",
    "interaction-to-next-paint": "INP",
    "server-response-time": "TTFB",
    "total-blocking-time": "TBT",
}


def _run_pagespeed(url: str, strategy: str) -> dict:
    """Call PageSpeed Insights API for one URL + strategy."""
    params = {
        "url": url,
        "strategy": strategy,
        "key": config.PAGESPEED_API_KEY,
    }
    for cat in CATEGORIES:
        params[f"category"] = cat  # API accepts repeated category params

    # Rebuild params with repeated category keys
    param_list = [("url", url), ("strategy", strategy), ("key", config.PAGESPEED_API_KEY)]
    for cat in CATEGORIES:
        param_list.append(("category", cat))

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(PAGESPEED_URL, params=param_list, timeout=(10, 90))
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF[attempt]
                logger.warning(f"PageSpeed attempt {attempt + 1} failed for {url} ({strategy}): {e} — retrying in {wait}s")
                time.sleep(wait)
            else:
                logger.error(f"PageSpeed API error for {url} ({strategy}) after {MAX_RETRIES} attempts: {e}")
    return {}


def _parse_result(raw: dict, url: str, strategy: str) -> dict:
    """Extract scores and vitals from raw API response."""
    result = {"url": url, "strategy": strategy}

    if not raw:
        result["error"] = "API call failed"
        return result

    # Category scores (0–100)
    cats = raw.get("lighthouseResult", {}).get("categories", {})
    for cat_id in CATEGORIES:
        key = cat_id.replace("-", "_")
        score = cats.get(cat_id, {}).get("score")
        result[key] = round(score * 100) if score is not None else None

    # Core Web Vitals
    audits = raw.get("lighthouseResult", {}).get("audits", {})
    for audit_id, label in CWV_AUDITS.items():
        audit = audits.get(audit_id, {})
        result[label] = audit.get("displayValue", "n/a")

    # Failed audits (score < 0.9 and not null)
    failed = []
    for audit_id, audit in audits.items():
        score = audit.get("score")
        if score is not None and score < 0.9:
            failed.append({
                "id": audit_id,
                "title": audit.get("title", ""),
                "description": audit.get("description", ""),
                "score": round(score * 100) if score is not None else None,
            })
    result["failed_audits"] = failed

    return result


def run_pagespeed_for_pages(pages: list[dict], top_n: int = 10) -> list[dict]:
    """
    Run PageSpeed for homepage + top N pages by internal link count.
    Returns list of result dicts (one per URL+strategy combination).
    """
    if not config.PAGESPEED_API_KEY:
        logger.warning("PAGESPEED_API_KEY not set — skipping PageSpeed audits")
        return []

    # Count how many times each URL is linked to internally
    link_counts: dict[str, int] = {}
    for page in pages:
        for link in page.get("internal_links", []):
            href = link["href"]
            link_counts[href] = link_counts.get(href, 0) + 1

    # Build target list: homepage first, then top by link count
    base = config.TARGET_URL.rstrip("/")
    target_urls = [base]
    sorted_by_links = sorted(link_counts.items(), key=lambda x: x[1], reverse=True)
    for url, _ in sorted_by_links:
        if url != base and len(target_urls) < top_n + 1:
            target_urls.append(url)

    results = []
    total = len(target_urls) * len(config.PAGESPEED_STRATEGIES)
    done = 0

    for url in target_urls:
        for strategy in config.PAGESPEED_STRATEGIES:
            done += 1
            logger.info(f"  PageSpeed [{done}/{total}]: {url} ({strategy})")
            raw = _run_pagespeed(url, strategy)
            result = _parse_result(raw, url, strategy)
            results.append(result)
            # Respect API rate limits
            time.sleep(1.5)

    logger.info(f"PageSpeed complete: {len(results)} result(s)")
    return results
