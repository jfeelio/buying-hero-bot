// Builds 11-acq-report-mailer.cloud.json -- the n8n half of the weekly
// acquisitions report. GitHub Actions (weekly-acq-report/) builds the PDF and
// POSTs it here; this workflow only emails it.
//
// Security: the webhook requires the X-Report-Key header (httpHeaderAuth
// credential acqrpthdr0001, value = GitHub secret ACQ_REPORT_WEBHOOK_KEY), and
// the recipient is fixed below, so the endpoint can't be used as a relay.
const fs = require('fs');

const RECIPIENTS = 'jorge@buyinghero.com';
const GMAIL = { gmailOAuth2: { id: 'gmailbh000001', name: 'Gmail - Buying Hero' } };
const HEADER = { httpHeaderAuth: { id: 'acqrpthdr0001', name: 'Acq Report Webhook Key' } };
const id = (n) => `e0000000-0000-4000-8000-${String(n).padStart(12, '0')}`;

const nodes = [
  { parameters: { httpMethod: 'POST', path: 'acq-report', authentication: 'headerAuth',
                  responseMode: 'lastNode', options: {} },
    id: id(1), name: 'Report webhook', type: 'n8n-nodes-base.webhook', typeVersion: 2,
    position: [0, 0], webhookId: id(1), credentials: HEADER },

  { parameters: { mode: 'runOnceForAllItems', language: 'javaScript', jsCode: `
const b = $input.first().json.body || {};
if (!['report', 'failure'].includes(b.kind)) throw new Error('unknown kind: ' + b.kind);
if (b.kind === 'report' && !b.pdf_base64) throw new Error('report without pdf_base64');
return [{ json: {
  kind: b.kind,
  subject: String(b.subject || 'Acquisitions report').slice(0, 200),
  html: String(b.html || ''),
  filename: String(b.filename || 'Acquisitions Report.pdf').replace(/[^\w .()-]/g, ''),
  pdf_base64: b.pdf_base64 || '',
} }];` },
    id: id(2), name: 'Validate', type: 'n8n-nodes-base.code', typeVersion: 2, position: [220, 0] },

  { parameters: { conditions: { options: { caseSensitive: true, typeValidation: 'strict' },
      conditions: [{ leftValue: '={{ $json.kind }}', rightValue: 'report',
                     operator: { type: 'string', operation: 'equals' } }], combinator: 'and' }, options: {} },
    id: id(3), name: 'Has PDF?', type: 'n8n-nodes-base.if', typeVersion: 2, position: [440, 0] },

  { parameters: { operation: 'toBinary', sourceProperty: 'pdf_base64', binaryPropertyName: 'data',
                  options: { fileName: '={{ $json.filename }}', mimeType: 'application/pdf' } },
    id: id(4), name: 'PDF to file', type: 'n8n-nodes-base.convertToFile', typeVersion: 1.1, position: [660, -100] },

  { parameters: { resource: 'message', operation: 'send', sendTo: RECIPIENTS,
                  subject: "={{ $('Validate').item.json.subject }}", emailType: 'html',
                  message: "={{ $('Validate').item.json.html }}",
                  options: { attachmentsUi: { attachmentsBinary: [{ property: 'data' }] }, appendAttribution: false } },
    id: id(5), name: 'Email report', type: 'n8n-nodes-base.gmail', typeVersion: 2.1, position: [880, -100], credentials: GMAIL },

  { parameters: { resource: 'message', operation: 'send', sendTo: RECIPIENTS,
                  subject: '={{ $json.subject }}', emailType: 'html', message: '={{ $json.html }}',
                  options: { appendAttribution: false } },
    id: id(6), name: 'Email failure', type: 'n8n-nodes-base.gmail', typeVersion: 2.1, position: [660, 100], credentials: GMAIL },
];

const link = (...to) => ({ main: to.map((t) => (t ? [{ node: t, type: 'main', index: 0 }] : [])) });
const connections = {
  'Report webhook': link('Validate'),
  'Validate': link('Has PDF?'),
  'Has PDF?': link('PDF to file', 'Email failure'),
  'PDF to file': link('Email report'),
};

fs.writeFileSync(__dirname + '/../11-acq-report-mailer.cloud.json', JSON.stringify({
  id: 'acqreport0001', name: '11 - Weekly Acquisitions Report Mailer', nodes, connections,
  settings: { timezone: 'America/New_York', executionOrder: 'v1' }, active: false,
}, null, 2));
new Function(nodes[1].parameters.jsCode.replace(/\$input/g, 'x'));  // syntax check
console.log('wrote 11-acq-report-mailer.cloud.json |', nodes.length, 'nodes');
