"""Render the metrics + narrative into the report page and a short email body.

Same visual family as the hand-built weekly reports (IBM Plex, ledger green),
light theme only because the page's job is to become a PDF.
"""
import html
import re

CSS = """
:root{--paper:#F3F5F2;--surface:#FFFFFF;--surface-2:#EDF1EE;--ink:#141A18;--ink-2:#57635D;--ink-3:#7C8781;
--rule:#D3DBD6;--rule-2:#E3E9E5;--accent:#1C5C4A;--bar:#2E7D68;--bar-soft:#BFDCD1;--warn:#8A5410;
--warn-bg:#FAF1E2;--warn-line:#C98A2E;--bad:#8E2A20;--bad-bg:#FAECEA;--good:#1C5C4A}
*{box-sizing:border-box}
html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{margin:0;background:var(--paper);color:var(--ink);font-family:"IBM Plex Sans",-apple-system,"Segoe UI",sans-serif;
font-size:13.5px;line-height:1.55;-webkit-font-smoothing:antialiased}
.wrap{max-width:900px;margin:0 auto;padding-inline:28px;padding-block:0 40px}
header.top{border-bottom:1px solid var(--rule);padding-block:30px 22px;margin-bottom:22px}
.eyebrow{font-family:"IBM Plex Mono",monospace;font-size:10.5px;font-weight:500;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-3);margin:0 0 10px}
h1{font-family:"IBM Plex Serif",Georgia,serif;font-weight:700;font-size:34px;line-height:1.1;letter-spacing:-.018em;margin:0 0 10px}
.standfirst{font-size:15px;line-height:1.55;color:var(--ink-2);max-width:66ch;margin:0}
h2{font-family:"IBM Plex Serif",Georgia,serif;font-weight:600;font-size:20px;line-height:1.2;letter-spacing:-.012em;margin:0 0 6px;text-wrap:balance}
h3.sub{font-family:"IBM Plex Serif",Georgia,serif;font-weight:600;font-size:15.5px;margin:20px 0 4px}
section{padding-block:22px;border-top:1px solid var(--rule-2)}
section:first-of-type{border-top:none;padding-top:0}
.kicker{font-family:"IBM Plex Mono",monospace;font-size:10.5px;font-weight:500;letter-spacing:.13em;text-transform:uppercase;color:var(--accent);margin:0 0 8px}
p{margin:0 0 12px;max-width:70ch}
strong{font-weight:600}
.num{font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums;font-weight:500}
.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:1px;background:var(--rule);border:1px solid var(--rule);margin:20px 0 0}
.stat{background:var(--surface);padding:12px 14px}
.stat .lab{font-family:"IBM Plex Mono",monospace;font-size:9.5px;letter-spacing:.11em;text-transform:uppercase;color:var(--ink-3);margin-bottom:5px}
.stat .val{font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums;font-size:24px;font-weight:600;line-height:1.05;letter-spacing:-.02em}
.stat .val small{font-size:14px}
.stat .sub{font-size:11px;color:var(--ink-2);margin-top:3px}
.stat.flag{background:var(--warn-bg)}.stat.flag .val{color:var(--warn)}
.stat.bad{background:var(--bad-bg)}.stat.bad .val{color:var(--bad)}
.stat.good .val{color:var(--good)}
.tbl{margin:14px 0 8px;border:1px solid var(--rule);background:var(--surface)}
table{border-collapse:collapse;width:100%;font-size:12.5px}
th,td{padding:7px 10px;text-align:left;border-bottom:1px solid var(--rule-2);vertical-align:top}
thead th{background:var(--surface-2);font-family:"IBM Plex Mono",monospace;font-size:9.5px;font-weight:600;letter-spacing:.07em;text-transform:uppercase;color:var(--ink-2);border-bottom:1px solid var(--rule)}
td.n,th.n{text-align:right;font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums;white-space:nowrap}
tbody tr:last-child td{border-bottom:none}
tr{break-inside:avoid}
tr.total td{font-weight:600;background:var(--surface-2);border-top:1px solid var(--rule)}
td.name{font-weight:500;white-space:nowrap}
.dim{color:var(--ink-3)}
.up{color:var(--good);font-weight:600}.down{color:var(--bad);font-weight:600}.wn{color:var(--warn);font-weight:600}
.pill{display:inline-block;font-family:"IBM Plex Mono",monospace;font-size:9.5px;font-weight:600;letter-spacing:.04em;padding:1px 6px;border-radius:2px;border:1px solid currentColor;white-space:nowrap}
.pill.kept{color:var(--good)}.pill.canc{color:var(--bad)}.pill.blank{color:var(--warn)}
.barcell{display:flex;align-items:center;gap:8px}
.bar{height:8px;background:var(--bar);border-radius:1px}
.bar.in{background:var(--bar-soft);border:1px solid var(--bar)}
.note{border-left:3px solid var(--accent);background:var(--surface);padding:12px 15px;margin:14px 0;break-inside:avoid}
.note.warn{border-left-color:var(--warn-line);background:var(--warn-bg)}
.note.bad{border-left-color:var(--bad);background:var(--bad-bg)}
.note h4{margin:0 0 5px;font-size:13.5px;font-weight:600}
.note p{margin:0;font-size:13px}
ol.actions{counter-reset:a;list-style:none;padding:0;margin:14px 0 0}
ol.actions li{counter-increment:a;position:relative;padding:0 0 12px 36px;border-bottom:1px solid var(--rule-2);margin-bottom:12px;break-inside:avoid}
ol.actions li:last-child{border-bottom:none;margin-bottom:0;padding-bottom:0}
ol.actions li::before{content:counter(a,decimal-leading-zero);position:absolute;left:0;top:1px;font-family:"IBM Plex Mono",monospace;font-size:11.5px;font-weight:600;color:var(--accent)}
ol.actions h3{margin:0 0 3px;font-size:14px;font-weight:600}
ol.actions p{margin:0;font-size:13px;color:var(--ink-2)}
ul.plain{margin:6px 0 12px;padding-left:18px}ul.plain li{margin-bottom:4px}
footer{border-top:1px solid var(--rule);margin-top:26px;padding-top:16px;font-size:11px;color:var(--ink-3)}
footer p{max-width:80ch;margin:0 0 7px}
@page{size:Letter;margin:0.45in 0.3in}
"""

