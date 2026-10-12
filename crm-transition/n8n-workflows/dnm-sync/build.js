// Emits ../10-dnm-sync.cloud.json. Source of truth for the workflow — edit
// core.js / render.js / this file, rebuild, re-import. Never hand-edit the
// generated JSON or the Code nodes in the n8n UI.
//
// Daily 7am ET: every REsimpli lead tagged "remove from list" that this
// workflow has not seen before -> lead details -> Miami-Dade Property
// Appraiser lookup -> append the COUNTY's property + mailing address to the
// DNM sheet -> email Jorge. Lead ids already handled live in the workflow's
// static data, so each lead is processed and reported exactly once. Any crash
// re-enters this workflow through its Error Trigger and emails a FAILED notice.
//
//   node build.js [seedIds.json]   seeds static data with already-handled ids
const fs = require('fs');
const path = require('path');

const strip = (f) => fs.readFileSync(path.join(__dirname, f), 'utf8')
  .replace(/^module\.exports[\s\S]*?;\s*$/m, '')
  .trim();

const WORKFLOW_ID = 'dnmsync000001';
const SHEET_ID = '1J3BjoQztugQnLjQiByp4cv3oEGUH1pJcrBu55kK5gV4';
const SHEETS = `https://sheets.googleapis.com/v4/spreadsheets/${SHEET_ID}/values/`;
const RESIMPLI_BASE = 'https://api.resimpli.com/api/v6/openapi';
const MDPA = 'https://apps.miamidadepa.gov/PApublicServiceProxy/PaServicesProxy.ashx';
const NOTIFY = 'jorge@buyinghero.com';

const RESIMPLI = { httpHeaderAuth: { id: 'resimpliapi01', name: 'REsimpli API' } };
// Service account (foreclosure-agent-sa). Its scope is drive, which the Sheets API accepts.
const GOOGLE_SA = { googleApi: { id: 'HLpyDuObwROMJsg8', name: 'Google Drive - Buying Hero' } };
const GMAIL = { gmailOAuth2: { id: 'gmailbh000001', name: 'Gmail - Buying Hero' } };

let n = 0;
const id = () => `d0000000-0000-4000-8000-${String(++n).padStart(12, '0')}`;
const lib = `${strip('core.js')}\n\n${strip('render.js')}`;
const code = (name, body, position) => ({
  parameters: { mode: 'runOnceForAllItems', language: 'javaScript', jsCode: `${lib}\n\n// ---- n8n entry point ----\n${body.trim()}` },
  id: id(), name, type: 'n8n-nodes-base.code', typeVersion: 2, position,
});
const throttle = (ms) => ({ batching: { batch: { batchSize: 1, batchInterval: ms } } });
const retry = { retryOnFail: true, maxTries: 5, waitBetweenTries: 3000 };

const resimpli = (name, endpoint, jsonBody, position, options = {}) => ({
  parameters: {
    method: 'POST', url: RESIMPLI_BASE + endpoint,
    authentication: 'genericCredentialType', genericAuthType: 'httpHeaderAuth',
    sendBody: true, specifyBody: 'json', jsonBody, options,
  },
  id: id(), name, type: 'n8n-nodes-base.httpRequest', typeVersion: 4.2, position, credentials: RESIMPLI, ...retry,
});

