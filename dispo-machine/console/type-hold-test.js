// The per-blast hold by buyer type, on both sides of the wire.
//
//   node type-hold-test.js
//
// Two things must hold or the review page lies to the dispo manager:
//   1. the count it shows equals the count W2 will actually text
//   2. a buyer carrying TWO held types is subtracted ONCE, not twice
// Rob Noel is JV;Realtor in the live database, which is what makes (2) real.
const fs = require('fs');
const path = require('path');

const DIR = path.join(__dirname, '..', '..', 'crm-transition', 'n8n-workflows');
const wf = (f) => JSON.parse(fs.readFileSync(path.join(DIR, f), 'utf8'));
const node = (f, n) => wf(f).nodes.find((x) => x.name === n).parameters.jsCode;

let fails = 0;
const ok = (c, m) => { console.log((c ? '  PASS  ' : '  FAIL  ') + m); if (!c) fails++; };

// ---------------------------------------------------- the console's arithmetic
const html = fs.readFileSync(path.join(__dirname, 'dist', 'index.html'), 'utf8');
function consoleMath(state) {
  const grab = (name) => {
    const i = html.indexOf('function ' + name + '(');
    if (i < 0) throw new Error('missing ' + name + ' in dist/index.html');
    // brace-match the function body
    let d = 0, j = html.indexOf('{', i);
    for (let k = j; k < html.length; k++) {
      if (html[k] === '{') d++;
      else if (html[k] === '}' && --d === 0) return html.slice(i, k + 1);
    }
    throw new Error('unbalanced ' + name);
  };
  const src = ['groupHeld', 'heldInSegment', 'segmentSendable', 'enabledTotal', 'heldTotal',
               'heldTypeList', 'heldTierList'].map(grab).join('\n');
  return new Function('S', src +
    '\nreturn {enabledTotal, heldTotal, heldInSegment, segmentSendable,' +
    ' heldTypeList, heldTierList};')(state);
}

// One segment shaped like the live database's warm list.
const segments = [{
  key: 'Warm list', count: 30,
  typeGroups: [
    { types: [],                  tier: '',    count: 8 },  // plain buyers
    { types: [],                  tier: 'VIP', count: 4 },  // VIPs, no type
    { types: ['JV'],              tier: '',    count: 9 },
    { types: ['JV'],              tier: 'VIP', count: 2 },  // VIP *and* JV
    { types: ['Realtor'],         tier: '',    count: 4 },
    { types: ['JV', 'Realtor'],   tier: '',    count: 1 },  // Rob Noel
    { types: ['Flipper', 'Realtor'], tier: '', count: 2 }   // Angie Gomez, Yoan
  ]
}];
const S = { review: { segments }, enabled: { 'Warm list': true },
            heldTypes: {}, heldTiers: {} };
let M = consoleMath(S);

console.log('Console arithmetic:\n');
ok(M.enabledTotal() === 30, 'nothing held: all 30 send');

S.heldTypes = { JV: true };
M = consoleMath(S);
ok(M.heldInSegment(segments[0]) === 12, 'holding JV removes 12 (9 + 2 VIP-JV + Rob Noel)');
ok(M.enabledTotal() === 18, 'and 18 remain');

S.heldTypes = { JV: true, Realtor: true };
M = consoleMath(S);
// 11 JV + 4 Realtor + 1 both + 2 Flipper;Realtor = 18 people, NOT 19.
ok(M.heldInSegment(segments[0]) === 18,
   'holding JV and Realtor removes 18 — Rob Noel is counted once, not twice');
ok(M.enabledTotal() === 12, 'leaving the 12 plain buyers');
ok(M.heldTypeList().join(',') === 'JV,Realtor', 'the payload lists both held types');

S.heldTypes = { JV: true, Realtor: false };
M = consoleMath(S);
ok(M.enabledTotal() === 18, 'releasing Realtor brings back the 4 + 2 Flipper;Realtor buyers');

// ---- tier holds, and the overlap that makes naive counting wrong ----------
S.heldTypes = {}; S.heldTiers = { VIP: true };
M = consoleMath(S);
ok(M.heldInSegment(segments[0]) === 6, 'holding VIP removes all 6 VIPs (4 plain + 2 who are also JV)');
ok(M.enabledTotal() === 24, 'and 24 remain');
ok(M.heldTierList().join(',') === 'VIP', 'the payload lists the held tier');

S.heldTypes = { JV: true }; S.heldTiers = { VIP: true };
M = consoleMath(S);
// 9 JV + 2 VIP-JV + 1 Rob Noel + 4 VIP-only = 16 people. Counting the two
// dimensions separately gives 12 + 6 = 18, double-counting the 2 VIP JVs.
ok(M.heldInSegment(segments[0]) === 16,
   'holding JV *and* VIP removes 16 — the 2 buyers who are both are counted once');
