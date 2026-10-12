// Pure logic for the DNM sync. No I/O — the HTTP nodes do the fetching — so
// runner.js can exercise the exact same code locally against live data.
//
// Pipeline: REsimpli lead -> parse its address -> Miami-Dade Property
// Appraiser (MDPA) lookup -> write the COUNTY's property + mailing address.
// REsimpli addresses are hand-typed and often wrong (cities appended to the
// street, a Miami house filed under Cape Coral), so they are only used to find
// the parcel, never written as-is.

const TAG_ID = '689e51591f1ec236f4f844b9'; // "remove from list"

const clean = (s) => String(s || '').toUpperCase().replace(/[.,#]/g, ' ').replace(/\s+/g, ' ').trim();

const SUFFIXES = ['ST', 'AVE', 'CT', 'TER', 'TERR', 'PL', 'RD', 'WAY', 'DR', 'LN', 'BLVD', 'CIR', 'TRL', 'PATH', 'HWY', 'PKWY', 'CSWY', 'LOOP', 'ROW'];
const LONG = { STREET: 'ST', AVENUE: 'AVE', COURT: 'CT', TERRACE: 'TER', TERR: 'TER', PLACE: 'PL', ROAD: 'RD', DRIVE: 'DR', LANE: 'LN', BOULEVARD: 'BLVD', CIRCLE: 'CIR' };

// Collect every tagged lead id from /lead/list pages. Paging is unstable, so dedupe.
function pickTagged(pages) {
  const seen = new Map();
  for (const page of pages) for (const l of (page && page.data && page.data.items) || []) seen.set(l._id, l);
  const tagged = [...seen.values()].filter((l) => (l.tags || []).some((t) => t._id === TAG_ID));
  return { total: seen.size, ids: tagged.map((l) => l._id) };
}

// Flatten a /lead/details response.
function fromDetails(leadData, leadId) {
  const d = leadData || {};
  const p = d.propertyInfo || {};
  const c = (d.contactData || [])[0] || {};
  return {
    leadId: d._id || leadId || null,
    raw: d.address || '',
    city: clean(p.city), zip: String(p.zip || '').slice(0, 5),
    name: c.fullName || [c.firstName, c.lastName].filter(Boolean).join(' ') || '',
  };
}

// "8220 SW 43 TER MIAMI" / "3725 Ne 169th St Apt 409, North Miami Beach, FL 33160"
// -> { street: "8220 SW 43 TER", unit: "", zip }. Everything after the street
// suffix is dropped (that is where hand-typed cities end up) except a unit.
function parseStreet(raw, fallbackZip) {
  const parts = String(raw || '').split(',');
  const first = clean(parts[0]).replace(/\b(\d+(?:ST|ND|RD|TH)?)(TERR|TER|AVE|CT|PL|WAY|DR|LN|CIR|BLVD)\b/g, '$1 $2');
  if (!/^\d+\s+\S/.test(first)) return null; // "5324", "" - no house number + street
  const words = first.split(' ');
  let end = words.length;
  const isSuffix = (w) => SUFFIXES.includes(w) || LONG[w];
  for (let i = 2; i < words.length; i++) if (isSuffix(words[i])) { end = i + 1; while (end < words.length && isSuffix(words[end])) end++; break; }
  const rest = words.slice(end).join(' ');
  const unitM = rest.match(/\b(?:APT|UNIT|STE|#)\s*(\w+)/);
  const zipM = String(raw).match(/\b(\d{5})(?:-\d{4})?\s*$/);
  return { street: words.slice(0, end).join(' '), unit: unitM ? unitM[1] : '', zip: (zipM && zipM[1]) || fallbackZip || '' };
}

// Comparison key: drop ordinals and long-form suffixes so "NW 23RD AVE",
// "NW 23 AVE" and "NW 23RD AVENUE" collide.
function streetKey(street) {
  return clean(street).split(' ')
    .map((w) => LONG[w] || w.replace(/^(\d+)(ST|ND|RD|TH)$/, '$1'))
    .join(' ');
}

// MDPA writes "NW 23 AVE"; the DNM sheet's existing rows use "NW 23RD AVE".
function ordinalize(street) {
  return clean(street).replace(/\b(N|S|E|W|NW|NE|SW|SE) (\d+) (?=[A-Z])/g, (m, dir, n) => {
    const v = Number(n) % 100, last = Number(n) % 10;
    const suf = v >= 11 && v <= 13 ? 'TH' : ({ 1: 'ST', 2: 'ND', 3: 'RD' }[last] || 'TH');
    return `${dir} ${n}${suf} `;
  }).replace(/\bTERR\b/g, 'TER');
}

// GetAddress can return several parcels (condo units, near-misses). Only
// accept an exact street match, and when several remain (a condo with no unit
// in REsimpli) refuse to guess — the lead goes to review instead.
function pickParcel(getAddressResponse, parsed) {
  const infos = (getAddressResponse && getAddressResponse.MinimumPropertyInfos) || [];
  const want = streetKey(parsed.street);
  let exact = infos.filter((i) => streetKey(i.SiteAddress) === want);
  if (parsed.unit) exact = exact.filter((i) => clean(i.SiteUnit) === clean(parsed.unit));
  if (exact.length !== 1) return { folio: null, reason: exact.length ? `${exact.length} county parcels at this address (condo?) - no unit in REsimpli` : 'Not found in Miami-Dade county records' };
  return { folio: String(exact[0].Strap || '').replace(/-/g, ''), reason: '' };
}

// Turn the MDPA folio record into a sheet row's address fields.
function countyAddress(folio, lead) {
  const sa = ((folio && folio.SiteAddress) || [])[0];
  const m = (folio && folio.MailingAddress) || {};
  if (!sa || !sa.Address) return null;
  const street = ordinalize(String(sa.Address).split(',')[0]);
  const zip = String(sa.Zip || '').slice(0, 5);
  const mailStreet = ordinalize([m.Address1, m.Address2].filter(Boolean).join(' '));
  const mailCity = clean(m.City);
  // MDPA names unincorporated parcels "Unincorporated County", which is not a
  // mailing city. Fall back to the owner's own mailing city when they live
  // there, then REsimpli's city if its ZIP agrees, then MIAMI.
  let city = clean(sa.City);
  if (!city || city === 'UNINCORPORATED COUNTY') {
    if (streetKey(mailStreet) === streetKey(street) && mailCity) city = mailCity;
    else if (lead.city && lead.zip === zip) city = lead.city;
    else city = 'MIAMI';
  }
  city = city.replace('OPA-LOCKA', 'OPA LOCKA');
  return {
    street, city, state: 'FL', zip,
    mailStreet, mailCity, mailState: clean(m.State) || (mailStreet ? 'FL' : ''), mailZip: String(m.ZipCode || '').slice(0, 5),
  };
}

// sheetRows: columns C:F (street, city, state, zip), header included.
function sheetKeys(sheetRows) {
  const keys = new Set();
  for (const r of (sheetRows || []).slice(1)) keys.add(streetKey(r[0]) + '|' + String(r[3] || '').slice(0, 5));
  return keys;
}

// resolved: [{ lead, county|null, reason? }] -> rows to append + report.
function buildRows(resolved, sheetRows, today) {
  const keys = sheetKeys(sheetRows);
  const streets = new Set((sheetRows || []).slice(1).map((r) => streetKey(r[0])));
  const rows = [], added = [], duplicates = [], needsReview = [];
  for (const { lead, county, reason } of resolved) {
    if (!county) {
      // Not verifiable, but if the hand-typed street is already on the sheet
      // someone added it manually - nothing to review.
      const p = parseStreet(lead.raw, lead.zip);
      if (p && streets.has(streetKey(p.street))) { duplicates.push({ leadId: lead.leadId }); continue; }
      needsReview.push({ leadId: lead.leadId, name: lead.name, address: lead.raw, reason });
      continue;
    }
    // Same street number + name exists in several cities (a Broward "9361 SW
    // 55th St" also exists in Miami-Dade). If REsimpli's ZIP disagrees with
    // the parcel we found, we may have the wrong house - a human decides.
    const typedZip = (parseStreet(lead.raw, lead.zip) || {}).zip || lead.zip;
    if (typedZip && typedZip !== county.zip) {
      needsReview.push({ leadId: lead.leadId, name: lead.name, address: lead.raw,
        reason: `ZIP mismatch: REsimpli ${typedZip}, county parcel is ${county.street}, ${county.city} ${county.zip}` });
      continue;
    }
    const key = streetKey(county.street) + '|' + county.zip;
    if (keys.has(key)) { duplicates.push({ leadId: lead.leadId }); continue; }
    keys.add(key);
    // A-B owner names stay blank on purpose (Jorge's call); K = date added.
    rows.push(['', '', county.street, county.city, county.state, county.zip,
      county.mailStreet, county.mailCity, county.mailState, county.mailZip, today]);
    added.push({ leadId: lead.leadId, name: lead.name, address: `${county.street}, ${county.city} ${county.zip}`,
      was: lead.raw, absentee: streetKey(county.mailStreet) !== streetKey(county.street) });
  }
  return { rows, added, duplicates, needsReview };
}

module.exports = { TAG_ID, pickTagged, fromDetails, parseStreet, streetKey, ordinalize, pickParcel, countyAddress, buildRows };
