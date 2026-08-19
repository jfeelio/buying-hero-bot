// Proves the InvestorBase import can only ADD to an existing buyer.
//
//   node merge-policy-test.js
//
// The scenario: Marlon is a VIP on the master list who was blacklisted, is also
// a seller-side JV partner, and now turns up in an InvestorBase pull for a new
// address. Before the merge policy, that import silently moved him into the
// cold segment, reset his tier to C, and reactivated him for texting.
const fs = require('fs');
const path = require('path');

const WF = path.join(__dirname, '..', '..', 'crm-transition', 'n8n-workflows',
                     '04-investorbase-capture.cloud.json');
const wf = JSON.parse(fs.readFileSync(WF, 'utf8'));
const SRC = wf.nodes.find((n) => n.name === 'Merge into Existing Buyer').parameters.jsCode;

let fails = 0;
const ok = (c, m) => { console.log((c ? '  PASS  ' : '  FAIL  ') + m); if (!c) fails++; };

// Field ids, as GHL returns them.
const F = {
  buy_source: 'f_src', record_type: 'f_rt', buy_tier: 'f_tier', buy_status: 'f_status',
  buy_notes: 'f_notes', buy_ib_property: 'f_ib', excl_all_blasts: 'f_excl',
  excl_notes: 'f_exnotes', buy_price_max: 'f_pmax', buy_zips: 'f_zips',
  buy_consent_status: 'f_consent',
};
const defs = Object.keys(F).map((name) => ({ name, id: F[name] }));

// What the mapper produces from an InvestorBase row.
const incoming = {
  contact: {
    locationId: 'loc', firstName: 'MARLON', lastName: 'PIERRE JR',
    phone: '+13055550141', companyName: 'PIERRE HOLDINGS LLC',
    email: 'skiptrace@example.com', source: 'InvestorBase',
    customFields: [
      { id: F.record_type, fieldValue: ['Buyer'] },
      { id: F.buy_source, fieldValue: ['InvestorBase'] },
      { id: F.buy_status, fieldValue: 'Active' },
      { id: F.buy_tier, fieldValue: 'C' },
      { id: F.buy_notes, fieldValue: 'Imported from InvestorBase. LinkedDeal count: 6.' },
      { id: F.buy_price_max, fieldValue: '400000' },
      { id: F.buy_zips, fieldValue: '33142' },
      { id: F.buy_consent_status, fieldValue: 'Not Opted In' },
      { id: F.buy_ib_property, fieldValue: '1420 SW 9th Ter, Miami, FL', _ibProperty: true },
    ],
  },
  _meta: { name: 'Marlon Pierre' },
};

// What is already in GHL: years of curation.
const existing = {
  id: 'existing_marlon', firstName: 'Marlon', lastName: 'Pierre',
  email: 'marlon@pierrecapital.com', companyName: 'Pierre Capital',
  phone: '+13055550141', source: 'Master list 2019',
  customFields: [
    { id: F.record_type, value: ['Buyer', 'Seller'] },
    { id: F.buy_source, value: ['BH Main'] },
    { id: F.buy_status, value: 'Blacklist' },
    { id: F.buy_tier, value: 'VIP' },
    { id: F.buy_notes, value: 'Retraded twice in 2025.' },
    { id: F.excl_all_blasts, value: 'Yes' },
    { id: F.excl_notes, value: 'Blacklisted by Jorge 3/2026.' },
    { id: F.buy_ib_property, value: '2165 NW 58th St. Miami, FL 33142' },
  ],
};

function run(lookup) {
  const $ = (name) => ({
    first: () => ({ json: { customFields: defs } }),
    all: () => (name === 'Map InvestorBase Rows' ? [{ json: incoming }] : []),
  });
  const $input = { all: () => [{ json: lookup }] };
  return new Function('$', '$input', SRC)($, $input);
}

// ---------------------------------------------------------------- merge case
const merged = run({ contact: existing })[0].json;
const cf = {};
for (const f of merged.contact.customFields) {
  for (const k of Object.keys(F)) if (F[k] === f.id) cf[k] = f.fieldValue;
}
const arr = (v) => (Array.isArray(v) ? v : [v]).map(String);

console.log('Existing buyer matched on phone — merging InvestorBase data in:\n');
ok(merged._merge.existing === true, 'matched the existing contact by phone');
ok(arr(cf.buy_source).indexOf('BH Main') !== -1 && arr(cf.buy_source).indexOf('InvestorBase') !== -1,
   'buy_source UNIONed — stays on the warm list AND records the IB pull: [' + arr(cf.buy_source) + ']');
ok(arr(cf.record_type).indexOf('Seller') !== -1,
   'record_type keeps Seller — JV partner stays in seller workflows: [' + arr(cf.record_type) + ']');
