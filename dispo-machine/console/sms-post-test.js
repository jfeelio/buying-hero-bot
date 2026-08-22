// The full property post, as SMS.
//
//   node sms-post-test.js
//
// On 2026-08-20 an interested buyer replied to the first blast and never got
// the details. The workflow was fine — GHL accepted the message and returned a
// messageId. The CARRIER marked it undelivered: 1,117 characters with emoji is
// 17 segments, because one emoji forces the whole message into UCS-2 at 67
// characters a segment instead of GSM-7 at 153. The SMS post was the WhatsApp
// post with the asterisks stripped, and nothing else.
const fs = require('fs');
const path = require('path');

const DIR = path.join(__dirname, '..', '..', 'crm-transition', 'n8n-workflows');
const wf = JSON.parse(fs.readFileSync(path.join(DIR, '03-dispo-intake.cloud.json'), 'utf8'));
const code = wf.nodes.find((n) => n.name === 'Build WhatsApp + SMS Post').parameters.jsCode;

let fails = 0;
const ok = (c, m) => { console.log((c ? '  PASS  ' : '  FAIL  ') + m); if (!c) fails++; };

function build(overrides) {
  const f = Object.assign({
    Address: '580 SE 6th St, Hialeah, FL 33010', Beds: '4', Baths: '3',
    'Living Area Sqft': '1978', 'Lot Size Sqft': '9066', 'Year Built': '1955',
    Headline: 'Amazing Hialeah Rental Play with 575 sq ft detached 1/1 ADU',
    HOA: 'None', 'Liens or Violations': 'None found', Occupancy: 'VACANT AT CLOSE',
    'Key Upgrades': 'ADU has newer mini split',
    'Extra Highlights': '3/2 Main Home with 1,402 living space\nHVAC in main home not working',
    'Asking Price': '265000', ARV: '385000', Escrow: '10000', 'Close Date': '2026-09-19',
    Comps: '1846 NW 49 ST - Sold for $480,000 on 7/10/26\n900 W 42 PL - Sold for $430,000 on 6/2/26',
    'Photos Videos URL': 'https://drive.google.com/drive/folders/1zcWR6cN0lczMxHtADuEeDFKkcBvoqwsf',
  }, overrides || {});
  const ctx = { json: { raw: f, recordId: 'x', props: {}, viaConsole: true } };
  return new Function('$input', '$', code)({ first: () => ctx }, () => ({ first: () => ctx }))[0].json;
}

const seg = (s) => {
  const gsm = [...s].every((c) => c.charCodeAt(0) < 128);
  return { gsm, n: Math.ceil(s.length / (gsm ? 153 : 67)) };
};

const out = build();
const s = out.sms_post;
const m = seg(s);

console.log('Deliverability:\n');
ok(m.gsm, 'the SMS post is pure GSM-7 — one emoji would cost 2.3x per character');
ok(!/[\u{1F300}-\u{1FAFF}⭐⚠]/u.test(s), 'no emoji anywhere in it');
ok(m.n <= 6, 'it fits in 6 segments or fewer: ' + m.n + ' (the undelivered one was 17)');
ok(s.length < 950, 'and under ~950 characters: ' + s.length);

console.log('\nNothing important was dropped:\n');
ok(s.indexOf('580 SE 6th St') !== -1, 'the address');
ok(s.indexOf('Amazing Hialeah Rental Play') !== -1, 'the headline');
ok(/4\/3/.test(s), 'beds and baths');
ok(s.indexOf('1,978') !== -1, 'living area');
ok(s.indexOf('$265,000') !== -1, 'the asking price');
ok(s.indexOf('$385,000') !== -1, 'the ARV');
ok(s.indexOf('$10,000') !== -1, 'the escrow');
ok(s.indexOf('VACANT AT CLOSE') !== -1, 'occupancy');
ok(s.indexOf('NO HOA') !== -1, 'the HOA position');
ok(s.indexOf('HVAC in main home not working') !== -1,
   'and the unflattering detail — a buyer finds out anyway, better from us');
ok(s.indexOf('drive.google.com') !== -1, 'the photos link');
ok(s.indexOf('COMPS') !== -1, 'the comps block');

// 2026-08-22: the cramped version fit in four segments and nobody could read
// it - three dense lines of '; ' and ' | ' separated facts. Bullets are the
// requirement now, and they are close to free: a newline costs one septet,
// the same as the space in '; ', while the ' | ' separators it replaced were
// GSM-7 EXTENSION characters billed as two.
const NL = String.fromCharCode(10);
console.log(NL + 'It is scannable, not a wall of text:' + NL);
const rows = s.split(NL);
const bullets = rows.filter((l) => l.indexOf('- ') === 0);
ok(bullets.length >= 5, 'the facts are bulleted, one per line: ' + bullets.length + ' bullets');
ok(rows.length >= 12, 'and it is laid out over ' + rows.length + ' lines, not 8');
ok(rows.some((l) => l === ''), 'blank lines separate the sections');
ok(s.indexOf('PRICE ') !== -1, 'money gets its own labelled block');
ok(s.indexOf(' | ') === -1,
   'no pipe separators left - each one was billed as two septets');
ok(bullets.every((l) => l.indexOf(String.fromCharCode(8226)) === -1),
   'bullets are hyphens, never the bullet character - one would force UCS-2');
const longest = rows.reduce((a, b) => (b.length > a.length ? b : a), '');
ok(longest.length < 75 || longest.indexOf('http') !== -1,
   'no line runs long enough to wrap badly, except the link: ' + longest.length);

console.log('\nWhat it deliberately drops:\n');
ok(s.indexOf('age unknown') === -1, '"roof age unknown" — not a detail, and it costs the same as one');
ok((s.match(/1,978/g) || []).length === 1, 'living area appears ONCE, not in a spec line and a bullet');
ok((s.match(/9,066/g) || []).length === 1, 'same for lot size');

console.log('\nIt stays short when the deal is wordy:\n');
const fat = build({
  'Extra Highlights': new Array(14).fill('Another selling point worth mentioning here').join('\n'),
  Comps: new Array(6).fill('1234 SOME LONG STREET NAME, Miami, FL 33142 - Sold for $500,000 on 1/1/26').join('\n'),
});
const fm = seg(fat.sms_post);
ok(fm.n <= 6, 'a deal with 14 highlights and 6 comps still fits: ' + fm.n + ' segments');
ok(fat.sms_post.indexOf('drive.google.com') !== -1,
   'and the photos link survives the trim — it is the point of the message');

console.log('\nThe WhatsApp post is untouched:\n');
ok(/[\u{1F300}-\u{1FAFF}]/u.test(out.whatsapp_post), 'it still has its emoji');
ok(out.whatsapp_post.indexOf('*') !== -1, 'and its bold markers');
ok(out.whatsapp_post !== s, 'the two are genuinely different artifacts now');

console.log(fails === 0 ? '\nSMS POST OK' : '\n' + fails + ' CHECK(S) FAILED');
process.exit(fails === 0 ? 0 : 1);
