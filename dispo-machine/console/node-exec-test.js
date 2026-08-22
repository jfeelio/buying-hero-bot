// Executes EVERY Code node in every workflow, to catch the one class of bug the
// other tests structurally cannot see: code that parses fine but throws the
// instant it runs.
//
//   node node-exec-test.js
//
// On 2026-08-19 a botched edit left
//     const subject = collapseRepeat(subjectRaw);
// on line 2 of W12's mapper - 137 lines above collapseRepeat's definition and
// 156 above subjectRaw's. Every execution died with a ReferenceError before
// reading a single row, and the InvestorBase pipeline silently wrote nothing
// for three days. Nobody found out until a buyer search came back empty.
//
// All 16 test files were green that entire time, because they pull FUNCTIONS
// out of the node source and test those. Not one of them asked the only
// question that mattered: does the node run at all?
//
// The check is deliberately narrow. Mock data here is thin, so a TypeError
// about some property being undefined is expected and is reported, not failed.
// Only structural failures - a name that does not exist, a const used before
// its declaration, a syntax error, an infinite loop - fail the build. Those
// are exactly the failures that are independent of the payload, which is what
// makes them safe to assert on.
const fs = require('fs');
const path = require('path');
const vm = require('vm');

// WF_DIR lets this be pointed at an older copy of the workflows, which is how
// the harness was proved against the pre-fix W12 that caused the outage.
const DIR = process.env.WF_DIR
  || path.join(__dirname, '..', '..', 'crm-transition', 'n8n-workflows');

let fails = 0;
const ok = (c, m) => { console.log((c ? '  PASS  ' : '  FAIL  ') + m); if (!c) fails++; };

// ---------------------------------------------------------------- the mock
// A value that tolerates nearly any shape a node might ask of it, so execution
// gets deep enough to expose a real structural error instead of dying on the
// first property access. Anything can be read, called, or iterated.
const ARRAY_METHODS = ['map', 'filter', 'find', 'findIndex', 'forEach', 'slice',
                       'concat', 'sort', 'reverse', 'reduce', 'some', 'every',
                       'flat', 'keys', 'entries', 'includes', 'indexOf'];

function loose() {
  const target = function () { return loose(); };
  return new Proxy(target, {
    get(t, prop) {
      if (prop === Symbol.iterator) return function* () {};
      if (prop === Symbol.toPrimitive) return () => '';
      if (prop === 'then') return undefined;              // must not look like a promise
      if (prop === 'length') return 0;
      if (prop === 'toString' || prop === 'valueOf') return () => '';
      if (prop === 'join') return () => '';
      if (prop === 'split') return () => [];
      if (prop === 'indexOf') return () => -1;
      if (ARRAY_METHODS.indexOf(prop) !== -1) return () => [];
      return loose();
    },
    apply() { return loose(); },
    has() { return true; },
  });
}

function sandbox() {
  const item = () => ({ json: loose(), binary: {} });
  return {
    $: () => ({ first: item, last: item, all: () => [], item: item() }),
    $input: { first: item, last: item, all: () => [], item: item() },
    $json: loose(), $node: loose(), $workflow: loose(), $execution: loose(),
    $vars: loose(), $env: loose(), $items: () => [], $itemMatching: item,
    $now: new Date(), $today: new Date(),
    console: { log() {}, error() {}, warn() {}, info() {} },
    JSON, Math, Date, Number, String, Boolean, Array, Object, RegExp, Map, Set,
    isFinite, isNaN, parseInt, parseFloat, encodeURIComponent, decodeURIComponent,
    Buffer, Error, TypeError, RangeError, Promise,
  };
}

// Failures that do not depend on the payload. These are the ones worth failing on.
const STRUCTURAL = [
  [/is not defined/, 'uses a name that does not exist'],
  [/before initialization/, 'uses a const/let above its own declaration'],
  [/Unexpected (token|identifier|end of input)/, 'syntax error'],
  [/Invalid or unexpected token/, 'syntax error'],
  [/Identifier .* has already been declared/, 'duplicate declaration'],
  [/Script execution timed out/, 'never terminates'],
  [/Maximum call stack/, 'infinite recursion'],
];

function classify(err) {
  if (!err) return null;
  const msg = String(err && err.message || err);
  for (const [re, what] of STRUCTURAL) if (re.test(msg)) return { fatal: true, what, msg };
  return { fatal: false, what: 'needs richer mock data', msg };
}

function runSource(jsCode) {
  try {
    vm.runInNewContext('(function(){\n' + jsCode + '\n})()', sandbox(), { timeout: 4000 });
    return null;
  } catch (e) { return e; }
}

// ------------------------------------------- the detector must actually work
// A test that cannot fail is worse than no test. Prove the detector catches the
// exact shape of the bug that shipped, before trusting it on real workflows.
console.log('The detector catches what it is for:\n');

const BUG = 'const subject = collapseRepeat(subjectRaw);\n'
          + 'const collapseRepeat = (s) => String(s || "");\n'
          + 'const subjectRaw = "x";\n'
          + 'return [{ json: { subject } }];';
const caught = classify(runSource(BUG));
ok(caught !== null && caught.fatal === true,
   'the 2026-08-19 bug shape is caught: ' + (caught ? caught.msg : 'NOT CAUGHT'));

const GOOD = 'const collapseRepeat = (s) => String(s || "");\n'
           + 'const subjectRaw = $("Some Node").first().json.address;\n'
           + 'const subject = collapseRepeat(subjectRaw);\n'
           + 'return [{ json: { subject } }];';
ok(classify(runSource(GOOD)) === null, 'and the corrected form passes cleanly');

ok(classify(runSource('return $("N").first().json.a.b.c.map(x => x).length;')) === null,
   'deep property access on thin mock data is tolerated, not failed');
ok(classify(runSource('while (true) {}')).fatal === true, 'a node that never terminates is caught');
ok(classify(runSource('const a = 1; const a = 2;')).fatal === true, 'a duplicate declaration is caught');

// ------------------------------------------------------- every real node
console.log('\nEvery Code node in every workflow runs:\n');

const files = fs.readdirSync(DIR).filter((f) => f.endsWith('.json')).sort();
let checked = 0;
const soft = [];

for (const f of files) {
  let wf;
  try {
    wf = JSON.parse(fs.readFileSync(path.join(DIR, f), 'utf8'));
  } catch (e) {
    ok(false, f + ' — is not valid JSON: ' + e.message);
    continue;
  }
  const codeNodes = (wf.nodes || []).filter((n) => n.parameters && n.parameters.jsCode);
  if (!codeNodes.length) continue;

  console.log('  ' + f + '  (' + codeNodes.length + ' code node' + (codeNodes.length > 1 ? 's' : '') + ')');
  for (const n of codeNodes) {
    checked++;
    const verdict = classify(runSource(n.parameters.jsCode));
    if (verdict && verdict.fatal) {
      ok(false, '   ' + n.name + ' — ' + verdict.what + ': ' + verdict.msg);
    } else {
      ok(true, '   ' + n.name);
      if (verdict) soft.push(f + ' · ' + n.name + ' — ' + verdict.msg.slice(0, 70));
    }
  }
}

ok(checked > 0, '\nfound code nodes to check at all (' + checked + ' checked)');

if (soft.length) {
  console.log('\nRan, but stopped on thin mock data (not failures):');
  for (const s of soft) console.log('   - ' + s);
}

console.log(fails === 0 ? '\nNODE EXEC OK' : '\n' + fails + ' CHECK(S) FAILED');
process.exit(fails === 0 ? 0 : 1);
