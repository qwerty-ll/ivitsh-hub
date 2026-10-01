const { launch, newContext, login, dismissCookies, SHOTS, path } = require('./lib');
(async () => {
  const browser = await launch();
  const ctx = await newContext(browser);
  const page = await ctx.newPage();
  await login(page, 'st01');
  await dismissCookies(page);
  await page.goto('/calendar', { waitUntil: 'networkidle' });
  const ref = page.locator('.sidebar-link').nth(2); // a control that does show the ring
  const block = page.locator('.cal-block').first();
  await block.scrollIntoViewIfNeeded();
  await page.keyboard.press('Tab');
  await block.focus();
  const box = await block.boundingBox();
  await page.screenshot({ path: path.join(SHOTS, 'focus_cal_block.png'), clip: { x: Math.max(0, box.x - 60), y: Math.max(0, box.y - 40), width: 320, height: 140 } });
  await page.goto('/profile'); // any page with a button that shows the ring
  await browser.close();
})();
