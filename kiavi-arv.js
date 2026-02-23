/**
 * Kiavi ARV Estimator Scraper
 * Usage: node kiavi-arv.js "123 Main St, Miami, FL 33101" 200000 45000
 * Args:  address  purchasePrice  rehabBudget
 */

const { chromium } = require('playwright');

const address       = process.argv[2];
const purchasePrice = parseInt(process.argv[3] || '0');
const rehabBudget   = parseInt(process.argv[4] || '0');

if (!address) {
  console.error('Usage: node kiavi-arv.js "ADDRESS" PURCHASE_PRICE REHAB_BUDGET');
  process.exit(1);
}

(async () => {
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-gpu']
  });

  const page = await browser.newPage();
  await page.setViewportSize({ width: 1280, height: 800 });

  try {
    await page.goto('https://www.kiavi.com/arv-estimator', {
      waitUntil: 'domcontentloaded',
      timeout: 30000
    });
    await page.waitForTimeout(3000);

    // Fill address
    const addressInput = await page.waitForSelector('#input-1', { timeout: 10000 });
    await addressInput.click();
    await page.keyboard.type(address, { delay: 50 });
    await page.waitForTimeout(2500);

    // Select autocomplete suggestion if present, otherwise press Enter
    const suggestionList = page.locator('#suggesting-input-0 li');
    if (await suggestionList.count().then(n => n > 0).catch(() => false)) {
      await suggestionList.first().click();
    } else {
      await page.keyboard.press('Enter');
    }
    await page.waitForTimeout(5000);

    // Fill purchase price if field appeared
    if (purchasePrice > 0) {
      const ppInput = await page.$('input[id*="purchase" i], input[name*="purchase" i]');
      if (ppInput) { await ppInput.click({ clickCount: 3 }); await ppInput.fill(String(purchasePrice)); }
    }

    // Fill rehab if field appeared
    if (rehabBudget > 0) {
      const rehabInput = await page.$('input[id*="rehab" i], input[name*="rehab" i]');
      if (rehabInput) { await rehabInput.click({ clickCount: 3 }); await rehabInput.fill(String(rehabBudget)); }
    }

    // Get full page text
    const text = await page.evaluate(() => document.body.innerText);

    // Parse ARV
    const arvMatch = text.match(/Estimated After Repair Value\s*\n\s*\$?([\d,]+)/i);
    const arv = arvMatch ? '$' + arvMatch[1] : null;

    // Parse Cash to Close
    const ctcMatch = text.match(/Cash to Close\s*\n\s*\$?([\d,]+\.?\d*)/i);
    const ctc = ctcMatch ? '$' + ctcMatch[1] : null;

    // Parse comparables — pattern: Distance\nX.XX miles\nSale Price\n$XXX\nBedrooms\nX\nBathrooms\nX\nDate Sold\nMM/DD/YYYY\nSQFT\nX,XXX
    const compPattern = /Distance\s*\n\s*([\d.]+ miles)\s*\nSale Price\s*\n\s*\$?([\d,]+)\s*\nBedrooms\s*\n\s*(\d+)\s*\nBathrooms\s*\n\s*([\d.]+)\s*\nDate Sold\s*\n\s*([\d/]+)\s*\nSQFT\s*\n\s*([\d,]+)/gi;

    const comps = [];
    let match;
    while ((match = compPattern.exec(text)) !== null && comps.length < 3) {
      const price = parseInt(match[2].replace(/,/g, ''));
      const sqft  = parseInt(match[6].replace(/,/g, ''));
      const ppsf  = sqft > 0 ? Math.round(price / sqft) : null;
      comps.push({
        distance: match[1],
        price:    '$' + match[2],
        ppsf:     ppsf ? '$' + ppsf + '/sqft' : 'N/A',
        beds:     match[3],
        baths:    match[4],
        dateSold: match[5],
        sqft:     match[6]
      });
    }

    // Output
    if (!arv) {
      console.log('ERROR: Could not get ARV from Kiavi — property may not be eligible or address not recognized');
      process.exit(1);
    }

    console.log(`ARV (Kiavi):    ${arv}`);
    if (ctc) console.log(`Cash to Close:  ${ctc}`);
    console.log('Comps (Kiavi):');
    if (comps.length === 0) {
      console.log('  No comparables returned');
    } else {
      comps.forEach((c, i) => {
        console.log(`  ${i + 1}. ${c.price} | ${c.ppsf} | ${c.beds}bd/${c.baths}ba | ${c.sqft} sqft | ${c.dateSold} | ${c.distance}`);
      });
    }

  } catch (err) {
    console.error('ERROR:', err.message);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
