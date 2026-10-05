"""
Finds who to mail on a probate case: the petitioner (the heir or personal
representative who filed) and their home address.

The OCS case detail lists parties by name only. Addresses live in the filed
documents, which are free to download with the Clerk login:
  - Affidavit of Heirs (form E-7): every heir with address, plus the affiant's
    phone/email. On ~80% of Formal and ~73% of Summary cases.
  - Oath of Personal Representative: the PR's address (Formal cases).
  - Petition for Determination of Heirs / Homestead.
The documents are scans with no text layer, so Claude reads them.

Returns per case:
  petitioner, recipient (name/relationship/address/phone/email),
  other_heirs, source (which document the address came from)
"""

import base64
import json
import logging

import anthropic

import clean
from scrapers.probate import OCS_API

logger = logging.getLogger(__name__)

# First match with a downloadable document wins.
DOC_PRIORITY = [
    "Affidavit of Heirs",
    "Oath of Personal Representative",
    "Petition for Det of Heirs",
    "Petition for Administration",
    "Petition for Summary Administration",
]

MODEL = "claude-opus-5-5"

HEIR_SCHEMA = {
    "type": "object",
    "properties": {
        "people": {
            "type": "array",
            "description": "Every living heir, beneficiary, petitioner or personal representative named in the document. Skip the decedent, attorneys, notaries and anyone listed as deceased.",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "relationship": {"type": "string", "description": "To the decedent, e.g. DAUGHTER, SON, SPOUSE, PERSONAL REPRESENTATIVE. Empty if not stated."},
                    "is_filer": {"type": "boolean", "description": "True if this person signed or filed the document (affiant, petitioner, or personal representative)."},
                    "street": {"type": "string", "description": "Street line including unit. Empty if no address is given."},
                    "city": {"type": "string"},
                    "state": {"type": "string", "description": "Two-letter code."},
                    "zip": {"type": "string"},
                    "phone": {"type": "string"},
                    "email": {"type": "string"},
                },
                "required": ["name", "relationship", "is_filer", "street", "city", "state", "zip", "phone", "email"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["people"],
    "additionalProperties": False,
}

PROMPT = (
    "This is a scanned Florida probate court filing. List every living person it names "
    "as an heir, beneficiary, petitioner, affiant or personal representative, with their "
    "mailing address, phone and email exactly as written. Leave a field empty when the "
    "document does not give it. Do not guess or fill in addresses from anywhere else."
)


def _case_detail(s, case_id) -> dict:
    qs = s.post(f"{OCS_API}/CaseInfo/PostSearchByCaseID", params={"caseID": case_id}, timeout=30)
    qs.raise_for_status()
    r = s.post(f"{OCS_API}/CaseInfo/GetSingleCaseResult", json=qs.text.strip().strip('"'), timeout=30)
    r.raise_for_status()
    return r.json()


def _download(s, docket: dict) -> bytes:
    r = s.get(f"{OCS_API}/CaseInfo/GetSDocumentByEvent?qs={docket['encID']}", timeout=30)
    r.raise_for_status()
    docs = r.json() or []
    if not docs or not docs[0].get("encDocInfo"):
        return b""
    pdf = s.get(f"{OCS_API}/CaseInfo/image", params={"imagePath": docs[0]["encDocInfo"]}, timeout=90)
    if pdf.status_code != 200 or not pdf.content.startswith(b"%PDF"):
        return b""
    return pdf.content


def _read_people(client: anthropic.Anthropic, pdf: bytes) -> list[dict]:
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": HEIR_SCHEMA}},
        messages=[{
            "role": "user",
            "content": [
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                "data": base64.standard_b64encode(pdf).decode("ascii")}},
                {"type": "text", "text": PROMPT},
            ],
        }],
    )
    if response.stop_reason != "end_turn":
        logger.warning(f"    Claude stopped with {response.stop_reason}; no heirs read")
        return []
    text = next((b.text for b in response.content if b.type == "text"), "")
    return json.loads(text).get("people", []) if text else []


def _norm(name: str) -> set:
    return {w for w in name.upper().replace(",", " ").split() if len(w) > 1}


def find_recipient(s, client: anthropic.Anthropic, case_id) -> dict:
    """Petitioner + best mailing recipient for one case. Empty recipient if none found."""
    out = {"petitioner": "", "recipient": {}, "other_heirs": "", "source": ""}
    detail = _case_detail(s, case_id)

    petitioners = [p["partyName"] for p in detail.get("parties") or [] if p.get("partyTypeCode") == "PE"]
    if petitioners:
        out["petitioner"] = petitioners[0].title()

    dockets = [d for d in detail.get("dockets") or [] if (d.get("numberOfDocuments") or 0) > 0 and d.get("encID")]
    for wanted in DOC_PRIORITY:
        docket = next((d for d in dockets if (d.get("docketDescrition") or "").startswith(wanted)), None)
        if not docket:
            continue
        pdf = _download(s, docket)
        if not pdf:
            continue
        people = [p for p in _read_people(client, pdf) if p.get("street") and p.get("zip")]
        if not people:
            continue

        # Prefer the court-listed petitioner, then whoever filed, then the first heir.
        pet = _norm(out["petitioner"])
        best = (next((p for p in people if pet and len(pet & _norm(p["name"])) >= 2), None)
                or next((p for p in people if p.get("is_filer")), None)
                or people[0])
        out["recipient"] = best
        out["other_heirs"] = "; ".join(
            f"{clean.person(p['name'])} ({clean.squeeze(p['relationship']).title()}) "
            f"{clean.mail_street(p['street'])}, {clean.mail_city(p['city'])} {clean.squeeze(p['state']).upper()} {clean.zip5(p['zip'])}"
            for p in people if p is not best
        )
        out["source"] = wanted
        return out

    return out
