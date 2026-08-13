/**
 * Buying Hero — Deal Sheet Apps Script (simplified)
 *
 * Two functions:
 *   1. Custom menu: "🏠 Buying Hero → New Deal from Address…" — duplicates the
 *      🏠 Deal Calculator tab, renames it to the address.
 *   2. Web app endpoint: lets the bot at jfeelio.github.io/buying-hero-bot/
 *      create deal tabs pre-filled with values.
 *
 * Install:
 *   1. Open the sheet: https://docs.google.com/spreadsheets/d/16of8fZhqeYlF_UzBWX3GoYiIOZJKT6F57JhzvKV5s0g/edit
 *   2. Extensions → Apps Script
 *   3. Replace any existing Code.gs with this file's contents
 *   4. Save (Ctrl+S)
 *   5. Reload the sheet — "🏠 Buying Hero" menu appears after a second
 *   6. (For bot integration) Deploy → New deployment → Web app
 *      - Execute as: Me
 *      - Who has access: Anyone
 *      - Copy URL → paste into docs/index.html WEB_APP_URL
 */

const SHEET_ID = '16of8fZhqeYlF_UzBWX3GoYiIOZJKT6F57JhzvKV5s0g';
const CALC_TAB = '🏠 Deal Calculator';
const CONFIG_TAB = '⚙️ Config';


// ───────────────────────────────────────────────────────────────────────────
// Menu
// ───────────────────────────────────────────────────────────────────────────

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('🏠 Buying Hero')
    .addItem('➕  New Deal from Address…', 'menuNewDeal')
    .addItem('🧪  Create Sample Deal (test)', 'menuCreateSampleDeal')
    .addToUi();
}


function menuNewDeal() {
  const ui = SpreadsheetApp.getUi();
  const resp = ui.prompt('🏠 New Deal', 'Enter property address:', ui.ButtonSet.OK_CANCEL);
  if (resp.getSelectedButton() !== ui.Button.OK) return;
  const address = resp.getResponseText().trim();
  if (!address) return;
  createDealFromAddress(address);
}


function menuCreateSampleDeal() {
  const ui = SpreadsheetApp.getUi();
  const resp = ui.alert('Create sample deal?', 'Creates "123 Test Lane, Miami FL" with sample numbers so you can see how it works.', ui.ButtonSet.YES_NO);
  if (resp !== ui.Button.YES) return;
  const sheet = createDealFromAddress('123 Test Lane, Miami FL');
  if (sheet) {
    sheet.getRange('B6').setValue(180000);
    sheet.getRange('B7').setValue(45000);
    sheet.getRange('B9').setValue(340000);
    sheet.getRange('B10').setValue(1400);
    sheet.getRange('A3').setValue('John Test');
    sheet.getRange('B3').setValue('305-555-0100');
    sheet.getRange('C3').setValue('Tax Deed List');
    SpreadsheetApp.getActiveSpreadsheet().setActiveSheet(sheet);
  }
}


// ───────────────────────────────────────────────────────────────────────────
// Core: duplicate the Deal Calculator tab, rename to address
// ───────────────────────────────────────────────────────────────────────────

function createDealFromAddress(rawAddress) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const calc = ss.getSheetByName(CALC_TAB);
  if (!calc) {
    throw new Error('Deal Calculator tab not found: ' + CALC_TAB);
  }

  const tabName = sanitizeTabName(rawAddress);
  const finalTabName = ensureUniqueTabName(ss, tabName);

  const newSheet = calc.copyTo(ss);
  newSheet.setName(finalTabName);
  newSheet.showSheet();

  // Position right after the Deal Calculator tab
  const calcPos = calc.getIndex();
  ss.setActiveSheet(newSheet);
  ss.moveActiveSheet(calcPos + 1);

  // Populate address bar (A1) and date added (D3)
  newSheet.getRange('A1').setValue('🏠  ' + rawAddress);
  newSheet.getRange('D3').setValue(new Date());
  newSheet.getRange('F3').setValue(formatDate(new Date()));

  ss.toast('Created deal tab: ' + finalTabName, '🏠 Buying Hero', 5);
  return newSheet;
}


// ───────────────────────────────────────────────────────────────────────────
// Tab name sanitization
// ───────────────────────────────────────────────────────────────────────────

function sanitizeTabName(address) {
  let name = String(address)
    .replace(/[:\\\/?*\[\]]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
  if (name.length > 50) name = name.substring(0, 50).trim();
  if (!name) name = 'New Deal';
  return name;
}


function ensureUniqueTabName(ss, baseName) {
  const sheets = ss.getSheets();
  const existing = {};
  sheets.forEach(function(s) { existing[s.getName()] = true; });
  if (!existing[baseName]) return baseName;
  let n = 2;
  while (existing[baseName + ' (' + n + ')']) n++;
  return baseName + ' (' + n + ')';
}


function formatDate(d) {
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return yyyy + '-' + mm + '-' + dd;
}


// ───────────────────────────────────────────────────────────────────────────
// Web App endpoint (for the docs/index.html bot integration)
// ───────────────────────────────────────────────────────────────────────────

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);

    if (body.action === 'createDeal') {
      const address = (body.address || '').trim();
      if (!address) return jsonOut({ ok: false, error: 'address required' });

      const ss = SpreadsheetApp.openById(SHEET_ID);
      const calc = ss.getSheetByName(CALC_TAB);
      if (!calc) return jsonOut({ ok: false, error: 'Deal Calculator tab not found' });

      const tabName = sanitizeTabName(address);
      const finalTabName = ensureUniqueTabName(ss, tabName);
      const newSheet = calc.copyTo(ss);
      newSheet.setName(finalTabName);
      newSheet.showSheet();

      const calcPos = calc.getIndex();
      ss.setActiveSheet(newSheet);
      ss.moveActiveSheet(calcPos + 1);

      newSheet.getRange('A1').setValue('🏠  ' + address);
      newSheet.getRange('D3').setValue(new Date());
      newSheet.getRange('F3').setValue(formatDate(new Date()));

      if (body.values) {
        const v = body.values;
        if (v.pp != null)     newSheet.getRange('B6').setValue(Number(v.pp));
        if (v.rehab != null)  newSheet.getRange('B7').setValue(Number(v.rehab));
        if (v.hold != null)   newSheet.getRange('B8').setValue(Number(v.hold));
        if (v.arv != null)    newSheet.getRange('B9').setValue(Number(v.arv));
        if (v.target != null) newSheet.getRange('B32').setValue(Number(v.target));
      }

      return jsonOut({
        ok: true,
        tabName: finalTabName,
        gid: newSheet.getSheetId(),
        url: 'https://docs.google.com/spreadsheets/d/' + SHEET_ID + '/edit#gid=' + newSheet.getSheetId(),
      });
    }

    return jsonOut({ ok: false, error: 'unknown action: ' + body.action });
  } catch (err) {
    return jsonOut({ ok: false, error: String(err) });
  }
}


function doGet(e) {
  return jsonOut({ ok: true, ping: 'buying-hero-deal-sheet' });
}


function jsonOut(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
