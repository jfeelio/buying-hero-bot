/**
 * Buying Hero — Deal Analyzer save backend
 *
 * Setup:
 *   1. Go to https://script.google.com → New Project (name it "Deal Analyzer Backend")
 *   2. Paste this whole file into Code.gs (replace anything there)
 *   3. Save the project
 *   4. Deploy → New deployment → Type: Web app
 *      - Execute as: Me (your Google account)
 *      - Who has access: Anyone
 *      - Click Deploy. Authorize when prompted.
 *   5. Copy the Web App URL it gives you
 *   6. Open docs/index.html, find "WEB_APP_URL", paste the URL there
 *   7. Commit + push. Saves now sync to the sheet across all devices.
 *
 * Re-deploying after changes: Deploy → Manage deployments → edit → New version → Deploy.
 * (The URL stays the same once created.)
 */

const SHEET_ID = '16of8fZhqeYlF_UzBWX3GoYiIOZJKT6F57JhzvKV5s0g';
const SHEET_NAME = 'Estimates';

const FIELDS = [
  'pp','rehab','hold','arv','target','origPts','apr','downPct',
  'titleFees','titleInsPct','govRecPct','homeInsp','notary','survey','transCoord','otherPurch',
  'appraisal','otherLend',
  'utilities','bldgIns','hoa',
  'buyersAgt','sellersAgt','saleTitleFee','saleTitleIns'
];

const HEADERS = ['id','name','savedAt','verdict','arv','mao','netProfit'].concat(FIELDS);

function getSheet_() {
  const ss = SpreadsheetApp.openById(SHEET_ID);
  let sh = ss.getSheetByName(SHEET_NAME);
  if (!sh) sh = ss.insertSheet(SHEET_NAME);
  if (sh.getLastRow() === 0) {
    sh.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]);
    sh.setFrozenRows(1);
  }
  return sh;
}

function listEstimates_() {
  const sh = getSheet_();
  const lastRow = sh.getLastRow();
  if (lastRow < 2) return [];
  const rows = sh.getRange(2, 1, lastRow - 1, HEADERS.length).getValues();
  const out = rows.map(function(row) {
    const obj = {};
    HEADERS.forEach(function(h, i) { obj[h] = row[i]; });
    const values = {};
    FIELDS.forEach(function(f) { values[f] = obj[f]; });
    return {
      id: String(obj.id),
      name: obj.name,
      savedAt: obj.savedAt,
      summary: {
        verdict: obj.verdict,
        arv: obj.arv,
        mao: obj.mao,
        netProfit: obj.netProfit
      },
      values: values
    };
  });
  out.reverse();
  return out;
}

function saveEstimate_(body) {
  const sh = getSheet_();
  const id = String(Date.now());
  const summary = body.summary || {};
  const values = body.values || {};
  const row = [
    id,
    body.name || '(unnamed)',
    new Date().toISOString(),
    summary.verdict || '',
    summary.arv || '',
    summary.mao || '',
    summary.netProfit || ''
  ];
  FIELDS.forEach(function(f) { row.push(values[f] != null ? values[f] : ''); });
  sh.appendRow(row);
  return { ok: true, id: id };
}

function deleteEstimate_(id) {
  const sh = getSheet_();
  const lastRow = sh.getLastRow();
  if (lastRow < 2) return { ok: false, error: 'no rows' };
  const ids = sh.getRange(2, 1, lastRow - 1, 1).getValues().map(function(r) { return String(r[0]); });
  const idx = ids.indexOf(String(id));
  if (idx === -1) return { ok: false, error: 'id not found' };
  sh.deleteRow(idx + 2);
  return { ok: true };
}

function jsonOut_(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function doGet(e) {
  try {
    return jsonOut_({ ok: true, estimates: listEstimates_() });
  } catch (err) {
    return jsonOut_({ ok: false, error: String(err) });
  }
}

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    if (body.action === 'save')   return jsonOut_(saveEstimate_(body));
    if (body.action === 'delete') return jsonOut_(deleteEstimate_(body.id));
    return jsonOut_({ ok: false, error: 'unknown action: ' + body.action });
  } catch (err) {
    return jsonOut_({ ok: false, error: String(err) });
  }
}
