// Email body for the DNM sync. Inline styles only — Gmail strips <style>.
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const SHEET_URL = 'https://docs.google.com/spreadsheets/d/1J3BjoQztugQnLjQiByp4cv3oEGUH1pJcrBu55kK5gV4/edit';

function table(rows, cols) {
  if (!rows.length) return '';
  const th = cols.map((c) => `<th style="text-align:left;padding:4px 10px;border-bottom:1px solid #ccc">${esc(c[0])}</th>`).join('');
  const tr = rows.map((r) => '<tr>' + cols.map((c) => `<td style="padding:4px 10px;border-bottom:1px solid #eee">${c[1](r)}</td>`).join('') + '</tr>').join('');
  return `<table style="border-collapse:collapse;font-size:13px">${'<tr>' + th + '</tr>'}${tr}</table>`;
}

function render(result, error) {
  const font = 'font-family:Arial,sans-serif;font-size:14px;color:#222';
  if (error) {
    return {
      subject: 'DNM sync FAILED',
      html: `<div style="${font}"><p><b>The REsimpli → DNM sheet sync failed.</b> Nothing was written for this run; it will retry tomorrow at 7am.</p>
<p style="white-space:pre-wrap;background:#f6f6f6;padding:8px">${esc(error)}</p>
<p><a href="${SHEET_URL}">Open the DNM sheet</a></p></div>`,
    };
  }
  const { added, duplicates, needsReview } = result;
  const subject = `DNM sync: ${added.length} added` + (needsReview.length ? `, ${needsReview.length} need review` : '');
  const who = (r) => esc(r.name || '(no name)');
  const html = `<div style="${font}">
<p><b>${added.length}</b> propert${added.length === 1 ? 'y' : 'ies'} added to the <a href="${SHEET_URL}">DNM sheet</a>, addresses verified against Miami-Dade Property Appraiser records.${duplicates.length ? ` ${duplicates.length} newly tagged lead${duplicates.length === 1 ? ' was' : 's were'} already on the sheet.` : ''}</p>
${table(added, [['Lead', who], ['County address', (r) => esc(r.address)], ['REsimpli had', (r) => esc(r.was)]])}
${needsReview.length ? `<p style="margin-top:18px"><b>${needsReview.length}</b> tagged lead${needsReview.length === 1 ? '' : 's'} could not be verified and were NOT added. Add these by hand if they belong on the list:</p>
${table(needsReview, [['Lead', who], ['REsimpli address', (r) => esc(r.address || '(none)')], ['Why', (r) => esc(r.reason)]])}` : ''}
<p style="color:#888;font-size:12px;margin-top:18px">Each lead is reported once. Runs daily at 7am ET.</p>
</div>`;
  return { subject, html };
}

module.exports = { render };
