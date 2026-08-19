// Intake drafts: shared server-side form state, on both sides of the wire.
//
//   node drafts-test.js
//
// A draft is deliberately NOT a GHL Property record. A half-filled intake is
// not a deal, and writing one into the Property object would pollute the same
// records the seller side upserts into.
const fs = require('fs');
const path = require('path');

const DIR = path.join(__dirname, '..', '..', 'crm-transition', 'n8n-workflows');
const wf = JSON.parse(fs.readFileSync(path.join(DIR, '08-intake-drafts.cloud.json'), 'utf8'));
const node = (n) => wf.nodes.find((x) => x.name === n);
const src = (n) => node(n).parameters.jsCode;

let fails = 0;
const ok = (c, m) => { console.log((c ? '  PASS  ' : '  FAIL  ') + m); if (!c) fails++; };

// ------------------------------------------------------------- routing
console.log('Routing and validation:\n');
const route = src('Route Action');
const run = (body) => new Function('$input',
  route)({ first: () => ({ json: { body } }) })[0].json;

const save = run({ action: 'save', fields: { Address: ' 9902 NW 25th Ave ', Beds: '3' } });
ok(save.ok === true && save.action === 'save', 'a save routes');
ok(save.address === '9902 NW 25th Ave', 'the address is trimmed for the list: "' + save.address + '"');
ok(!!save.id && save.id.length > 5, 'a new draft gets an id: ' + save.id);
ok(save.params.length === 4, 'save binds 4 params');
ok(JSON.parse(save.params[2]).Beds === '3', 'the whole form goes into the payload');

// Clicking save twice must update ONE row, not litter the list.
const again = run({ action: 'save', id: save.id, fields: { Address: 'x' } });
ok(again.id === save.id, 're-saving keeps the same id, so the row is updated not duplicated');

// The half-finished case this feature exists for.
const noAddr = run({ action: 'save', fields: { Beds: '2' } });
ok(noAddr.ok === true, 'a draft with NO address still saves — that is the whole point');
ok(noAddr.address === '', 'and carries an empty address rather than failing');

ok(run({ action: 'list' }).ok === true, 'list routes');
ok(run({ action: 'load', id: 'abc' }).params[0] === 'abc', 'load binds the id');
ok(run({ action: 'delete', id: 'abc' }).params[0] === 'abc', 'delete binds the id');

ok(run({ action: 'explode' }).ok === false, 'an unknown action is refused');
ok(run({ action: 'load' }).ok === false, 'load without an id is refused, not run against everything');
ok(run({ action: 'delete' }).ok === false, 'and so is delete — this one matters');

// ------------------------------------------------------------- shaping
console.log('\nResponse shaping:\n');
const shape = src('Shape Response');
const shaped = (action, rows, r) => new Function('$', '$input', shape)(
  () => ({ first: () => ({ json: Object.assign({ action }, r || {}) }) }),
  { all: () => rows.map((j) => ({ json: j })) })[0].json;

// A Postgres node with an empty result still emits one item. Unfiltered, an
// empty table rendered as a single blank draft row in the picker.
ok(shaped('list', [{}]).drafts.length === 0, 'an empty table lists ZERO drafts, not one blank row');
ok(shaped('list', [{ error: 'boom' }]).drafts.length === 0, 'and an error row is not a draft either');
const one = shaped('list', [{ id: 'd1', address: '', saved_by: 'Jorge', updated_at: 'T' }]);
ok(one.drafts[0].address === '(no address yet)', 'an addressless draft still gets a label');
ok(one.drafts[0].savedBy === 'Jorge', 'and says whose it is');

const loaded = shaped('load', [{ id: 'd1', address: 'A', payload: { Beds: '4' } }]);
ok(loaded.fields.Beds === '4', 'load returns the saved form fields');
ok(shaped('load', [{}]).ok === false, 'loading a deleted draft says so rather than returning blanks');

// ------------------------------------------------------------- the console
console.log('\nConsole:\n');
const html = fs.readFileSync(path.join(__dirname, 'dist', 'index.html'), 'utf8');
ok(/DRAFTS_URL:\s*"\/webhook\/drafts"/.test(html), 'the console points at the drafts workflow');
ok(/id="draftBtn"/.test(html), 'the Save Intake Draft button exists');
ok(/id="draftsPanel"/.test(html), 'and the shared drafts panel');
const fn = html.slice(html.indexOf('function saveDraft'), html.indexOf('function loadDraftsList'));
ok(/S_DRAFT\.id = j\.id/.test(fn), 'the id is kept after the first save, so re-saving updates one row');
ok(/typeof fetch !== "function"/.test(html),
   'draftsCall is guarded — a throw at load would take the rest of the page down with it');
ok(/panel\.hidden = true/.test(html.slice(html.indexOf('function loadDraftsList'))),
   'if the drafts store is down the panel hides and the form still works');
ok(/localStorage/.test(html.slice(html.indexOf('function whoAmI'), html.indexOf('function saveDraft'))),
   'the saver is asked once per browser, not nagged on every save');

console.log(fails === 0 ? '\nDRAFTS OK' : '\n' + fails + ' CHECK(S) FAILED');
process.exit(fails === 0 ? 0 : 1);
