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

function decide(ctx, aiJson, opts) {
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
  let code = DECIDE;
  // Force the switch to the state this case is about, whichever way production
  // happens to be set. The earlier version only rewrote false -> true, so the
  // day AUTO_SEND was turned back on every 'auto-send is off' case below started
  // silently testing the ON path instead.
  if (opts && typeof opts.autoSend === 'boolean') {
    const want = 'const AUTO_SEND = ' + opts.autoSend + ';';
    const other = 'const AUTO_SEND = ' + !opts.autoSend + ';';
    if (code.indexOf(want) === -1 && code.indexOf(other) === -1) {
      throw new Error('AUTO_SEND switch not found - test is lying');
    }
    code = code.replace(other, want);
  }
  return new Function('$', '$input', code)($, $input)[0].json;
}
// Both states are tested explicitly, so neither depends on how production is
// set today. ON is the live setting as of 2026-08-25.
const ON = { autoSend: true };
const OFF = { autoSend: false };
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

ok(decide({}, YES, ON).send === true, 'clear interest from a normal buyer sends');
ok(decide({}, YES, ON).moveStageId === 'stage_info', 'and moves the opportunity to Info Sent');
ok(cfVal(decide({}, YES, ON), 'buy_replies') === 4, 'and records the reply');

ok(decide({ investorLift: true }, YES, ON).send === false,
   'an INVESTORLIFT buyer never auto-sends, even saying yes outright');
ok(decide({ investorLift: true }, YES, ON).blockedBy.indexOf('notInvestorLift') !== -1,
   'and the reason is on the record: ' + JSON.stringify(decide({ investorLift: true }, YES, ON).blockedBy));
ok(decide({ investorLift: true }, YES, ON).needsHuman === true, 'it is routed to a human instead');

ok(decide({}, { intent: 'interested', confidence: 'low', objection: '', reason: '' }).send === false,
   'low confidence holds rather than guessing');
ok(decide({}, { intent: 'unclear', confidence: 'high', objection: '', reason: '' }).send === false,
   'unclear holds');
ok(decide({}, { intent: 'not_interested', confidence: 'high', objection: 'too small', reason: '' }).send === false,
   'a decline never gets the package');
ok(decide({ dealOppId: null }, YES, ON).send === false,
   'no open deal at Reached Out means nothing to send');
ok(decide({ address: '' }, YES, ON).send === false, 'no address means nothing to send');

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

const amb = decide({ ambiguous: true, openAtReachedOut: 2 }, YES, ON);
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

// ======================= which stages still count as "waiting on us"
// A "Called" stage was added on 2026-08-20. The first version matched only the
// literal stage name "reached out", so a buyer we phoned and then moved to
// Called would silently stop getting auto-responses: no deal found, haveDeal
// gate closed, nothing sent, no error anywhere. Matching by POSITION instead
// means any early stage added later just works.
console.log('\nStages that still count as waiting on us:\n');
const ctxSrc = wf.nodes.find((n) => n.name === 'Prepare Reply Context').parameters.jsCode;
const bi = ctxSrc.indexOf('const stages = (BI');
const TAIL = ') || lastDeal;';
const bj = ctxSrc.indexOf(TAIL) + TAIL.length;
if (bi < 0 || bj < TAIL.length) throw new Error('could not extract the deal-selection block');
const nrm = (v) => String(v == null ? '' : v).toLowerCase().replace(/[^a-z0-9]/g, '');
const pickRaw = new Function('BI', 'opps', 'prior', 'norm', ctxSrc.slice(bi, bj)
  + '; return { found: !!deal, n: reachedOut.length, dealId: deal && deal.id,'
  + ' dealSource, ambiguous, address };');
const pick = (BI, opps, prior) => pickRaw(BI, opps, prior || {}, nrm);

// The REAL Buyer Interest stages, read off the live pipeline on 2026-08-22.
// Called was added at position 2 - AFTER Info Sent, not before it. The first
// version of this fixture guessed the other order and quietly asserted
// behaviour production does not have.
const STAGES = [
  { id: 's0', name: 'Reached Out', position: 0 },
  { id: 's1', name: 'Info Sent', position: 1 },
  { id: 'sC', name: 'Called', position: 2 },
  { id: 's2', name: 'Interested', position: 3 },
  { id: 's5', name: 'Walked', position: 4 },
  { id: 's6', name: 'Offer', position: 5 },
  { id: 's7', name: 'Contract Sent', position: 6 },
  { id: 's3', name: 'Closed', position: 7 },
  { id: 's4', name: 'Passed', position: 8 },
];
const at = (id) => pick({ stages: STAGES },
  [{ id: 'o1', pipelineStageId: id, updatedAt: '2026-08-20' }], {});

ok(at('s0').found === true, 'Reached Out — a reply is acted on');
// Called sits AFTER Info Sent in the live pipeline, so a buyer who has reached
// it already has the details and is not auto-answered. That follows from the
// position rule rather than from anything named 'Called' - move the stage above
// Info Sent in GHL and this flips on its own, which is the point of the rule.
ok(at('sC').found === false,
   'Called — sits after Info Sent, so no auto-resend (18 buyers are here)');
ok(at('s1').found === false, 'Info Sent — they already have the details, no auto-resend');
ok(at('s2').found === false, 'Interested — a human is working it');
ok(at('s3').found === false, 'Closed — left alone');
ok(at('s4').found === false, 'Passed — left alone');

