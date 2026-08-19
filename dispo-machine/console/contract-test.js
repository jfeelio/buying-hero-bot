// Contract test: render the console against a REAL response captured from
// POST /webhook/dispo-intake, not the mock. This is what catches backend and
// front end drifting apart — the mock will always agree with itself.
//
//   node contract-test.js path/to/live-response.json
//
// Capture a fresh one with:
//   curl -s -X POST https://automations.buyinghero.com/webhook/dispo-intake \
//        -H 'Content-Type: application/json' -d @deal.json -o live.json
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const RESP = process.argv[2] || path.join(__dirname, 'fixtures', 'live-intake.json');
const HTML = fs.readFileSync(path.join(__dirname, 'dist', 'index.html'), 'utf8');
const live = JSON.parse(fs.readFileSync(RESP, 'utf8'));

let fails = 0;
const ok = (c, m) => { console.log((c ? '  PASS  ' : '  FAIL  ') + m); if (!c) fails++; };

const dom = new JSDOM(HTML, {
  runScripts: 'dangerously',
  url: 'https://automations.buyinghero.com/dispo/',
  pretendToBeVisual: true,
  beforeParse(w) {
    // Serve the captured response in place of the network.
    w.fetch = () => Promise.resolve({
      ok: true, status: 200, text: () => Promise.resolve(JSON.stringify(live)),
    });
  },
});
const w = dom.window, d = w.document;
w.onerror = (e) => { console.log('  WINDOW ERROR: ' + e); fails++; };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  await wait(60);
  d.querySelector('[name="Address"]').value = live.address || 'x';
  d.querySelector('[name="Headline"]').value = 'x';
  d.querySelector('[name="Photos Videos URL"]').value = 'https://x';
  d.getElementById('intake').dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));
  await wait(400);

  ok(!d.getElementById('review').hidden, 'live response renders the review state');
  ok(d.getElementById('intakeErr').hidden, 'no error banner');
  ok(d.querySelector('.addr').textContent === live.address, 'address round-trips: ' + d.querySelector('.addr').textContent);
  ok(d.querySelectorAll('.tsr').length === (live.segments || []).length,
     (live.segments || []).length + ' segments each got a teaser box');

  // Every segment must carry text. A blank box here means Claude failed or the
  // key names drifted — and it would ship as an empty text to real buyers.
  const blanks = [];
  (live.segments || []).forEach((s, i) => {
    const v = d.getElementById('tsr-' + i);
    if (!v || !v.value.trim()) blanks.push(s.key);
  });
  ok(blanks.length === 0, 'every segment teaser arrived non-empty' + (blanks.length ? ' — BLANK: ' + blanks.join(', ') : ''));

  ok(d.getElementById('wa').value === live.whatsappPost, 'WhatsApp post binds byte-for-byte');
  ok(d.getElementById('sms').value === live.smsPost, 'SMS post binds byte-for-byte');
  ok(d.getElementById('voice').value === live.voiceBrief, 'voice brief binds byte-for-byte');
  ok(live.aiError == null, 'backend reported no AI error' + (live.aiError ? ': ' + live.aiError : ''));

  const total = (live.segments || []).reduce((a, s) => a + Number(s.count || 0), 0);
  const btn = d.getElementById('sendBtn');
  ok(btn != null, 'send button rendered');
  if (btn) ok(btn.textContent.indexOf(total.toLocaleString('en-US')) !== -1,
              'send button total matches the segment counts (' + total + '): "' + btn.textContent + '"');
  ok(total === 0 ? btn.disabled : !btn.disabled,
     total === 0 ? 'send is disabled when no buyer matched' : 'send is enabled');

  // The payload the send webhook will receive must use the same segment labels
  // W2 maps on. A rename on either side breaks the blast silently.
  const LABELS = ['Inquired', 'Warm list', 'InvestorBase Matched', 'General cold'];
  const bad = (live.segments || []).map((s) => s.key).filter((k) => LABELS.indexOf(k) === -1);
  ok(bad.length === 0, 'segment labels match what W2 maps on' + (bad.length ? ' — UNKNOWN: ' + bad.join(', ') : ''));

  // "Geo-matched cold" was renamed to "InvestorBase Matched" on 2026-08-19.
  // The label is the wire contract - the console keys its teasers on it and W2
  // maps it back to a segment key - so renaming it on one side only would mean
  // that segment silently gets no teaser and every buyer in it is skipped. The
  // old label stays as an alias: a review page opened before the rename is
  // still sitting in somebody's browser.
  const guard = JSON.parse(fs.readFileSync(
    path.join(__dirname, '..', '..', 'crm-transition', 'n8n-workflows',
              '05-send-teaser-blast.cloud.json'), 'utf8'))
    .nodes.find((n) => n.name === 'Guard Rails').parameters.jsCode;
  ok(/'investorbase matched': 'geo_cold'/.test(guard), 'W2 accepts the new segment label');
  ok(/'geo-matched cold': 'geo_cold'/.test(guard), 'and still accepts the old one');

console.log(fails === 0 ? '\nCONTRACT OK' : '\n' + fails + ' CONTRACT CHECK(S) FAILED');
  process.exit(fails === 0 ? 0 : 1);
})();
