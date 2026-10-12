#!/usr/bin/env python3
"""
Probe the REsimpli API to find out whether we can PULL leads instead of
depending on the single outgoing-webhook slot (which AirMail already owns).

Usage:
    set RESIMPLI_API_KEY=...        (PowerShell: $env:RESIMPLI_API_KEY="...")
    python probe_api.py

Prints status codes and response SHAPE only. Lead values are redacted so you can
paste the output back into chat safely.
"""
import json
import os
import sys

import httpx

KEY = os.environ.get("RESIMPLI_API_KEY", "").strip()
if not KEY:
    sys.exit("Set RESIMPLI_API_KEY first. Find it in REsimpli:\n"
             "  Settings > Webhooks & API Token > API Token tab")

# NOTE: api.resimpli.com does NOT resolve (verified 2026-08-18, NXDOMAIN).
# dashboard.resimpli.com is the real app host, but every /api/* path there
# returns the SPA shell (200 text/html), not JSON. Set BASE from REsimpli's
# own API Token page / support before re-running.
BASE = os.environ.get("RESIMPLI_BASE_URL", "https://api.resimpli.com/api")

AUTHS = {
    "Bearer":  {"Authorization": f"Bearer {KEY}"},
    "X-API-KEY": {"X-API-KEY": KEY},
    "api-key":   {"api-key": KEY},
}

# Candidate read endpoints, most likely first.
PATHS = [
    "/leads", "/lead", "/leads/list", "/leads/search",
    "/lead-sources", "/leadSources", "/lead-status", "/campaigns",
    "/contacts", "/me", "/user", "/account",
]

SENSITIVE = {"phone", "email", "firstname", "lastname", "first_name", "last_name",
             "address", "address1", "address_1", "street", "name", "mobile"}


def redact(obj, depth=0):
    """Keep structure, drop values that could be PII."""
    if depth > 3:
        return "..."
    if isinstance(obj, dict):
        out = {}
        for k, v in list(obj.items())[:40]:
            if k.lower().replace("_", "") in {s.replace("_", "") for s in SENSITIVE}:
                out[k] = "<redacted>"
            else:
                out[k] = redact(v, depth + 1)
        return out
    if isinstance(obj, list):
        return [redact(o, depth + 1) for o in obj[:1]] + ([f"...{len(obj)} items"] if len(obj) > 1 else [])
    if isinstance(obj, str) and len(obj) > 60:
        return obj[:60] + "..."
    return obj


def main():
    working_auth = None
    print(f"Probing {BASE}\n" + "=" * 70)

    with httpx.Client(timeout=20, follow_redirects=True) as c:
        # 1. Which auth header does it accept?
        for name, hdr in AUTHS.items():
            try:
                r = c.get(f"{BASE}/leads", headers={**hdr, "Accept": "application/json"})
            except httpx.ConnectError as e:
                print(f"  auth {name:10} -> NETWORK/DNS FAILURE: {e}")
                print("")
                print(f"  {BASE} is unreachable. This is NOT an auth problem -")
                print("  the host does not resolve. Get the correct base URL from")
                print("  REsimpli (Settings > Webhooks & API Token > API Token),")
                print("  then re-run with RESIMPLI_BASE_URL set.")
                return
            except Exception as e:
                print(f"  auth {name:10} -> ERROR {type(e).__name__}: {e}")
                continue
            print(f"  auth {name:10} -> HTTP {r.status_code}")
            if r.status_code not in (401, 403) and working_auth is None:
                working_auth = (name, hdr)

        if not working_auth:
            print("\nNo auth style accepted. The token may be write-only, or reads "
                  "may live on a different host. Next step: ask REsimpli support "
                  "for the read/list endpoint for leads.")
            return

        name, hdr = working_auth
        hdr = {**hdr, "Accept": "application/json"}
        print(f"\nUsing auth: {name}\n" + "=" * 70)

        for path in PATHS:
            try:
                r = c.get(f"{BASE}{path}", headers=hdr, params={"limit": 2, "per_page": 2})
            except Exception as e:
                print(f"{path:20} ERROR {e}")
                continue
            print(f"{path:20} HTTP {r.status_code}", end="")
            if r.status_code == 200 and "json" not in r.headers.get("content-type", ""):
                print("  (HTML — SPA catch-all, not a real endpoint)")
            elif r.status_code == 200:
                try:
                    print("  <-- READABLE")
                    print(json.dumps(redact(r.json()), indent=2)[:1500])
                except Exception:
                    print(f"  (non-JSON: {r.text[:120]})")
            else:
                print(f"  {r.text[:100]}")
            print("-" * 70)


if __name__ == "__main__":
    main()
