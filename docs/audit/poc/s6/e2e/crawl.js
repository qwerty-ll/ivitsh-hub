// Per page and viewport: axe (WCAG 2.2 AA tags), horizontal overflow, touch targets, console/HTTP errors, screenshot.
const { launch, newContext, login, dismissCookies, watch, SHOTS, path, fs, S6 } = require('./lib');
const axeSrc = fs.readFileSync(path.join(S6, 'node_modules', 'axe-core', 'axe.min.js'), 'utf8');

const PAGES = ['/', '/calendar', '/schedule', '/tasks', '/tasks/1', '/associations', '/associations/3', '/events', '/events/1', '/booking', '/tribes', '/shop',
  '/forum', '/forum/question/1', '/map', '/teachers', '/faq', '/profile', '/privacy'];
const VIEWPORTS = { desktop: { width: 1280, height: 800 }, phone320: { width: 320, height: 640 }, phone390: { width: 390, height: 844 } };

(async () => {
  const browser = await launch();
  const out = {};
  for (const [vp, size] of Object.entries(VIEWPORTS)) {
    const ctx = await newContext(browser, { viewport: size, hasTouch: vp !== 'desktop', isMobile: vp !== 'desktop' });
    const page = await ctx.newPage();
    const log = [];
    watch(page, log);
    await login(page, 'st02');
    await dismissCookies(page);
    for (const url of PAGES) {
      log.length = 0;
      await page.goto(url, { waitUntil: 'networkidle' }).catch(() => {});
      await page.waitForTimeout(500);
      await page.addScriptTag({ content: axeSrc });
      const res = await page.evaluate(async () => {
        const r = await window.axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa', 'best-practice'] } });
        const small = [];
        for (const el of document.querySelectorAll('a[href],button,input:not([type=hidden]),select,textarea,[role=button],[role=tab]')) {
          const b = el.getBoundingClientRect();
          const cs = getComputedStyle(el);
          if (b.width === 0 || b.height === 0 || cs.visibility === 'hidden' || cs.display === 'none') continue;
          if (b.top > window.innerHeight * 5) continue;
          if (b.width < 24 || b.height < 24) small.push(`${el.tagName.toLowerCase()}${el.className ? '.' + String(el.className).split(' ')[0] : ''} ${Math.round(b.width)}x${Math.round(b.height)} "${(el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 30)}"`);
        }
        return {
          violations: r.violations.map((v) => ({ id: v.id, impact: v.impact, n: v.nodes.length, sample: v.nodes.slice(0, 2).map((n) => n.target.join(' ')) })),
          overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          small: small.slice(0, 12), smallCount: small.length,
          lang: document.documentElement.lang, title: document.title,
        };
      });
      res.log = [...new Set(log)].slice(0, 6);
      out[`${vp} ${url}`] = res;
      if (vp !== 'phone390') await page.screenshot({ path: path.join(SHOTS, `${vp}_${url.replace(/\W+/g, '_') || 'home'}.png`), fullPage: false });
    }
    await ctx.close();
  }
  fs.writeFileSync(path.join(S6, 'crawl.json'), JSON.stringify(out, null, 1));
  await browser.close();
  // summary
  const agg = {};
  for (const [k, v] of Object.entries(out)) {
    for (const x of v.violations) { agg[x.id] = agg[x.id] || { impact: x.impact, pages: [] }; agg[x.id].pages.push(`${k}(${x.n})`); }
  }
  for (const [id, v] of Object.entries(agg)) console.log(id, v.impact, v.pages.length, v.pages.slice(0, 6).join(' | '));
  console.log('--- overflow');
  for (const [k, v] of Object.entries(out)) if (v.overflowX > 0) console.log(k, 'overflowX', v.overflowX);
  console.log('--- small targets');
  for (const [k, v] of Object.entries(out)) if (v.smallCount) console.log(k, v.smallCount, v.small.slice(0, 4).join('; '));
  console.log('--- logs');
  for (const [k, v] of Object.entries(out)) if (v.log.length) console.log(k, v.log.join(' || '));
})();
