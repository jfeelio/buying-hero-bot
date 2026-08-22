// Headless smoke test of the Dispo Deal Console, run against dist/index.html
// in demo mode: fill the intake form, submit, assert the review state renders
// every block, then edit a teaser, toggle a segment, and run the send flow.
const fs = require('fs');
const { JSDOM } = require('jsdom');

const HTML = fs.readFileSync('D:/Dropbox/J Feels/Dev/dispo-machine/console/dist/index.html', 'utf8');

let fails = 0;
function ok(cond, msg) {
  console.log((cond ? '  PASS  ' : '  FAIL  ') + msg);
  if (!cond) fails++;
}

const dom = new JSDOM(HTML, {
  runScripts: 'dangerously',
  url: 'https://automations.buyinghero.com/dispo/?demo=1',
  pretendToBeVisual: true,
});
const w = dom.window, d = w.document;

w.onerror = (e) => { console.log('  WINDOW ERROR: ' + e); fails++; };
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  await wait(50);

  // ---- intake ----
  ok(d.getElementById('intake') && !d.getElementById('intake').hidden, 'intake form is visible on load');
  ok(d.getElementById('f-county').options.length === 15, 'County dropdown filled (' + d.getElementById('f-county').options.length + ' options)');
  ok(d.getElementById('f-hood').options.length === 93, 'Neighborhood dropdown filled with blank + 92 (' + d.getElementById('f-hood').options.length + ')');
  ok(d.getElementById('envPill').textContent.indexOf('DEMO') === 0, 'demo badge shown in header');

  const named = [...d.querySelectorAll('#intake [name]')].map((e) => e.getAttribute('name'));
  const REQUIRED = ['Address','County','Neighborhood','Property Type','Beds','Baths','Living Area Sqft','Lot Size Sqft',
    'Year Built','Headline','Roof Age','AC Age','HOA','Liens or Violations','Occupancy','Key Upgrades','Extra Highlights',
    'Asking Price','ARV','Repair Estimate','Escrow','Close Date','Comps','Photos Videos URL','Access Notes','Additional Details'];
  const missing = REQUIRED.filter((n) => named.indexOf(n) === -1);
  ok(missing.length === 0, 'all 26 backend field names present' + (missing.length ? ' — MISSING ' + missing.join(', ') : ''));

  // ---- submit ----
  d.querySelector('[name="Address"]').value = '2165 NW 58th St. Miami, FL 33142';
  d.querySelector('[name="Headline"]').value = 'New Roof plus Impact Windows and Doors';
  d.querySelector('[name="Photos Videos URL"]').value = 'https://drive.google.com/x';
  d.getElementById('intake').dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }));

  ok(!d.getElementById('overlay').hidden, 'loading overlay appears while building');
  await wait(1200);

  // ---- review ----
  ok(d.getElementById('intake').hidden, 'intake hidden after submit');
  ok(!d.getElementById('review').hidden, 'review shown after submit');
  ok(d.getElementById('overlay').hidden, 'overlay dismissed');
  ok(d.querySelector('.addr').textContent === '2165 NW 58th St. Miami, FL 33142', 'deal address in header');
  ok(d.querySelectorAll('.tile').length === 3, 'three segment tiles (Inquired was removed with InvestorLift)');
  ok(d.querySelectorAll('.tsr').length === 3, 'three per-segment teaser boxes');

  const editable = ['tsr-0','tsr-1','tsr-2','wa','sms','voice'];
  const notEditable = editable.filter((id) => {
    const e = d.getElementById(id);
    return !e || e.tagName !== 'TEXTAREA' || e.readOnly || e.disabled;
  });
  ok(notEditable.length === 0, 'every message is an editable textarea' + (notEditable.length ? ' — NOT: ' + notEditable.join(', ') : ''));

  ok(d.getElementById('wa').value.indexOf('🏠 *2165 NW 58th') === 0, 'WhatsApp post loaded verbatim with emoji + asterisks');
  ok(d.querySelectorAll('.tbl').length === 3, 'three buyer tables (included / excluded / worth a call)');
  ok(d.querySelectorAll('.tbl')[0].querySelectorAll('tbody tr').length === 9, '9 included buyers rendered');
  ok(/571/.test(d.getElementById('sendBtn').textContent), 'send button counts all 571 buyers: "' + d.getElementById('sendBtn').textContent + '"');

  // ---- SMS segment math ----
  const m0 = d.getElementById('tsrmeta-0').textContent;
  ok(/\d+ characters/.test(m0) && /SMS segment/.test(m0), 'teaser shows character + segment count: "' + m0 + '"');
  const ta = d.getElementById('tsr-0');
  ta.value = 'short 🏠';
  ta.dispatchEvent(new w.Event('input', { bubbles: true }));
  ok(/emoji/.test(d.getElementById('tsrmeta-0').textContent), 'emoji in a teaser raises the 70-char warning');

  // ---- revert ----
  const before = d.getElementById('tsr-1').value;
  d.getElementById('tsr-1').value = 'clobbered';
  [...d.querySelectorAll('#tsrbox-1 .btn')].find((b) => b.textContent === 'Revert').click();
  ok(d.getElementById('tsr-1').value === before, 'Revert restores the original teaser');

  // ---- segment toggle ----
  // General cold is the last box now that Inquired is gone: 0, 1, 2.
  const cb = d.querySelector('#tsrbox-2 .sw input');
  cb.checked = false;
  cb.dispatchEvent(new w.Event('change', { bubbles: true }));
  ok(/169/.test(d.getElementById('sendBtn').textContent), 'holding back General cold (402) drops the count to 169: "' + d.getElementById('sendBtn').textContent + '"');
  ok(d.getElementById('tsrbox-2').className.indexOf('off') !== -1, 'held-back segment dims');
  ok(d.getElementById('tile-03').className.indexOf('tile-off') !== -1, 'matching stat tile dims too');

  // ---- send: two-step confirm ----
  d.getElementById('sendBtn').click();
  ok(d.getElementById('confirmBtn') != null, 'first click asks for confirmation instead of sending');
  ok(/Going to:/.test(d.getElementById('sendbar').textContent), 'confirmation lists the segments being sent');
  ok(/169/.test(d.getElementById('confirmBtn').textContent), 'confirm button repeats the count');

  d.getElementById('confirmBtn').click();
  await wait(1400);
  ok(d.querySelector('.sent-box') != null, 'send completes and shows a result');
  ok(/DEMO/.test(d.querySelector('.sent-box').textContent), 'demo mode reports that nothing was sent: "' + d.querySelector('.sent-box').textContent.trim() + '"');

  console.log(fails === 0 ? '\nALL CHECKS PASSED' : '\n' + fails + ' CHECK(S) FAILED');
  process.exit(fails === 0 ? 0 : 1);
})();