ok(M.enabledTotal() === 14, 'leaving 14');
ok(M.heldTypeList().concat(M.heldTierList()).join(',') === 'JV,VIP',
   'both dimensions travel in the payload');

S.heldTypes = {}; S.heldTiers = {};

M = consoleMath(S);
ok(M.enabledTotal() === 30, 'releasing everything restores all 30');

S.enabled = { 'Warm list': false };
M = consoleMath(S);
ok(M.enabledTotal() === 0 && M.heldTotal() === 0,
   'a disabled segment contributes nothing to either number');

// ------------------------------------------------------------ W2 enforcement
console.log('\nW2 enforcement (the send must agree with the review):\n');
const BRL = node('05-send-teaser-blast.cloud.json', 'Build Recipient List');
const start = BRL.indexOf('// ---- TEST SEND');
const end = BRL.indexOf('row.teaser =', start);
ok(BRL.indexOf('deal.tiersHeld', start) > 0 && BRL.indexOf('deal.tiersHeld') < end,
   'the tier hold lives in the same block, so both are enforced together');
ok(start > 0, 'the hold block exists in Build Recipient List');
const gate = BRL.slice(start, end);

function w2(typesHeld, buyerTypes, tiersHeld, tier, testOnly) {
  const fn = new Function('deal', 'buyerTypes', 'tier', `
    const norm = (s) => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
    const arr = (v) => v == null ? [] : (Array.isArray(v) ? v : String(v).split(';').map(s => s.trim()).filter(Boolean));
    const cf = (c, name) => name === 'buy_tier' ? tier : buyerTypes;
    const c = {}, row = {}, skipped = [];
    let sent = true;
    for (let once = 0; once < 1; once++) {
      ${gate.replace(/continue;/g, 'sent = false; continue;')}
    }
    return { sent, why: (skipped[0] || {}).why || '' };
  `);
  return fn({ typesHeld, tiersHeld: tiersHeld || [], testOnly: !!testOnly },
            buyerTypes, tier || '');
}

ok(w2(['JV'], ['JV']).sent === false, 'a JV partner is held when JV is held');
ok(/JV/.test(w2(['JV'], ['JV']).why), 'and the reason names the type: "' + w2(['JV'], ['JV']).why + '"');
ok(w2(['JV'], ['Flipper']).sent === true, 'a flipper is untouched');
ok(w2([], ['JV']).sent === true, 'holding nothing sends to everyone, JV included');
ok(w2(['JV', 'Realtor'], ['Flipper', 'Realtor']).sent === false,
   'Flipper;Realtor IS held when Realtor is held — the review page shows this cost');
ok(w2(['Realtor'], ['Flipper']).sent === true, 'and released when Realtor is not held');
ok(w2(['jv'], ['JV']).sent === false, 'matching is case-insensitive');
ok(w2(['JV'], []).sent === true, 'a buyer with no buy_type at all is never held');

ok(w2([], ['Flipper'], ['VIP'], 'VIP').sent === false, 'a VIP is held when VIP is held');
ok(/VIP/.test(w2([], ['Flipper'], ['VIP'], 'VIP').why),
   'and the reason says so: "' + w2([], ['Flipper'], ['VIP'], 'VIP').why + '"');
ok(w2([], ['Flipper'], ['VIP'], 'A').sent === true, 'a tier-A buyer still sends');
ok(w2([], ['Flipper'], ['VIP'], '').sent === true, 'an untiered buyer is never caught by a tier hold');
ok(w2([], ['Flipper'], [], 'VIP').sent === true, 'holding no tier sends to VIPs');
ok(w2(['JV'], ['JV'], ['VIP'], 'VIP').sent === false,
   'a VIP JV partner is held once, by whichever rule fires first');

// The console sends the key the workflow reads. A rename on one side only is
// silent: everyone would receive the blast including the JVs.
console.log('\nContract:\n');
const GR = node('05-send-teaser-blast.cloud.json', 'Guard Rails');
const W1_ = node('03-dispo-intake.cloud.json', 'Build Console Response');
ok(/typesHeld/.test(html), 'the console emits typesHeld');
ok(/con\.typesHeld/.test(GR), 'Guard Rails reads con.typesHeld off the console payload');
ok(/typesHeld,/.test(GR), 'and passes it downstream');
ok(/deal\.typesHeld/.test(BRL), 'Build Recipient List reads deal.typesHeld');
ok(/tiersHeld/.test(html), 'the console emits tiersHeld');
ok(/con\.tiersHeld/.test(GR), 'Guard Rails reads con.tiersHeld');
ok(/deal\.tiersHeld/.test(BRL), 'Build Recipient List reads deal.tiersHeld');
ok(/buyerTiers/.test(W1_) && /buyerTiers/.test(html),
   'W1 emits buyerTiers and the console renders it');