FONTS = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600'
         '&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@500;600;700&display=swap">')


def e(s):
    return html.escape(str(s if s is not None else ""))


def md(s):
    """Escape, then allow **bold** only."""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", e(s))


def pct(a, b):
    return "%d%%" % round(100 * a / b) if b else "–"


def table(head, rows, total=None, numeric=()):
    th = "".join('<th class="n">%s</th>' % h if i in numeric else "<th>%s</th>" % h for i, h in enumerate(head))
    def tr(r, cls=""):
        tds = []
        for i, c in enumerate(r):
            klass = "n" if i in numeric else ("name" if i == 0 else "")
            tds.append('<td class="%s">%s</td>' % (klass, c))
        return '<tr class="%s">%s</tr>' % (cls, "".join(tds))
    body = "".join(tr(r) for r in rows) + (tr(total, "total") if total else "")
    return '<div class="tbl"><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>' % (th, body)


def callouts(narr, section):
    out = []
    for c in narr.get("callouts", []):
        if c.get("section") == section:
            tone = {"good": "", "warn": " warn", "bad": " bad"}.get(c.get("tone"), "")
            out.append('<div class="note%s"><h4>%s</h4><p>%s</p></div>' % (tone, e(c["title"]), md(c["body"])))
    return "".join(out)


def outcome_pill(o):
    cls = {"Kept": "kept", "Cancelled": "canc", "No Show": "canc"}.get(o, "blank")
    return '<span class="pill %s">%s</span>' % (cls, e(o.upper()))


