// Proves the blast creates a buyer's pipeline card BEFORE it texts them.
//
//   node blast-order-test.js
//
// This is an ORDERING test, which is unusual here, because the bug it guards
// was an ordering bug and nothing about the code of any single node was wrong.
//
// 2026-08-26: W2 sent every teaser, then wrote engagement, then created cards.
// Odette Martinez replied four minutes into a 142-buyer blast asking for the
// address. She was classified interested/high - correctly - and held, because
// she had no card and no buy_last_deal yet, so nothing could say WHICH deal she
// meant. Three of the four replies inside that window hit the same gap. The
// faster a buyer replied, the more likely the machine refused to answer.
//
// The reply handler resolves the deal as `matched || reachedOut[0]`, so a card
// that exists before the text answers the question on its own.
const fs = require('fs');
const path = require('path');

const WF = path.join(__dirname, '..', '..', 'crm-transition', 'n8n-workflows',
                     '05-send-teaser-blast.cloud.json');
const wf = JSON.parse(fs.readFileSync(WF, 'utf8'));

let fails = 0;
const ok = (c, m) => { console.log((c ? '  PASS  ' : '  FAIL  ') + m); if (!c) fails++; };

const node = (n) => wf.nodes.find((x) => x.name === n);
const adj = {};
for (const [src, out] of Object.entries(wf.connections || {})) {
  adj[src] = [];
  for (const branch of out.main || []) for (const c of branch || []) adj[src].push(c.node);
}

// Walk from each entry point the same way n8n does, so "before" means what it
// means at runtime rather than where a node sits on the canvas.
function reachOrder(start) {
  const seen = new Set(), order = [], queue = [start];
  while (queue.length) {
    const cur = queue.shift();
    if (seen.has(cur)) continue;
    seen.add(cur); order.push(cur);
    for (const nxt of adj[cur] || []) queue.push(nxt);
  }
  return order;
}

console.log('The console send path:\n');
for (const entry of ['Console Send', 'Blast Form']) {
  const order = reachOrder(entry);
  const at = (n) => order.indexOf(n);
  const label = entry === 'Console Send' ? 'console' : 'form';

  ok(at('Create Buyer Interest Opps') !== -1, `[${label}] cards are created at all`);
  ok(at('Send Teaser SMS') !== -1, `[${label}] teasers are sent at all`);
  ok(at('Create Buyer Interest Opps') < at('Send Teaser SMS'),
     `[${label}] the card is created BEFORE the text goes out`);
  ok(at('Send Teaser SMS') < at('Write Engagement to Buyers'),
     `[${label}] engagement is still written AFTER the send, never before`);
  ok(at('Build Recipient List') < at('Create Buyer Interest Opps'),
     `[${label}] and the recipient list is settled before either`);
  console.log('');
}

// ============================================ the send must still see buyers
// Card creation is a detour off the main line. If Send Teaser SMS were left
// reading the opportunity API's response it would try to text the wrong shape
// entirely, so a node has to put the recipients back.
console.log('The detour puts the recipients back:\n');
const resume = node('Resume Recipient List');
ok(!!resume, 'a node re-emits the recipient list after the cards are created');
ok(adj['Resume Recipient List'] && adj['Resume Recipient List'].indexOf('Send Teaser SMS') !== -1,
   'and it feeds Send Teaser SMS directly');
ok(/\$\('Build Recipient List'\)\.all\(\)/.test(resume.parameters.jsCode),
   'it returns the recipient list itself, not a filtered copy');

// ================================================ no stale Tally dependency
console.log('\nCard building no longer waits on the send:\n');
const opps = node('Build Buyer Interest Opps').parameters.jsCode;
ok(opps.indexOf("$('Tally Sends')") === -1,
   'Build Buyer Interest Opps does not read Tally Sends');
ok(opps.indexOf('sentNames') === -1,
   'and does not filter to buyers who already received it - none have yet');
ok(/\$\('Build Recipient List'\)\.all\(\)/.test(opps),
   'it builds from the recipient list instead');
ok(/const dealAddress = \(recips\[0\]/.test(opps),
   'and takes the deal address from the same place Tally Sends took it');

// ============================================ the invariant that still holds
// Creating cards early is a deliberate trade: a failed send now leaves a card
// for someone never texted. Marking a buyer CONTACTED on a failed send is a
// different matter and is still forbidden - writeback-test.js owns that rule,
// and this asserts the ordering it depends on.
console.log('\nWhat did NOT change:\n');
const eng = node('Build Engagement Updates').parameters.jsCode;
ok(eng.indexOf("$('Tally Sends')") !== -1,
   'engagement is still built from what actually sent');

// ==================================================== a rate limit must not abort
const cbo = node('Create Buyer Interest Opps');
ok(cbo.retryOnFail === true,
   'card creation retries, so a burst limit cannot abort a blast before it sends');
ok(cbo.onError === 'continueRegularOutput',
   'and a card that will not create never stops the texts');

console.log(fails === 0 ? '\nBLAST ORDER OK' : '\n' + fails + ' CHECK(S) FAILED');
process.exit(fails === 0 ? 0 : 1);
