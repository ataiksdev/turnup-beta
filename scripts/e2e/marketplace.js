// Browser check of the venue marketplace and Turnup+ (docs/venues-spec.md), production build.
// Needs: backend seeded with `python -m app.cli seed` (DEBUG=true so Paystack runs in mock mode),
// PUBLIC_BASE_URL/FRONTEND_URL=http://localhost:3003, relaxed RATE_LIMIT_LOGIN; frontend on :3003.
// Run: node scripts/e2e/marketplace.js <screenshot dir>
//
// Paystack's mock checkout URL isn't reachable, so after "pay" the script opens the payment
// callback page with the reference, which is what Paystack's redirect would do.
const { chromium } = require('playwright');
const BASE = 'http://localhost:3003', API = 'http://localhost:8000/api';
const OUT = process.argv[2] || '.';
const ok = (m) => console.log('✓', m), bad = (m) => { console.log('✗', m); process.exitCode = 1; };
async function api(path, opts = {}, token) {
  const r = await fetch(API + path, { ...opts, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}), ...(opts.headers || {}) } });
  const t = await r.text(); try { return { status: r.status, body: JSON.parse(t) }; } catch { return { status: r.status, body: t }; }
}
const login = async (u) => (await api('/auth/login', { method: 'POST', body: JSON.stringify({ identifier: u, password: 'password123' }) })).body.access_token;

async function browserLogin(b, user, viewport = { width: 420, height: 900 }) {
  const p = await b.newPage({ viewport });
  p.on('pageerror', (e) => console.log('PAGEERROR', e.message));
  // Pretend Paystack redirects straight back (the mock checkout host doesn't exist).
  await p.route('https://checkout.paystack.com/**', (route) => {
    const ref = route.request().url().split('/').pop();
    route.fulfill({ status: 302, headers: { location: `${BASE}/payments/callback?reference=${ref}&next=${encodeURIComponent(p.__next || '/')}` } });
  });
  await p.goto(BASE + '/login'); await p.waitForLoadState('networkidle');
  await p.getByLabel('Email or username').fill(user); await p.getByLabel('Password').fill('password123');
  await p.getByRole('button', { name: 'Log In' }).click(); await p.waitForURL((u) => !u.pathname.startsWith('/login'));
  return p;
}

