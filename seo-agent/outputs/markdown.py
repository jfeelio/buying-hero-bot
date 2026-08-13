"""
Local Markdown file writer.

Writes:
  reports/audit_YYYY-MM-DD.md        — Full audit report
  reports/blog_plan_YYYY-MM-DD.md    — Blog content calendar
"""

import logging
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).parent.parent / "reports"


def _reports_dir() -> Path:
    REPORTS_DIR.mkdir(exist_ok=True)
    return REPORTS_DIR


def write_audit_report(
    audit_result: dict,
    pagespeed_data: list[dict],
    issues: list[dict],
    crawl_data: list[dict],
) -> Path:
    """Write full audit report to local markdown file."""
    path = _reports_dir() / f"audit_{date.today().isoformat()}.md"

    critical = [i for i in issues if i["severity"] == "critical"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    info_issues = [i for i in issues if i["severity"] == "info"]

    lines = [
        f"# Buying Hero SEO Audit — {date.today().isoformat()}\n",
        "---\n",

        "## Executive Summary\n",
        audit_result.get("executive_summary", "No summary available."),
        "\n",

        "---\n",
        "## Critical Issues\n",
    ]
    for i, issue in enumerate(audit_result.get("critical_issues", []), 1):
        lines.append(f"{i}. {issue}")
    lines.append("\n")

    # PageSpeed scores
    lines += [
        "---\n",
        "## PageSpeed Insights Scores\n",
        "| URL | Strategy | Performance | SEO | Accessibility | LCP | CLS |",
        "|-----|----------|-------------|-----|---------------|-----|-----|",
    ]
    for r in pagespeed_data:
        lines.append(
            f"| {r.get('url','')} | {r.get('strategy','')} | "
            f"{r.get('performance','n/a')} | {r.get('seo','n/a')} | "
            f"{r.get('accessibility','n/a')} | {r.get('LCP','n/a')} | {r.get('CLS','n/a')} |"
        )
    lines.append("\n")

    # Priority fixes
    lines += [
        "---\n",
        "## Priority Fixes\n",
    ]
    for fix in audit_result.get("priority_fixes", []):
        lines += [
            f"### {fix.get('issue','')}",
            f"**Page:** {fix.get('page_url','')}",
            f"**Current:** {fix.get('current_value','n/a')}",
            f"**Recommended:** {fix.get('recommended_value','n/a')}",
            f"**Notes:** {fix.get('implementation_notes','')}",
            "",
        ]

    # Revised meta
    lines += [
        "---\n",
        "## Revised Meta Titles & Descriptions\n",
        "| Page | New Title (chars) | New Description (chars) |",
        "|------|-------------------|------------------------|",
    ]
    for meta in audit_result.get("revised_meta", []):
        t = meta.get("new_title", "")
        d = meta.get("new_description", "")
        lines.append(f"| {meta.get('page_url','')} | {t} ({len(t)}) | {d} ({len(d)}) |")
    lines.append("\n")

    # On-page issues
    lines += [
        "---\n",
        f"## On-Page Issues ({len(issues)} total)\n",
        f"- **Critical:** {len(critical)}",
        f"- **Warnings:** {len(warnings)}",
        f"- **Info:** {len(info_issues)}",
        "",
        "### Critical Issues",
    ]
    for i in critical:
        lines.append(f"- `{i['check']}` — **{i['url']}** — {i['detail']}")
    lines += ["", "### Warnings"]
    for i in warnings:
        lines.append(f"- `{i['check']}` — **{i['url']}** — {i['detail']}")
    lines += ["", "### Info"]
    for i in info_issues:
        lines.append(f"- `{i['check']}` — **{i['url']}** — {i['detail']}")
    lines.append("\n")

    # Pages crawled
    lines += [
        "---\n",
        f"## Pages Crawled ({len(crawl_data)} pages)\n",
        "| Status | URL | Title | Words | H1 | Missing Alts |",
        "|--------|-----|-------|-------|----|--------------|",
    ]
    for p in crawl_data:
        h1s = " / ".join(p.get("h1", []))[:60]
        title = p.get("title", "")[:50]
        lines.append(
            f"| {p.get('status','?')} | {p.get('url','')} | {title} | "
            f"{p.get('word_count',0)} | {h1s} | {len(p.get('images_missing_alt',[]))} |"
        )

    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"Audit report written: {path}")
    return path


def write_blog_plan(blog_posts: list[dict]) -> Path:
    """Write blog content calendar to local markdown file."""
    path = _reports_dir() / f"blog_plan_{date.today().isoformat()}.md"

    lines = [
        f"# Buying Hero — 3-Month Blog Content Calendar\n",
        f"Generated: {date.today().isoformat()}\n",
        "---\n",
        "| # | Keyword | Searches | Intent | Priority | Title |",
        "|---|---------|----------|--------|----------|-------|",
    ]

    for post in blog_posts:
        lines.append(
            f"| {post.get('rank','')} | {post.get('keyword','')} | "
            f"{post.get('monthly_searches','')} | {post.get('search_intent','')} | "
            f"{post.get('priority','')} | {post.get('title','')} |"
        )

    lines += ["\n", "---\n", "## Full Post Details\n"]
    for post in blog_posts:
        lines += [
            f"### {post.get('rank','')}. {post.get('title','')}",
            f"**Keyword:** {post.get('keyword','')}  ",
            f"**Searches:** {post.get('monthly_searches','')}  ",
            f"**Intent:** {post.get('search_intent','')}  ",
            f"**Priority:** {post.get('priority','')}  ",
            "",
            "**Outline:**",
        ]
        for section in post.get("outline", []):
            lines.append(f"- {section}")
        notes = post.get("notes", "")
        if notes:
            lines.append(f"\n*Notes: {notes}*")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(f"Blog plan written: {path}")
    return path