def page(m, narr, author):
    t = m["totals"]
    trend = {w["week"]: w for w in m["trend"]}
    prev = trend.get("prior", {})
    fu_pct = t["followup_touched"] / t["followup_leads"] if t["followup_leads"] else 1

    def tile(lab, val, sub, cls=""):
        return '<div class="stat %s"><div class="lab">%s</div><div class="val">%s</div><div class="sub">%s</div></div>' % (cls, lab, val, sub)

    tiles = "".join([
        tile("Appointments", t["appointments"], "%s last week" % prev.get("appointments", "–"),
             "bad" if prev.get("appointments") and t["appointments"] < prev["appointments"] / 2 else ""),
        tile("Kept", t["kept"], "%d with no outcome" % t["no_outcome"] if t["no_outcome"] else "all recorded",
             "good" if t["kept"] else "flag"),
        tile("Offers made", t["offers"], "%s last week" % prev.get("offers", "–"),
             "flag" if prev.get("offers") and t["offers"] < prev["offers"] else "good"),
        tile("New leads", t["new_leads"], " · ".join(str(trend[k]["new_leads"]) for k in ("prior-2", "prior") if k in trend) + " prior weeks",
             "good"),
        tile("Follow-up touched", "%d<small>/%d</small>" % (t["followup_touched"], t["followup_leads"]),
             "%s of the buckets" % pct(t["followup_touched"], t["followup_leads"]),
             "bad" if fu_pct < 0.2 else ("flag" if fu_pct < 0.5 else "good")),
    ])

    # --- headline / trend
    trend_rows = []
    for w in m["trend"]:
        dash = '<span class="dim">–</span>'
        trend_rows.append([e(w["label"]), w["new_leads"], w["appointments"],
                           dash if w["kept"] is None else w["kept"], dash if w["offers"] is None else w["offers"]])
    trend_tbl = table(["Week", "New leads", "Appointments", "Kept", "Offers"], trend_rows, numeric=(1, 2, 3, 4))
    created_days = ", ".join("%s %d" % d for d in t["appointments_created_days"]) or "none"
    lead = "".join("<p>%s</p>" % md(p) for p in narr.get("lead_body", []))

    # --- appointments
    appt_rows = []
    for a in m["appointments"]:
        nxt = ("%s: %s" % (a["next"]["day"], a["next"]["to"])) if a["next"] else "No status change logged"
        appt_rows.append([e(a["when"]), "%s<br><span class='dim'>%s · %s</span>" % (e(a["title"]), e(a["lead"]["short"] or "no address"), e(a["lead"]["market"])),
                          '<span class="wn">Blank</span>' if a["format"] == "Not set" else e(a["format"]),
                          outcome_pill(a["outcome"]) if a["occurred"] else '<span class="dim">Upcoming</span>',
                          a["calls"], '<span class="dim">%s</span>' % e(nxt)])
    appt_tbl = table(["When", "Seller · property", "Format", "Outcome", "Calls", "What happened next"],
                     appt_rows, numeric=(4,)) if appt_rows else "<p class='dim'>No appointments this week.</p>"
    fmt_rows = []
    for f in ("Phone", "In person", "Not set"):
        v = m["formats"].get(f)
        if v:
            fmt_rows.append([e(f), v.get("booked", 0), v.get("Kept", 0), v.get("Cancelled", 0) + v.get("No Show", 0), v.get("No outcome", 0)])
    fmt_tbl = table(["Format", "Booked", "Kept", "Cancelled / no-show", "No outcome"], fmt_rows,
                    total=["Total", t["appointments"], t["kept"], t["cancelled"] + t["no_show"], t["no_outcome"]],
                    numeric=(1, 2, 3, 4)) if fmt_rows else ""

    # --- offers
    off_rows = [[e(o["when"]), e(o["address"] or "no address"), e(o["by"]), e(o["source"]),
                 e(o["market"]) if o["in_market"] else '<span class="wn">%s</span>' % (
                     "Likely mailing address" if o.get("likely_mailing_address") else e(o["market"])),
                 "Yes" if o["from_appointment"] else "No"] for o in m["offers"]]
    off_tbl = table(["When", "Property", "By", "Source", "Market", "From an appt"], off_rows) if off_rows else "<p class='dim'>No offers logged this week.</p>"

    # --- hygiene
    hy_rows = []
    for h in m["hygiene"]:
        cnt = "%d of %d" % (h["n"], h["of"]) if h["of"] is not None else str(h["n"])
        cls = "up" if h["n"] == 0 else ("down" if h["of"] and h["n"] / max(h["of"], 1) >= 0.4 else "wn")
        hy_rows.append([e(h["gap"]), '<span class="%s">%s</span>' % (cls, cnt), '<span class="dim">%s</span>' % e(h["detail"]),
                        '<span class="dim">%s</span>' % e(h["hides"])])
    hy_tbl = table(["Gap", "Count", "Detail", "What it hides"], hy_rows, numeric=(1,))

    # --- intake
    src_rows = [[e(s["source"]), s["n"], '<span class="dim">%s</span>' % e(" · ".join("%s %d" % x for x in s["statuses"]))]
                for s in m["intake"]["by_source"]]
    src_tbl = table(["Source", "Leads", "Where they are now"], src_rows, total=["Total", t["new_leads"], ""], numeric=(1,))
    method = ", ".join("%d by %s" % (n, k) for k, n in m["intake"]["method"])
    ppc = m["intake"]["ppc"]
    ppc_line = ""
    if ppc["n"]:
        ppc_line = "<p><strong>PPC:</strong> %d leads, %d out of market%s, %d with an address we can't place.</p>" % (
            ppc["n"], len(ppc["out_of_market"]),
            (" (%s)" % "; ".join(e(r["short"]) for r in ppc["out_of_market"])) if ppc["out_of_market"] else "",
            len(ppc["unknown"]))
    speed_rows = [[e(s["label"]), s["n"], '<span class="dim">%s</span>' % e(", ".join(("%s ×%d" % w) if w[1] > 1 else w[0] for w in s["who"]))]
                  for s in m["speed"]]
    speed_tbl = table(["First outbound call", "Leads", "Who"], speed_rows, numeric=(1,))
    reasons = {}
    for r in m["no_call"]:
        if r["reason"]:
            reasons[r["reason"].split(" (")[0]] = reasons.get(r["reason"].split(" (")[0], 0) + 1
    miss_html = ""
    if m["no_call"]:
        miss_html = "<p>Of the %d with no outbound call: %s.</p>" % (
            len(m["no_call"]), "; ".join("%d %s" % (n, k.lower()) for k, n in reasons.items()) or "none have an obvious reason")
    if m["real_misses"]:
        miss_html += "<p><strong>Real misses</strong> (in market or unplaceable, still at New Leads, no call):</p><ul class='plain'>%s</ul>" % "".join(
            "<li>%s &middot; %s &middot; came in %s &middot; seller called in %d time%s</li>" % (
                e(r["short"] or "no address"), e(r["source"]), e(r["created"]), r["inbound_calls"], "" if r["inbound_calls"] == 1 else "s")
            for r in m["real_misses"])
    if m["slow"]:
        miss_html += "<p><strong>Waited over 40 hours for a first call:</strong></p><ul class='plain'>%s</ul>" % "".join(
            "<li>%s &middot; %s hours &middot; seller called in %d time%s &middot; now %s</li>" % (
                e(r["short"] or "no address"), r["first_call_hours"], r["inbound_calls"], "" if r["inbound_calls"] == 1 else "s", e(r["status"]))
            for r in m["slow"])

    # --- follow-up
    fu_rows = [[e(f["bucket"]), f["leads"], f["touched"],
                '<span class="%s">%s</span>' % ("down" if f["leads"] and f["touched"] / f["leads"] < 0.25 else "up", pct(f["touched"], f["leads"]))]
               for f in m["followup"]]
    fu_tbl = table(["Bucket", "Leads", "Called or texted by a person", "Coverage"], fu_rows,
                   total=["Total", t["followup_leads"], t["followup_touched"], pct(t["followup_touched"], t["followup_leads"])],
                   numeric=(1, 2, 3))

    # --- actions
    acts = "".join("<li><h3>%s</h3><p>%s</p></li>" % (e(a["title"]), md(a["body"])) for a in narr.get("actions", []))

    # --- calls appendix
    c = m["calls"]
    prev_by = c.get("prev_out_by_person", {})
    names = [p["name"] for p in c["people"]] + [n for n in prev_by if n not in {p["name"] for p in c["people"]}]
    pmap = {p["name"]: p for p in c["people"]}
    ppl_rows = []
    for n in names:
        p = pmap.get(n, {"out": 0, "leads": 0, "in": 0, "sms": 0, "auto_sms": 0})
        last = prev_by.get(n, 0)
        chg = ""
        if last and p["out"] < last * 0.5:
            chg = ' <span class="down">(%d last wk)</span>' % last
        elif last:
            chg = ' <span class="dim">(%d)</span>' % last
        ppl_rows.append([e(n), "%d%s" % (p["out"], chg), p["leads"], p["in"],
                         "%d%s" % (p["sms"], (" + %d auto" % p["auto_sms"]) if p["auto_sms"] else "")])
    ppl_rows.append(['<span class="dim">No rep attached</span>', "–", "–", c["unrouted_in"], "–"])
    ppl_tbl = table(["Person", "Outbound calls (last week)", "Sellers called", "Inbound taken", "Texts sent"], ppl_rows,
                    total=["Total", "%d (%d)" % (c["outbound"], c["prev_outbound"]), "–", c["inbound"], "–"],
                    numeric=(1, 2, 3, 4))
    mx = max([max(v["out"], v["in"]) for v in c["days"].values()] + [1])
    day_rows = []
    for d, v in c["days"].items():
        cell = lambda n, cls: '<div class="barcell">%s<span class="num">%d</span></div>' % (
            '<div class="bar%s" style="width:%dpx"></div>' % (cls, max(2, round(120 * n / mx))) if n else "", n)
        day_rows.append([d, cell(v["out"], ""), cell(v["in"], " in")])
    day_tbl = table(["Day", "Outbound", "Inbound"], day_rows)
    lm_rows = [
        ["Inbound calls answered", "%d of %d" % (c["inbound"] - c["inbound_missed"], c["inbound"]),
         "%d missed (%s): %s" % (c["inbound_missed"], pct(c["inbound_missed"], c["inbound"]), ", ".join("%s %d" % x for x in c["inbound_missed_breakdown"]))],
        ["Outbound call outcomes", c["outbound"], " · ".join("%s %d" % x for x in c["outcomes"])],
        ["Texts received", c["sms_in"], ""],
        ["Status moves", sum(n for _, n in m["status_moves"]), " · ".join("%s %d" % x for x in m["status_moves"])],
        ["Live leads with any activity", c["leads_touched"], "%d logged activities" % c["activities"]],
        ["Appointments booked this week", t["appointments_created"], "by day: %s" % created_days],
        ["Appointments on the calendar after this week", t["upcoming_appointments"], ""],
    ]
    lm_tbl = table(["Metric", "This week", "Detail"], [[e(a), e(b), '<span class="dim">%s</span>' % e(d)] for a, b, d in lm_rows], numeric=(1,))

    w = m["week"]
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Acquisitions Report %(label)s</title>%(fonts)s<style>%(css)s</style></head><body><div class="wrap">
<header class="top">
  <p class="eyebrow">Buying Hero &middot; Acquisitions &middot; Week of %(start)s &ndash; %(end)s</p>
  <h1>Acquisitions Report</h1>
  <p class="standfirst">%(standfirst)s</p>
  <div class="stats">%(tiles)s</div>
