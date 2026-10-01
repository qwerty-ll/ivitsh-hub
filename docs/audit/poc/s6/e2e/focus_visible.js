const { launch, newContext, login, dismissCookies } = require('./lib');
(async () => {
  const browser = await launch();
  const ctx = await newContext(browser);
  const page = await ctx.newPage();
  await login(page, 'st01');
  await dismissCookies(page);
  const targets = { '/calendar': ['.cal-block', '.cal-deadline', '.sidebar-link', 'button.btn-primary'], '/booking': ['.booking-block', 'button'], '/tasks': ['.task-card-title', 'select.task-status-select'],
    '/forum': ['.forum-row-title a'], '/faq': ['.faq-trigger'], '/teachers': ['.teacher-row'], '/map': ['.plan-room.is-pickable'] };
  for (const [url, sels] of Object.entries(targets)) {
    await page.goto(url, { waitUntil: 'networkidle' });
    for (const sel of sels) {
      const el = page.locator(sel).first();
      if (!(await el.count())) { console.log(url, sel, 'not present'); continue; }
      await page.keyboard.press('Tab'); // make sure :focus-visible heuristics are keyboard-based
      await el.focus();
      const cs = await el.evaluate((e) => { const s = getComputedStyle(e); return { outline: `${s.outlineStyle} ${s.outlineWidth} ${s.outlineColor}`, shadow: s.boxShadow.slice(0, 60), matches: e.matches(':focus-visible') }; });
      console.log(url.padEnd(10), sel.padEnd(28), JSON.stringify(cs));
    }
  }
  await browser.close();
})();
