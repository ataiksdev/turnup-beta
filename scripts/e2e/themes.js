// Browser check of the theme feature (production build): default look, migration of the old
// setting, Glass/Fluffy styles, no flash on reload, System mode, toggle, account sync across
// devices, offline changes, and screenshots of all 16 theme/mode combinations.
// Needs: backend with demo data (python -m app.cli seed) on :8000 with RATE_LIMIT_LOGIN relaxed,
// frontend standalone server on :3003.   Run: node scripts/e2e/themes.js /tmp/theme-shots
// Theme feature, in a real browser on a production build.
const { chromium } = require('playwright');
const BASE = 'http://localhost:3003', API = 'http://localhost:8000/api';
const OUT = process.argv[2];
let failed = 0;
const ok = (m) => console.log('✓', m), bad = (m) => { console.log('✗', m); failed++; };
const html = (p) => p.evaluate(() => {
  const r = document.documentElement, cs = getComputedStyle(r);
  return { theme: r.dataset.theme, style: r.dataset.style, dark: r.classList.contains('dark'), light: r.classList.contains('light'),
           bg: cs.backgroundColor, radius: cs.getPropertyValue('--radius').trim(), pageBg: cs.backgroundImage.slice(0, 15),
           meta: document.querySelector('meta[name="theme-color"]:not([media])')?.content };
});
async function login(p, u) {
  await p.goto(BASE + '/login'); await p.waitForLoadState('networkidle');
  await p.getByLabel('Email or username').fill(u); await p.getByLabel('Password').fill('password123');
  await p.getByRole('button', { name: 'Log In' }).click(); await p.waitForURL(x => !x.pathname.startsWith('/login'));
}
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: 400, height: 860 }, colorScheme: 'dark' });
  const p = await ctx.newPage(); p.on('pageerror', e => bad('page error: ' + e.message));

  // 1. Default is today's look
  await p.goto(BASE + '/'); await p.waitForLoadState('networkidle');
  let h = await html(p);
  h.theme === 'turnup' && h.dark && h.bg === 'rgb(10, 10, 10)' ? ok('default: Turnup dark, unchanged look') : bad('default wrong: ' + JSON.stringify(h));

  // 2. Old saved setting {theme:"light"} is migrated, not lost
  await p.evaluate(() => localStorage.setItem('turnup-ui', JSON.stringify({ state: { theme: 'light' }, version: 0 })));
  await p.reload({ waitUntil: 'domcontentloaded' }); h = await html(p);
  h.light && h.theme === 'turnup' ? ok('old light-mode setting kept after update (applied before hydration)') : bad('legacy migration: ' + JSON.stringify(h));

  // 3. Pick Glass from Settings (signed out)
  await p.goto(BASE + '/settings'); await p.waitForLoadState('networkidle');
  await p.getByRole('radio', { name: /^Glass/ }).click(); await p.waitForTimeout(300);
  h = await html(p);
  h.style === 'glass' && h.radius === '14px' && h.pageBg.startsWith('radial-gradient') ? ok('Glass applied: rounded, gradient page') : bad('glass: ' + JSON.stringify(h));
  const blur = await p.locator('.bg-bg-card').first().evaluate(e => getComputedStyle(e).backdropFilter);
  blur.includes('blur') ? ok(`Glass panels are frosted (${blur})`) : bad('no blur on glass panels: ' + blur);

  // 4. No flash: theme is already on <html> when the HTML first parses, before React loads
  await p.goto(BASE + '/', { waitUntil: 'domcontentloaded' }); h = await html(p);
  h.style === 'glass' ? ok('no flash: Glass is set at first paint on reload') : bad('flash of default theme: ' + JSON.stringify(h));

  // 5. System mode follows the device, live
  await p.goto(BASE + '/settings'); await p.waitForLoadState('networkidle');
  await p.getByRole('radio', { name: /^Fluffy/ }).click();
  await p.getByRole('radio', { name: 'System' }).click(); await p.waitForTimeout(200);
  await p.emulateMedia({ colorScheme: 'light' }); await p.waitForTimeout(300); const l = await html(p);
  await p.emulateMedia({ colorScheme: 'dark' }); await p.waitForTimeout(300); const d = await html(p);
  l.light && d.dark && l.style === 'fluffy' ? ok('System mode switches light/dark live with the device') : bad(`system: ${JSON.stringify(l)} / ${JSON.stringify(d)}`);
  const pill = await p.getByRole('button', { name: 'Log In' }).evaluate(e => getComputedStyle(e).borderRadius).catch(() => '?');
  pill === '9999px' ? ok('Fluffy buttons are pills') : bad('fluffy button radius: ' + pill);
  const card = await p.getByRole('radio', { name: /^Fluffy/ }).evaluate(e => getComputedStyle(e).borderRadius);
  card !== '9999px' ? ok(`theme cards keep normal rounded corners (${card})`) : bad('theme cards turned into pills');

  // 6. Sun/moon toggle flips mode within the theme
  await p.emulateMedia({ colorScheme: 'light' }); await p.goto(BASE + '/'); await p.waitForLoadState('networkidle');
  await p.getByRole('button', { name: /Switch to dark mode/ }).first().click(); await p.waitForTimeout(200); h = await html(p);
  h.dark && h.style === 'fluffy' ? ok('toggle: Fluffy light -> Fluffy dark') : bad('toggle: ' + JSON.stringify(h));

  // 7. Account sync: choose on one device, appears on another
  await login(p, 'tunde_vibes');
  await p.goto(BASE + '/settings'); await p.waitForLoadState('networkidle');
  await p.getByRole('radio', { name: /^Owambe Gold/ }).click(); await p.getByRole('radio', { name: 'Light' }).click();
  await p.waitForTimeout(800);
  const tok = (await (await fetch(API + '/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ identifier: 'tunde_vibes', password: 'password123' }) })).json()).access_token;
  const pref = (await (await fetch(API + '/auth/me', { headers: { Authorization: 'Bearer ' + tok } })).json()).theme_preference;
  pref === 'gold:light' ? ok('choice saved to the account (gold:light)') : bad('account pref: ' + pref);
  const ctx2 = await b.newContext({ viewport: { width: 400, height: 860 }, colorScheme: 'dark' }); const p2 = await ctx2.newPage();
  await login(p2, 'tunde_vibes'); await p2.waitForTimeout(800); h = await html(p2);
  h.theme === 'gold' && h.light ? ok('second device picks up Owambe Gold light after login') : bad('second device: ' + JSON.stringify(h));
  h.meta === '#FFFDF5' ? ok('browser/OS chrome colour follows the theme') : bad('meta theme-color: ' + h.meta);

  // 8. A change made on another device arrives on reload
  await fetch(API + '/auth/me', { method: 'PATCH', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + tok }, body: JSON.stringify({ theme_preference: 'neon:dark' }) });
  await p2.reload(); await p2.waitForLoadState('networkidle'); await p2.waitForTimeout(600); h = await html(p2);
  h.theme === 'neon' && h.dark ? ok('change made on another device shows up after reload') : bad('cross-device: ' + JSON.stringify(h));

  // 9. A change made offline is not reverted by stale account data on reload
  await p2.route('**/api/auth/me', r => r.request().method() === 'PATCH' ? r.abort() : r.continue());
  await p2.goto(BASE + '/settings'); await p2.waitForLoadState('networkidle');
  await p2.getByRole('radio', { name: /^Palm/ }).click(); await p2.waitForTimeout(400);
  await p2.unroute('**/api/auth/me');
  await p2.reload(); await p2.waitForLoadState('networkidle'); await p2.waitForTimeout(600); h = await html(p2);
  h.theme === 'palm' ? ok('offline change kept after reload (not overwritten by stale account data)') : bad('offline change lost: ' + JSON.stringify(h));

  // 10. Screenshots of every theme, light and dark, on the home feed (signed in)
  const ids = ['turnup', 'sunset', 'lagoon', 'palm', 'gold', 'neon', 'glass', 'fluffy'];
  for (const id of ids) for (const mode of ['dark', 'light']) {
    await fetch(API + '/auth/me', { method: 'PATCH', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + tok }, body: JSON.stringify({ theme_preference: `${id}:${mode}` }) });
    await p2.goto(BASE + '/'); await p2.waitForLoadState('networkidle'); await p2.waitForTimeout(400);
    await p2.screenshot({ path: `${OUT}/${id}-${mode}.png` });
  }
  await p2.goto(BASE + '/settings'); await p2.waitForLoadState('networkidle'); await p2.waitForTimeout(300);
  await p2.screenshot({ path: `${OUT}/settings-appearance.png` });
  ok('captured 16 theme screenshots + settings');
  await b.close();
  console.log(failed ? `${failed} FAILED` : 'ALL PASSED');
})().catch(e => { console.error('✗ CRASH:', e.message); process.exit(1); });
