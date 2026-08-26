// Proves a failed send says WHY it failed.
//
//   node tally-error-test.js
//
// 2026-08-26: one of 142 buyers on 3461 NW 171 St did not get their text.
// The blast reported failed=1 and, as the reason, the literal string
// "[object Object]". Finding out what actually happened meant pulling an 8MB
// execution blob off the VM and walking n8n's flattened data by hand.
//
// The cause was String(r.message) where GHL returns `message` as an OBJECT on
// failure. The real error was a 401 "Command timed out" - GHL throttling
// wearing an auth error's clothes, the same shape as the Cloudflare 1010 that
// already cost a day during the import work.
//
// A report that cannot say why is barely a report, so this pins it.
const fs = require('fs');
const path = require('path');

const WF = path.join(__dirname, '..', '..', 'crm-transition', 'n8n-workflows',
                     '05-send-teaser-blast.cloud.json');
const wf = JSON.parse(fs.readFileSync(WF, 'utf8'));
const CODE = wf.nodes.find((n) => n.name === 'Tally Sends').parameters.jsCode;

let fails = 0;
const ok = (c, m) => { console.log((c ? '  PASS  ' : '  FAIL  ') + m); if (!c) fails++; };

// Run the real node against a stubbed n8n, so this cannot drift from what runs.
function tally(results, recips) {
  const wrap = (a) => a.map((json) => ({ json }));
  const $input = { all: () => wrap(results) };
  const $ = (name) => {
    if (name === 'Build Recipient List') return { all: () => wrap(recips) };
    throw new Error('unexpected node reference: ' + name);
  };
  return new Function('$input', '$', CODE)($input, $)[0].json;
}

const RECIPS = [
  { contactId: 'c1', name: 'Angel Alberto', phone: '+13053006333', tier: 'C',
    address: '3461 NW 171 St', recordId: 'r1',
    _stats: { eligible: 2, sending: 2, heldByLimit: 0, skipped: [] } },
  { contactId: 'c2', name: 'Odette Martinez', phone: '+13055550100', tier: 'B' },
];

// ======================================================= the real failure shape
console.log('The 2026-08-26 failure, exactly as GHL returned it:\n');
const REAL = {
  error: {
    message: '401 - "{\\"statusCode\\":401,\\"message\\":\\"Command timed out\\"}"',
    name: 'AxiosError',
  },
};
const r1 = tally([REAL, { messageId: 'm2' }], RECIPS);

ok(r1.failed === 1 && r1.sent === 1, 'one send failed and one succeeded');
const err = r1.failed_rows[0].error;
ok(err.indexOf('[object Object]') === -1,
   'the reason is not "[object Object]"');
ok(/401/.test(err), 'it names the status: ' + err.slice(0, 80));
ok(/Command timed out/.test(err),
   'and the message GHL actually sent back');
ok(r1.failed_rows[0].name === 'Angel Alberto',
   'and it names the buyer who did not get their text');

// ============================================== the other shapes GHL can send
console.log('\nEvery other shape a failure arrives in:\n');
const cases = [
  [{ message: { statusCode: 429, message: 'Too Many Requests' } },
   'a bare object in message', /429|Too Many Requests/],
  [{ message: 'plain string failure' }, 'a plain string', /plain string failure/],
  [{ error: 'string error' }, 'a string in error', /string error/],
  [{ error: { message: 'nested string message' } }, 'a nested string message', /nested string message/],
  [{ statusCode: 500 }, 'no message at all', /500/],
  [{}, 'a completely empty response', /.+/],
];
for (const [resp, label, want] of cases) {
  const out = tally([resp, { messageId: 'm2' }], RECIPS);
  const e = out.failed_rows[0].error;
  ok(e.indexOf('[object Object]') === -1 && want.test(e),
     label + ' -> ' + JSON.stringify(e).slice(0, 70));
}

// ================================================= success is still success
console.log('\nSuccess is unchanged:\n');
const good = tally([{ messageId: 'm1' }, { conversationId: 'k2' }], RECIPS);
ok(good.sent === 2 && good.failed === 0, 'messageId and conversationId both count as sent');
ok(good.failed_rows.length === 0, 'and nothing is reported as failed');
ok(good.sent_rows[0].messageId === 'm1', 'the message id is carried for verification');

console.log(fails === 0 ? '\nTALLY ERROR OK' : '\n' + fails + ' CHECK(S) FAILED');
process.exit(fails === 0 ? 0 : 1);