(async () => {
  const b = await chromium.launch();

  // ── Public search: Lagos, featured strip, filters ─────────────────────────────
  const anon = await b.newPage({ viewport: { width: 420, height: 900 } });
  await anon.goto(BASE + '/venues'); await anon.waitForLoadState('networkidle');
  (await anon.getByText('The Grand Pavilion').first().isVisible()) ? ok('venues page lists Lagos venues') : bad('no venues listed');
  (await anon.getByText('Featured venues').isVisible()) ? ok('featured strip shows the state-wide slot') : bad('no featured strip');
  await anon.screenshot({ path: OUT + '/venues.png', fullPage: true });
  await anon.getByLabel('State').selectOption('FCT'); await anon.waitForTimeout(1200);
  (await anon.getByText('Maitama Garden Court').first().isVisible()) ? ok('switching to FCT shows Abuja venues') : bad('FCT search failed');
  (await anon.getByText('Wuse Creative Studio').count()) === 0 ? ok('venue still in review is hidden') : bad('in-review venue listed');

  // ── Organizer: venue page, enquiry ────────────────────────────────────────────
  const org = await browserLogin(b, 'adaeze_sounds');
  const venues = (await api('/venues?state=Lagos')).body.items;
  const sky = venues.find((v) => v.name === 'Skyline Rooftop');
  await org.goto(`${BASE}/venues/${sky.slug}`); await org.waitForLoadState('networkidle');
  await org.screenshot({ path: OUT + '/venue-page.png', fullPage: true });
  await org.getByRole('button', { name: 'Enquire' }).click();
  const start = new Date(Date.now() + 33 * 86400000); start.setHours(18, 0, 0, 0);
  const fmt = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  await org.getByLabel('Starts').fill(fmt(start)); await org.getByLabel('Ends').fill(fmt(new Date(start.getTime() + 5 * 3600000)));
  await org.getByLabel('Guests').fill('120');
  await org.getByLabel('Message').fill('Hello! Product launch for 120 guests. Is the rooftop free?');
  await org.getByRole('button', { name: 'Send enquiry' }).click();
  await org.waitForURL(/\/enquiries\//); ok('enquiry sent, thread opened');
  const enquiryId = org.url().split('/').pop();

  // ── Venue owner (web portal): reply with a quote ──────────────────────────────
  const owner = await browserLogin(b, 'bola_venues', { width: 1280, height: 900 });
  await owner.goto(`${BASE}/venue/manage?id=${sky.id}&tab=enquiries`); await owner.waitForLoadState('networkidle');
  await owner.getByText('Adaeze').first().click();
  await owner.getByRole('button', { name: 'Send quote' }).click();
  await owner.getByLabel('Total (₦)').fill('900000');
  await owner.getByRole('button', { name: 'Send quote' }).last().click();
  await owner.getByText('₦900,000').first().waitFor({ timeout: 10000 }).then(() => ok('venue sent a quote from the portal'), () => bad('quote not shown'));
  await owner.screenshot({ path: OUT + '/portal-enquiry.png', fullPage: true });

  // ── Organizer accepts and pays the deposit (mock Paystack) ────────────────────
  org.__next = `/enquiries/${enquiryId}`;
  await org.reload(); await org.waitForLoadState('networkidle');
  await org.getByRole('checkbox').first().check();
  await org.getByRole('button', { name: 'Accept and pay deposit' }).click();
  await org.waitForURL(/\/enquiries\//, { timeout: 15000 });
  await org.waitForTimeout(1500);
  const tok = await login('adaeze_sounds');
  const bookings = (await api('/venue-bookings', {}, tok)).body;
  const bk = bookings.find((x) => x.venue.id === sky.id && x.status === 'confirmed');
  bk && bk.paid_kobo === 27_000_000 ? ok('deposit paid: booking confirmed (30% of ₦900,000)') : bad('booking not confirmed: ' + JSON.stringify(bookings.map((x) => x.status)));
  await org.goto(`${BASE}/venue-bookings/${bk.id}`); await org.waitForLoadState('networkidle');
  (await org.getByText('08030000000').isVisible()) ? ok('venue phone revealed after booking') : bad('phone not shown');
  await org.getByRole('button', { name: 'Cancel booking' }).click();
  await org.getByText(/You'd get ₦270,000 back/).waitFor().then(() => ok('cancellation preview: full refund, paid by the venue'), () => bad('no refund preview'));
  await org.screenshot({ path: OUT + '/booking.png', fullPage: true });
  await org.getByRole('button', { name: 'Keep booking' }).click();

  // ── Turnup+ page and a member's deal code ─────────────────────────────────────
  const member = await browserLogin(b, 'chiamaka_lit');
  await member.goto(`${BASE}/venues/${sky.slug}`); await member.waitForLoadState('networkidle');
  await member.getByRole('button', { name: 'Get code' }).first().click();
  const code = await member.locator('span.font-mono').first().textContent({ timeout: 10000 }).catch(() => null);
  code && /^[A-Z2-9]{8}$/.test(code) ? ok(`member claimed deal code ${code}`) : bad('no deal code');
  await member.goto(BASE + '/plus'); await member.waitForLoadState('networkidle');
  (await member.getByText("You're a member", { exact: true }).isVisible()) ? ok('Turnup+ page shows membership') : bad('membership not shown');
  await member.screenshot({ path: OUT + '/plus.png', fullPage: true });
  const ownerTok = await login('bola_venues');
  const redeem = (await api(`/venue-portal/venues/${sky.id}/deals/redeem`, { method: 'POST', body: JSON.stringify({ code }) }, ownerTok)).body;
  redeem.ok ? ok('venue redeemed the code at the door') : bad('redeem failed ' + JSON.stringify(redeem));

  // ── Agent and admin screens render ────────────────────────────────────────────
  const agent = await browserLogin(b, 'kemi_agent', { width: 1280, height: 900 });
  await agent.goto(BASE + '/agent'); await agent.waitForLoadState('networkidle');
  (await agent.getByText('Maitama Garden Court').isVisible()) ? ok('agent sees the scheduled visit') : bad('agent visits missing');
  const admin = await browserLogin(b, 'turnup_admin', { width: 1280, height: 900 });
  await admin.goto(BASE + '/admin/venues'); await admin.waitForLoadState('networkidle');
  (await admin.getByText('Wuse Creative Studio').isVisible()) ? ok('admin review queue lists the submitted venue') : bad('review queue empty');
  await admin.screenshot({ path: OUT + '/admin-venues.png', fullPage: true });
  await admin.goto(BASE + '/admin/marketplace?tab=settings'); await admin.waitForLoadState('networkidle');
  (await admin.getByText('Booking commission %').isVisible()) ? ok('marketplace settings load') : bad('settings missing');

  await b.close();
})();
