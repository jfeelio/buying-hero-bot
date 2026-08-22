// The compliance gates: DNC, litigators, and the opt-out sentence.
//
//   node compliance-test.js
//
// Florida's FTSA carries a private right of action at $500 a text, trebled for
// willful, and Florida is the national centre of text-marketing class actions.
// A 90-buyer blast is 90 potential claims, so these are hard stops, not
// preferences, and none of them may depend on a model behaving.
const fs = require('fs');
const path = require('path');

const DIR = path.join(__dirname, '..', '..', 'crm-transition', 'n8n-workflows');
const node = (f, n) => JSON.parse(fs.readFileSync(path.join(DIR, f), 'utf8'))
  .nodes.find((x) => x.name === n).parameters.jsCode;

let fails = 0;
const ok = (c, m) => { console.log((c ? '  PASS  ' : '  FAIL  ') + m); if (!c) fails++; };

// ─────────────────────────────────── the scrub gate, in BOTH engines
console.log('Scrub gate:\n');
const engines = {
  'W1 intake (the review count)': node('03-dispo-intake.cloud.json', 'Exclusion Engine'),
  'W2 send (the actual text)': node('05-send-teaser-blast.cloud.json', 'Build Recipient List'),
};

function gate(src, push) {
  const start = src.indexOf('// ---- DNC + LITIGATOR SCRUB ----');
  const end = src.indexOf('const pulledLines', start);
  const block = src.slice(start, end);
  return (scrubResult, sources) => new Function('scrubVal', 'srcList', `
    const norm = (s) => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
    const cf = () => scrubVal;
    const srcNorm = srcList.map(norm);
    const c = {}, row = {}, ${push.split('.')[0]} = [];
    let sent = true;
    for (let once = 0; once < 1; once++) {
      ${block.replace(/continue;/g, 'sent = false; continue;')}
    }
    return { sent, why: (${push.split('.')[0]}[0] || {}).why || '' };
  `)(scrubResult, sources);
}

for (const label of Object.keys(engines)) {
  const run = gate(engines[label], label.indexOf('W1') === 0 ? 'suppressed.push' : 'skipped.push');
  const BH = ['BH Main'], IB = ['InvestorBase'];

  ok(run('DNC', BH).sent === false, label + ' — a DNC scrub hit is refused even on the master list');
  ok(run('Litigator', BH).sent === false, label + ' — so is a known TCPA litigator');
  ok(/litigator/.test(run('Litigator', IB).why), '   and the reason names it: "' + run('Litigator', IB).why + '"');
  ok(run('Clean', IB).sent === true, label + ' — a scrubbed purchased buyer sends');
  ok(run('', BH).sent === true, label + ' — the master list is not blocked for want of a scrub');
  ok(run('', ['Referral']).sent === true, '   nor are referrals');
  ok(run('', ['InvestorBase', 'BH Main']).sent === true,
     '   a buyer on BOTH the master list and a pull counts as master list');
}

// ───────────────── the override: unscrubbed only, never a confirmed hit
// Jorge, 2026-08-19, having been told the risk: "just go with the override for
// now, im texting these folks tomorrow." So it exists - but it reaches exactly
// one thing, and the line it must never cross is a positive DNC or litigator
// hit.
console.log('\nThe override:\n');
const w2 = engines['W2 send (the actual text)'];
const gateBlock = w2.slice(w2.indexOf('// ---- DNC + LITIGATOR SCRUB ----'),
                           w2.indexOf('const pulledLines'));
const w2run = (scrubVal, srcList, includeUnscrubbed) => new Function(
  'scrubVal', 'srcList', 'deal', `
    const norm = (s) => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
    const cf = () => scrubVal;
    const srcNorm = srcList.map(norm);
    const c = {}, row = {}, skipped = [];
    let sent = true;
    for (let once = 0; once < 1; once++) {
      ${gateBlock.replace(/continue;/g, 'sent = false; continue;')}
    }
    return { sent, why: (skipped[0] || {}).why || '' };
  `)(scrubVal, srcList, { includeUnscrubbed });

const IBL = ['InvestorBase'];
ok(w2run('', IBL, false).sent === false, 'off by default: an unscrubbed buyer is held');
ok(w2run('', IBL, true).sent === true, 'on: an unscrubbed buyer sends');
ok(w2run('DNC', IBL, true).sent === false, 'ON, a confirmed DNC hit is STILL refused');
ok(w2run('Litigator', IBL, true).sent === false, 'ON, a known litigator is STILL refused');
ok(w2run('DNC', ['BH Main'], true).sent === false, 'ON, a DNC hit on the master list too');
ok(/scrub hit/.test(w2run('Litigator', IBL, true).why),
   'the reason is the hit, not the override: "' + w2run('Litigator', IBL, true).why + '"');