ok(/TIERS_HELD_BY_DEFAULT = \[\]/.test(W1_),
   'no tier is held by default — a VIP is a buyer we want, holding is a per-deal call');

ok(/buyerTypes/.test(W1_) && /buyerTypes/.test(html),
   'W1 emits buyerTypes and the console renders it');
ok(/typeGroups/.test(W1_) && /typeGroups/.test(html),
   'W1 emits per-segment typeGroups and the console does its arithmetic on them');
ok(/HOLD_BY_DEFAULT = \['JV', 'Realtor', 'TEST'\]/.test(W1_),
   'JV, Realtor and TEST arrive pre-held — the first blast is end-buyers-only,\n' +
   '         and a messaging-test record can never ride along on a real one');

// ---------------------------------------------- the Included buyers table
// The bug Jorge caught: the table listed 121 "included" buyers while the send
// was going to drop 31 of them. "Included" is the exclusion engine's verdict,
// "held" is a separate and later decision. One table has to carry both.
console.log('\nIncluded-buyers table:\n');
ok(/function rowHeld\(/.test(html), 'the table can ask whether a row is held');
ok(/function markHeldRows\(/.test(html), 'and repaints itself');
ok(/markHeldRows\(\);/.test(html.slice(html.indexOf('renderTypeNote();'))),
   'toggling a chip repaints the table, not just the counts');
ok(/held-badge/.test(html), 'held rows carry a visible HELD badge');
ok(/\.row-held/.test(html), 'and are dimmed, not reddened — nothing is wrong with them');
ok(/types: b\.types/.test(W1_),
   'W1 sends buy_type on each included row, without which none of this works');
const rh = html.slice(html.indexOf('function rowHeld('), html.indexOf('function markHeldRows('));
ok(/\(none\)/.test(rh), 'the "(none)" tier placeholder is not mistaken for a real tier');

// ------------------------------------------------------- TEST SEND whitelist
// The most dangerous control on the page: it decides between texting one phone
// and texting the whole database. Every check here is about it failing CLOSED.
console.log('\nTest send (whitelist):\n');
S.enabled = { 'Warm list': true };   // re-enable: the block above turned it off
S.testOnly = true; S.heldTypes = {}; S.heldTiers = {};
segments[0].typeGroups.push({ types: ['TEST'], tier: 'VIP', count: 1 });
segments[0].count = 31;
M = consoleMath(S);
ok(M.enabledTotal() === 1, 'test send sends to exactly the 1 TEST record');
ok(M.heldInSegment(segments[0]) === 30, 'and holds all 30 real buyers');

// The whitelist must not be re-openable by any other control on the page.
S.heldTypes = { JV: false, Realtor: false }; S.heldTiers = { VIP: false };
M = consoleMath(S);
ok(M.enabledTotal() === 1, 'unchecking every chip does NOT let real buyers back in');
S.heldTiers = { VIP: true };
M = consoleMath(S);
ok(M.enabledTotal() === 1, "and holding the TEST record's own tier does not drop it");

S.testOnly = false; S.heldTypes = {}; S.heldTiers = {};
M = consoleMath(S);
ok(M.enabledTotal() === 31, 'switching test send off restores the normal pool');

ok(w2([], ['Flipper'], [], '', true).sent === false,
   'W2: a normal buyer is skipped during a test send');
ok(/TEST SEND/.test(w2([], ['Flipper'], [], '', true).why),
   'and the reason says why: "' + w2([], ['Flipper'], [], '', true).why + '"');
ok(w2([], ['Cash', 'TEST'], [], '', true).sent === true, 'W2: the TEST record sends');
ok(w2([], ['Cash', 'TEST'], ['VIP'], 'VIP', true).sent === true,
   'W2: a held tier cannot suppress the TEST record during a test send');
ok(w2([], ['Cash', 'TEST'], [], '', false).sent === true,
   'W2: outside a test send the flag does nothing on its own');
ok(/con\.testOnly === true/.test(GR), 'Guard Rails reads testOnly strictly (=== true)');
ok(/deal\.testOnly === true/.test(BRL), 'Build Recipient List checks it strictly too');

console.log(fails === 0 ? '\nTYPE HOLD OK' : '\n' + fails + ' CHECK(S) FAILED');
process.exit(fails === 0 ? 0 : 1);