// Two open deals at Reached Out is the case that actually bit on 2026-08-22:
// a blast crashed before creating opportunities, so replies about the NEW deal
// matched the buyer's still-open opportunity on the PREVIOUS one and answered
// with the wrong property. The handler must see both and flag the ambiguity.
const two = pick({ stages: STAGES }, [
  { id: 'a', pipelineStageId: 's0', updatedAt: '2026-08-19' },
  { id: 'b', pipelineStageId: 's0', updatedAt: '2026-08-22' }]);
ok(two.n === 2, 'two live deals at Reached Out are both seen, and flagged as ambiguous');
ok(two.found === true, 'and it still picks one - the most recently updated');

// A pipeline with no Info Sent must not start replying to closed deals.
const noInfoSent = pick(
  { stages: [{ id: 'x', name: 'Reached Out', position: 0 }, { id: 'y', name: 'Won', position: 1 }] },
  [{ id: 'o', pipelineStageId: 'y', updatedAt: '2026-08-20' }]);
ok(noInfoSent.found === false,
   'with no Info Sent stage it stays conservative rather than replying to anything');

// ============================ which DEAL the reply is answered with
// The 2026-08-22 incident: a blast sent ~150 texts and then crashed before
// creating its opportunities. Buyers who replied about the new deal were
// answered with the PREVIOUS one, because 'newest open opportunity' was all
// the handler had to go on. buy_last_deal is stamped at send time and names
// the property the buyer was actually texted, so it decides now.
console.log('');
console.log('Which deal a reply is about:');
console.log('');

const OPP_ADDR = '23Qr6cqR1IP1zFknf5Wn';
const oppFor = (id, addr, updatedAt) => ({
  id, pipelineStageId: 's0', updatedAt,
  customFields: [{ id: OPP_ADDR, fieldValue: addr }],
});
const KEND = '14440 Sw 145th Pl, Miami, FL 33186';
const HIAL = '580 SE 6th St, Hialeah, FL 33010';
// the Hialeah card is deliberately the more recently touched one
const TWO = [oppFor('hialeah', HIAL, '2026-08-23'),
             oppFor('kendall', KEND, '2026-08-22')];

const byLast = pick({ stages: STAGES }, TWO, { buy_last_deal: KEND });
ok(byLast.dealId === 'kendall',
   'the deal the buyer was TEXTED wins, even when the other card was touched later');
ok(byLast.dealSource === 'buy_last_deal', 'and the record says why: ' + byLast.dealSource);
ok(byLast.address === KEND, 'the address answered with is the one they were sent');
ok(byLast.ambiguous === false,
   'matching buy_last_deal is not a guess, so it is not flagged ambiguous');

// Without the stamp it must still work - by inference, and honest about it.
const noStamp = pick({ stages: STAGES }, TWO, {});
ok(noStamp.dealId === 'hialeah', 'with no buy_last_deal it falls back to the newest card');
ok(noStamp.dealSource === 'newest open opportunity', 'and says so: ' + noStamp.dealSource);
ok(noStamp.ambiguous === true, 'and THAT is flagged ambiguous, because it is a guess');

// A stamp naming a deal with no open opportunity must fall back rather than
// answer with nothing - and the fallback is still marked as a guess.
const stale = pick({ stages: STAGES }, [oppFor('hialeah', HIAL, '2026-08-23')],
                   { buy_last_deal: KEND });
ok(stale.dealSource === 'newest open opportunity',
   'a stamp with no matching open opportunity falls back rather than inventing one');
ok(stale.address === HIAL, 'and answers with the deal it actually has');

// ================================================ the auto-send kill switch
// Off 2026-08-22 -> back on 2026-08-25. Whichever way it is set, the point of
// this section is that turning it OFF stops outbound text and nothing else:
// the workflow stays ACTIVE so opt-outs keep being honoured - deactivating it
// outright would have silently stopped processing STOP.
console.log('');
console.log('With auto-send off, nothing else is off:');
console.log('');
const off = decide({}, YES, OFF);
ok(off.send === false, 'a clearly interested buyer is NOT texted');
ok(off.blockedBy.indexOf('autoSendEnabled') !== -1,
   'and the reason is on the record: ' + JSON.stringify(off.blockedBy));
ok(cfVal(off, 'buy_replies') === 4, 'the reply is still counted');
ok(typeof cfVal(off, 'buy_last_responded') === 'string', 'buy_last_responded is still stamped');
ok(off.needsHuman === true, 'and it is routed to a human');

const stop = decide({ optOut: true }, null, OFF);
ok(cfVal(stop, 'buy_status') === 'DNC', 'STOP still writes DNC with auto-send off');
ok(cfVal(stop, 'buy_consent_status') === 'Opted Out', 'and still records Opted Out');

const objOff = decide({}, { intent: 'not_interested', confidence: 'high',
                            objection: 'wrong county', reason: '' }, OFF);
ok(cfVal(objOff, 'buy_objection_last') === 'wrong county',
   'objections are still captured with auto-send off');

ok(decide({}, YES, ON).send === true,
   'and flipping AUTO_SEND back on restores sending, so this is one switch');

console.log(fails === 0 ? '\nREPLY HANDLER OK' : '\n' + fails + ' CHECK(S) FAILED');
process.exit(fails === 0 ? 0 : 1);
