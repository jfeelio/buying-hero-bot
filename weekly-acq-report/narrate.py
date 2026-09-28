"""Ask Claude to interpret the week's metrics.

Claude writes only the prose: the standfirst, the headline section, a few
callouts and the ranked actions. Every table in the report is rendered from the
metrics directly, so a bad narrative can never change a number. If the API call
fails for any reason, fallback() produces plain rule-based text and the report
still goes out.
"""
import json
import os
import sys

MODEL = "claude-opus-5"

SYSTEM = """You write the weekly acquisitions report for Buying Hero, a four-person
off-market real estate wholesaler in Miami-Dade and Broward (revenue = assignment fees,
~$29K average). The readers are Jorge and Adrian (co-owners), Albert (Director of
Acquisitions, runs appointments and offers), Andrew (lead manager / dispositions) and
Luis (Lead Manager, hourly, Mon-Sat).

You receive the week's metrics as JSON, computed from REsimpli. Tables are rendered
separately from the same JSON; your job is the interpretation.

Rules:
- Use only numbers that appear in the JSON, or simple arithmetic on them. Never invent
  a figure, a name or an event.
- Be specific and name names. "Andrew called back in 4 minutes" beats "speed was good".
- Lead with the one thing that most explains the week. If data hygiene makes a metric
  unreadable, say so.
- Do not draw conclusions from one or two cases. Say plainly when something is a
  single data point, and frame it as a question.
- A big change in one person's logged activity may be absence or a tool change, not
  performance. Flag it as something to confirm, not a judgement.
- Each action explains WHY the metric matters, not just what to do. Rank by return.
  Keep them executable by a four-person team.
- Plain, direct sentences. No em-dash asides, no "not X but Y" framing, no hype, no
  emoji. Use **bold** sparingly for the key figure in a paragraph; no other markup.
- Never speculate about anyone's motives or imply wrongdoing. Stick to what the data
  shows and what needs confirming.
- "Qualified" is REsimpli's own flag: an automation marks a lead qualified when someone
  moves it from New Leads to Discovery Done. The funnel (new leads -> qualified ->
  appointments set -> held -> kept -> offers) and last week's qualified cohort followed
  to today are the core of the report; comment on the weakest step. Appointments set
  can exceed qualified leads because older leads also get appointments.
- Market: Miami-Dade and Broward are in market. Anything else is out of market. An
  offer or lead flagged likely_mailing_address comes from a Miami mail campaign but
  carries an out-of-state address, so the address on file is probably the owner's
  mailing address, not the property. Say it needs correcting; don't treat it as an
  out-of-state deal."""

SCHEMA = {
    "type": "object",
    "properties": {
        "standfirst": {"type": "string", "description": "2-3 sentences under the title summing up the week."},
        "lead_title": {"type": "string", "description": "Headline section title, under 12 words."},
        "lead_body": {"type": "array", "items": {"type": "string"}, "description": "1-3 short paragraphs."},
        "callouts": {
            "type": "array",
            "description": "2-5 callout boxes, each attached to a report section.",
            "items": {
                "type": "object",
                "properties": {
                    "section": {"type": "string", "enum": ["funnel", "appointments", "offers", "hygiene", "intake", "followup", "calls"]},
                    "tone": {"type": "string", "enum": ["good", "warn", "bad"]},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["section", "tone", "title", "body"],
                "additionalProperties": False,
            },
        },
        "actions": {
            "type": "array",
            "description": "3-4 ranked actions for the team review.",
            "items": {
                "type": "object",
                "properties": {"title": {"type": "string"}, "body": {"type": "string"}},
                "required": ["title", "body"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["standfirst", "lead_title", "lead_body", "callouts", "actions"],
    "additionalProperties": False,
}


def narrate(metrics):
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.stderr.write("narrate: no ANTHROPIC_API_KEY, using fallback text\n")
        return fallback(metrics), "fallback (no API key)"
    try:
        import anthropic
        client = anthropic.Anthropic()
        with client.messages.stream(
            model=MODEL,
            max_tokens=32000,
            thinking={"type": "adaptive"},
            system=SYSTEM,
            messages=[{"role": "user", "content":
                       "Metrics for the week (JSON):\n\n" + json.dumps(metrics, default=str)}],
            output_config={"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}},
        ) as stream:
            msg = stream.get_final_message()
        if msg.stop_reason not in ("end_turn", "stop_sequence"):
            raise RuntimeError("stop_reason=%s" % msg.stop_reason)
        text = next(b.text for b in msg.content if b.type == "text")
        return json.loads(text), MODEL
    except Exception as e:  # the report must still ship
        sys.stderr.write("narrate: Claude call failed (%s: %s), using fallback text\n" % (type(e).__name__, e))
        return fallback(metrics), "fallback (%s)" % type(e).__name__


def fallback(m):
    t = m["totals"]
    prev = next((w for w in m["trend"] if w["week"] == "prior"), {})
    actions = []
    if t["followup_leads"] and t["followup_touched"] / t["followup_leads"] < 0.3:
        actions.append({"title": "Work the follow-up buckets",
                        "body": "Only **%d of %d** follow-up sellers got a call or text from a person. "
                                "These sellers already know us and are the cheapest appointments we can get."
                                % (t["followup_touched"], t["followup_leads"])})
    if m["real_misses"] or m["slow"]:
        actions.append({"title": "First call the same day",
                        "body": "%d new leads have no outbound call and %d waited over 40 hours. "
                                "Speed to first call decides whether a lead becomes an appointment."
                                % (len(m["real_misses"]), len(m["slow"]))})
    if t["no_outcome"]:
        actions.append({"title": "Record every appointment outcome the same day",
                        "body": "%d of %d completed appointments have no outcome, so the kept rate can't be measured."
                                % (t["no_outcome"], t["occurred"])})
    if m["intake"]["ppc"]["out_of_market"]:
        actions.append({"title": "Check PPC geo-targeting",
                        "body": "%d of %d PPC leads were out of market."
                                % (len(m["intake"]["ppc"]["out_of_market"]), m["intake"]["ppc"]["n"])})
    return {
        "standfirst": "%d appointments (%d kept), %d offers and %d new leads this week. "
                      "Last week: %s appointments and %s offers."
                      % (t["appointments"], t["kept"], t["offers"], t["new_leads"],
                         prev.get("appointments", "?"), prev.get("offers", "?")),
        "lead_title": "The week in numbers",
        "lead_body": ["The written commentary could not be generated this week, so this report "
                      "shows the numbers with rule-based notes only."],
        "callouts": [],
        "actions": actions[:4] or [{"title": "No automatic flags this week", "body": "Review the tables below."}],
    }
