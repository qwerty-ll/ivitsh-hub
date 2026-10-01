// Offline / flaky network / stale deploy behaviour of the SPA (student st02).
const { launch, newContext, login, dismissCookies, SHOTS, path } = require('./lib');
(async () => {
  const browser = await launch();
  // --- stale deploy: a lazy chunk of the old build is gone (404) ---
  {
    const ctx = await newContext(browser);
    const page = await ctx.newPage();
    await login(page, 'st02');
    await dismissCookies(page);
    await page.goto('/', { waitUntil: 'networkidle' });
    await page.route(/\/assets\/Tasks-.*\.js/, (r) => r.fulfill({ status: 404, body: 'gone' }));
    await page.getByRole('link', { name: 'Задачи', exact: true }).first().click();
    await page.waitForTimeout(1500);
    console.log('stale chunk -> body text:', (await page.locator('body').innerText()).replace(/\s+/g, ' ').slice(0, 300));
    await page.screenshot({ path: path.join(SHOTS, 'stale_chunk_error.png') });
    await ctx.close();
  }
  // --- offline while using the app ---
  {
    const ctx = await newContext(browser);
    const page = await ctx.newPage();
    await login(page, 'st02');
    await dismissCookies(page);
    await page.goto('/tasks', { waitUntil: 'networkidle' });
    await page.goto('/teachers', { waitUntil: 'networkidle' });
    await ctx.setOffline(true);
    await page.getByRole('link', { name: 'Задачи', exact: true }).first().click();
    await page.waitForTimeout(2500);
    console.log('offline /tasks (client nav):', (await page.locator('body').innerText()).replace(/\s+/g, ' ').slice(0, 260));
    await page.screenshot({ path: path.join(SHOTS, 'offline_tasks.png') });
    await ctx.setOffline(false);
    await ctx.close();
  }
  // --- slow API (3 s per call): are loading states shown, do double-click creates happen? ---
  {
    const ctx = await newContext(browser);
    const page = await ctx.newPage();
    await login(page, 'st02');
    await dismissCookies(page);
    await page.route('**/api/v1/tasks', async (r) => { if (r.request().method() === 'POST') await new Promise((s) => setTimeout(s, 2500)); await r.continue(); });
    await page.goto('/tasks?new=1', { waitUntil: 'networkidle' });
    await page.fill('[role=dialog] input', 'Двойной клик');
    const btn = page.getByRole('button', { name: 'Создать задачу' });
    await btn.dblclick();
    await page.waitForTimeout(4000);
    const r = await page.evaluate(async () => (await (await fetch('/api/v1/tasks/my', { headers: { 'X-Requested-With': 'XMLHttpRequest' } })).json()).filter((t) => t.title === 'Двойной клик').length);
    console.log('double-click "Создать задачу" on slow API -> tasks created:', r);
    await ctx.close();
  }
  await browser.close();
})();
