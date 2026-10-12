// ─── Code by Zapier · JavaScript ────────────────────────────────────────────
// Parses a REsimpli webhook payload, keeps only Bolt Deals (PPC) leads, and
// emits flat fields for the Lead Performance sheet.
//
// Input Data:
//   raw          →  1. Raw Body   (Catch RAW Hook trigger)
//   sourceMatch  →  bolt          (plain text — the Bolt Deals identifier)
//
// Verified against a real REsimpli payload captured 2026-08-18 from the webhook
// log. Field names are Title Case With Spaces ("Phone Number"), NOT camelCase.
//
// PRIVACY: the raw payload contains staff emails/phones (Teams[]) and seller
// notes with personal detail (Notes[]). This step emits NEITHER. Nothing here
// should ever write the full payload to a sheet the PPC vendor can read.

const SOURCE_MATCH = String(inputData.sourceMatch || 'bolt').toLowerCase();

// Only consulted when the Qualified flag can't settle it. Real values observed
// are messy and user-defined (e.g. "☆ albert bucket"), so keep this loose.
const DEAD_STATUSES = [
  'dead', 'not interested', 'wrong number', 'unqualified', 'do not call',
  'dnc', 'spam', 'agent', 'retail', 'no longer selling',
];

let body;
try {
  body = JSON.parse(inputData.raw);
} catch (e) {
  body = {};
}

const norm = (s) => String(s == null ? '' : s).toLowerCase().replace(/[^a-z0-9]/g, '');

// Direct lookup: REsimpli keys are flat and Title Cased.
function get(...names) {
  const wanted = names.map(norm);
  for (const [k, v] of Object.entries(body)) {
    if (v === '' || v === null || v === undefined) continue;
    if (typeof v === 'object') continue;              // skip Teams/Notes/arrays
    if (wanted.includes(norm(k))) return String(v);
  }
  return '';
}

// Pull an answer out of the nested Lead Questions groups by matching question
// text. Answers are "N/A" or [] when unanswered — both treated as empty.
function answer(...fragments) {
  const groups = Array.isArray(body['Lead Questions']) ? body['Lead Questions'] : [];
  const frags = fragments.map(norm);
  for (const g of groups) {
    for (const q of (g && Array.isArray(g.Questions) ? g.Questions : [])) {
      const qn = norm(q.Question);
      if (!frags.some((f) => qn.includes(f))) continue;
      const a = Array.isArray(q.Answer) ? q.Answer.join(', ') : q.Answer;
      if (a && String(a).trim() && String(a).trim().toUpperCase() !== 'N/A') return String(a).trim();
    }
  }
  return '';
}

const leadSource = get('Lead Source');
const campaign   = get('Campaign Name');
const action     = get('Action');
const status     = get('Lead Status');
const deadReason = get('Dead Lead Reason');
const tags       = get('Tags');

// ── Bolt Deals detection ───────────────────────────────────────────────────
// Scoped to the attribution fields ONLY. A payload-wide scan would false-match
// on a seller note or a staff email that happens to contain the word.
const haystack = [leadSource, campaign, tags, get('Market Name')].join(' ').toLowerCase();
const isBoltDeals = haystack.includes(SOURCE_MATCH);

// ── Qualification ──────────────────────────────────────────────────────────
// "Qualified" is a native boolean REsimpli sends on every event.
//
// Caveat worth knowing: `false` is ambiguous. It means BOTH "not yet worked"
// and "explicitly marked not qualified" — a bare boolean cannot separate them.
// So false alone is never enough to call a lead Unqualified; that needs a dead
// reason or a dead status. Otherwise a lead that arrived ten minutes ago would
// be reported to the PPC vendor as a failed lead.
const qualifiedFlag = body['Qualified'];
const st = norm(status);
const isNewLead = norm(action).includes('newlead') || norm(action).includes('created');

let qualification;
let disqualifyReason = '';

if (qualifiedFlag === true) {
  qualification = 'Qualified';
} else if (deadReason) {
  qualification = 'Unqualified';
  disqualifyReason = deadReason;
} else if (!isNewLead && st && DEAD_STATUSES.map(norm).some((d) => st.includes(d))) {
  qualification = 'Unqualified';
  disqualifyReason = status;
} else {
  qualification = 'Pending';
}

const now = new Date().toISOString();

output = {
  receivedAt: now,
  lastUpdated: now,
  leadId: get('Property Id') || get('Lead Id', 'id') || 'no-id-' + Date.now(),
  eventType: action || 'unknown',
  firstName: get('firstName', 'First Name'),
  lastName: get('lastName', 'Last Name'),
  phone: get('Phone Number'),
  email: get('Email Address'),
  propertyAddress: [get('Property Street Address'), get('Property Street Address 2')]
    .filter(Boolean).join(' ').trim(),
  city: get('Property City').trim(),
  state: get('Property State'),
  zip: get('Property Zip'),
  leadSource,
  campaign,
  trackingNumber: get('Tracking Number', 'Dialed Number'),
  qualification,
  disqualifyReason,
  status,
  timelineToSell: answer('when would you like to sell', 'what kind of timeline'),
  motivation: answer('main reason you', 'reason for selling'),
  propertyCondition: answer('how would you rate the overall condition',
                            'current condition of the property'),
  leadCreatedDate: get('Lead Created Date'),
  // Control field for the Filter step — not a sheet column
  isBoltDeals: isBoltDeals ? 'yes' : 'no',
  // Diagnostic: top-level scalar keys only. Deliberately excludes Teams, Notes,
  // and Lead Questions so staff and seller PII never reaches the output.
  scalarKeys: Object.entries(body)
    .filter(([, v]) => typeof v !== 'object')
    .map(([k]) => k).join(', '),
};
