// Drives /zoning in a browser against a running API and web app (see verify_experience.cjs
// for PLAYWRIGHT_MODULE / PLAYWRIGHT_CHANNEL). WEB_URL defaults to http://localhost:3000.
// Expects the API's Pickering store to hold the test fixture's "1 Test St" lot in zone R4.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const os = require('node:os');
const WEB = process.env.WEB_URL || 'http://localhost:3000';
(async () => {
  const browser = await chromium.launch({headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || undefined});
  const errors = [];
  for (const viewport of [{width: 1440, height: 1000}, {width: 390, height: 844}]) {
    const page = await browser.newPage({viewport});
    page.setDefaultTimeout(10000);
    page.on('pageerror', e => errors.push(String(e)));
    const shot = name => page.screenshot({path: path.join(os.tmpdir(), `${name}-${viewport.width}.png`), fullPage: true,
                                          animations: 'disabled'});
    await page.goto(`${WEB}/zoning`);
    await page.getByPlaceholder('Address, roll number or PIN').fill('test st');
    await page.getByRole('button', {name: /1 Test St/}).click();
    await page.getByRole('heading', {name: '1 Test St'}).waitFor();
    await page.locator('.zr-summary').waitFor();
    await page.getByText('Property identification').waitFor();
    assert.equal(await page.locator('.zr-summary .tile-value').first().innerText(), 'R4');
    assert.ok(await page.getByText('1801000000').first().isVisible());
    const excerpt = page.locator('blockquote').filter({hasText: 'minimum lot frontage'}).first();
    assert.ok(await excerpt.isVisible());
    assert.match(await excerpt.locator('a').getAttribute('href'), /documents\/file\?path=.*#page=2$/);
    assert.ok(await page.getByText(/Rail proximity/).isVisible());
    // Step 3: this lot's own setbacks, side by side, each from its by-law page.
    const setbacks = await page.locator('.zr-setbacks').innerText();
    for (const expected of ['Every setback from the by-law', 'corner lot', 'Front yard', 'Exterior side yard',
                            'Zone R4 table, p. 2', 'Buildable area inside setbacks']) {
      assert.ok(setbacks.toLowerCase().includes(expected.toLowerCase()), `setbacks card shows "${expected}"`);
    }
    assert.match(setbacks, /South \(street\)\s+Front yard\s+6 m/);
    assert.match(setbacks, /East \(flank street\)\s+Exterior side yard\s+4\.5 m/);
    assert.match(await page.locator('.zoning-search').innerText(), /Setbacks from the by-law for \d+ of \d+ lots/);
    // Step 3: the zone's standards from the by-law text, and a preliminary check of a proposal.
    const height = page.locator('.zr-standard').filter({hasText: 'Building height'});
    await height.getByRole('textbox').fill('11');
    assert.match(await height.innerText(), /Above the maximum/);
    await height.getByRole('textbox').fill('8.5');
    assert.match(await height.innerText(), /Appears to meet/);
    assert.ok(await page.getByText('Adjacent zoning (within 30 m)').isVisible());
    assert.ok(await page.locator('.zr-hits').filter({hasText: 'R3-7'}).first().isVisible());
    assert.ok(page.url().includes('lat=') && page.url().includes('q=1+Test+St'));
    const noHorizontalScroll = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
    assert.ok(noHorizontalScroll, 'page scrolls sideways');
    await shot('zoning-review');

    await page.getByRole('tab', {name: 'Search all by-laws'}).click();
    await page.getByPlaceholder(/minimum lot frontage/).fill('frontage');
    await page.getByRole('button', {name: 'Search', exact: true}).click();
    await page.getByText(/page.? mention/).waitFor();
    assert.ok(await page.locator('blockquote').filter({hasText: 'R4 zone'}).first().isVisible());
    await shot('zoning-bylaws');

    // The data gaps from the last scrape are shown, not hidden.
    assert.match(await page.locator('.zr-gaps summary').innerText(), /Data gaps: \d+/);
    // A neighbouring lot named by a council amendment lists it.
    await page.getByRole('tab', {name: 'Lot review'}).click();
    await page.getByPlaceholder('Address, roll number or PIN').fill('3 test');
    await page.getByRole('button', {name: /3 Test St/}).click();
    await page.getByRole('heading', {name: '3 Test St'}).waitFor();
    await page.getByText('names Lot 17, Concession 8').waitFor();

    // The lot goes to the design workspace with its measured sides, street side and setbacks.
    const handoff = Object.fromEntries(new URL(await page.getByRole('link', {name: /Use this lot in the workspace/})
      .getAttribute('href'), 'http://x').searchParams);
    assert.ok(handoff.front && handoff.rear && handoff.side, 'setbacks travel to the workspace');
    await page.getByRole('link', {name: /Use this lot in the workspace/}).click();
    await page.waitForURL(/\/\?lot=/);
    const width = page.getByRole('spinbutton', {name: /Lot width/});
    await width.waitFor();
    assert.ok(Math.abs(Number(await width.inputValue()) - 48.2) < 0.6, 'lot width from the parcel');
    assert.equal(await page.getByRole('spinbutton', {name: /front setback/i}).inputValue(),
                 String(handoff.front), 'front setback from the by-law');
    await page.getByText(/is zoned|R4/).first().waitFor();
    assert.ok(await page.getByRole('link', {name: 'Full zoning review and by-laws'}).isVisible());
    await shot('workspace-lot');
    await page.goBack();
    await page.getByRole('heading', {name: '3 Test St'}).waitFor();

    // A shared link reopens the same lot.
    const shared = page.url();
    await page.goto(shared);
    await page.getByRole('heading', {name: '3 Test St'}).waitFor();
    await page.close();
  }
  await browser.close();
  assert.deepEqual(errors, []);
  console.log('zoning page verified; screenshots in', os.tmpdir());
})().catch(e => { console.error(e); process.exit(1); });
