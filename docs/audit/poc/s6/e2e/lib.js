// Shared helpers for the S6 browser checks. Run with:
//   S6_DIR=<scratch>/s6 NODE_PATH=/opt/node-tools/node_modules node docs/audit/poc/s6/e2e/<script>.js
// against the sandbox from docs/audit/poc/s6/local_server.py (http://127.0.0.1:8766).
const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright');

const BASE = process.env.S6_BASE || 'http://127.0.0.1:8766';
const S6 = process.env.S6_DIR || path.join(__dirname, '..', '_run');
const SHOTS = path.join(S6, 'shots');
fs.mkdirSync(SHOTS, { recursive: true });

async function launch() {
  const executablePath = process.env.S6_CHROME || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
  return chromium.launch({ executablePath, args: ['--no-sandbox'] });
}

async function newContext(browser, opts = {}) {
  const ctx = await browser.newContext({ baseURL: BASE, locale: 'ru-RU', timezoneId: 'Europe/Moscow', viewport: { width: 1280, height: 800 }, ...opts });
  // Nothing outside the sandbox may be contacted (teacher photos are hot-linked from kosgos.ru)
  await ctx.route((url) => !['127.0.0.1', 'localhost'].includes(url.hostname), (route) => route.abort());
  return ctx;
}

async function login(page, user, pw = 'pw', staff = false) {
  await page.goto('/profile');
  if (staff) await page.getByRole('tab', { name: /Администратор/ }).click();
  await page.fill('#login-username', user);
  await page.fill('#login-password', pw);
  if (!staff) await page.check('.login-consent input[type=checkbox]');
  await page.click('button[type=submit]');
  await page.waitForSelector('.sidebar-user', { timeout: 15000 });
}

// Cookie notice would cover bottom controls: dismiss it like a real user does
async function dismissCookies(page) {
  const b = page.getByRole('button', { name: 'Понятно' });
  if (await b.count()) await b.click().catch(() => {});
}

function watch(page, log) {
  page.on('console', (m) => { if (['error', 'warning'].includes(m.type())) log.push(`console.${m.type()}: ${m.text().slice(0, 200)}`); });
  page.on('pageerror', (e) => log.push(`pageerror: ${String(e).slice(0, 200)}`));
  page.on('requestfailed', (r) => log.push(`requestfailed: ${r.method()} ${r.url().slice(0, 120)}`));
  page.on('response', (r) => { if (r.status() >= 400 && !r.url().includes('/auth/me')) log.push(`http ${r.status()}: ${r.request().method()} ${r.url().replace(BASE, '').slice(0, 120)}`); });
}

module.exports = { chromium, BASE, S6, SHOTS, launch, newContext, login, dismissCookies, watch, path, fs };
