// Exercises the buyer reply handler's decision logic — the only workflow that
// sends a text to a real person without anyone clicking anything.
//
//   node reply-handler-test.js
//
// The two code nodes that decide everything (Normalize Reply, Decide Action)
// are extracted from the workflow JSON, so this cannot drift from what runs.
const fs = require('fs');
const path = require('path');

const WF = path.join(__dirname, '..', '..', 'crm-transition', 'n8n-workflows',
                     '07-buyer-reply-handler.cloud.json');
const wf = JSON.parse(fs.readFileSync(WF, 'utf8'));
const src = (n) => wf.nodes.find((x) => x.name === n).parameters.jsCode;
const NORMALIZE = src('Normalize Reply');
const DECIDE = src('Decide Action');

let fails = 0;
const ok = (c, m) => { console.log((c ? '  PASS  ' : '  FAIL  ') + m); if (!c) fails++; };

function normalize(payload) {
  const $input = { first: () => ({ json: payload }) };
  return new Function('$input', NORMALIZE)($input)[0].json;
}

const IDS = {
  buy_replies: 'f_rep', buy_last_responded: 'f_lr', buy_status: 'f_status',
  buy_consent_status: 'f_consent', buy_objection_last: 'f_obj',
};

function decide(ctx, aiJson) {
  const prep = Object.assign({
    contactId: 'c1', text: 'x', optOut: false, investorLift: false, priorReplies: 3,
    fieldIds: IDS, dealOppId: 'opp1', address: '2165 NW 58th St', ambiguous: false,
    openAtReachedOut: 1, infoSentStageId: 'stage_info', pipelineId: 'pipe1',
  }, ctx);
  const $ = (name) => ({
    first: () => ({ json: name === 'Prepare Reply Context' ? prep : {} }),
  });
  const $input = { first: () => ({ json: aiJson
    ? { content: [{ type: 'text', text: JSON.stringify(aiJson) }] } : {} }) };
  return new Function('$', '$input', DECIDE)($, $input)[0].json;
}
const cfVal = (d, field) => {
  const hit = (d.contactBody.customFields || []).find((c) => c.id === IDS[field]);
  return hit ? hit.value : undefined;
};

// ============================================================ opt-out first
console.log('Opt-out — deterministic, before any AI:\n');
for (const word of ['STOP', 'stop', 'Stop.', 'UNSUBSCRIBE', 'remove me',
                    'take me off', 'quit', 'opt out', 'do not contact']) {
  const n = normalize({ body: { contactId: 'c1', message: word, direction: 'inbound', type: 'SMS' } });
  ok(n.optOut === true, 'recognised as opt-out: "' + word + '"');
}
const notStop = normalize({ body: { contactId: 'c1', message: 'stop by tomorrow and see it', direction: 'inbound', type: 'SMS' } });
ok(notStop.optOut === false, '"stop by tomorrow and see it" is NOT an opt-out');

const sup = decide({ optOut: true }, null);
ok(sup.send === false, 'an opt-out never sends anything');
ok(cfVal(sup, 'buy_status') === 'DNC', 'opt-out sets buy_status = DNC');
ok(cfVal(sup, 'buy_consent_status') === 'Opted Out', 'consent record stays factual: Opted Out');
ok(cfVal(sup, 'buy_replies') === 4, 'the opt-out still counts as a reply (3 -> 4)');
ok(sup.needsHuman === false, 'an opt-out does not need a human — it is fully handled');

// ================================================== what must be ignored
console.log('\nMessages the handler must ignore:\n');
ok(normalize({ body: { contactId: 'c1', message: 'hi', direction: 'outbound', type: 'SMS' } }).actionable === false,
   'our own outbound is ignored — no talking to itself');
ok(normalize({ body: { contactId: 'c1', message: 'hi', direction: 'inbound', type: 'Email' } }).actionable === false,
   'email is ignored');
ok(normalize({ body: { message: 'hi', direction: 'inbound' } }).actionable === false,
   'a payload with no contactId is ignored');
ok(normalize({ body: { contactId: 'c1', message: '  ', direction: 'inbound' } }).actionable === false,
   'an empty body is ignored');
ok(normalize({ body: { contactId: 'c1', message: 'yes', direction: 'inbound' } }).actionable === true,
   'a real inbound SMS with no explicit type is still handled');

// ======================================================== the send gates
console.log('\nEvery gate that must pass before a text goes out:\n');
const YES = { intent: 'interested', confidence: 'high', objection: '', reason: 'asked for the address' };

