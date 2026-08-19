// Proves the blast writes engagement back to every buyer who actually received
// a text — the data that makes "never contacted", "went quiet" and source ROI
// answerable, and that can only be captured at the moment of the send.
//
//   node writeback-test.js
const fs = require('fs');
const path = require('path');

const WF = path.join(__dirname, '..', '..', 'crm-transition', 'n8n-workflows',
                     '05-send-teaser-blast.cloud.json');
const wf = JSON.parse(fs.readFileSync(WF, 'utf8'));
const SRC = wf.nodes.find((n) => n.name === 'Build Engagement Updates').parameters.jsCode;

let fails = 0;
const ok = (c, m) => { console.log((c ? '  PASS  ' : '  FAIL  ') + m); if (!c) fails++; };

const F = {
  buy_last_contacted: 'f_lc', buy_last_deal: 'f_ld', buy_last_hook: 'f_hook',
  buy_deals_sent: 'f_sent', buy_first_contacted: 'f_first',
};
const defs = Object.keys(F).map((name) => ({ name, id: F[name] }));

// Two buyers got the text, one failed to send, one was never a recipient.
const RECIPIENTS = [
  { contactId: 'veteran', name: 'Carmen Delgado', teaser: 'Carmen, got another one in Liberty City. 2/1, new roof. Reply YES.',
    priorDealsSent: 7, priorFirstContacted: '2025-03-01T00:00:00.000Z' },
  { contactId: 'rookie', name: 'New Buyer', teaser: 'Hi, Buying Hero here. Off-market 2/1 in Miami-Dade. Reply STOP to opt out.',
    priorDealsSent: 0, priorFirstContacted: '' },
  { contactId: 'failed', name: 'Bad Number', teaser: 'whatever',
    priorDealsSent: 3, priorFirstContacted: '2025-01-01T00:00:00.000Z' },
];

const TALLY = {
  address: '2165 NW 58th St. Miami, FL 33142',
  sent_rows: [
    { contactId: 'veteran', name: 'Carmen Delgado' },
    { contactId: 'rookie', name: 'New Buyer' },
  ],
  failed_rows: [{ contactId: 'failed', name: 'Bad Number' }],
};

function run(tally, recips, fieldDefs) {
  const $ = (name) => ({
    first: () => ({ json: name === 'Fetch Field Definitions'
      ? { customFields: fieldDefs } : tally }),
    all: () => recips.map((r) => ({ json: r })),
  });
  return new Function('$', SRC)($);
}

const out = run(TALLY, RECIPIENTS, defs).map((o) => o.json);
const byId = {};
for (const o of out) byId[o.contactId] = o;
const val = (o, field) => {
  const hit = (o.body.customFields || []).find((c) => c.id === F[field]);
  return hit ? hit.value : undefined;
};

console.log('Engagement write-back after a blast:\n');
ok(out.length === 2, 'one update per buyer who actually received a text: ' + out.length);
ok(!byId.failed, 'a buyer whose send FAILED is not marked as contacted');

const v = byId.veteran, r = byId.rookie;
ok(val(v, 'buy_deals_sent') === 8, 'deals_sent increments from the prior value (7 -> ' + val(v, 'buy_deals_sent') + ')');
ok(val(r, 'buy_deals_sent') === 1, 'a first-time buyer goes to 1');

ok(val(v, 'buy_first_contacted') === undefined,
   'first_contacted is NOT rewritten for a buyer who already had one');
ok(typeof val(r, 'buy_first_contacted') === 'string' && val(r, 'buy_first_contacted').length > 0,
   'first_contacted IS set for a buyer who never had one');

ok(val(v, 'buy_last_deal') === TALLY.address, 'last_deal records this address');
const lc = val(v, 'buy_last_contacted');
ok(typeof lc === 'string' && Math.abs(Date.now() - Date.parse(lc)) < 60000,
   'last_contacted is now, as an ISO timestamp: ' + lc);

// The hook exists so the generator never reuses an opener on the same buyer.
const hook = val(v, 'buy_last_hook');
ok(hook === 'Carmen, got another one in Liberty City.',
   'last_hook captures the OPENER only, not the whole teaser: "' + hook + '"');
ok(val(r, 'buy_last_hook').length <= 240, 'hook is truncated to fit the field');

// ---------------------------------------------------------------- edge cases
console.log('\nEdge cases:\n');
const none = run({ address: 'x', sent_rows: [] }, RECIPIENTS, defs).map((o) => o.json);
ok(none.length === 1 && none[0]._skip === true, 'nothing sent -> a skip marker, not a crash');
ok(none[0].reason === 'nothing sent', 'skip marker says why: "' + none[0].reason + '"');

// If the field lookup fails the run must say so rather than PUT empty bodies.
const noDefs = run(TALLY, RECIPIENTS, []).map((o) => o.json);
ok(noDefs.length === 1 && noDefs[0]._skip === true, 'unresolvable field ids -> skip, never an empty write');
ok(noDefs[0].reason === 'no field ids resolved', 'and says which failure it was');

const orphan = run({ address: 'x', sent_rows: [{ contactId: 'ghost', name: 'Ghost' }] }, RECIPIENTS, defs)
  .map((o) => o.json);
ok(orphan.length === 1 && orphan[0].contactId === 'ghost',
   'a recipient with no matching row still gets last_contacted written');
ok(val(orphan[0], 'buy_deals_sent') === 1, 'and counts as their first deal rather than crashing');

// buy_last_hook must hold what the buyer READ, not the template. The field
// exists so the generator does not reuse an opener on someone — and
// "{{first_name}}, got another one for you." is the same string for every buyer
// alive, which makes it useless for that and confusing on the contact card.
console.log('\nThe hook we record is the hook they saw:\n');
const hookSrc = wf.nodes.find((n) => n.name === 'Build Engagement Updates').parameters.jsCode;
ok(/buy_last_hook', opener\(r\.smsBody \|\| r\.teaser\)\)/.test(hookSrc),
   'buy_last_hook is built from smsBody, the personalised text that was sent');
ok(hookSrc.indexOf("opener(r.teaser))") === -1,
   'and never from the raw teaser, which still carries the merge token');

console.log(fails === 0 ? '\nWRITE-BACK OK' : '\n' + fails + ' CHECK(S) FAILED');
process.exit(fails === 0 ? 0 : 1);
