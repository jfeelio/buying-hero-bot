"""Build the fix PR's title and body from the fixer report.

  python pr_body.py /tmp/fixer/report.json /tmp/fixer/pr_body.md   -> prints the title
"""
import json
import sys

try:
    r = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    r = {"summary": "", "items": []}
fixes = [i for i in r.get("items", []) if i.get("action") == "proposed_fix"]
lines = ["Proposed by the daily automation check. Review the diff before merging.", "", r.get("summary", ""), ""]
for i in fixes:
    lines += ["### " + i.get("automation", ""), "**Problem:** " + i.get("problem", ""),
              "**Cause:** " + i.get("cause", ""), "**Fix:** " + i.get("details", ""), ""]
open(sys.argv[2], "w", encoding="utf-8").write("\n".join(lines))
title = next((i.get("pr_title") for i in fixes if i.get("pr_title")), "") or "Fix from the daily automation check"
print(" ".join(title.split())[:100])
