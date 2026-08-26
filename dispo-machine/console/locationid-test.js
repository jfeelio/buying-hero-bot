// Every GHL endpoint that needs locationId, and the banner that must not call
// a failed blast a success.
//
//   node locationid-test.js
//
// On 2026-08-19 the first real test send failed with a bare
//   422 COMMON_LOCATION_ID_UNDEFINED
// from /conversations/messages, and /opportunities/pipelines failed the same
// way — which the workflow reported as "Buyer Interest pipeline not found".
// Neither field is in GHL's published request schema, so nothing about the
// docs tells you they are required. This test is the memory.
const fs = require('fs');
const path = require('path');

const DIR = path.join(__dirname, '..', '..', 'crm-transition', 'n8n-workflows');
const LOC = 'ib5jEnyqqq06FIEqlVGs';
let fails = 0;
const ok = (c, m) => { console.log((c ? '  PASS  ' : '  FAIL  ') + m); if (!c) fails++; };

const httpNodes = (f) => JSON.parse(fs.readFileSync(path.join(DIR, f), 'utf8'))
  .nodes.filter((n) => n.type === 'n8n-nodes-base.httpRequest');

// Endpoints that 422 without a location, verified live against the API.
// Everything else is either record-scoped (/contacts/{id}) or carries the
// location inside a payload object built by a code node.
const NEEDS = [
  ['/conversations/messages', 'body'],
  ['/opportunities/pipelines', 'url'],
  ['/opportunities/search', 'url'],
];

console.log('Every GHL call that needs a location has one:\n');
for (const f of ['03-dispo-intake.cloud.json', '04-investorbase-capture.cloud.json',
                 '05-send-teaser-blast.cloud.json', '07-buyer-reply-handler.cloud.json']) {
  for (const n of httpNodes(f)) {
    const url = String(n.parameters.url || '');
    const body = String(n.parameters.jsonBody || '');
    for (const [ep, where] of NEEDS) {
      if (url.indexOf(ep) === -1) continue;
      const hay = where === 'url' ? url : body;
      ok(/location_?[Ii]d/.test(hay),
         f.slice(0, 2) + ' · ' + n.name + ' → ' + ep + ' carries a location in the ' + where);
    }
  }
}

// The literal id, not a stray expression that could resolve to undefined.
const w2 = httpNodes('05-send-teaser-blast.cloud.json');
const sms = w2.find((n) => n.name === 'Send Teaser SMS');
ok(String(sms.parameters.jsonBody).indexOf(LOC) !== -1,
   'the SMS body carries the literal location id');
const pipes = w2.find((n) => n.name === 'Fetch Pipelines');
ok(String(pipes.parameters.url).indexOf('locationId=' + LOC) !== -1,
   'Fetch Pipelines pins the location on the query string');
ok(/locationId/.test(sms.notes || ''),
   'and the node carries a note saying why, so nobody "cleans it up"');

// ------------------------------------------------------- the result banner
console.log('\nThe send banner tells the truth:\n');
const html = fs.readFileSync(path.join(__dirname, 'dist', 'index.html'), 'utf8');
const i = html.indexOf('if (S.sent){');
const box = html.slice(i, i + 1600);
ok(/queued \|\| 0/.test(box) && /failed \|\| 0/.test(box),
   'it reads both the queued and failed counts');
ok(/bad = q === 0/.test(box), '0 sent is treated as a failure, whatever else happened');
ok(/partial = q > 0 && f > 0/.test(box), 'some-failed is called out as partial');
ok(/Nothing was sent\./.test(box), 'a total failure says so in plain words');
ok(/sent-bad/.test(html) && /sent-warn/.test(html),
   'and is coloured as a failure rather than green');
ok(/failed: Number\(r\.failed \|\| 0\)/.test(html),
   'the failed count is carried out of the workflow response');

// ----------------------------------------- the Buyer Interest opportunity
// With several deals live at once the pipeline is unreadable unless each card
// says WHO it is, and each opp records WHICH deal it belongs to.
console.log('\nBuyer Interest opportunity:\n');
const opps = JSON.parse(fs.readFileSync(path.join(DIR, '05-send-teaser-blast.cloud.json'), 'utf8'))
  .nodes.find((n) => n.name === 'Build Buyer Interest Opps').parameters.jsCode;
ok(/name: b\.name \+/.test(opps), 'the card leads with the buyer name, not the address');
// GHL's opportunity search cannot filter on a contact's fields, so the
// opportunity carries its own copy of who this buyer is. Without these,
// "show me the VIPs on this deal" is not a question the pipeline can answer.
ok(opps.indexOf("{ id: '23Qr6cqR1IP1zFknf5Wn'") !== -1,
   'the opportunity carries opp_deal_address, so it can be filtered by deal');
ok(opps.indexOf("{ id: '9teeY5fWTPptnVygRVae'") !== -1, "and the buyer's tier");
ok(opps.indexOf("{ id: 'hJ06opXeHtm3nt072Wog'") !== -1, "and their source");
ok(opps.indexOf("{ id: 'hLc4zz9NtnpjwlCQERMV'") !== -1, 'and which script they got');
ok(/SEG_LABEL = \{ warm: 'Warm list'/.test(opps),
   'segment labels match what the review page showed, so filter and console agree');
ok(/fieldValue: dealAddress/.test(opps), 'populated from the deal address on the blast');
// 2026-08-26: cards are built BEFORE the send, so the address comes straight
// from the recipient list rather than from Tally Sends, which has not run yet.
ok(opps.indexOf("$('Tally Sends')") === -1,
   'and never from Tally Sends, which does not exist yet at card time');
// Contacts take `value`, opportunities take `fieldValue`. The wrong key does
// not error — the field just stays empty, which is how this hid for a while.
ok(!/value: tally\.address/.test(opps),
   'using fieldValue, not value — opportunities and contacts differ here');

console.log(fails === 0 ? '\nLOCATION ID OK' : '\n' + fails + ' CHECK(S) FAILED');
process.exit(fails === 0 ? 0 : 1);
