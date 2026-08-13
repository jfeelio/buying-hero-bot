"""
Site Crawler — Playwright headless crawl of buyinghero.com.

Starts at TARGET_URL, follows internal links up to MAX_CRAWL_PAGES.
Returns a list of page dicts with full on-page data.
"""

import logging
import re
from urllib.parse import urljoin, urlparse

from playwright.sync_api import Page

import config

logger = logging.getLogger(__name__)

# File extensions to skip
SKIP_EXTENSIONS = {
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
    ".mp4", ".mp3", ".zip", ".doc", ".docx", ".xls", ".xlsx",
}


def _is_internal(href: str, base_domain: str) -> bool:
    parsed = urlparse(href)
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        return False
    if parsed.netloc and parsed.netloc.lstrip("www.") != base_domain.lstrip("www."):
        return False
    ext = parsed.path.rsplit(".", 1)[-1].lower() if "." in parsed.path else ""
    if f".{ext}" in SKIP_EXTENSIONS:
        return False
    return True


def _normalize(url: str) -> str:
    parsed = urlparse(url)
    # Drop fragment, normalize trailing slash
    normalized = parsed._replace(fragment="").geturl()
    if normalized.endswith("/"):
        normalized = normalized[:-1]
    return normalized


def _extract_page_data(page: Page, url: str) -> dict:
    """Extract all on-page SEO signals from the current page."""
    data = {"url": url}

    # Title
    data["title"] = page.evaluate("() => document.title || ''")

    # Meta description
    data["meta_description"] = page.evaluate("""
        () => {
            const el = document.querySelector('meta[name="description"]');
            return el ? el.getAttribute('content') || '' : '';
        }
    """)

    # H1, H2, H3
    data["h1"] = page.evaluate("""
        () => Array.from(document.querySelectorAll('h1')).map(el => el.innerText.trim())
    """)
    data["h2"] = page.evaluate("""
        () => Array.from(document.querySelectorAll('h2')).map(el => el.innerText.trim())
    """)
    data["h3"] = page.evaluate("""
        () => Array.from(document.querySelectorAll('h3')).map(el => el.innerText.trim())
    """)

    # Word count (visible body text)
    body_text = page.evaluate("""
        () => {
            const clone = document.body.cloneNode(true);
            clone.querySelectorAll('script, style, nav, header, footer').forEach(el => el.remove());
            return clone.innerText || '';
        }
    """)
    data["word_count"] = len(body_text.split())

    # Internal links
    base = config.TARGET_URL
    links_raw = page.evaluate("""
        () => Array.from(document.querySelectorAll('a[href]')).map(a => ({
            href: a.href,
            text: a.innerText.trim()
        }))
    """)
    base_domain = urlparse(base).netloc
    data["internal_links"] = [
        {"href": _normalize(l["href"]), "text": l["text"]}
        for l in links_raw
        if _is_internal(l["href"], base_domain)
    ]

    # Images missing alt
    data["images_missing_alt"] = page.evaluate("""
        () => Array.from(document.querySelectorAll('img')).filter(img => {
            const alt = img.getAttribute('alt');
            return alt === null || alt.trim() === '';
        }).map(img => img.src)
    """)

    # Schema markup
    data["schema"] = page.evaluate("""
        () => Array.from(document.querySelectorAll('script[type="application/ld+json"]'))
              .map(el => el.textContent)
    """)

    # Canonical tag
    data["canonical"] = page.evaluate("""
        () => {
            const el = document.querySelector('link[rel="canonical"]');
            return el ? el.getAttribute('href') || '' : '';
        }
    """)

    # Robots meta
    data["robots_meta"] = page.evaluate("""
        () => {
            const el = document.querySelector('meta[name="robots"]');
            return el ? el.getAttribute('content') || '' : '';
        }
    """)

    # OG tags
    data["og_title"] = page.evaluate("""
        () => {
            const el = document.querySelector('meta[property="og:title"]');
            return el ? el.getAttribute('content') || '' : '';
        }
    """)
    data["og_description"] = page.evaluate("""
        () => {
            const el = document.querySelector('meta[property="og:description"]');
            return el ? el.getAttribute('content') || '' : '';
        }
    """)
    data["og_image"] = page.evaluate("""
        () => {
            const el = document.querySelector('meta[property="og:image"]');
            return el ? el.getAttribute('content') || '' : '';
        }
    """)

    return data


def crawl_site(page: Page) -> list[dict]:
    """
    Crawl TARGET_URL, follow internal links up to MAX_CRAWL_PAGES.
    Returns list of page data dicts.
    """
    base = config.TARGET_URL.rstrip("/")
    base_domain = urlparse(base).netloc

    visited: set[str] = set()
    queue: list[str] = [_normalize(base)]
    results: list[dict] = []

    logger.info(f"Starting crawl at {base} (max {config.MAX_CRAWL_PAGES} pages)")

    while queue and len(results) < config.MAX_CRAWL_PAGES:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        logger.info(f"  Crawling [{len(results)+1}]: {url}")
        try:
            response = page.goto(url, timeout=30000, wait_until="domcontentloaded")
            status = response.status if response else 0
            page.wait_for_timeout(1500)
        except Exception as e:
            logger.warning(f"  Failed to load {url}: {e}")
            results.append({"url": url, "status": 0, "error": str(e)})
            continue

        if status >= 400:
            logger.warning(f"  HTTP {status} for {url}")
            results.append({"url": url, "status": status})
            continue

        try:
            data = _extract_page_data(page, url)
            data["status"] = status
        except Exception as e:
            logger.warning(f"  Extraction error on {url}: {e}")
            data = {"url": url, "status": status, "error": str(e)}

        results.append(data)

        # Discover new links
        for link in data.get("internal_links", []):
            href = link["href"]
            norm = _normalize(href)
            if norm not in visited and norm not in queue:
                if _is_internal(href, base_domain):
                    queue.append(norm)

    logger.info(f"Crawl complete: {len(results)} pages collected")
    return results