ok(decide({}, YES).send === true, 'clear interest from a normal buyer sends');
ok(decide({}, YES).moveStageId === 'stage_info', 'and moves the opportunity to Info Sent');
ok(cfVal(decide({}, YES), 'buy_replies') === 4, 'and records the reply');

ok(decide({ investorLift: true }, YES).send === false,
   'an INVESTORLIFT buyer never auto-sends, even saying yes outright');
ok(decide({ investorLift: true }, YES).blockedBy.indexOf('notInvestorLift') !== -1,
   'and the reason is on the record: ' + JSON.stringify(decide({ investorLift: true }, YES).blockedBy));
ok(decide({ investorLift: true }, YES).needsHuman === true, 'it is routed to a human instead');

ok(decide({}, { intent: 'interested', confidence: 'low', objection: '', reason: '' }).send === false,
   'low confidence holds rather than guessing');
ok(decide({}, { intent: 'unclear', confidence: 'high', objection: '', reason: '' }).send === false,
   'unclear holds');
ok(decide({}, { intent: 'not_interested', confidence: 'high', objection: 'too small', reason: '' }).send === false,
   'a decline never gets the package');
ok(decide({ dealOppId: null }, YES).send === false,
   'no open deal at Reached Out means nothing to send');
ok(decide({ address: '' }, YES).send === false, 'no address means nothing to send');

// A Claude failure must never be read as consent to text someone.
const broken = decide({}, null);
ok(broken.send === false, 'a Claude failure holds the message rather than sending');
ok(broken.aiError !== null, 'and the error is reported: ' + String(broken.aiError).slice(0, 40));
ok(cfVal(broken, 'buy_replies') === 4, 'the reply is still recorded even when Claude fails');

// ==================================================== recording behaviour
console.log('\nWhat gets written back:\n');
const obj = decide({}, { intent: 'not_interested', confidence: 'high',
                         objection: 'only buys in Broward', reason: 'said wrong county' });
ok(cfVal(obj, 'buy_objection_last') === 'only buys in Broward',
   'the objection is captured for later analysis: "' + cfVal(obj, 'buy_objection_last') + '"');
ok(typeof cfVal(obj, 'buy_last_responded') === 'string', 'buy_last_responded is stamped');
ok(cfVal(decide({ priorReplies: 0 }, YES), 'buy_replies') === 1, 'a first reply counts as 1');

const amb = decide({ ambiguous: true, openAtReachedOut: 2 }, YES);
ok(amb.send === true && amb.ambiguous === true,
   'two open deals still sends the most recent, but flags the guess for review');

// ======================= the payload GHL ACTUALLY sends
// Captured from execution 50 on 2026-08-19 — the first real buyer reply.
// GHL posts BOTH the customData we mapped in the workflow AND its own native
// `message` object, { type: 2, body: "..." }. The handler read the native one,
// stringified it whole, and threw the reply away as text "[object Object]",
// type "2", "not an SMS". This fixture exists so that cannot come back.
console.log('\nThe real GHL payload:\n');
const live = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures', 'live-ghl-reply.json'), 'utf8'));
const L = normalize(live);
ok(L.actionable === true, 'a real GHL reply is actionable (it was not, before)');
ok(L.text === 'Okay send details', 'the text is the words the buyer typed: "' + L.text + '"');
ok(L.type === 'sms', 'GHL numeric type 2 maps to sms, not the string "2"');
ok(L.direction === 'inbound', 'direction comes through');
ok(L.contactId === 'nmJtaJQhjdyGZBDDkiwI', 'contactId comes through');
ok(L.optOut === false, 'and it is not mistaken for an opt-out');

// Each shape in isolation.
const nativeOnly = normalize({ body: { contact_id: 'c1', message: { type: 2, body: 'yes please' } } });
ok(nativeOnly.actionable === true && nativeOnly.text === 'yes please',
   'the native message object alone is unwrapped correctly');
const asEmail = normalize({ body: { contact_id: 'c1', message: { type: 3, body: 'hello' } } });
ok(asEmail.actionable === false && /email/.test(asEmail.ignore),
   'numeric type 3 is recognised as email and ignored: "' + asEmail.ignore + '"');
const objText = normalize({ body: { contactId: 'c1', message: { nested: { a: 1 } }, direction: 'inbound' } });
ok(objText.actionable === false,
   'an object with no readable body is ignored, not stringified into a message');
ok(String(objText.text).indexOf('[object') === -1,
   'nothing ever becomes the literal text "[object Object]"');

console.log(fails === 0 ? '\nREPLY HANDLER OK' : '\n' + fails + ' CHECK(S) FAILED');
process.exit(fails === 0 ? 0 : 1);
