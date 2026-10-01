// Keyboard / focus / modal / drawer / reduced-motion / timezone / double-submit checks (student st02, leader st01).
const { launch, newContext, login, dismissCookies, watch, SHOTS, path } = require('./lib');

const results = [];
const note = (k, v) => { results.push([k, v]); console.log(k.padEnd(46), typeof v === 'string' ? v : JSON.stringify(v)); };

(async () => {
  const browser = await launch();

  // ---- 1. Modal: focus handling (leader opens "Новая задача") ----
  {
    const ctx = await newContext(browser);
    const page = await ctx.newPage();
    await login(page, 'st01');
    await dismissCookies(page);
    await page.goto('/tasks', { waitUntil: 'networkidle' });
    const opener = page.getByRole('button', { name: /Новая задача/ });
    await opener.focus();
    await page.keyboard.press('Enter');
    await page.waitForSelector('[role=dialog]');
    await page.waitForTimeout(400);
    note('modal: initial focus inside dialog?', await page.evaluate(() => !!document.activeElement.closest('[role=dialog]')));
    // Tab 40 times: does focus ever leave the dialog?
    let escaped = false; let where = '';
    for (let i = 0; i < 40; i++) {
      await page.keyboard.press('Tab');
      const inside = await page.evaluate(() => !!document.activeElement.closest('[role=dialog]'));
      if (!inside) { escaped = true; where = await page.evaluate(() => `${document.activeElement.tagName}.${document.activeElement.className}`.slice(0, 60)); break; }
    }
    note('modal: Tab escapes the dialog (no focus trap)?', escaped ? `YES -> ${where}` : 'no');
    note('modal: background not inert (aria-hidden/inert on #root siblings)?', await page.evaluate(() => {
      const main = document.getElementById('main-content');
      return { mainAriaHidden: main.getAttribute('aria-hidden'), inert: main.hasAttribute('inert') };
    }));
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);
    note('modal: Esc closes', (await page.locator('[role=dialog]').count()) === 0);
    note('modal: focus returns to opener?', await page.evaluate(() => document.activeElement && document.activeElement.textContent.includes('Новая задача')));
    // Overlay click with typed data loses it
    await page.getByRole('button', { name: /Новая задача/ }).click();
    await page.waitForSelector('[role=dialog]');
    await page.fill('[role=dialog] input[type=text], [role=dialog] input:not([type])', 'Черновик, который нельзя терять');
    await page.mouse.click(5, 5);
    await page.waitForTimeout(500);
    note('modal: click on overlay closes a dirty form silently', (await page.locator('[role=dialog]').count()) === 0);
    await ctx.close();
  }

  // ---- 2. Mobile drawer: hidden links focusable? ----
  {
    const ctx = await newContext(browser, { viewport: { width: 375, height: 700 }, isMobile: true, hasTouch: true });
    const page = await ctx.newPage();
    await login(page, 'st02');
    await dismissCookies(page);
    await page.goto('/', { waitUntil: 'networkidle' });
    const info = await page.evaluate(() => {
      const aside = document.getElementById('app-sidebar');
      const r = aside.getBoundingClientRect();
      const cs = getComputedStyle(aside);
      const links = [...aside.querySelectorAll('a,button')].filter((e) => { const b = e.getBoundingClientRect(); return b.right <= 0; });
      return { right: Math.round(r.right), visibility: cs.visibility, offscreenFocusables: links.length, ariaHidden: aside.getAttribute('aria-hidden'), inert: aside.hasAttribute('inert') };
    });
    note('drawer closed: off-screen focusable controls', info);
    // Tab through first 12 stops and record where focus goes
    const stops = [];
    for (let i = 0; i < 12; i++) { await page.keyboard.press('Tab'); stops.push(await page.evaluate(() => { const e = document.activeElement; const b = e.getBoundingClientRect(); return `${(e.textContent || e.getAttribute('aria-label') || '').trim().slice(0, 18)}@${Math.round(b.left)}`; })); }
    note('drawer closed: first Tab stops (x<0 = invisible)', stops.join(' | '));
    await ctx.close();
  }

  // ---- 3. Reduced motion / forced colors / zoom ----
  {
    const ctx = await newContext(browser, { reducedMotion: 'reduce' });
    const page = await ctx.newPage();
    await login(page, 'st02');
    await page.goto('/', { waitUntil: 'networkidle' });
    const anim = await page.evaluate(() => {
      let running = 0; const names = [];
      for (const a of document.getAnimations()) { if (a.playState === 'running') { running++; names.push(a.animationName || a.transitionProperty || a.constructor.name); } }
      return { running, names: [...new Set(names)].slice(0, 8) };
    });
    note('reduced-motion: running CSS animations on dashboard', anim);
    const css = await page.evaluate(() => [...document.styleSheets].some((s) => { try { return [...s.cssRules].some((r) => r.media && r.media.mediaText.includes('prefers-reduced-motion')); } catch { return false; } }));
    note('reduced-motion: media query present in CSS', css);
    await ctx.close();
  }

  // ---- 4. Timezone: device not in Moscow (Yekaterinburg, UTC+5) ----
  {
    const ctx = await newContext(browser, { timezoneId: 'Asia/Yekaterinburg' });
    const page = await ctx.newPage();
    const log = []; watch(page, log);
    await login(page, 'st01');
    await dismissCookies(page);
    await page.goto('/booking?day=' + new Date(Date.now() + 2 * 864e5).toISOString().slice(0, 10), { waitUntil: 'networkidle' });
    await page.getByRole('button', { name: /Забронировать/ }).first().click().catch(() => {});
    await page.waitForTimeout(500);
    const dlg = page.locator('[role=dialog]');
    if (await dlg.count()) {
      const fields = await dlg.locator('input[type=time]').count();
      note('tz: booking form time inputs', fields);
      await dlg.locator('input[type=time]').nth(0).fill('09:00');
      await dlg.locator('input[type=time]').nth(1).fill('10:00');
      const submit = dlg.getByRole('button', { name: /Забронировать|Сохранить/ }).last();
      await submit.click();
      await page.waitForTimeout(800);
      note('tz: booking 09:00-10:00 on a UTC+5 device ->', (await page.locator('.field-error, [role=alert], .toast').allInnerTexts()).join(' / ').slice(0, 200));
    } else note('tz: booking dialog not found', '');
    await page.screenshot({ path: path.join(SHOTS, 'tz_booking_yekt.png') });
    await ctx.close();
  }

  await browser.close();
})();
