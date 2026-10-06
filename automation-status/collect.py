"""Hourly health check of every Buying Hero automation.

Writes one JSON status file to a private Google Drive file (never to this
public repo). The private Automations Hub artifact reads that file live
through the viewer's Google Drive connector.

What it collects, per source:
  * GitHub Actions: every workflow in this repo, its last runs, 30-day pass
    rate, and countable stats parsed from the latest successful run's log
    (STAT_PATTERNS below; counts only, never lead details).
  * n8n (automations.buyinghero.com): every workflow, active or paused, and its
    recent executions. Needs the N8N_API_KEY secret; without it the n8n section
    reports the auth problem instead of failing the run.

This repo is PUBLIC: log counts and statuses only.
"""
import datetime as dt
import io
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

REPO = os.environ.get("GITHUB_REPOSITORY", "jfeelio/buying-hero-bot")
N8N_BASE = os.environ.get("N8N_BASE_URL", "https://automations.buyinghero.com")
STATUS_FILE_ID = os.environ["AUTOMATION_STATUS_FILE_ID"]
NOW = dt.datetime.now(dt.timezone.utc)
WINDOW_DAYS = 30

# workflow file -> [(label, regex with one number group)] read from the newest
# successful run's log. Keep these to counts.
STAT_PATTERNS = {
    "run_foreclosures.yml": [("Rows added", r"Pipeline complete\. (\d+) row\(s\) added")],
    "run_tax_deed.yml": [("Rows added", r"Pipeline complete\. (\d+) row\(s\) added")],
    "run_probate.yml": [("Rows added", r"Probate pipeline complete\. (\d+) row\(s\) added")],
    "run_probate_mail.yml": [
        ("Pieces mailed", r"Probate mailer complete\. (\d+) piece\(s\)"),
        ("Failed orders", r"mailed, (\d+) failed order"),
    ],
    "run_pokemon_tracker.yml": [("Rows written", r"Pipeline complete\. (\d+) row\(s\) written")],
    "run_levelup_sync.yml": [
        ("LevelUp leads in REsimpli", r"LevelUp leads: (\d+)"),
        ("New sheet rows", r"sheet: (\d+) new rows"),
        ("Rows updated", r"sheet: \d+ new rows, (\d+) updated"),
    ],
}


def log(msg):
    sys.stderr.write(msg + "\n")


def http(url, headers=None, raw=False, timeout=60):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    return body if raw else json.loads(body)


