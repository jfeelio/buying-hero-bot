// Proves a buyer InvestorBase pulled for THIS address is counted as matched,
// even when InvestorBase and the dispo manager name the city differently.
//
//   node addr-match-test.js
//
// The block is identical in W1's Exclusion Engine (so the review page's
// segment counts are honest) and W2's Build Recipient List (so the send is
// right even if the list is rebuilt in between). Both are extracted and run
// here, and asserted byte-for-byte equal, so the two can never drift.
//
// Written after 2026-08-25, when 1125 Highview Rd reported 0 InvestorBase
// Matched against 76 buyers that had just imported cleanly.
const fs = require('fs');
const path = require('path');

const DIR = path.join(__dirname, '..', '..', 'crm-transition', 'n8n-workflows');
const SRC = {
  'W1 Exclusion Engine': ['03-dispo-intake.cloud.json', 'Exclusion Engine'],
  'W2 Build Recipient List': ['05-send-teaser-blast.cloud.json', 'Build Recipient List'],
};

let fails = 0;
const ok = (c, m) => { console.log((c ? '  PASS  ' : '  FAIL  ') + m); if (!c) fails++; };

function block(file, nodeName) {
  const wf = JSON.parse(fs.readFileSync(path.join(DIR, file), 'utf8'));
  const node = wf.nodes.find((n) => n.name === nodeName);
  if (!node) throw new Error('node not found: ' + nodeName);
  const src = node.parameters.jsCode;
  const start = src.indexOf('// Address comparison for deal-scoping.');
  const end = src.indexOf('const dealAddr');
  if (start < 0 || end < 0) throw new Error('address block not found in ' + nodeName);
  return src.slice(start, end);
}

// ============================================ the two copies must be one copy
const texts = Object.keys(SRC).map((k) => block(SRC[k][0], SRC[k][1]));
console.log('One block, two workflows:\n');
ok(texts[0] === texts[1],
   'W1 and W2 carry a byte-identical address matcher');

const engines = {};
for (const label of Object.keys(SRC)) {
  const [file, node] = SRC[label];
  engines[label] = new Function(
    block(file, node) + '\nreturn { normAddr, addrParts, addrMatch };')();
}

// The engines are identical, so behaviour is asserted against both at once.
const both = (a, b) => Object.keys(engines).map((label) => {
  const e = engines[label];
  return e.addrMatch(e.normAddr(a), e.normAddr(b));
});
const matches = (a, b, msg) => {
  const [w1, w2] = both(a, b);
  ok(w1 === true && w2 === true, msg);
};
const rejects = (a, b, msg) => {
  const [w1, w2] = both(a, b);
  ok(w1 === false && w2 === false, msg);
};

// ================================================== the incident that caused this
console.log('\n1125 Highview Rd - the case that reported 0 of 76:\n');
const IB   = '1125 Highview Rd, Lantana, FL 33462';       // what InvestorBase stamped
const DEAL = '1125 Highview Rd Lake Worth FL 33462';      // what was typed on the form
matches(IB, DEAL, 'Lantana (municipality) matches Lake Worth (USPS) in ZIP 33462');
rejects(IB, '1125 Highview Rd, Lantana, FL 33460',
        'but a different ZIP is a different property, not a naming difference');

// ================================================================ normalisation
console.log('\nThe same street, written the many ways it gets written:\n');
matches('2165 NW 58th St, Miami, FL 33142', '2165 NW 58 St, Miami, FL 33142',
        'the ordinal is noise: "58th St" is "58 St"');
matches('1125 Highview Rd, Lantana, FL 33462', '1125 Highview Road, Lantana, FL 33462',
        'the suffix is canonicalised: "Rd" is "Road"');
matches('2165 Northwest 58th Street, Miami, FL 33142', '2165 NW 58 St, Miami, FL 33142',
        'and so is the directional: "Northwest" is "NW"');
matches('580 SE 6th St, Hialeah, FL 33010', '580 se 6th st. hialeah fl 33010',
        'case and punctuation never mattered and still do not');
matches('1125 Highview Rd', '1125 Highview Rd Lake Worth FL 33462',
        'a bare street with no ZIP still matches - one side having none is not a conflict');

// ============================================================ real distinctions
console.log('\nWhat must still NOT match:\n');
rejects('1127 Highview Rd, Lantana, FL 33462', '1125 Highview Rd Lake Worth FL 33462',
        'the house number next door is a different house');
rejects('1125 Highview Ter, Lantana, FL 33462', '1125 Highview Rd Lake Worth FL 33462',
        'Highview Ter is not Highview Rd');
rejects('900 Main St, Miami, FL 33101', '900 Main St, Hialeah, FL 33010',
        'the same street name in two ZIPs is two properties');
rejects('', '1125 Highview Rd Lake Worth FL 33462', 'an empty pull matches nothing');

// ================================================================ the fallback
// InvestorBase pulls are not always addresses. "4200 Dispo" has no street
// suffix to find, so the old containment test still runs rather than the
// buyer being dropped.
console.log('\nUnparseable pulls fall back instead of vanishing:\n');
matches('4200 Dispo', '4200 Dispo, Miami FL',
        'a suffix-less pull still matches by containment');
matches('352 sw kentwood', '352 SW Kentwood',
        'and so does a pull with no city, state or ZIP at all');
rejects('4200 Dispo', '1125 Highview Rd Lake Worth FL 33462',
        'but the fallback does not match unrelated things');

// ============================================ the five-digit house number trap
console.log('\nA five-digit house number is not a ZIP:\n');
const e = engines['W1 Exclusion Engine'];
ok(e.addrParts(e.normAddr('10250 NW 7th St, Miami, FL 33172')).zip === '33172',
   'the ZIP is read as 33172, not the house number 10250');
ok(e.addrParts(e.normAddr('10250 NW 7th St, Miami, FL 33172')).street === '10250nw7st',
   'and the street key keeps the full house number: 10250nw7st');
matches('10250 NW 7th St, Miami, FL 33172', '10250 NW 7 Street Miami FL 33172',
        'so a five-digit house number still matches across spellings');

console.log(fails === 0 ? '\nADDR MATCH OK' : '\n' + fails + ' CHECK(S) FAILED');
process.exit(fails === 0 ? 0 : 1);
