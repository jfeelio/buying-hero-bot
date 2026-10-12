# Rebuilding the REsimpli Lead Zap

**Integration runbook — Buying Hero**

REsimpli retired the integration our old Zap authenticated against. This is the
replacement: a direct API call that puts PPC leads back into the Active Leads
pipeline. Your LeadConnector trigger stays exactly as it is — only the action
changes.

| | |
|---|---|
| **For** | Bolt Deals PPC |
| **Trigger** | LeadConnector → unchanged |
| **Campaign** | Bolt PPC |
| **Est. time** | 20 minutes |
| **Updated** | 12 September 2026 |

---

## What broke

REsimpli's Zapier app was tied to their 3.0 integration, which no longer
authenticates. There is no updated Zapier app to swap in.

Their replacement is a standard REST API. That means the REsimpli action in the
existing Zap gets deleted and replaced with a generic webhook call.

**Your LeadConnector trigger does not change.** Whatever fires it today — new
contact, form submission, tag added — keeps firing it. Everything in this
document happens downstream of that trigger.

---

## Before you start

> **You need an API key, and it is not in this document.** Jorge will send it to
> you separately — please don't paste it into email threads, shared docs, or
> Slack channels beyond where it lands.
>
> You will also need a Zapier plan that includes **Webhooks by Zapier** and
> **Formatter by Zapier**. Both are premium apps. If your account can't add
> them, tell Jorge before going further.

---

## The build

### 01 — Format the phone number

Add a **Formatter by Zapier** step between the LeadConnector trigger and the
webhook. This is not optional: **LeadConnector always returns phone numbers in
E.164** — `+17861234567` — and REsimpli rejects anything that isn't exactly ten
bare digits.

| Setting | Value |
|---|---|
| Event | Numbers → Format Phone Number |
| Input | LeadConnector `Phone` |
| Format | strip to digits only, then remove the leading `1` |
| Expected output | `7861234567` |

Check the output in Zapier's test panel before moving on. If it still shows a
`+` or eleven digits, every lead will fail at the next step.

### 02 — Replace the REsimpli step

Delete the old REsimpli action. Add **Webhooks by Zapier** and choose the
**Custom Request** event — not "POST", which formats the body differently.

| Setting | Value |
|---|---|
| Method | `POST` |
| URL | `https://api.resimpli.com/api/v6/openapi/lead/add` |
| Data Pass-Through? | `false` |
| Unflatten | `no` |
| Headers | `Authorization` → the key Jorge sent<br>`Content-Type` → `application/json` |

The `Authorization` header takes the key on its own. Do not prefix it with
`Bearer` — that will fail authentication.

### 03 — Paste the request body

This goes in the **Data** field. The four IDs are already filled in and correct
— they route leads to the Bolt PPC campaign in the Active Leads pipeline.
Replace only the `{{...}}` placeholders by inserting fields from the steps above.

Map them from LeadConnector like this. Exact labels vary by which LeadConnector
trigger you're on, so pick the closest match from your trigger's test output:

| From LeadConnector | Into REsimpli |
|---|---|
| `First Name` | `firstName` — required |
| `Last Name` | `lastName` |
| Formatter output (step 01) | `phoneNumber` — required |
| `Email` | `email` |
| `Address 1`, `City`, `State`, `Postal Code` | `address` — joined into one line |

REsimpli wants the property address as a **single string**, but LeadConnector
returns it in separate fields. Insert all four next to each other in the one
value, as shown below — no extra Formatter step needed.

```json
{
  "contactDetails": {
    "firstName": "{{LC First Name}}",
    "lastName": "{{LC Last Name}}",
    "phoneNumbers": [
      { "phoneNumber": "{{Formatter Output}}", "isPrimary": true }
    ],
    "emails": [
      { "email": "{{LC Email}}", "isPrimary": true }
    ]
  },
  "propertyType": "residential",
  "address": "{{LC Address 1}}, {{LC City}}, {{LC State}} {{LC Postal Code}}",
  "marketingCampignId": "6aa4f3c24ded82f2fd087b6d",
  "marketId": "686e80f9cb41069d6c7735b4",
  "pipelineId": "6aa4dc81d18014f8fc5e5357",
  "mainStatusId": "6aa4dc81d18014f8fc5e5358"
}
```

