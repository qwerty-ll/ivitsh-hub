const { launch, newContext, login, dismissCookies, SHOTS, path } = require('./lib');
(async () => {
  const browser = await launch();
  const ctx = await newContext(browser);
  const page = await ctx.newPage();
  await login(page, 'st02');
  await dismissCookies(page);
  await page.goto('/calendar', { waitUntil: 'networkidle' });
  const blocks = await page.evaluate(() => [...document.querySelectorAll('.cal-block, .cal-deadline')].slice(0, 12).map((b) => ({
    cls: b.className.replace(/\s+/g, ' ').slice(0, 50), name: (b.getAttribute('aria-label') || '').slice(0, 60), text: b.innerText.replace(/\s+/g, ' ').slice(0, 60),
  })));
  console.log(JSON.stringify(blocks, null, 0).replace(/\},\{/g, '},\n{'));
  // grayscale screenshot to simulate colour-blindness
  await page.addStyleTag({ content: 'html{filter:grayscale(1)}' });
  await page.screenshot({ path: path.join(SHOTS, 'calendar_grayscale.png') });
  await browser.close();
})();