</header>
<section><p class="kicker">The headline</p><h2>%(lead_title)s</h2>%(trend)s%(lead)s</section>
<section><p class="kicker">Appointments</p><h2>%(n_appt)d appointments, %(kept)d kept, %(noout)d not recorded</h2>%(appt)s%(fmt)s%(c_appt)s</section>
<section><p class="kicker">Offers</p><h2>%(n_off)d offer%(off_s)s made</h2>%(off)s%(c_off)s</section>
<section><p class="kicker">Data hygiene</p><h2>The gaps, in one table</h2><p>Each row hides a different number. None takes more than a minute per record to fix.</p>%(hy)s%(c_hy)s</section>
<section><p class="kicker">Lead intake</p><h2>%(n_new)d new leads</h2>%(src)s<p><strong>How they came in:</strong> %(method)s.</p>%(ppc)s
<h3 class="sub">Speed to first call</h3><p class="dim">First outbound call after the lead was created. Automated texts don&rsquo;t count.</p>%(speed)s%(miss)s%(c_in)s</section>
<section><p class="kicker">Follow-up pipeline</p><h2>%(fu_n)d sellers in follow-up, %(fu_t)d got a human touch</h2>%(fu)s
<p class="dim">Texts and drips sent from Jorge&rsquo;s account count as automated, so they don&rsquo;t count as a touch.</p>%(c_fu)s</section>
<section><p class="kicker">For the review</p><h2>Where to focus this week</h2><ol class="actions">%(acts)s</ol></section>
<section><p class="kicker">Appendix</p><h2>Calls and lead-management metrics</h2>%(ppl)s%(days)s%(lm)s%(c_calls)s</section>
<footer>
<p><strong>Source.</strong> REsimpli Open API, generated %(gen)s. %(scope)s Calls to numbers not attached to a lead are not counted. Activity from REsimpli&rsquo;s two activity streams is deduplicated.</p>
<p><strong>Outcome labels</strong> (Kept / Cancelled / No outcome) come from a bare integer in REsimpli with no lookup. If a label looks wrong, the mapping needs fixing, not the counts. Appointment records stay editable, so numbers can change if outcomes are filled in later.</p>
<p>Commentary written by %(author)s from the numbers above; every table is computed directly from REsimpli. Buying Hero &middot; internal.</p>
</footer></div></body></html>""" % {
        "label": e(w["label"]), "fonts": FONTS, "css": CSS, "start": e(w["start"]), "end": e(w["end"]),
        "standfirst": md(narr.get("standfirst")), "tiles": tiles, "lead_title": e(narr.get("lead_title")),
        "trend": trend_tbl, "lead": lead + callouts(narr, "headline"),
        "n_appt": t["appointments"], "kept": t["kept"], "noout": t["no_outcome"], "appt": appt_tbl, "fmt": fmt_tbl,
        "c_appt": callouts(narr, "appointments"), "n_off": t["offers"], "off_s": "" if t["offers"] == 1 else "s",
        "off": off_tbl, "c_off": callouts(narr, "offers"), "hy": hy_tbl, "c_hy": callouts(narr, "hygiene"),
        "n_new": t["new_leads"], "src": src_tbl, "method": e(method), "ppc": ppc_line, "speed": speed_tbl,
        "miss": miss_html, "c_in": callouts(narr, "intake"), "fu_n": t["followup_leads"], "fu_t": t["followup_touched"],
        "fu": fu_tbl, "c_fu": callouts(narr, "followup"), "acts": acts, "ppl": ppl_tbl, "days": day_tbl, "lm": lm_tbl,
        "c_calls": callouts(narr, "calls"), "gen": e(m["generated"]), "scope": e(m["scope_note"]),
        "author": "Claude" if author.startswith("claude") else "rule-based fallback (%s)" % e(author),
    }


def email_body(m, narr):
    """Short inline-styled summary; the full report is the attached PDF."""
    t = m["totals"]
    s = "font-family:Arial,sans-serif;color:#141A18;font-size:14px;line-height:1.5"
    acts = "".join('<li style="margin-bottom:8px"><strong>%s</strong><br>%s</li>' % (e(a["title"]), md(a["body"]))
                   for a in narr.get("actions", []))
    return """<div style="%s;max-width:640px">
