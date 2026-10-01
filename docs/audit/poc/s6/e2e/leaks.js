// What stays in the browser after sign-out, and what the next account on the same device can see.
const { launch, newContext, login, dismissCookies, SHOTS, path } = require('./lib');
(async () => {
  const browser = await launch();
  const ctx = await newContext(browser);
  const page = await ctx.newPage();
  await login(page, 'st02');
  await dismissCookies(page);
  // use some features so keys get written
  await page.goto('/', { waitUntil: 'networkidle' });
  await page.goto('/calendar', { waitUntil: 'networkidle' });
  await page.goto('/profile', { waitUntil: 'networkidle' });
  // set a custom avatar (data URL) like the profile page does
  await page.evaluate(() => localStorage.setItem('portal_avatar_2', 'data:image/png;base64,iVBORw0KGgo='));
  const keys = async () => page.evaluate(() => Object.fromEntries(Object.keys(localStorage).map((k) => [k, localStorage.getItem(k).slice(0, 70)])));
  console.log('BEFORE logout:', JSON.stringify(await keys(), null, 1));
  await page.getByRole('button', { name: /Выйти/ }).first().click();
  await page.waitForTimeout(800);
  console.log('AFTER logout:', JSON.stringify(await keys(), null, 1));
  const cookies = await ctx.cookies();
  console.log('cookies after logout:', cookies.map((c) => c.name));
  // Back button after logout: does the page still show private data from memory/bfcache?
  await page.goto('/tasks', { waitUntil: 'networkidle' });
  console.log('tasks as guest ->', (await page.locator('h2').allInnerTexts()).join(' / '));
  // login as another student: does the previous person's data show?
  await login(page, 'st03');
  await page.goto('/tasks', { waitUntil: 'networkidle' });
  console.log('st03 tasks page cards:', (await page.locator('.task-card-title').allInnerTexts()).join(' / '));
  console.log('AFTER st03 login:', JSON.stringify(await keys(), null, 1));
  // Session cookie replay after logout (token revoked?)
  await browser.close();
})();
