// Which number we text a buyer from.
//
//   node from-number-test.js
//
// Buyers save our number. Texting an established buyer from a different one
// makes us a stranger in a fresh thread, and carriers score sender->recipient
// pairs. So the rule is STICKY first, rotate only for someone never texted.
// VIPs and JV partners are pinned to one line that carries no cold volume.
const fs = require('fs');
const path = require('path');

const DIR = path.join(__dirname, '..', '..', 'crm-transition', 'n8n-workflows');
const wf = (f) => JSON.parse(fs.readFileSync(path.join(DIR, f), 'utf8'));
const node = (f, n) => wf(f).nodes.find((x) => x.name === n);

let fails = 0;
const ok = (c, m) => { console.log((c ? '  PASS  ' : '  FAIL  ') + m); if (!c) fails++; };

const REL = '+17868414589';
const ROT = ['+17864345766', '+17867306407', '+19543292967'];
const MAIN = '+17869827813';                       // the seller-side main line

// Pull the assignment block out of Build Recipient List so this cannot drift.
const BRL = node('05-send-teaser-blast.cloud.json', 'Build Recipient List').parameters.jsCode;
const start = BRL.indexOf('// ---- WHICH NUMBER WE TEXT FROM ----');
const end = BRL.indexOf('row.teaser =', start);
ok(start > 0, 'the assignment block exists');
const block = BRL.slice(start, end);

function assign(opts) {
  const fn = new Function('stored', 'tier', 'types', 'phone', `
    const norm = (s) => String(s == null ? '' : s).toLowerCase().replace(/[^a-z0-9]/g, '');
    const arr = (v) => v == null ? [] : (Array.isArray(v) ? v : String(v).split(';'));
    const cf = (c, name) => name === 'buy_from_number' ? stored
                          : name === 'buy_tier' ? tier : types;
    const c = {}, row = { phone };
    ${block}
    return row;
  `);
  return fn(opts.stored || '', opts.tier || '', opts.types || [], opts.phone || '+13055550100');
}

// ---------------------------------------------------------------- stickiness
console.log('\nStickiness beats everything:\n');
const kept = assign({ stored: ROT[1], phone: '+13055550111' });
ok(kept.fromNumber === ROT[1], 'a buyer we have texted keeps their number');
ok(kept.fromNumberIsNew === false, 'and is not re-stamped');

// Promotion must not move an established buyer - they already saved the number.
const promoted = assign({ stored: ROT[2], tier: 'VIP', phone: '+13055550111' });
ok(promoted.fromNumber === ROT[2],
   'promoting someone to VIP does NOT move them off the number they already have');

// A retired number is worse than none: the send would come from a dead line.
const retired = assign({ stored: '+15550001111', phone: '+13055550111' });
ok(ROT.concat(REL).indexOf(retired.fromNumber) !== -1,
   'a number no longer in the pool is reassigned, not used: ' + retired.fromNumber);
ok(retired.fromNumberIsNew === true, 'and the new one is stamped');

// ------------------------------------------------------- relationship number
console.log('\nVIPs and JV partners share one clean line:\n');
ok(assign({ tier: 'VIP' }).fromNumber === REL, 'a VIP gets the relationship number');
ok(assign({ types: ['JV'] }).fromNumber === REL, 'a JV partner does too');
ok(assign({ types: ['Flipper', 'JV'] }).fromNumber === REL, 'JV alongside another type still counts');
ok(assign({ tier: 'A' }).fromNumber !== REL, 'a tier-A buyer does not');

// ------------------------------------------------------------------ rotation
console.log('\nRotation for everyone else:\n');
const seen = {};
for (let i = 0; i < 400; i++) {
  const got = assign({ phone: '+1305555' + String(1000 + i).slice(0, 4) }).fromNumber;
  seen[got] = (seen[got] || 0) + 1;
}
ok(Object.keys(seen).every((k) => ROT.indexOf(k) !== -1),
   'over 400 cold buyers, only rotation numbers are ever used: '
   + JSON.stringify(Object.keys(seen)));
ok(!seen[MAIN], 'and the seller-side main line is never one of them');
const counts = ROT.map((r) => seen[r] || 0);
ok(counts.every((n) => n > 400 / ROT.length * 0.5),
   'the spread is even-ish across all three: ' + JSON.stringify(counts));
ok(assign({ phone: '+13055550123' }).fromNumber === assign({ phone: '+13055550123' }).fromNumber,
   'the same phone always lands on the same number — it is a hash, not a counter');

// ------------------------------------------------------------------ plumbing
console.log('\nPlumbing:\n');
ok(BRL.indexOf('fromNumber: b.fromNumber') !== -1,
   'fromNumber survives the explicit projection');
const send = node('05-send-teaser-blast.cloud.json', 'Send Teaser SMS').parameters.jsonBody;
ok(/fromNumber: \$json\.fromNumber/.test(send), 'the send node uses it instead of a constant');
// Check the POOL, not the source text - the block mentions the main line in a
// comment precisely to explain why it is excluded.
const poolLine = (block.match(/const ROTATION = \[[^\]]*\]/) || [''])[0]
               + (block.match(/const RELATIONSHIP_NUMBER = '[^']*'/) || [''])[0];
ok(poolLine.indexOf(MAIN) === -1, 'the seller-side main line is not in the pool constants');
ok(send.indexOf(MAIN) === -1, 'nor hardcoded in the send node');

const eng = node('05-send-teaser-blast.cloud.json', 'Build Engagement Updates').parameters.jsCode;
ok(/if \(r\.fromNumberIsNew && r\.fromNumber\) put\('buy_from_number'/.test(eng),
   'it is stamped set-once, so a later rule change cannot move an established buyer');

const ctx = node('07-buyer-reply-handler.cloud.json', 'Prepare Reply Context').parameters.jsCode;
ok(/buy_from_number/.test(ctx), 'the reply handler reads the buyer\'s own number');
const post = node('07-buyer-reply-handler.cloud.json', 'Send Full House Post').parameters.jsonBody;
ok(/Prepare Reply Context'\)\.first\(\)\.json\.fromNumber/.test(post),
   'and answers from it, not from a constant');

console.log(fails === 0 ? '\nFROM NUMBER OK' : '\n' + fails + ' CHECK(S) FAILED');
process.exit(fails === 0 ? 0 : 1);
