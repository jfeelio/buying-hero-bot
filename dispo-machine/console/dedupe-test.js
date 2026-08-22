// Proves the send list never texts one phone number twice, and that when it
// has to choose between two records for the same human it keeps the better one.
//
//   node dedupe-test.js
//
// The dedupe block is identical in W1's Exclusion Engine (so the review page
// count is honest) and W2's Build Recipient List (so the send is right even if
// the database gained a duplicate in between). Both are extracted and run here.
const fs = require('fs');
const path = require('path');

const DIR = path.join(__dirname, '..', '..', 'crm-transition', 'n8n-workflows');
const SRC = {
  'W1 Exclusion Engine': ['03-dispo-intake.cloud.json', 'Exclusion Engine'],
  'W2 Build Recipient List': ['05-send-teaser-blast.cloud.json', 'Build Recipient List'],
};

let fails = 0;
const ok = (c, m) => { console.log((c ? '  PASS  ' : '  FAIL  ') + m); if (!c) fails++; };

// Pull just the dedupe helpers out of each node so the logic is tested where it
// actually lives — a copy here would drift the moment either node changed.
function helpers(file, nodeName) {
  const wf = JSON.parse(fs.readFileSync(path.join(DIR, file), 'utf8'));
  const src = wf.nodes.find((n) => n.name === nodeName).parameters.jsCode;
  const start = src.indexOf('const TIER_RANK');
  const end = src.indexOf('};', src.indexOf('const betterOf')) + 2;
  if (start < 0 || end < 2) throw new Error('dedupe block not found in ' + nodeName);
  return new Function(src.slice(start, end) + '\nreturn { phoneKey, betterOf };')();
}

// Same human, three records. Formats differ; the number does not.
const ROWS = [
  { name: 'Marlon Pierre',        phone: '+13055550141', tier: 'VIP', segment: 'warm' },
  { name: 'M. Pierre (IB)',       phone: '3055550141',   tier: 'C',   segment: 'geo_cold' },
  { name: 'PIERRE HOLDINGS LLC',  phone: '13055550141',  tier: 'B',   segment: 'general_cold' },
  { name: 'Carmen Delgado',       phone: '(305) 555-0128', tier: 'A', segment: 'warm' },
  { name: 'Ray Osterman',         phone: '',             tier: 'B',   segment: 'warm' },
];

function dedupe(h, rows) {
  const byPhone = new Map(), dupes = [];
  for (const b of rows) {
    const k = h.phoneKey(b.phone);
    if (!k) continue;
    const prev = byPhone.get(k);
    if (!prev) { byPhone.set(k, b); continue; }
    const keep = h.betterOf(prev, b);
    byPhone.set(k, keep);
    dupes.push(keep === prev ? b : prev);
  }
  const kept = new Set(Array.from(byPhone.values()));
  return { uniq: rows.filter((b) => kept.has(b)), dupes };
}

for (const label of Object.keys(SRC)) {
  console.log('\n' + label + ':\n');
  const h = helpers(SRC[label][0], SRC[label][1]);

  ok(h.phoneKey('+13055550141') === h.phoneKey('3055550141')
     && h.phoneKey('3055550141') === h.phoneKey('(305) 555-0141')
     && h.phoneKey('13055550141') === h.phoneKey('305-555-0141'),
     'every phone format collapses to one key');
  ok(h.phoneKey('') === '' && h.phoneKey(null) === '', 'a missing phone yields no key');
  // 5551234567 is a valid 10-digit number that happens to start with 1 after a
  // naive strip; the leading-1 rule must only fire on 11 digits.
  ok(h.phoneKey('1555123456') === '1555123456', 'a 10-digit number starting with 1 is not truncated');

  const { uniq, dupes } = dedupe(h, ROWS);
  // 5 rows in: 3 Pierre records collapse to 1, Carmen stays, Ray has no phone.
  ok(uniq.length === 2, 'three records for one human collapse to one: ' + uniq.length + ' of ' + ROWS.length + ' kept');
  const survivor = uniq.find((b) => h.phoneKey(b.phone) === '3055550141');
  ok(survivor && survivor.name === 'Marlon Pierre',
     'the VIP warm-list record survives, not the cold IB one: ' + (survivor || {}).name);
  ok(dupes.length === 2 && dupes.every((d) => d.name !== 'Marlon Pierre'),
     'both losers are reported so the review page can show why');
  ok(uniq.some((b) => b.name === 'Carmen Delgado'), 'unrelated buyers are untouched');
  ok(!uniq.some((b) => b.name === 'Ray Osterman'),
     'a buyer with no phone is not in the send list (nothing to text)');

  // Tier decides first; segment only breaks a tier tie.
  ok(h.betterOf({ tier: 'A', segment: 'general_cold' }, { tier: 'C', segment: 'warm' }).tier === 'A',
     'better tier wins over warmer segment');
  ok(h.betterOf({ tier: 'B', segment: 'general_cold' }, { tier: 'B', segment: 'warm' }).segment === 'warm',
     'on equal tiers the warmer segment wins');
  ok(h.betterOf({ tier: 'VIP', segment: 'warm' }, { tier: undefined, segment: 'warm' }).tier === 'VIP',
     'a tiered record beats an untiered one');
}

console.log(fails === 0 ? '\nDEDUPE OK' : '\n' + fails + ' CHECK(S) FAILED');
process.exit(fails === 0 ? 0 : 1);
