// The Create Drive folder button, on both sides of the wire.
//
//   node drive-folder-test.js
//
// The two things that matter: the address is safe to use as a folder name,
// and clicking twice does not make two folders for one house.
const fs = require('fs');
const path = require('path');

const DIR = path.join(__dirname, '..', '..', 'crm-transition', 'n8n-workflows');
const wf = JSON.parse(fs.readFileSync(path.join(DIR, '06-drive-folder.cloud.json'), 'utf8'));
const node = (n) => wf.nodes.find((x) => x.name === n);
const src = (n) => node(n).parameters.jsCode;

let fails = 0;
const ok = (c, m) => { console.log((c ? '  PASS  ' : '  FAIL  ') + m); if (!c) fails++; };

// ------------------------------------------------- the address becomes a name
console.log('Address cleaning:\n');
const validate = src('Validate Address');
const run = (address) => new Function('$input',
  validate)({ first: () => ({ json: { body: { address } } }) })[0].json;

const clean = run('  2165 NW 58th St.   Miami, FL 33142 ');
ok(clean.ok === true, 'a normal address passes');
ok(clean.address === '2165 NW 58th St. Miami, FL 33142',
   'runs of whitespace collapse: "' + clean.address + '"');
ok(clean.photosName === 'Photos and Videos for 2165 NW 58th St. Miami, FL 33142',
   'the photos folder is named after it');

const slash = run('123 Main St / Unit 2');
ok(slash.address.indexOf('/') === -1, 'a forward slash is stripped: "' + slash.address + '"');
const back = run('123 Main St ' + String.fromCharCode(92) + ' Rear');
ok(back.address.indexOf(String.fromCharCode(92)) === -1, 'so is a backslash');
const nl = run('123 Main St\nApt 4');
ok(nl.address === '123 Main St Apt 4', 'newlines collapse rather than breaking the name');

// Drive's q= syntax is single-quoted; an apostrophe must be escaped or the
// lookup is malformed and the workflow creates a duplicate folder.
const apos = run("123 O'Brien Way");
ok(apos.addressQ === "123 O" + String.fromCharCode(92) + "'Brien Way",
   'an apostrophe is escaped for the Drive query: ' + JSON.stringify(apos.addressQ));
ok(apos.address === "123 O'Brien Way", 'but the folder name keeps it');

ok(run('').ok === false, 'an empty address is refused');
ok(run('   ').ok === false, 'so is whitespace only');
ok(run('x'.repeat(200)).ok === false, 'and an absurd one');

// --------------------------------------------------------------- idempotency
console.log('\nClicking twice must not make two folders:\n');
ok(/in parents and name = /.test(node('Find Existing Folder').parameters.url),
   'it looks for the folder by name under the parent before creating');
const reuse = src('Create or Reuse?');
const reuseRun = (files) => new Function('$', '$input', reuse)(
  () => ({ first: () => ({ json: { address: 'A', parentId: 'P' } }) }),
  { first: () => ({ json: { files } }) })[0].json;
ok(reuseRun([{ id: 'f1', webViewLink: 'L' }]).reused === true, 'an existing folder is reused');
ok(reuseRun([{ id: 'f1', webViewLink: 'L' }]).existingId === 'f1', 'and its id carried forward');
ok(reuseRun([]).reused === false, 'a missing one is created');
ok(/photos and videos/.test(src('Photos Needed?')),
   'the photos subfolder is matched on its prefix, so renaming the deal folder does not orphan it');

// ------------------------------------------------------------- failure modes
console.log('\nWhat must not break the button:\n');
ok(node('Copy Deal Doc').onError === 'continueRegularOutput',
   'a missing deal-doc template does not cost the whole click');
// An HTTP node's response REPLACES $json, so anything after one that still
// reads $json gets undefined. That produced .../files/undefined/copy and an
// HTML 404 that looked nothing like a Drive error.
const copyNode = node('Copy Deal Doc');
ok(String(copyNode.parameters.url).indexOf('$json.') === -1,
   'Copy Deal Doc does not read $json - the Share node before it wipes it');
ok(String(copyNode.parameters.url).indexOf("$('Photos Id')") !== -1,
   'it reads from the node that owns the ids instead');
ok(String(copyNode.parameters.jsonBody).indexOf('$json.') === -1,
   'and the same for its body');
// The service account has zero Drive storage: folders are zero-byte and work,
// a Doc copy it would own fails with storageQuotaExceeded. Everything runs as
// the OAuth user so the files are owned by a real person.
const googly = wf.nodes.filter((n) => n.parameters && n.parameters.nodeCredentialType);
ok(googly.length > 0 && googly.every((n) => n.parameters.nodeCredentialType === 'googleDriveOAuth2Api'),
   'every Drive call runs as the OAuth user, not the service account');
ok(node('Share Photos Publicly').onError === 'continueRegularOutput',
   'nor does a re-run of the public share');
const resp = src('Build Response');
ok(/dealDocError/.test(resp), 'but the doc failure IS reported back, not swallowed');
ok(/role: 'reader', type: 'anyone'/.test(node('Share Photos Publicly').parameters.jsonBody),
   'the photos folder is shared anyone-with-link, read only');
ok(node('Share Photos Publicly').parameters.url.indexOf('$json.photosId') !== -1,
   'sharing targets the PHOTOS folder, never the parent deal folder');

// ---------------------------------------------------------------- the console
console.log('\nConsole:\n');
const html = fs.readFileSync(path.join(__dirname, 'dist', 'index.html'), 'utf8');
ok(/DRIVE_URL:\s*"\/webhook\/drive-folder"/.test(html), 'the console posts to the workflow');
ok(/id="driveBtn"/.test(html), 'the button is on the form, next to the address');
ok(/Photos Videos URL/.test(html.slice(html.indexOf('function createDriveFolder'))),
   'and fills the Photos/Videos field from the result');
const fn = html.slice(html.indexOf('function createDriveFolder'), html.indexOf('function createDriveFolder') + 2600);
ok(/!photoEl\.value\.trim\(\)/.test(fn),
   'without clobbering a link the dispo agent already pasted');
ok(/AbortController/.test(fn), 'and it cannot hang forever');

console.log(fails === 0 ? '\nDRIVE FOLDER OK' : '\n' + fails + ' CHECK(S) FAILED');
process.exit(fails === 0 ? 0 : 1);