ok(w2.indexOf('deal.includeUnscrubbed !== true') !== -1,
   'W2 reads the flag strictly - an absent flag means held, never sent');

const gr = node('05-send-teaser-blast.cloud.json', 'Guard Rails');
ok(gr.indexOf('con.includeUnscrubbed === true') !== -1, 'Guard Rails reads it strictly too');
ok(gr.indexOf('includeUnscrubbed,') !== -1,
   'and passes it downstream, so the execution log records that it was used');

// ─────────────────────────────────── the opt-out sentence
console.log('\nOpt-out sentence:\n');
const brl = node('05-send-teaser-blast.cloud.json', 'Build Recipient List');
ok(/const OPT_OUT_LINE = 'Reply STOP to opt out\.';/.test(brl),
   'the wording is a fixed constant, not something the model writes');

const bodyStart = brl.indexOf('// ---- OPT-OUT LINE ----');
const bodyEnd = brl.indexOf('row.hasOptOut', bodyStart);
const append = brl.slice(bodyStart, bodyEnd);
const build = (teaser, onMaster, wantIt) => new Function('teaser', 'onMasterList', 'deal', `
  const OPT_OUT_LINE = 'Reply STOP to opt out.';
  const row = {};
  let body = teaser;
  ${append}
  return body;
`)(teaser, onMaster, { includeOptOut: wantIt });

const cold = build('Off-market 3/2 in Hialeah, $265K. Interested?', false);
ok(/Reply STOP to opt out\.$/.test(cold), 'a purchased-list text ends with it: "…' + cold.slice(-34) + '"');
ok(build('Got another one for you.', true).indexOf('STOP') === -1,
   'a master-list text does not carry it');
// Belt and braces: if a teaser somehow already says STOP, do not say it twice.
ok((build('Deal here. Reply STOP to opt out.', false).match(/STOP/g) || []).length === 1,
   'it is never appended twice');
ok(build('Deal here.  ', false) === 'Deal here. Reply STOP to opt out.',
   'trailing whitespace does not produce a double space');

// The line is a per-blast toggle now. Jorge, 2026-08-20: "for this first blast
// im not sending it." The DEFAULT direction is what matters — an absent flag
// must mean include, so a stale page or a dropped field can never silently
// strip it.
ok(build('Deal here.', false, undefined) === 'Deal here. Reply STOP to opt out.',
   'an ABSENT flag still includes it — the safe default');
ok(build('Deal here.', false, true) === 'Deal here. Reply STOP to opt out.',
   'explicitly on includes it');
ok(build('Deal here.', false, false) === 'Deal here.',
   'explicitly off drops it');
// BH Main is a RULE, not a preference. Jorge, 2026-08-20: "BH Main never gets
// reply stop to opt out." These people are on the master list because they
// asked to be; a form-letter opt-out line to someone Andrew spoke to last week
// reads as a stranger. No per-blast setting may override this.
ok(build('Got another one.', true, true) === 'Got another one.',
   'a master-list buyer gets NO opt-out line even with the toggle ON');
ok(build('Got another one.', true, false) === 'Got another one.',
   'and none with it off');
ok(build('Got another one.', true, undefined) === 'Got another one.',
   'and none when the flag is missing entirely');
const brlSrc = node('05-send-teaser-blast.cloud.json', 'Build Recipient List');
ok(brlSrc.indexOf('const optOutForbidden = onMasterList;') !== -1,
   'the rule is its own named condition, not a clause inside the toggle');
ok(brlSrc.indexOf('!optOutForbidden && wantOptOut') !== -1,
   'and it is checked BEFORE the toggle, so no setting can reach past it');
const gr2 = node('05-send-teaser-blast.cloud.json', 'Guard Rails');
ok(gr2.indexOf('con.includeOptOut !== false') !== -1,
   'Guard Rails defaults to true — only an explicit false drops the line');
ok(node('05-send-teaser-blast.cloud.json', 'Build Recipient List')
     .indexOf('deal.includeOptOut !== false') !== -1,
   'and so does the send, independently');

// ─────────────────────── and the model is told not to write its own
console.log('\nThe model does not write compliance text:\n');
const prompt = node('03-dispo-intake.cloud.json', 'Build Claude Request');
ok(!/End with the opt-out/.test(prompt),
   'the old "end with the opt-out" instruction is gone from every teaser');
ok((prompt.match(/Do NOT write an opt-out line/g) || []).length === 3,
   'all three teasers tell it not to — otherwise cold texts double up');

console.log(fails === 0 ? '\nCOMPLIANCE OK' : '\n' + fails + ' CHECK(S) FAILED');
process.exit(fails === 0 ? 0 : 1);