// MDPA is public but rejects requests without a browser-ish UA + Referer.
const mdpa = (name, query, position) => ({
  parameters: {
    method: 'GET', url: MDPA,
    sendQuery: true, queryParameters: { parameters: [{ name: 'clientAppName', value: 'PropertySearch' }, ...query] },
    sendHeaders: true, headerParameters: { parameters: [
      { name: 'User-Agent', value: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36' },
      { name: 'Referer', value: 'https://apps.miamidadepa.gov/PropertySearch/' },
    ] },
    options: throttle(400),
  },
  id: id(), name, type: 'n8n-nodes-base.httpRequest', typeVersion: 4.2, position,
  ...retry, onError: 'continueRegularOutput',
});

const sheetsHttp = (name, method, url, position, extra = {}) => ({
  parameters: { method, url, authentication: 'predefinedCredentialType', nodeCredentialType: 'googleApi', ...extra, options: {} },
  id: id(), name, type: 'n8n-nodes-base.httpRequest', typeVersion: 4.2, position, credentials: GOOGLE_SA, ...retry,
});

const ifNode = (name, left, operation, right, position) => ({
  parameters: {
    conditions: {
      options: { caseSensitive: true, leftValue: '', typeValidation: 'loose' },
      conditions: [{ id: 'c1', leftValue: left, rightValue: right, operator: { type: 'number', operation } }],
      combinator: 'and',
    },
    options: {},
  },
  id: id(), name, type: 'n8n-nodes-base.if', typeVersion: 2, position,
});

const nodes = [
  { parameters: { rule: { interval: [{ field: 'cronExpression', expression: '0 7 * * *' }] } },
    id: id(), name: 'Daily 7am ET', type: 'n8n-nodes-base.scheduleTrigger', typeVersion: 1.2, position: [0, 0] },
  { parameters: {}, id: id(), name: 'Run manually', type: 'n8n-nodes-base.manualTrigger', typeVersion: 1, position: [0, 200] },

  resimpli('Count leads', '/lead/list', '={{ JSON.stringify({ page: 1, limit: 1 }) }}', [220, 100]),
  code('Plan pages', `
const count = Number($input.first().json.data.count);
if (!count) throw new Error('REsimpli returned no lead count');
// One spare page: leads added mid-pull shift everything by a slot.
return Array.from({ length: Math.ceil(count / 100) + 1 }, (_, i) => ({ json: { page: i + 1, count } }));`, [440, 100]),
  resimpli('List leads', '/lead/list', '={{ JSON.stringify({ page: $json.page, limit: 100 }) }}', [660, 100], throttle(700)),
  code('Pick new tagged', `
const count = $('Plan pages').first().json.count;
const { total, ids } = pickTagged($input.all().map((i) => i.json));
// A short pull would silently miss tagged leads. Fail loudly instead.
if (total < count * 0.95) throw new Error(\`Only pulled \${total} of \${count} REsimpli leads - aborting\`);
const processed = $getWorkflowStaticData('global').processed || {};
const fresh = ids.filter((id) => !processed[id]);
if (!fresh.length) return [{ json: { newCount: 0, tagged: ids.length } }];
return fresh.map((leadId) => ({ json: { leadId, newCount: fresh.length, tagged: ids.length } }));`, [880, 100]),
  ifNode('Anything new?', '={{ $json.newCount }}', 'gt', 0, [1100, 100]),

  resimpli('Lead details', '/lead/details', '={{ JSON.stringify({ leadId: $json.leadId }) }}', [1320, 0], throttle(700)),
  code('Prep county lookup', `
const ids = $('Pick new tagged').all();
return $input.all().map((it, i) => {
  const leadData = it.json && it.json.data && it.json.data.leadData;
  const lead = fromDetails(leadData, ids[i].json.leadId);
  const parsed = leadData ? parseStreet(lead.raw, lead.zip) : null;
  return { json: { lead, parsed, detailsFailed: !leadData, query: parsed ? parsed.street : 'NONE', unit: parsed ? parsed.unit : '' } };
});`, [1540, 0]),
  mdpa('County: find parcel', [
    { name: 'Operation', value: 'GetAddress' }, { name: 'myAddress', value: '={{ $json.query }}' },
    { name: 'myUnit', value: '={{ $json.unit }}' }, { name: 'from', value: '1' }, { name: 'to', value: '200' },
  ], [1760, 0]),
  code('Pick parcel', `
const preps = $('Prep county lookup').all();
return $input.all().map((it, i) => {
  const p = preps[i].json;
  let pick;
  if (p.detailsFailed) pick = { folio: null, reason: 'REsimpli lookup failed - will retry tomorrow' };
  else if (!p.lead.raw) pick = { folio: null, reason: 'No property address in REsimpli' };
  else if (!p.parsed) pick = { folio: null, reason: 'Address has no house number + street' };
  else pick = pickParcel(it.json, p.parsed);
  return { json: { ...pick, folio: pick.folio || '0' } };
});`, [1980, 0]),
  mdpa('County: owner + mailing', [
    { name: 'Operation', value: 'GetPropertySearchByFolio' }, { name: 'folioNumber', value: '={{ $json.folio }}' },
  ], [2200, 0]),
  { ...sheetsHttp('Read sheet', 'GET', SHEETS + encodeURIComponent('Sheet1!C:F'), [2420, 0]), executeOnce: true },
  code('Build rows', `
const preps = $('Prep county lookup').all();
const picks = $('Pick parcel').all();
const folios = $('County: owner + mailing').all();
const sheet = $input.first().json.values || [];
if (!sheet.length) throw new Error('DNM sheet read returned no rows (not even the header) - refusing to write blind');

const retryIds = [];
const resolved = preps.map((p, i) => {
  const { lead, detailsFailed } = p.json;
  const pick = picks[i].json;
  if (detailsFailed) retryIds.push(lead.leadId);
  if (pick.folio === '0') return { lead, county: null, reason: pick.reason };
  const county = countyAddress(folios[i].json, lead);
  if (!county) { retryIds.push(lead.leadId); return { lead, county: null, reason: 'County record lookup failed - will retry tomorrow' }; }
  return { lead, county };
});
const today = new Date().toLocaleDateString('en-US', { timeZone: 'America/New_York', month: '2-digit', day: '2-digit', year: 'numeric' });
const result = buildRows(resolved, sheet, today);
// Transient failures are retried tomorrow, so don't mark them handled.
const handled = preps.map((p) => p.json.lead.leadId).filter((id) => id && !retryIds.includes(id));
return [{ json: { ...result, count: result.rows.length, handled } }];`, [2640, 0]),
  ifNode('Rows to write?', '={{ $json.count }}', 'gt', 0, [2860, 0]),
  sheetsHttp('Append rows', 'POST',
    SHEETS + encodeURIComponent('Sheet1!A:K') + ':append?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS',
    [3080, -100],
    { sendBody: true, specifyBody: 'json', jsonBody: '={{ JSON.stringify({ values: $json.rows }) }}' }),
  code('Compose email', `
let result = { added: [], duplicates: [], needsReview: [], handled: [] };
try { result = $('Build rows').first().json; } catch (e) { /* nothing new today */ }
// Record handled ids only now, after the sheet write succeeded.
const store = $getWorkflowStaticData('global');
store.processed = store.processed || {};
for (const id of result.handled || []) store.processed[id] = new Date().toISOString().slice(0, 10);
return [{ json: render(result) }];`, [3300, 100]),
  { parameters: { sendTo: NOTIFY, subject: '={{ $json.subject }}', emailType: 'html',
      message: '={{ $json.html }}', options: { appendAttribution: false } },
    id: id(), name: 'Email Jorge', type: 'n8n-nodes-base.gmail', typeVersion: 2.1,
    position: [3520, 100], credentials: GMAIL },

  { parameters: {}, id: id(), name: 'On failure', type: 'n8n-nodes-base.errorTrigger', typeVersion: 1, position: [2860, 400] },
  code('Compose failure', `
const e = $json.execution || {};
const msg = [(e.error && e.error.message) || 'Unknown error', e.lastNodeExecuted ? 'Failed at node: ' + e.lastNodeExecuted : '', e.url || ''].filter(Boolean).join('\\n');
return [{ json: render(null, msg) }];`, [3300, 400]),
];

const link = (...to) => ({ main: to.map((t) => (t ? [{ node: t, type: 'main', index: 0 }] : [])) });
const connections = {
  'Daily 7am ET': link('Count leads'),
  'Run manually': link('Count leads'),
  'Count leads': link('Plan pages'),
  'Plan pages': link('List leads'),
  'List leads': link('Pick new tagged'),
  'Pick new tagged': link('Anything new?'),
  'Anything new?': link('Lead details', 'Compose email'),
  'Lead details': link('Prep county lookup'),
  'Prep county lookup': link('County: find parcel'),
  'County: find parcel': link('Pick parcel'),
  'Pick parcel': link('County: owner + mailing'),
  'County: owner + mailing': link('Read sheet'),
  'Read sheet': link('Build rows'),
  'Build rows': link('Rows to write?'),
  'Rows to write?': link('Append rows', 'Compose email'),
  'Append rows': link('Compose email'),
  'Compose email': link('Email Jorge'),
  'On failure': link('Compose failure'),
  'Compose failure': link('Email Jorge'),
};

const seedFile = process.argv[2];
const seed = seedFile ? JSON.parse(fs.readFileSync(seedFile, 'utf8')) : null;
const workflow = {
  id: WORKFLOW_ID, name: '10 - REsimpli Remove-from-List -> DNM Sheet',
  nodes, connections, active: true,
  settings: { timezone: 'America/New_York', executionOrder: 'v1', errorWorkflow: WORKFLOW_ID },
  ...(seed ? { staticData: { global: { processed: Object.fromEntries(seed.map((i) => [i, 'seed'])) } } } : {}),
};

fs.writeFileSync(path.join(__dirname, '..', '10-dnm-sync.cloud.json'), JSON.stringify(workflow, null, 2));
console.log('wrote 10-dnm-sync.cloud.json -', nodes.length, 'nodes', seed ? `(seeded ${seed.length} ids)` : '');
