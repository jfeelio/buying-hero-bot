"""Read-only n8n lookups for the fixer agent. GET requests only.

  python n8n_read.py execution <id>     why one execution failed
  python n8n_read.py workflow <id>      a workflow's nodes and whether it is active
"""
import json
import os
import sys
import urllib.request

BASE = os.environ.get("N8N_BASE_URL", "https://automations.buyinghero.com") + "/api/v1/"


def get(path):
    req = urllib.request.Request(BASE + path, headers={"X-N8N-API-KEY": os.environ["N8N_API_KEY"],
                                                       "Accept": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def execution(eid):
    e = get("executions/%s?includeData=true" % eid)
    rd = ((e.get("data") or {}).get("resultData") or {})
    err = rd.get("error") or {}
    nodes = []
    for name, runs in (rd.get("runData") or {}).items():
        for r in runs or []:
            if r.get("error"):
                nodes.append({"node": name, "error": (r["error"].get("message") or "")[:500],
                              "description": (r["error"].get("description") or "")[:500]})
    print(json.dumps({"id": e.get("id"), "workflowId": e.get("workflowId"), "status": e.get("status"),
                      "mode": e.get("mode"), "startedAt": e.get("startedAt"), "stoppedAt": e.get("stoppedAt"),
                      "lastNodeExecuted": rd.get("lastNodeExecuted"),
                      "error": (err.get("message") or "")[:800], "failedNodes": nodes}, indent=1))


def workflow(wid):
    w = get("workflows/%s" % wid)
    print(json.dumps({"id": w.get("id"), "name": w.get("name"), "active": w.get("active"),
                      "nodes": [{"name": n.get("name"), "type": n.get("type"),
                                 "credentials": list((n.get("credentials") or {}).keys())}
                                for n in w.get("nodes") or []]}, indent=1))


if __name__ == "__main__":
    {"execution": execution, "workflow": workflow}[sys.argv[1]](sys.argv[2])