Reference for the four IDs (do not change them):

| Field | Value | What it is |
|---|---|---|
| `marketingCampignId` | `6aa4f3c24ded82f2fd087b6d` | Bolt PPC |
| `marketId` | `686e80f9cb41069d6c7735b4` | Primary Market |
| `pipelineId` | `6aa4dc81d18014f8fc5e5357` | Active Leads |
| `mainStatusId` | `6aa4dc81d18014f8fc5e5358` | New Leads |

Only `firstName` and one phone number are strictly required. Send `lastName`,
`email` and `address` whenever LeadConnector has them — a lead without an
address is much harder to work.

**If a contact has no email,** drop the whole `emails` block rather than sending
it with an empty value — the field is required *within* that block, so an empty
string can fail the request. If your LeadConnector contacts are inconsistent
about email, tell Jorge and we'll handle it with a Zapier filter path instead of
guessing.

### 04 — Test and confirm

Run the Zap end to end from the LeadConnector side — create a real test contact
so the trigger fires naturally, rather than replaying an old sample. Sample data
in Zapier can carry fields that a live contact won't have, which hides exactly
the failures you want to catch now.

Use an obviously fake name like *ZZ Test Lead* and a phone number you control,
so it's easy to spot and remove.

A successful response looks like this:

```json
{ "statusCode": 200, "type": "SUCCESS", "data": { "_id": "..." } }
```

Then tell Jorge, so he can confirm the lead landed in Active Leads under the
Bolt PPC campaign and delete the test record on his side.

---

## Three things that will trip you up

These are the failure modes we already hit. Each one produces an error that
points somewhere unhelpful.

### Trap 1 — the misspelling is intentional

The field is `marketingCampignId`. There is no second **a** — it is not
"Campaign". This is a typo in REsimpli's own API, confirmed in both their
documentation and their live records. If you correct the spelling, the request
fails.

### Trap 2 — do not send APN

REsimpli's field list marks `apn` as required. It isn't, for us: it only applies
when `propertyType` is `"land"`. Ours is `"residential"`, so leave `apn` and
`referenceId` out of the body entirely.

### Trap 3 — no `Bearer` prefix

The `Authorization` header value is the raw key and nothing else. Most APIs want
`Bearer <key>`; this one rejects it. If you're testing from a terminal on
Windows, also note that PowerShell aliases `curl` to a different command — use
`curl.exe`.

---

## Reading the response

Every failure comes back as a `401`, so the message text is what tells you where
to look.

| Status | Message | What it means |
|---|---|---|
| `200` | `"type": "SUCCESS"` | Lead created. You're done. |
| `401` | `"Invalid param!"` | The `Authorization` header never arrived — check the header name spelling and that it's set on the request, not the body. |
| `401` | `"Record not found!"` | The header arrived but the key wasn't recognised. The request is built correctly; the key is wrong or expired. Ask Jorge to reissue. |
| `4xx` | validation error | Almost always the phone number. Confirm step 01 is producing ten bare digits. |

---

## When you're done

Send Jorge these three things so he can verify from the REsimpli side:

- A screenshot of the successful Zap run, showing the `200` response.
- The name and phone number you used on the test lead, so he can find and delete it.
- Confirmation that the phone formatter step is live in the published Zap — not
  just in the editor.

> **Please don't send real PPC traffic through until Jorge confirms the test
> lead landed correctly.** Leads that fail this call are not queued or retried
> anywhere — they're simply lost, and there's no way to recover them after the
> fact.

---

Questions on anything here go to Jorge directly. If REsimpli support tells you
something that contradicts this document, send it over rather than improvising —
these field names and IDs were pulled from the live account on 12 September 2026
and verified against existing Bolt PPC leads.
