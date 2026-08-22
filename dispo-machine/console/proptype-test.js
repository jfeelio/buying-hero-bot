// Property-type matching, across both engines.
//
//   node proptype-test.js
//
// GHL stores a picklist KEY on the Property record ("2to4unit") while the
// buyer's field holds the LABEL ("2-4 Unit"). Normalising both by stripping
// non-alphanumerics gives "2to4unit" and "24unit", which never match — so a
// buyer who told us "no 2-4 units" was being blasted 2-4 units anyway. Every
// deal so far has been an SFR, where key and label happen to agree, so nothing
// ever showed it.
const fs = require('fs');
const path = require('path');

const DIR = path.join(__dirname, '..', '..', 'crm-transition', 'n8n-workflows');
const node = (f, n) => JSON.parse(fs.readFileSync(path.join(DIR, f), 'utf8'))
  .nodes.find((x) => x.name === n).parameters.jsCode;

let fails = 0;
const ok = (c, m) => { console.log((c ? '  PASS  ' : '  FAIL  ') + m); if (!c) fails++; };

const engines = {
  'W1 intake (reads the form LABEL)': node('03-dispo-intake.cloud.json', 'Exclusion Engine'),
  'W2 send (reads the stored KEY)': node('05-send-teaser-blast.cloud.json', 'Build Recipient List'),
};

// key/label pairs as GHL actually holds them
const PAIRS = [
  ['SFR', 'sfr'],
  ['2-4 Unit', '2to4unit'],
  ['5+ Unit', '5plusunit'],
  ['Condo', 'condo'],
  ['Land', 'land'],
  ['Townhome', 'townhome'],
  ['Manufactured Home', 'manufacturedhome'],
];

console.log('Key and label resolve to the same token:\n');
for (const label of Object.keys(engines)) {
  const src = engines[label];
  const i = src.indexOf('const TYPE_ALIAS');
  const j = src.indexOf('};', src.indexOf('const canonType')) + 2;
  ok(i > 0, label + ' — has the alias table');
  const canon = new Function(
    'const norm = (s) => String(s == null ? "" : s).toLowerCase().replace(/[^a-z0-9]/g, "");\n'
    + src.slice(i, j) + '; return canonType;')();

  for (const pair of PAIRS) {
    ok(canon(pair[0]) === canon(pair[1]),
       '   "' + pair[0] + '" matches the stored "' + pair[1] + '"');
  }
  // A fix that collapsed everything to one value would also pass the above.
  ok(canon('2-4 Unit') !== canon('5+ Unit'), '   and 2-4 Unit is still not 5+ Unit');
  ok(canon('Condo') !== canon('Land'), '   nor Condo Land');
}

console.log('\nBoth engines canonicalise — not just one:\n');
for (const label of Object.keys(engines)) {
  const src = engines[label];
  ok(src.indexOf("'excl_prop_types')).map(canonType)") !== -1,
     label + " — the buyer's excl_prop_types");
  ok(src.indexOf('canonType(f[\'Property Type\'])') !== -1
     || src.indexOf('canonType(p.prop_type)') !== -1,
     label + " — the deal's own type");
  ok(!/prop_types'\)\)\.map\(norm\)/.test(src),
     label + ' — no property-type list left on the raw norm()');
}

// The four lists that must agree, or a type exists in one place and not another.
console.log('\nThe console offers what the engines can match:\n');
const html = fs.readFileSync(path.join(__dirname, 'dist', 'index.html'), 'utf8');
const m = html.match(/var PROPERTY_TYPES = (\[[^\]]*\])/);
ok(!!m, 'the console has a PROPERTY_TYPES list');
const offered = JSON.parse(m[1]);
for (const pair of PAIRS) {
  ok(offered.indexOf(pair[0]) !== -1, '   the dropdown offers "' + pair[0] + '"');
}
ok(offered.length === PAIRS.length,
   'and offers nothing the engines have never heard of: ' + offered.length + ' of ' + PAIRS.length);

console.log(fails === 0 ? '\nPROP TYPE OK' : '\n' + fails + ' CHECK(S) FAILED');
process.exit(fails === 0 ? 0 : 1);
