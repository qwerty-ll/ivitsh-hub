// A sign-in that takes 13 s (slow EIOS: tokenauth + UserInfo/Student may take up to ~24 s on the server) vs the client's 12 s timeout.
const { launch, newContext, dismissCookies, SHOTS, path } = require('./lib');
(async () => {
  const browser = await launch();
  const ctx = await newContext(browser);
  const page = await ctx.newPage();
  await page.route('**/api/v1/auth/eios-login', async (route) => { await new Promise((s) => setTimeout(s, 13000)); await route.continue().catch(() => {}); });
  await page.goto('/profile');
  await dismissCookies(page);
  await page.fill('#login-username', 'st77');
  await page.fill('#login-password', 'pw');
  await page.check('.login-consent input[type=checkbox]');
  const t = Date.now();
  await page.click('button[type=submit]');
  await page.waitForSelector('#login-error, .sidebar-user', { timeout: 30000 });
  console.log(`after ${((Date.now() - t) / 1000).toFixed(1)} s:`, (await page.locator('#login-error').allInnerTexts()).join(' / ') || 'signed in');
  await page.screenshot({ path: path.join(SHOTS, 'slow_login_timeout.png') });
  await browser.close();
})();
