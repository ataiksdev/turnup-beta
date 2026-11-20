// No page may be wider than the phone screen (that makes the whole page, bottom bar included,
// slide sideways). Opens the main screens at 360 and 390 px, signed in and signed out, and
// fails if the document is wider than the viewport.
//
// Needs: the app build served on APP (default http://localhost:8090, e.g. the Capacitor
// export in frontend/out), the API on API (default http://localhost:8000) with demo data, and
// that origin in the API's ALLOWED_ORIGINS.
// Run: node scripts/e2e/no_sideways_scroll.js
const { chromium } = require('playwright');
const APP = process.env.APP || 'http://localhost:8090';
const API = process.env.API || 'http://localhost:8000/api';
const PAGES = ['/', '/explore', '/search', '/communities', '/saved', '/tickets', '/for-you', '/venues'];

(async () => {
  const login = await fetch(`${API}/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ identifier: 'adaeze@turnup.ng', password: 'password123' }) });
  const token = (await login.json()).access_token;
  const user = await (await fetch(`${API}/auth/me`, { headers: { Authorization: 'Bearer ' + token } })).json();
  const b = await chromium.launch();
  const failures = [];
  for (const signedIn of [true, false]) for (const width of [360, 390]) {
    const ctx = await b.newContext({ viewport: { width, height: 800 }, serviceWorkers: 'block' });
    if (signedIn) await ctx.addInitScript(([t, u]) => localStorage.setItem('turnup-auth', JSON.stringify({ state: { token: t, user: u }, version: 0 })), [token, user]);
    const p = await ctx.newPage();
    for (const path of PAGES) {
      await p.goto(APP + path, { waitUntil: 'networkidle' }).catch(() => {});
      await p.waitForTimeout(800);
      const { doc, vw } = await p.evaluate(() => ({ doc: document.documentElement.scrollWidth, vw: document.documentElement.clientWidth }));
      const line = `${signedIn ? 'signed in ' : 'signed out'} ${width}px ${path.padEnd(13)} page width ${doc}px`;
      if (doc > vw) { failures.push(line); console.log('✗', line, `(screen ${vw}px)`); } else console.log('✓', line);
    }
    await ctx.close();
  }
  await b.close();
  if (failures.length) { console.log(`\n${failures.length} page(s) scroll sideways`); process.exit(1); }
  console.log('\nNo page scrolls sideways.');
})().catch((e) => { console.error(e); process.exit(1); });
