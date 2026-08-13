"""
Claude AI SEO Expert — Anthropic SDK integration.

Two calls:
  1. analyze_audit()  → executive summary + priority fixes + revised meta
  2. generate_blog_plan() → 50 blog post topics for South Florida real estate
"""

import json
import logging

import anthropic

import config

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


SEO_EXPERT_SYSTEM = """You are a senior SEO strategist specializing in real estate investor websites,
particularly Carrot.com-hosted sites targeting motivated sellers in South Florida
(Miami-Dade, Broward, Palm Beach counties).

Your client is Buying Hero — a cash buyer / wholesale company targeting distressed sellers.
Their primary conversion goal is to capture seller leads via their website (www.buyinghero.com).

Target keywords: "sell house fast [city]", "sell my house fast Miami",
"cash home buyers Miami", "stop foreclosure Miami", "sell probate property Florida".

When analyzing SEO issues, prioritize by business impact on lead generation.
When writing meta titles and descriptions, use direct, high-conversion language
that addresses seller pain points (speed, certainty, no repairs needed).

Always respond with valid JSON matching the requested schema exactly.
Do not include markdown fences or extra text — just the JSON object."""


def analyze_audit(crawl_data: list[dict], pagespeed_data: list[dict], issues: list[dict]) -> dict:
    """
    Call 1: Send full audit data to Claude. Returns structured analysis dict.

    Output schema:
    {
      "executive_summary": str,
      "critical_issues": [str, ...],
      "priority_fixes": [
        {
          "page_url": str,
          "issue": str,
          "current_value": str,
          "recommended_value": str,
          "implementation_notes": str
        }
      ],
      "revised_meta": [
        {
          "page_url": str,
          "new_title": str,
          "new_description": str
        }
      ]
    }
    """
    logger.info("Calling Claude AI for audit analysis...")

    # Summarize audit data to stay within token limits
    pages_summary = []
    for p in crawl_data:
        if p.get("status", 200) < 400:
            pages_summary.append({
                "url": p.get("url"),
                "title": p.get("title", ""),
                "meta_description": p.get("meta_description", ""),
                "h1": p.get("h1", []),
                "word_count": p.get("word_count", 0),
                "images_missing_alt": len(p.get("images_missing_alt", [])),
                "has_schema": bool(p.get("schema", [])),
                "canonical": p.get("canonical", ""),
                "robots_meta": p.get("robots_meta", ""),
            })

    # Summarize PageSpeed to key scores only
    ps_summary = [
        {
            "url": r.get("url"),
            "strategy": r.get("strategy"),
            "performance": r.get("performance"),
            "seo": r.get("seo"),
            "accessibility": r.get("accessibility"),
            "LCP": r.get("LCP"),
            "CLS": r.get("CLS"),
            "failed_audit_count": len(r.get("failed_audits", [])),
        }
        for r in pagespeed_data
    ]

    # Group issues by severity
    critical = [i for i in issues if i["severity"] == "critical"]
    warnings = [i for i in issues if i["severity"] == "warning"]

    prompt = f"""Analyze this SEO audit for www.buyinghero.com and return a JSON object.

## Pages Crawled ({len(pages_summary)} pages)
{json.dumps(pages_summary, indent=2)}

## PageSpeed Insights
{json.dumps(ps_summary, indent=2)}

## Critical Issues ({len(critical)})
{json.dumps(critical[:30], indent=2)}

## Warnings ({len(warnings)})
{json.dumps(warnings[:30], indent=2)}

Return this exact JSON schema:
{{
  "executive_summary": "2-3 paragraph summary of site SEO health and top priorities",
  "critical_issues": ["list of top 10 most impactful issues to fix immediately"],
  "priority_fixes": [
    {{
      "page_url": "full URL",
      "issue": "issue name",
      "current_value": "what it is now",
      "recommended_value": "what it should be",
      "implementation_notes": "how to fix this in Carrot dashboard"
    }}
  ],
  "revised_meta": [
    {{
      "page_url": "full URL",
      "new_title": "50-60 char SEO-optimized title targeting seller keywords",
      "new_description": "130-160 char compelling description with CTA"
    }}
  ]
}}

Include revised_meta for ALL pages that have missing, duplicate, or suboptimal meta.
Priority fixes should cover top 15-20 highest-impact items.
"""

    client = _get_client()
    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=8192,
        system=SEO_EXPERT_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    logger.info("Audit analysis received from Claude")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON if wrapped in text
        import re
        match = re.search(r'\{[\s\S]*\}', raw)
        if match:
            return json.loads(match.group(0))
        logger.error("Could not parse Claude audit response as JSON")
        return {"executive_summary": raw, "priority_fixes": [], "revised_meta": [], "critical_issues": []}


def generate_blog_plan(audit_summary: dict, crawl_data: list[dict]) -> dict:
    """
    Call 2: Generate 50-topic blog content calendar for South Florida real estate.

    Output schema:
    {
      "blog_posts": [
        {
          "rank": int,
          "keyword": str,
          "monthly_searches": str,
          "search_intent": str,
          "title": str,
          "outline": [str, ...],
          "priority": "high" | "medium" | "low",
          "notes": str
        }
      ]
    }
    """
    logger.info("Calling Claude AI for blog content calendar...")

    existing_pages = [p.get("url", "") for p in crawl_data if p.get("status", 200) < 400]

    prompt = f"""Generate a 3-month blog content calendar for www.buyinghero.com.

## Site Context
- Company: Buying Hero — cash home buyer and wholesaler
- Target market: South Florida (Miami-Dade, Broward, Palm Beach)
- Target audience: Distressed sellers facing foreclosure, probate, divorce, job loss,
  code violations, behind on taxes, inherited properties
- Business model: Wholesale / assignment of contract
- Platform: Carrot.com (WordPress-based real estate investor site)
- Conversion goal: Seller lead capture (phone + form fill)

## Existing Site Pages
{json.dumps(existing_pages, indent=2)}

## Current SEO Gaps (from audit)
{json.dumps(audit_summary.get("critical_issues", [])[:10], indent=2)}

## Instructions
Create 50 blog post topics targeting:
1. "sell house fast [city]" keywords for top South Florida cities
2. Distressed seller situation keywords (foreclosure, probate, divorce, code violations)
3. "cash home buyers [city]" variations
4. Educational content for motivated sellers
5. Neighborhood/zip-code level content for Miami-Dade, Broward

Prioritize transactional and commercial intent keywords.
Avoid generic real estate topics — every post must serve a motivated seller.
Link each post to the Buying Hero homepage or relevant landing page.

Return this exact JSON schema with exactly 50 blog_posts:
{{
  "blog_posts": [
    {{
      "rank": 1,
      "keyword": "primary target keyword",
      "monthly_searches": "estimated search volume (e.g. '1,000-2,000')",
      "search_intent": "transactional | informational | navigational",
      "title": "compelling blog post title (under 60 chars)",
      "outline": ["Intro paragraph description", "H2: Section title", "H2: Section title", "H2: Section title", "CTA: Call to action"],
      "priority": "high | medium | low",
      "notes": "SEO notes, internal linking suggestions, geo targeting"
    }}
  ]
}}
"""

    client = _get_client()
    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=16000,
        system=SEO_EXPERT_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    logger.info("Blog plan received from Claude")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        import re
        match = re.search(r'\{[\s\S]*\}', raw)
        if match:
            return json.loads(match.group(0))
        logger.error("Could not parse Claude blog plan response as JSON")
        return {"blog_posts": []}