def iso(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


# ---------------------------------------------------------------- GitHub

def gh(path, raw=False):
    return http("https://api.github.com/repos/%s/%s" % (REPO, path), raw=raw, headers={
        "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
        "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})


def run_stats(file, run_id):
    pats = STAT_PATTERNS.get(file)
    if not pats:
        return {}
    try:
        z = zipfile.ZipFile(io.BytesIO(gh("actions/runs/%d/logs" % run_id, raw=True)))
        text = "\n".join(z.read(n).decode("utf-8", "replace") for n in z.namelist())
    except Exception as e:
        log("logs for %s unavailable (%s)" % (file, type(e).__name__))
        return {}
    out = {}
    for label, rx in pats:
        m = re.findall(rx, text)
        if m:
            out[label] = int(m[-1])
    return out


def github():
    since = (NOW - dt.timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    out = []
    for w in gh("actions/workflows?per_page=100")["workflows"]:
        file = w["path"].rsplit("/", 1)[-1]
        if not file.endswith((".yml", ".yaml")):
            continue
        runs = gh("actions/workflows/%d/runs?per_page=100&created=%%3E%%3D%s" % (w["id"], since))["workflow_runs"]
        if not runs:  # nothing in 30 days: still show the last run ever
            runs = gh("actions/workflows/%d/runs?per_page=1" % w["id"])["workflow_runs"]
        done = [r for r in runs if r["status"] == "completed"]
        recent = [r for r in done if iso(r["created_at"]) >= NOW - dt.timedelta(days=WINDOW_DAYS)]
        ok = [r for r in recent if r["conclusion"] == "success"]
        last = done[0] if done else None
        last_ok = next((r for r in done if r["conclusion"] == "success"), None)
        out.append({
            "key": "gh:" + file,
            "name": w["name"],
            "state": w["state"],  # active / disabled_manually / disabled_inactivity
            "running": any(r["status"] in ("in_progress", "queued") for r in runs),
            "last_run": last and {"id": last["id"], "at": last["run_started_at"] or last["created_at"],
                                  "conclusion": last["conclusion"], "event": last["event"]},
            "last_success_at": last_ok and (last_ok["run_started_at"] or last_ok["created_at"]),
            "runs_30d": len(recent),
            "success_30d": len(ok),
            "recent": [{"id": r["id"], "at": r["run_started_at"] or r["created_at"], "conclusion": r["conclusion"],
                        "event": r["event"]} for r in done[:10]],
            "stats": run_stats(file, last_ok["id"]) if last_ok else {},
        })
    log("github: %d workflows" % len(out))
    return {"ok": True, "items": out}


# ---------------------------------------------------------------- n8n

def n8n(path):
    return http(N8N_BASE + "/api/v1/" + path, headers={
        "X-N8N-API-KEY": os.environ.get("N8N_API_KEY", ""), "Accept": "application/json"})


def n8n_all(path, params):
    items, cursor = [], None
    for _ in range(50):
        q = dict(params, limit=100, **({"cursor": cursor} if cursor else {}))
        d = n8n(path + "?" + urllib.parse.urlencode(q))
        items += d.get("data") or []
        cursor = d.get("nextCursor")
        if not cursor:
            break
    return items


def n8n_status():
    if not os.environ.get("N8N_API_KEY"):
        return {"ok": False, "error": "N8N_API_KEY secret is not set", "items": []}
    try:
        flows = n8n_all("workflows", {})
    except urllib.error.HTTPError as e:
        why = "n8n rejected the API key (HTTP 401): update the N8N_API_KEY secret" if e.code == 401 \
            else "n8n API returned HTTP %d" % e.code
        log(why)
        return {"ok": False, "error": why, "items": []}
    except Exception as e:
        log("n8n unreachable (%s)" % type(e).__name__)
        return {"ok": False, "error": "n8n unreachable (%s)" % type(e).__name__, "items": []}

    cutoff = NOW - dt.timedelta(days=WINDOW_DAYS)
    out = []
    for w in flows:
        try:
            ex = n8n("executions?" + urllib.parse.urlencode({"workflowId": w["id"], "limit": 100}))["data"]
        except Exception:
            ex = []
        recent = [e for e in ex if iso(e.get("startedAt")) and iso(e["startedAt"]) >= cutoff]
        good = [e for e in recent if e.get("status") == "success"]
        last = ex[0] if ex else None
        out.append({
            "key": "n8n:" + w["id"],
            "name": w.get("name"),
            "state": "active" if w.get("active") else "inactive",
            "last_run": last and {"id": last.get("id"), "at": last.get("startedAt"),
                                  "conclusion": last.get("status"), "event": last.get("mode")},
            "last_success_at": next((e.get("startedAt") for e in ex if e.get("status") == "success"), None),
            "runs_30d": len(recent),
            "success_30d": len(good),
            "capped": len(ex) == 100,  # 100 executions returned: the 30-day count is a floor
            "recent": [{"id": e.get("id"), "at": e.get("startedAt"), "conclusion": e.get("status")} for e in ex[:10]],
        })
    log("n8n: %d workflows" % len(out))
    return {"ok": True, "items": out}


# ---------------------------------------------------------------- Drive

def save(doc):
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaInMemoryUpload
    scopes = ["https://www.googleapis.com/auth/drive"]
    raw = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    creds = (service_account.Credentials.from_service_account_info(json.loads(raw), scopes=scopes) if raw else
             service_account.Credentials.from_service_account_file(
                 os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "foreclosure-agent", "credentials.json"),
                 scopes=scopes))
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    body = json.dumps(doc, separators=(",", ":")).encode()
    drive.files().update(fileId=STATUS_FILE_ID, supportsAllDrives=True,
                         media_body=MediaInMemoryUpload(body, mimetype="application/json")).execute()
    log("status file: %d bytes written" % len(body))


# ---------------------------------------------------------------- problems

# Hours after which a job with no new run is overdue (weekday jobs span a weekend).
CADENCE_H = {
    "gh:run_foreclosures.yml": 84, "gh:run_tax_deed.yml": 84, "gh:run_probate.yml": 84,
    "gh:run_probate_mail.yml": 84, "gh:run_acq_report.yml": 204, "gh:run_levelup_sync.yml": 204,
    "gh:run_pokemon_tracker.yml": 30, "n8n:dnmsync000001": 30, "n8n:ghscheduler0001": 30,
}
IGNORE = {"gh:run_automation_status.yml"}  # this job; a broken run can't report itself


def problems(doc):
    out = []
    if not doc["n8n"]["ok"]:
        out.append({"key": "n8n", "name": "n8n status check", "problem": doc["n8n"]["error"]})
    for src in ("github", "n8n"):
        for w in doc[src]["items"]:
            if w["key"] in IGNORE or w["state"] != "active" or w.get("running"):
                continue
            last = w.get("last_run")
            if last and last["conclusion"] not in ("success", None):
                age = (NOW - iso(last["at"])).total_seconds() / 3600
                if src == "github" or age < 48:  # n8n: only fresh errors; old ones were seen already
                    out.append({"key": w["key"], "name": w["name"],
                                "problem": "last run %s at %s" % (last["conclusion"], last["at"]),
                                "run_id": last.get("id")})
                    continue
            cad = CADENCE_H.get(w["key"])
            if cad and last and (NOW - iso(last["at"])).total_seconds() / 3600 > cad:
                out.append({"key": w["key"], "name": w["name"],
                            "problem": "overdue: no run since %s" % last["at"]})
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="also write the status JSON here (for the fixer step)")
    ap.add_argument("--attach-report", help="add a fixer report JSON to the saved status file")
    args = ap.parse_args()
    if args.attach_report:
        doc = json.load(open(args.out))
        try:
            doc["fixer"] = json.load(open(args.attach_report))
        except Exception as e:
            doc["fixer"] = {"summary": "The fixer did not produce a report (%s)." % type(e).__name__, "items": []}
        doc["fixer"]["at"] = NOW.isoformat(timespec="seconds")
        save(doc)
        return
    doc = {"generated_at": NOW.isoformat(timespec="seconds"), "window_days": WINDOW_DAYS,
           "github": github(), "n8n": n8n_status()}
    doc["problems"] = problems(doc)
    log("problems: %d" % len(doc["problems"]))
    if args.out:
        json.dump(doc, open(args.out, "w"))
    save(doc)


if __name__ == "__main__":
    main()
