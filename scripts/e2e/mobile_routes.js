// Drives the Capacitor (Android) static export through in-app navigation. Setup:
//   cd frontend && CAPACITOR_BUILD=true NEXT_PUBLIC_STATIC_EXPORT=true NEXT_PUBLIC_API_URL=http://localhost:8000 npx next build
//   node scripts/e2e/capacitor_like_server.js frontend/out 3005
//   backend with seed data (scripts/seed.py) and ALLOWED_ORIGINS including http://localhost:3005
//   node scripts/e2e/mobile_routes.js
// Navigates the Capacitor static export like a user would (client-side), on a server that
// behaves like the Android WebView's local server.
const { chromium } = require('playwright');
const BASE = 'http://localhost:3005';
const ok = (m) => console.log('✓', m), bad = (m) => console.log('✗', m);
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 400, height: 860 } });
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  const apiCalls = []; p.on('request', r => { if (r.url().includes(':8000/api/')) apiCalls.push(r.url()); });
  await p.goto(BASE + '/'); await p.waitForLoadState('networkidle');

  // Sign in the way the app stores a session, then only navigate by clicking.
  const tok = await (await fetch('http://localhost:8000/api/auth/login', { method: 'POST',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ identifier: 'dayo_hype', password: 'password123' }) })).json();
  const me = await (await fetch('http://localhost:8000/api/auth/me', { headers: { Authorization: 'Bearer ' + tok.access_token } })).json();
  await p.evaluate(([t, u]) => localStorage.setItem('turnup-auth', JSON.stringify({ state: { token: t, user: u }, version: 0 })), [tok.access_token, me]);
  await p.goto(BASE + '/'); await p.waitForLoadState('networkidle'); await p.waitForTimeout(1500);
  ok('signed in as ' + me.username);
  const ev = p.locator('a[href^="/events/view?id="]').first();
  if (!(await ev.count())) { bad('no /events/view links on home: ' + (await p.locator('a[href^="/events/"]').first().getAttribute('href'))); }
  else {
    const href = await ev.getAttribute('href'); await ev.click();
    await p.waitForURL('**/events/view?id=*'); await p.waitForTimeout(2500);
    const title = await p.locator('h1').first().innerText().catch(() => '');
    const id = new URL(BASE + href).searchParams.get('id');
    title && apiCalls.some(u => u.includes('/api/events/' + id)) ? ok(`event page via ${href.slice(0, 40)}… shows "${title.slice(0, 40)}"`) : bad('event page empty; API calls: ' + apiCalls.filter(u => u.includes('/events/')).slice(-2).join(' '));
    const host = p.locator('a[href^="/profile/by-name?username="]').first();
    if (await host.count()) {
      await host.click(); await p.waitForURL('**/profile/by-name?*'); await p.waitForTimeout(2000);
      const t = (await p.locator('main, body').first().innerText()).slice(0, 300);
      /@\w+/.test(t) && !/couldn.t load|not found/i.test(t) ? ok('host profile page loads') : bad('profile page: ' + t.replace(/\s+/g, ' ').slice(0, 120));
    } else bad('no profile link on event page');
  }
  // bottom-nav to communities, then into one
  await p.getByRole('link', { name: /communities/i }).first().click(); await p.waitForURL('**/communities'); await p.waitForTimeout(2000);
  const c = p.locator('a[href^="/communities/view?slug="]').first();
  if (await c.count()) {
    await c.click(); await p.waitForURL('**/communities/view?*'); await p.waitForTimeout(2000);
    const t = (await p.locator('h1').first().innerText().catch(() => ''));
    t ? ok(`community page shows "${t.slice(0, 40)}"`) : bad('community page empty');
  } else bad('no community links');
  // organizer: my events → edit page
  await p.evaluate(() => { const a = document.createElement('a'); a.href = '/organizer/events'; a.id = 'go'; document.body.appendChild(a); });
  await p.evaluate(() => window.next && window.next.router ? window.next.router.push('/organizer/events') : document.getElementById('go').click());
  await p.waitForURL('**/organizer/events', { timeout: 15000 }).catch(() => {}); await p.waitForTimeout(2500);
  const edit = p.locator('a[href^="/organizer/events/view/edit?id="]').first();
  if (await edit.count()) {
    await edit.click(); await p.waitForURL('**/organizer/events/view/edit?*'); await p.waitForTimeout(2500);
    const v = await p.locator('input').first().inputValue().catch(() => '');
    v ? ok(`organizer edit page loads event ("${v.slice(0, 30)}")`) : bad('edit page has no data');
  } else bad('no edit links in organizer events: ' + await p.locator('a[href*="/organizer/events/"]').first().getAttribute('href').catch(() => 'none'));
  // full reload on a deep link: Capacitor serves the root index.html for it
  const evId = (await (await fetch('http://localhost:8000/api/events?limit=1')).json())[0].slug;
  await p.goto(BASE + '/events/view?id=' + evId); await p.waitForTimeout(4000);
  console.log('  (info) hard reload of a deep link renders:', new URL(p.url()).pathname, '/', (await p.locator('h1').first().innerText().catch(() => '-')).slice(0, 30));
  if (errs.length) console.log('page errors:', errs.slice(0, 3));
  await b.close();
})();
