#!/usr/bin/env node
/**
 * RentCast Comp Puller
 * Usage: node rentcast.js "123 Main St, Miami, FL 33101"
 * Returns ARV estimate + top 3 comps formatted for the bot
 */

const address = process.argv[2];

if (!address) {
  console.error("Usage: node rentcast.js \"<full address>\"");
  process.exit(1);
}

const API_KEY = process.env.RENTCAST_API_KEY;
if (!API_KEY) {
  console.error("Missing RENTCAST_API_KEY environment variable");
  process.exit(1);
}

async function getComps(address) {
  const params = new URLSearchParams({
    address,
    maxRadius: "1",
    daysOld: "180",
    compCount: "5",
    lookupSubjectAttributes: "true"
  });

  const url = `https://api.rentcast.io/v1/avm/value?${params}`;

  const res = await fetch(url, {
    headers: {
      "X-Api-Key": API_KEY,
      "accept": "application/json"
    }
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`RentCast API error ${res.status}: ${text}`);
  }

  return res.json();
}

function formatCurrency(n) {
  if (!n && n !== 0) return "N/A";
  return "$" + Math.round(n).toLocaleString("en-US");
}

function formatPricePerSqft(price, sqft) {
  if (!price || !sqft) return "N/A";
  return "$" + Math.round(price / sqft).toLocaleString("en-US") + "/sqft";
}

async function main() {
  let data;
  try {
    data = await getComps(address);
  } catch (err) {
    console.error(err.message);
    process.exit(1);
  }

  const arv = data.price;
  const low = data.priceRangeLow;
  const high = data.priceRangeHigh;
  const comps = (data.comparables || []).slice(0, 3);

  const lines = [];
  lines.push(`ARV (RentCast):     ${formatCurrency(arv)}`);
  lines.push(`ARV Range:          ${formatCurrency(low)} – ${formatCurrency(high)}`);
  lines.push("");
  lines.push("Comps used:");

  if (comps.length === 0) {
    lines.push("  No comps found within 1 mile / 180 days");
  } else {
    comps.forEach((c, i) => {
      const addr = c.formattedAddress || "Unknown";
      const price = formatCurrency(c.price);
      const ppsf = formatPricePerSqft(c.price, c.squareFootage);
      const dist = c.distance ? `${c.distance.toFixed(2)} mi` : "?";
      const age = c.daysOld ? `${c.daysOld}d ago` : "?";
      lines.push(`  ${i + 1}. ${addr}`);
      lines.push(`     ${price} | ${ppsf} | ${dist} | ${age}`);
    });
  }

  console.log(lines.join("\n"));
}

main();
