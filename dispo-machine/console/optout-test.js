// Opt-out suppression, across every layer that has to hold.
//
//   node optout-test.js
//
// Three independent guards, and they are independent on purpose:
//   1. GHL sets contact.dnd itself when a carrier-level STOP arrives
//   2. our reply handler sets buy_status = DNC before any AI runs
//   3. both exclusion engines refuse to text either signal
// Any one of them failing must not be enough to text someone who opted out.
const fs = require('fs');
const path = require('path');

const DIR = path.join(__dirname, '..', '..', 'crm-transition', 'n8n-workflows');
const node = (f, n) => JSON.parse(fs.readFileSync(path.join(DIR, f), 'utf8'))
  .nodes.find((x) => x.name === n).parameters.jsCode;

let fails = 0;
const ok = (c, m) => { console.log((c ? '  PASS  ' : '  FAIL  ') + m); if (!c) fails++; };

// --------------------------------------- both engines agree on who is silenced
console.log('Both engines refuse the same people:\n');
const engines = {
  'W1 intake (the review count)': node('03-dispo-intake.cloud.json', 'Exclusion Engine'),
  'W2 send (the actual text)':    node('05-send-teaser-blast.cloud.json', 'Build Recipient List'),
};
for (const label of Object.keys(engines)) {
  const src = engines[label];
  ok(/status === 'dnc' \|\| status === 'blacklist'/.test(src),
     label + ' — buy_status DNC/Blacklist is refused');
  // W1 originally did NOT check dnd. The review page counted a buyer the send
  // would drop, so the number a dispo manager approved was not the number sent.
  ok(/c\.dnd === true/.test(src), label + ' — GHL contact DND is refused');
}

// ------------------------------------------- the reply handler, before any AI
console.log('\nThe reply handler, before Claude is consulted:\n');
const norm = node('07-buyer-reply-handler.cloud.json', 'Normalize Reply');
const decide = node('07-buyer-reply-handler.cloud.json', 'Decide Action');
const normalize = (msg) => new Function('$input', norm)(
  { first: () => ({ json: { body: { contactId: 'c1', message: msg,
                                    direction: 'inbound', type: 'SMS' } } }) })[0].json;

for (const word of ['STOP', 'stop', 'Stop.', 'STOPALL', 'unsubscribe', 'quit',
                    'cancel', 'end', 'remove me', 'take me off', 'do not contact']) {
  ok(normalize(word).optOut === true, 'recognised: "' + word + '"');
}
ok(normalize('stop by the house tomorrow').optOut === false,
   '"stop by the house tomorrow" is NOT an opt-out — a real reply is not thrown away');

const IDS = { buy_replies: 'f_rep', buy_last_responded: 'f_lr', buy_status: 'f_status',
              buy_consent_status: 'f_consent', buy_objection_last: 'f_obj' };
const decided = new Function('$', '$input', decide)(
  () => ({ first: () => ({ json: { contactId: 'c1', text: 'STOP', optOut: true,
    investorLift: false, priorReplies: 2, fieldIds: IDS, dealOppId: 'o1',
    address: 'A', ambiguous: false, openAtReachedOut: 1,
    infoSentStageId: 's', pipelineId: 'p' } }) }),
  { first: () => ({ json: {} }) })[0].json;
const cf = (f) => (decided.contactBody.customFields || []).find((c) => c.id === IDS[f]);

ok(decided.send === false, 'an opt-out never sends a reply of any kind');
ok(cf('buy_status').value === 'DNC', 'buy_status is set to DNC');
ok(cf('buy_consent_status').value === 'Opted Out', 'and the consent record says Opted Out');
ok(decided.needsHuman === false, 'it needs no human — it is fully handled');
ok(decided.moveStageId === null, 'and the opportunity is not advanced');

// The decision must not depend on the model being available or correct.
ok(/const optOut = p\.optOut \|\| ai\.intent === 'opt_out'/.test(decide),
   'opt-out is decided on the raw text first, with the model only able to ADD to it');

console.log(fails === 0 ? '\nOPT-OUT OK' : '\n' + fails + ' CHECK(S) FAILED');
process.exit(fails === 0 ? 0 : 1);
