"""Weekly acquisitions report: REsimpli -> metrics -> Claude commentary -> PDF -> email.

    python run.py                          # the week that just ended (Sunday run) and send it
    python run.py --week-start 2026-09-21 --no-send
    python run.py --cache raw.json --no-send   # re-render from a saved pull, no API sweep

Env:
  RESIMPLI_KEY              REsimpli Open API key (falls back to ~/.resimpli_key locally)
  ANTHROPIC_API_KEY         optional; without it the commentary is rule-based
  ACQ_REPORT_WEBHOOK_URL    n8n mailer webhook
  ACQ_REPORT_WEBHOOK_KEY    shared secret, sent as X-Report-Key
"""
import argparse
import base64
import datetime
import json
import os
import sys
import urllib.request
from pathlib import Path

import analyze
import narrate
import render

HERE = Path(__file__).resolve().parent


def default_week_start(today):
    """Sunday run -> the week ending today. Any other day -> last full Mon-Sun week."""
    monday = today - datetime.timedelta(days=today.weekday())
    return monday if today.weekday() == 6 else monday - datetime.timedelta(days=7)


def to_pdf(html_path, pdf_path):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
        page.emulate_media(media="screen", color_scheme="light")
        page.pdf(path=str(pdf_path), format="Letter", print_background=True, prefer_css_page_size=True)
        browser.close()


def send(subject, body_html, pdf_path):
    url, key = os.environ["ACQ_REPORT_WEBHOOK_URL"], os.environ["ACQ_REPORT_WEBHOOK_KEY"]
    payload = {"kind": "report", "subject": subject, "html": body_html, "filename": pdf_path.name,
               "pdf_base64": base64.b64encode(pdf_path.read_bytes()).decode()}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Report-Key": key})
    with urllib.request.urlopen(req, timeout=120) as r:
        print("mailer:", r.status, r.read().decode()[:200])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week-start", help="YYYY-MM-DD Monday")
    ap.add_argument("--cache", help="load a saved raw pull instead of calling REsimpli")
    ap.add_argument("--out", default=str(HERE / "out"))
    ap.add_argument("--no-send", action="store_true")
    ap.add_argument("--no-narrate", action="store_true")
    args = ap.parse_args()

    today = datetime.datetime.now(analyze.ET).date()
    week_start = (datetime.date.fromisoformat(args.week_start) if args.week_start
                  else default_week_start(today))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tag = week_start.isoformat()

    if args.cache:
        raw = json.load(open(args.cache, encoding="utf-8"))
    else:
        import pull
        ws, we, pws = analyze.week_bounds(week_start)
        raw = pull.pull(since_ms=pws, appt_window=(pws, we))
        json.dump(raw, open(out / ("raw-%s.json" % tag), "w", encoding="utf-8"), default=str)

    metrics = analyze.analyze(raw, week_start)
    json.dump(metrics, open(out / ("metrics-%s.json" % tag), "w", encoding="utf-8"), indent=1, default=str)

    if args.no_narrate:
        narr, author = narrate.fallback(metrics), "fallback (--no-narrate)"
    else:
        narr, author = narrate.narrate(metrics)
    json.dump(narr, open(out / ("narrative-%s.json" % tag), "w", encoding="utf-8"), indent=1)

    html_path = out / ("acquisitions-report-%s.html" % tag)
    html_path.write_text(render.page(metrics, narr, author), encoding="utf-8")
    pdf_path = out / ("Buying Hero Acquisitions Report %s.pdf" % metrics["week"]["label"].replace("–", "-"))
    to_pdf(html_path, pdf_path)
    print("wrote", html_path, "and", pdf_path, "| commentary:", author)

    if not args.no_send:
        send("Acquisitions report: %s" % metrics["week"]["label"], render.email_body(metrics, narr), pdf_path)


if __name__ == "__main__":
    sys.exit(main())
