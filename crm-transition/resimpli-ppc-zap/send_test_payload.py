#!/usr/bin/env python3
"""
POST a synthetic Bolt Deals lead to a webhook URL.

Two jobs:
  1. DIAGNOSTIC — proves whether a Zapier Catch Raw Hook is reachable and
     capturing. If this shows up in Zapier but the drip doesn't, the fault is
     on REsimpli's side, not Zapier's.
  2. UNBLOCKER — seeds Zapier with a realistically-shaped sample so you can
     build and test the whole Zap (Lookup + Update) before the drip works.

Payload matches the real REsimpli schema (Title Case keys, Property Id,
Qualified boolean, Action) but contains NO real seller or staff data.

Usage:
    python send_test_payload.py "<catch-raw-hook-url>"
    python send_test_payload.py "<url>" --qualified
    python send_test_payload.py "<url>" --dead "Wrong Number"
"""
import argparse
import json
import sys
import uuid

import httpx

ap = argparse.ArgumentParser()
ap.add_argument("url")
ap.add_argument("--qualified", action="store_true", help="send Qualified: true")
ap.add_argument("--dead", default="", help="set a Dead Lead Reason")
ap.add_argument("--lead-id", default="", help="reuse an ID to test the update path")
ap.add_argument("--source", default="PPC")
ap.add_argument("--campaign", default="Bolt Deals - Search - Miami")
a = ap.parse_args()

if not a.url.lower().startswith("https://"):
    sys.exit("Refusing to send: URL must be https://")

lead_id = a.lead_id or uuid.uuid4().hex[:24]

payload = {
    "firstName": "Test", "lastName": "Lead-DoNotContact",
    "Property Street Address": "100 Test St", "Property Street Address 2": "",
    "Property City": "Miami", "Property State": "FL", "Property Zip": "33101",
    "Property Id": lead_id,
    "Phone Number": "+15555550100",           # 555 range - never a real number
    "Email Address": "test@example.com",
    "Lead Status": "New Leads",
    "Lead Source": a.source,
    "Campaign Name": a.campaign,
    "Market Name": "Primary Market",
    "Lead Created Date": "Aug 18, 2026",
    "Tags": "", "Dead Lead Reason": a.dead,
    "Lead Questions": [{
        "Group Title": "MOTIVATION AND TIMELINE - LEAD MANAGER",
        "Questions": [
            {"Question": "What's the main reason you're considering selling right now?",
             "Answer": "Relocating for work"},
            {"Question": " If we come to an agreement, when would you like to sell ?",
             "Answer": "30-60 days"},
        ]}],
    "Qualified": bool(a.qualified),
    "Action": "Status Change" if (a.qualified or a.dead or a.lead_id) else "New Lead Created",
}

print(f"POST {a.url[:60]}...")
print(f"  Property Id : {lead_id}   <-- reuse with --lead-id to test the UPDATE path")
print(f"  Source      : {a.source} / {a.campaign}")
print(f"  Qualified   : {payload['Qualified']}   Dead Reason: {a.dead or '(none)'}")
print(f"  Action      : {payload['Action']}")

try:
    r = httpx.post(a.url, json=payload, timeout=25,
                   headers={"Content-Type": "application/json"})
except Exception as e:
    sys.exit(f"\nFAILED to send: {type(e).__name__}: {e}")

print(f"\nHTTP {r.status_code}")
print(r.text[:400])
if r.status_code < 300:
    print("\nDelivered. Now open the Zap and click 'Test trigger' — it should appear.")
    print("If it does NOT appear, the problem is Zapier-side (wrong URL / wrong Zap).")
    print("If it DOES appear but your drip never does, the problem is REsimpli-side.")