ok(cf.buy_tier === undefined, 'buy_tier NOT written — hand-set VIP survives');
ok(cf.buy_status === undefined, 'buy_status NOT written — Blacklist is never reset to Active');
ok(cf.excl_all_blasts === undefined, 'excl_all_blasts untouched — the human exclusion rule stands');
ok(String(cf.buy_notes).indexOf('Retraded twice') !== -1 && String(cf.buy_notes).indexOf('LinkedDeal') !== -1,
   'buy_notes appended, not replaced: "' + cf.buy_notes + '"');

// Semicolon-delimited, not newline: buy_ib_property is a single-line TEXT field
// in GHL whose type can no longer be changed, so newlines would be unreadable in
// the contact card. Readers accept either.
const ib = String(cf.buy_ib_property).split(/[;\n]/).map((s) => s.trim());
ok(ib.length === 2 && ib[0].indexOf('2165') !== -1 && ib[1].indexOf('1420') !== -1,
   'buy_ib_property appended — both sourced addresses retained');

ok(merged.contact.firstName === undefined && merged.contact.lastName === undefined,
   'curated name not overwritten by the skip-traced one');
ok(merged.contact.email === undefined, 'real email not overwritten by the low-confidence one');
ok(merged.contact.companyName === undefined, 'company name not overwritten');
ok(merged.contact.source === undefined, 'original source attribution preserved');
ok(cf.buy_price_max === '400000' && cf.buy_zips === '33142',
   'genuinely NEW buy-box data still fills the blanks');
ok(merged.contact.phone === '+13055550141', 'phone — the join key — is always sent');

// ------------------------------------------------------------- new-buyer case
console.log('\nNo phone match — a brand new buyer:\n');
const fresh = run({})[0].json;
const fcf = {};
for (const f of fresh.contact.customFields) {
  for (const k of Object.keys(F)) if (F[k] === f.id) fcf[k] = f.fieldValue;
}
ok(fresh._merge.existing === false, 'treated as new');
ok(String(fcf.buy_status) === 'Active' && String(fcf.buy_tier) === 'C',
   'a new buyer gets the full mapped payload, nothing held back');
ok(fresh.contact.firstName === 'MARLON', 'new buyer keeps the name from the import');
ok(String(fcf.buy_ib_property) === '1420 SW 9th Ter, Miami, FL',
   'buy_ib_property starts the list');

// ================ the address InvestorBase repeats once per row
// A 77-buyer pull arrives as the SAME address 77 times in one 2,540-char
// string, comma-joined. The first collapse tried at most 12 repeats and assumed
// a ", " separator, so every contact in the Hialeah import was written with an
// unusable field that no smart list could match.
console.log('\nRepeated-address collapse:\n');
const mapSrc = wf.nodes.find((n) => n.name === 'Map InvestorBase Rows').parameters.jsCode;
const ci = mapSrc.indexOf('const collapseRepeat');
const cj = mapSrc.indexOf('};', mapSrc.indexOf('return t;', ci)) + 2;
const collapse = new Function(mapSrc.slice(ci, cj) + '; return collapseRepeat;')();

const ADDR = '580 Se 6th St, Hialeah, FL 33010';
ok(collapse(new Array(77).fill(ADDR).join(',')) === ADDR,
   '77 repeats joined by a bare comma collapse to one address');
ok(collapse(new Array(77).fill(ADDR).join(', ')) === ADDR, 'and joined by comma-space');
ok(collapse(new Array(2).fill(ADDR).join(',')) === ADDR, 'two repeats collapse');
ok(collapse(ADDR + '; ' + ADDR) === ADDR, 'semicolon-joined repeats too');
ok(collapse(ADDR) === ADDR, 'a single clean address is untouched');
ok(collapse('') === '', 'empty stays empty');

// buy_ib_property is append-only. Collapsing two REAL entries would cost a
// buyer their geo match on an earlier deal — worse than an over-long field.
const twoAddrs = ADDR + ',1420 SW 9th Ter, Miami, FL';
ok(collapse(twoAddrs) === twoAddrs, 'two genuinely different addresses are left alone');

// The merge path needs the same function, or an existing buyer gets the broken
// value appended to their history instead.
const mergeSrc = wf.nodes.find((n) => n.name === 'Merge into Existing Buyer').parameters.jsCode;
ok(/const dedupeRepeat/.test(mergeSrc) && /SEPS/.test(mergeSrc),
   'the merge path uses the same period detection, not the old guesswork');

console.log(fails === 0 ? '\nMERGE POLICY OK' : '\n' + fails + ' CHECK(S) FAILED');
process.exit(fails === 0 ? 0 : 1);
