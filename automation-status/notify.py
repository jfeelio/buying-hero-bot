"""Email Jorge the fixer's report through the n8n mailer (acqreport0001).

  python notify.py /tmp/fixer/status.json /tmp/fixer/report.json [pr_url]

Sends only when the status check found problems. Everything is HTML-escaped:
the report is written by an AI that read untrusted logs.
"""
import html
import json
import os
import sys
import urllib.request

HUB = "https://claude.ai/artifact/RJ3Xta8e9jEAyPYEjhK8cM"
LABEL = {"reran": "Re-ran it", "proposed_fix": "Fix ready for your approval",
         "needs_jorge": "Needs you", "no_action": "No action"}


def main():
    status = json.load(open(sys.argv[1]))
    if not status.get("problems"):
        print("no problems: no email")
        return
    try:
        rep = json.load(open(sys.argv[2], encoding="utf-8"))
    except Exception:
        rep = {"summary": "The fixer agent did not finish, so these problems were not diagnosed.",
               "items": [{"automation": p["name"], "problem": p["problem"], "action": "needs_jorge",
                          "cause": "", "details": "", "jorge_steps": ""} for p in status["problems"]]}
    pr = sys.argv[3] if len(sys.argv) > 3 else ""
    e = lambda s: html.escape(str(s or ""))
    parts = ["<p>%s</p>" % e(rep.get("summary"))]
    if pr:
        parts.append('<p><b>A code fix is waiting for your approval:</b> <a href="%s">%s</a></p>' % (e(pr), e(pr)))
    for it in rep.get("items") or []:
        parts.append("<hr><p><b>%s</b> · %s</p>" % (e(it.get("automation")), e(LABEL.get(it.get("action"), it.get("action")))))
        for k, lab in (("problem", "What we saw"), ("cause", "Why"), ("details", "What happened")):
            if it.get(k):
                parts.append("<p><i>%s:</i> %s</p>" % (lab, e(it[k])))
        if it.get("jorge_steps"):
            parts.append("<p><i>What you need to do:</i><br>%s</p>" % e(it["jorge_steps"]).replace("\n", "<br>"))
    parts.append('<hr><p>Automations hub: <a href="%s">%s</a></p>' % (HUB, HUB))
    n = len(status["problems"])
    need = sum(1 for it in rep.get("items") or [] if it.get("action") in ("needs_jorge", "proposed_fix"))
    subject = "Automations: %d problem%s%s" % (n, "" if n == 1 else "s", (", %d need you" % need) if need else ", handled")
    body = json.dumps({"kind": "failure", "subject": subject, "html": "\n".join(parts)}).encode()
    req = urllib.request.Request(os.environ["ACQ_REPORT_WEBHOOK_URL"], data=body, method="POST", headers={
        "Content-Type": "application/json", "X-Report-Key": os.environ["ACQ_REPORT_WEBHOOK_KEY"]})
    print("mailer:", urllib.request.urlopen(req, timeout=60).status)


if __name__ == "__main__":
    main()
