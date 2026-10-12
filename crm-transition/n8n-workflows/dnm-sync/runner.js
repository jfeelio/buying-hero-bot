// Dry run of the whole pipeline with the same core.js the workflow bundles,
// against live REsimpli + Miami-Dade PA data. Writes nothing to the sheet.
//   node runner.js <sheetValuesC-F.json> <leadIds.json> [out.json]
const fs = require('fs');
const core = require('./core');
const { render } = require('./render');
const KEY = fs.readFileSync(require('os').homedir() + '/.resimpli_key', 'utf8').trim();
const MDPA = 'https://apps.miamidadepa.gov/PApublicServiceProxy/PaServicesProxy.ashx';
const MDPA_HEADERS = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36', Referer: 'https://apps.miamidadepa.gov/PropertySearch/' };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const details = async (leadId) => {
  const res = await fetch('https://api.resimpli.com/api/v6/openapi/lead/details', {
    method: 'POST', headers: { Authorization: KEY, 'Content-Type': 'application/json' }, body: JSON.stringify({ leadId }),
  });
  return (await res.json()).data.leadData;
};
const mdpa = async (params) => {
  const qs = new URLSearchParams({ clientAppName: 'PropertySearch', ...params });
  return (await fetch(`${MDPA}?${qs}`, { headers: MDPA_HEADERS })).json();
};

(async () => {
  const [sheetFile, idsFile, outFile] = process.argv.slice(2);
  const sheet = JSON.parse(fs.readFileSync(sheetFile, 'utf8'));
  const ids = JSON.parse(fs.readFileSync(idsFile, 'utf8'));
  const resolved = [];
  for (const leadId of ids) {
    const lead = core.fromDetails(await details(leadId), leadId);
    await sleep(700);
    if (!lead.raw) { resolved.push({ lead, county: null, reason: 'No property address in REsimpli' }); continue; }
    const parsed = core.parseStreet(lead.raw, lead.zip);
    if (!parsed) { resolved.push({ lead, county: null, reason: 'Address has no house number + street' }); continue; }
    const pick = core.pickParcel(await mdpa({ Operation: 'GetAddress', myAddress: parsed.street, myUnit: parsed.unit, from: 1, to: 200 }), parsed);
    if (!pick.folio) { resolved.push({ lead, county: null, reason: pick.reason }); continue; }
    const county = core.countyAddress(await mdpa({ Operation: 'GetPropertySearchByFolio', folioNumber: pick.folio }), lead);
    resolved.push(county ? { lead, county } : { lead, county: null, reason: 'County record lookup failed' });
    await sleep(400);
  }
  const result = core.buildRows(resolved, sheet, 'MM/DD/YYYY');
  console.log(render(result).subject, `| ${result.duplicates.length} already on sheet`);
  if (outFile) fs.writeFileSync(outFile, JSON.stringify(result, null, 1));
})();
