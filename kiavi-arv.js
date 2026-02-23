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

async function fillCurrencyInput(page, selector, value) {
  const input = await page.$(selector);
  if (!input) return false;
  await input.click({ clickCount: 3 });
  await page.keyboard.press('Control+a');
  await page.keyboard.press('Delete');
  await page.keyboard.type(String(value), { delay: 30 });
  await page.keyboard.press('Tab');
  await page.waitForTimeout(300);
  return true;
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

    // Step 1: Fill address
    const addressInput = await page.waitForSelector('#input-1', { timeout: 10000 });
    await addressInput.click();
    await page.keyboard.type(address, { delay: 50 });
    await page.waitForTimeout(2500);

    const suggestionList = page.locator('#suggesting-input-0 li');
    if (await suggestionList.count().then(n => n > 0).catch(() => false)) {
      await suggestionList.first().click();
    } else {
      await page.keyboard.press('Enter');
    }
    await page.waitForTimeout(4000);

    // Step 2: Fill Offer Price and Rehab Amount
    if (purchasePrice > 0) await fillCurrencyInput(page, '#input-5', purchasePrice);
    if (rehabBudget   > 0) await fillCurrencyInput(page, '#input-8', rehabBudget);

    // Step 3: Click "Get Estimate" / "Refresh My Estimate"
    const estimateBtn = page.locator('button:has-text("Get Estimate"), button:has-text("Refresh My Estimate")').first();
    if (await estimateBtn.count() > 0) await estimateBtn.click();
    await page.waitForTimeout(7000);

    // Step 4: Click "Show Comparables" div to expand comps
    await page.evaluate(() => {
      const el = Array.from(document.querySelectorAll('*')).find(
        e => e.childElementCount === 0 && e.innerText && e.innerText.trim().startsWith('Show Comparables')
      );
      if (el) el.click();
    });
    await page.waitForTimeout(2000);

    // Step 5: Parse page text
    const text = await page.evaluate(() => document.body.innerText);

    // Parse ARV — match the main result heading (includes "(ARV)")
    const arvMatch = text.match(/Estimated After Repair Value \(ARV\)\s*\n\s*\$?([\d,]+)/i);
    const arv = arvMatch ? '$' + arvMatch[1] : null;

    // Parse comps — new format after expanding
    // Pattern: ADDRESS\nDistance from Deal:\nX.XX mi\nSale Price:\n$X\nSale Date:\nX\nBeds:\nX\nBaths:\nX\nSq Footage:\nX\nPrice/Sq Foot:\n$X
    const compPattern = /([A-Z0-9 ]+(?:ST|AVE|DR|RD|LN|CT|PL|WAY|BLVD|CIR|TER|TRL)[^\n]*)\nDistance from Deal:\n([\d.]+ mi)\nSale Price:\n\$?([\d,]+)\nSale Date:\n([\d/]+)\nBeds:\n(\d+)\nBaths:\n([\d.]+)\nSq Footage:\n([\d,]+)\nPrice\/Sq Foot:\n\$?([\d,]+)/g;

    const seen = new Set();
    const comps = [];
    let m;
    while ((m = compPattern.exec(text)) !== null) {
      const key = m[1] + m[4]; // address + date to deduplicate carousel
      if (seen.has(key)) continue;
      seen.add(key);
      comps.push({
        address:  m[1].trim(),
        distance: m[2],
        price:    '$' + m[3],
        dateSold: m[4],
        beds:     m[5],
        baths:    m[6],
        sqft:     m[7],
        ppsf:     '$' + m[8] + '/sqft'
      });
      if (comps.length >= 5) break;
    }

    // Output
    if (!arv) {
      console.log('ERROR: Could not get ARV from Kiavi — property may not be eligible or address not recognized');
      process.exit(1);
    }

    console.log(`ARV (Kiavi):    ${arv}`);
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
