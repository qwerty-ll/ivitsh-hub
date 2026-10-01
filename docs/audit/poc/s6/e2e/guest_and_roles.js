// What a guest, a plain student and an admin see on pages whose API they may not use (UI vs server rights).
const { launch, newContext, login, dismissCookies, watch } = require('./lib');
const PAGES = ['/calendar', '/tasks', '/associations/3', '/events', '/events/1', '/booking', '/tribes', '/shop', '/forum/question/1', '/admin', '/tasks/1', '/profile'];
(async () => {
  const browser = await launch();
  for (const who of ['guest', 'st05', 'portal_admin']) {
    const ctx = await newContext(browser);
    const page = await ctx.newPage();
    const log = []; watch(page, log);
    if (who === 'st05') await login(page, 'st05');
    if (who === 'portal_admin') await login(page, 'portal_admin', 'Adm1n-Local-Pass!', true);
    await dismissCookies(page);
    console.log(`\n=== ${who}`);
    for (const url of PAGES) {
      log.length = 0;
      await page.goto(url, { waitUntil: 'networkidle' }).catch(() => {});
      await page.waitForTimeout(300);
      const text = (await page.locator('main').innerText().catch(() => '')).replace(/\s+/g, ' ');
      const errs = [...new Set(log.filter((l) => l.startsWith('http')))].join(' ');
      console.log(url.padEnd(20), text.slice(0, 150).padEnd(150), errs);
    }
    await ctx.close();
  }
  await browser.close();
})();