<p style="font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:#7C8781;margin:0 0 6px">Buying Hero &middot; Weekly acquisitions report</p>
<h2 style="font-family:Georgia,serif;margin:0 0 10px">%s</h2>
<p style="color:#57635D">%s</p>
<table style="border-collapse:collapse;margin:12px 0;font-size:13px">
<tr><td style="padding:3px 14px 3px 0">Appointments</td><td><strong>%d</strong> (%d kept, %d no outcome)</td></tr>
<tr><td style="padding:3px 14px 3px 0">Offers made</td><td><strong>%d</strong></td></tr>
<tr><td style="padding:3px 14px 3px 0">New leads</td><td><strong>%d</strong></td></tr>
<tr><td style="padding:3px 14px 3px 0">Follow-up touched</td><td><strong>%d of %d</strong></td></tr></table>
<p style="margin:16px 0 6px"><strong>Where to focus</strong></p><ol style="padding-left:20px;margin:0">%s</ol>
<p style="color:#7C8781;font-size:12px;margin-top:18px">Full report attached as a PDF. Forward it to the team as-is.</p></div>""" % (
        s, e(m["week"]["label"]), md(narr.get("standfirst")), t["appointments"], t["kept"], t["no_outcome"],
        t["offers"], t["new_leads"], t["followup_touched"], t["followup_leads"], acts)
