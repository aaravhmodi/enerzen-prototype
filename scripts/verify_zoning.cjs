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
    await page.getByText('Property identification').waitFor();
    assert.equal(await page.locator('.zr-summary .tile-value').first().innerText(), 'R4');
    assert.ok(await page.getByText('1801000000').first().isVisible());
    const excerpt = page.locator('blockquote').filter({hasText: 'minimum lot frontage'}).first();
    assert.ok(await excerpt.isVisible());
    assert.match(await excerpt.locator('a').getAttribute('href'), /documents\/file\?path=.*#page=2$/);
    assert.ok(await page.getByText(/Rail proximity/).isVisible());
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

    // A shared link reopens the same lot.
    const shared = page.url();
    await page.goto(shared);
    await page.getByRole('heading', {name: '1 Test St'}).waitFor();
    await page.close();
  }
  await browser.close();
  assert.deepEqual(errors, []);
  console.log('zoning page verified; screenshots in', os.tmpdir());
})().catch(e => { console.error(e); process.exit(1); });
