// Proves the vetting gate holds InvestorLift inquiries until a dispo agent
// clears them — and, just as important, that it does NOT touch anyone else.
//
//   node vetting-test.js
//
// buy_vetted has three values and one blank:
//   Unvetted  W11 stamps this on every InvestorLift inquiry -> held
//   Vetted    the dispo agent's one flip                    -> blasts
//   Rejected  confirmed snake                               -> held forever
//   (blank)   trusted source                                -> blasts
//
// The blank case is the one that matters most: the 121 master buyers and every
// InvestorBase import have nothing in this field. If the gate ever treated
// blank as unvetted it would silently mute the entire database.
//
// The gate is extracted from BOTH workflows so a change in one that is not
// mirrored in the other fails here rather than in production.
const fs = require('fs');
const path = require('path');

const DIR = path.join(__dirname, '..', '..', 'crm-transition', 'n8n-workflows');
const SRC = {
  'W1 Exclusion Engine': ['03-dispo-intake.cloud.json', 'Exclusion Engine', 'suppressed'],
  'W2 Build Recipient List': ['05-send-teaser-blast.cloud.json', 'Build Recipient List', 'skipped'],
};

let fails = 0;
const ok = (c, m) => { console.log((c ? '  PASS  ' : '  FAIL  ') + m); if (!c) fails++; };

const MARK = '// ---- VETTING GATE ----';
const TAIL = "(known snake)' }); continue; }";

function extract(file, nodeName) {
  const wf = JSON.parse(fs.readFileSync(path.join(DIR, file), 'utf8'));
  const src = wf.nodes.find((n) => n.name === nodeName).parameters.jsCode;
  const start = src.indexOf(MARK);
  const end = src.indexOf(TAIL, start);
  if (start < 0 || end < 0) throw new Error('vetting gate not found in ' + nodeName);
  return src.slice(start, end + TAIL.length);
}

function runner(block, pushArr) {
  return new Function('contacts', `
    const norm = (s) => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
    const cf = (c, name) => c[name];
    const ${pushArr} = [], blasted = [];
    for (const c of contacts) {
      const row = { name: c.name };
      ${block}
      blasted.push(row);
    }
    return { held: ${pushArr}, blasted };
  `);
}

const POOL = [
  { name: 'IL inquiry, untouched',   buy_vetted: 'Unvetted' },
  { name: 'IL inquiry, cleared',     buy_vetted: 'Vetted' },
  { name: 'known snake',             buy_vetted: 'Rejected' },
  { name: 'master list buyer',       buy_vetted: null },
  { name: 'InvestorBase import',     buy_vetted: '' },
  { name: 'legacy record, no field' },
];

const blocks = {};
for (const label of Object.keys(SRC)) {
  const [file, node, arrName] = SRC[label];
  const block = extract(file, node);
  blocks[label] = block;

  console.log('\n' + label + ':\n');
  const { held, blasted } = runner(block, arrName)(POOL);
  const heldNames = held.map((h) => h.name);
  const blastNames = blasted.map((b) => b.name);

  ok(heldNames.indexOf('IL inquiry, untouched') !== -1, 'Unvetted is held');
  ok(heldNames.indexOf('known snake') !== -1, 'Rejected is held');
  ok(held.length === 2, 'nothing else is held: ' + JSON.stringify(heldNames));

  ok(blastNames.indexOf('IL inquiry, cleared') !== -1, 'Vetted blasts — the dispo agent\'s one flip works');
  ok(blastNames.indexOf('master list buyer') !== -1, 'a null buy_vetted blasts (the 121 master buyers)');
  ok(blastNames.indexOf('InvestorBase import') !== -1, 'an empty-string buy_vetted blasts (IB imports)');
  ok(blastNames.indexOf('legacy record, no field') !== -1, 'a record with no buy_vetted at all blasts');

  const unv = held.find((h) => h.name === 'IL inquiry, untouched');
  ok(/vetted/i.test(unv.why) && /dispo/i.test(unv.why),
     'the reason tells the dispo agent what to do: "' + unv.why + '"');
  const rej = held.find((h) => h.name === 'known snake');
  ok(/rejected/i.test(rej.why), 'a rejected buyer reads as rejected, not as pending: "' + rej.why + '"');

  // Case and stray whitespace come from humans typing into GHL, not from us.
  const messy = runner(block, arrName)([{ name: 'x', buy_vetted: ' UNVETTED ' }]);
  ok(messy.held.length === 1, 'matching is case- and space-insensitive');
}

// The two nodes name their reject bucket differently (suppressed vs skipped);
// everything else about the gate must match.
const labels = Object.keys(blocks);
const canon = (s) => s.replace(/\b(suppressed|skipped)\b/g, 'REJECTS');
ok(canon(blocks[labels[0]]) === canon(blocks[labels[1]]),
   '\nthe gate is identical in both workflows — intake cannot promise a count\n' +
   '         the send will not honour');

console.log(fails === 0 ? '\nVETTING OK' : '\n' + fails + ' CHECK(S) FAILED');
process.exit(fails === 0 ? 0 : 1);
