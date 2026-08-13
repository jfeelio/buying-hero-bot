"""
LeadZolo → REsimpli + WhatsApp Notification via Twilio
Receives LeadZolo webhook, creates lead in REsimpli, notifies team via WhatsApp.
"""

import os
import json
import httpx
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from twilio.rest import Client as TwilioClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

RESIMPLI_API_KEY = os.environ["RESIMPLI_API_KEY"]
RESIMPLI_BASE_URL = "https://api.resimpli.com/api"

# Twilio WhatsApp
# Sign up at twilio.com, get Account SID + Auth Token
# WhatsApp sandbox: https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "")  # e.g. "whatsapp:+14155238886" (sandbox) or your approved number
# Comma-separated list of team WhatsApp numbers, e.g. "+13055551234,+13055555678"
TEAM_WHATSAPP_NUMBERS = os.environ.get("TEAM_WHATSAPP_NUMBERS", "")

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")  # optional security token


def build_resimpli_payload(data: dict) -> dict:
    """Map LeadZolo fields to REsimpli Create Lead fields."""

    first_name = data.get("first_name", "")
    last_name = data.get("last_name", "")

    address_parts = [
        data.get("address_1", ""),
        data.get("address_2", ""),
        data.get("city", ""),
        data.get("state", ""),
        str(data.get("zip", "")),
    ]
    full_address = ", ".join(p for p in address_parts if p)

    rehab_lines = []
    if data.get("Absentee_Owner"):
        rehab_lines.append(f"Absentee Owner: {data['Absentee_Owner']}")
    if data.get("howsoontosell"):
        rehab_lines.append(f"How Soon to Sell: {data['howsoontosell']}")
    if data.get("reasonforselling"):
        rehab_lines.append(f"Reason for Selling: {data['reasonforselling']}")
    if data.get("recent_updates"):
        rehab_lines.append(f"Recent Updates: {data['recent_updates']}")
    if data.get("repairs_needed"):
        rehab_lines.append(f"Repairs Needed: {data['repairs_needed']}")
    if data.get("property_condition"):
        rehab_lines.append(f"Property Condition: {data['property_condition']}")
    rehab_details = "\n".join(rehab_lines)

    return {
        "firstName": first_name,
        "lastName": last_name,
        "phone": data.get("phone", ""),
        "email": data.get("email", ""),
        "leadSource": "Pay Per Lead",
        "propertyAddress": full_address,
        "leadStatus": "New Leads",
        "market": "Primary Market",
        "isHotLead": True,
        "rehabDetails": rehab_details,
    }


def build_whatsapp_message(data: dict) -> str:
    first = data.get("first_name", "")
    last = data.get("last_name", "")
    phone = data.get("phone", "N/A")
    email = data.get("email", "N/A")
    city = data.get("city", "")
    state = data.get("state", "")
    address = f"{data.get('address_1', '')} {city}, {state}".strip(", ")
    how_soon = data.get("howsoontosell", "N/A")
    reason = data.get("reasonforselling", "N/A")
    condition = data.get("property_condition", "N/A")

    return (
        f"*New LeadZolo Lead*\n"
        f"Name: {first} {last}\n"
        f"Phone: {phone}\n"
        f"Email: {email}\n"
        f"Address: {address}\n"
        f"Timeline: {how_soon}\n"
        f"Reason: {reason}\n"
        f"Condition: {condition}"
    )


async def post_to_resimpli(payload: dict) -> dict:
    url = f"{RESIMPLI_BASE_URL}/leads"
    headers = {
        "Authorization": f"Bearer {RESIMPLI_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


def send_whatsapp(message: str):
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM, TEAM_WHATSAPP_NUMBERS]):
        logger.warning("Twilio env vars not set — skipping WhatsApp notification")
        return

    client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    numbers = [n.strip() for n in TEAM_WHATSAPP_NUMBERS.split(",") if n.strip()]

    for number in numbers:
        to = f"whatsapp:{number}" if not number.startswith("whatsapp:") else number
        msg = client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=to,
            body=message,
        )
        logger.info(f"WhatsApp sent to {number}: SID={msg.sid}")


@app.post("/webhook/leadzolo")
async def receive_lead(request: Request):
    try:
        body = await request.json()
    except Exception:
        raw = await request.body()
        logger.error(f"Failed to parse JSON: {raw}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    logger.info(f"Received lead: {json.dumps(body)}")

    # Build and post to REsimpli
    try:
        resimpli_payload = build_resimpli_payload(body)
        result = await post_to_resimpli(resimpli_payload)
        logger.info(f"REsimpli response: {result}")
    except httpx.HTTPStatusError as e:
        logger.error(f"REsimpli API error: {e.response.status_code} — {e.response.text}")
        raise HTTPException(status_code=502, detail=f"REsimpli error: {e.response.text}")

    # Send WhatsApp notification (non-fatal if it fails)
    try:
        message = build_whatsapp_message(body)
        send_whatsapp(message)
    except Exception as e:
        logger.error(f"WhatsApp error (non-fatal): {e}")

    return JSONResponse({"status": "ok", "resimpli": result})


@app.get("/health")
async def health():
    return {"status": "running"}
