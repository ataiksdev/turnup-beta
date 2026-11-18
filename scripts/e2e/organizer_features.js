// Browser check of the organizer/community management screens (production build).
// Needs: backend with scripts/seed.py data, PUBLIC_BASE_URL=http://localhost:3003, relaxed
// RATE_LIMIT_LOGIN/RATE_LIMIT_REGISTER; frontend standalone server on :3003.
// Run: node scripts/e2e/organizer_features.js /tmp
// Drives the new organizer/community features in a production build.
const { chromium } = require('playwright');
const zlib = require('zlib');
const BASE = 'http://localhost:3003', API = 'http://localhost:8000/api';
const OUT = process.argv[2];
const ok = (m) => console.log('✓', m), bad = (m) => { console.log('✗', m); process.exitCode = 1; };
async function api(path, opts = {}, token) {
  const r = await fetch(API + path, { ...opts, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}), ...(opts.headers || {}) } });
  const t = await r.text(); try { return { status: r.status, body: JSON.parse(t) }; } catch { return { status: r.status, body: t }; }
}
const login = async (u) => (await api('/auth/login', { method: 'POST', body: JSON.stringify({ identifier: u, password: 'password123' }) })).body.access_token;
function png(w, h) { // tiny valid PNG, solid color
  const crc = (b) => { let c, crcT = []; for (let n = 0; n < 256; n++) { c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; crcT[n] = c >>> 0; } let x = 0xffffffff; for (const v of b) x = crcT[(x ^ v) & 255] ^ (x >>> 8); return (x ^ 0xffffffff) >>> 0; };
  const chunk = (type, data) => { const len = Buffer.alloc(4); len.writeUInt32BE(data.length); const td = Buffer.concat([Buffer.from(type), data]); const c = Buffer.alloc(4); c.writeUInt32BE(crc(td)); return Buffer.concat([len, td, c]); };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 2;
  const row = Buffer.concat([Buffer.from([0]), Buffer.alloc(w * 3, 0x9b)]);
  const raw = Buffer.concat(Array.from({ length: h }, () => row));
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]);
}
(async () => {
  const hostTok = await login('dayo_hype');
  const events = (await api('/organizer/events', {}, hostTok)).body;
  const paid = events.find(e => !e.is_free);
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 420, height: 900 } });
  p.on('pageerror', e => console.log('PAGEERROR', e.message));
  await p.goto(BASE + '/login'); await p.waitForLoadState('networkidle');
  await p.getByLabel('Email or username').fill('dayo_hype'); await p.getByLabel('Password').fill('password123');
  await p.getByRole('button', { name: 'Log In' }).click(); await p.waitForURL(u => !u.pathname.startsWith('/login'));

  // ── Ticket tiers + image upload on the edit page
  await p.goto(`${BASE}/organizer/events/${paid.id}/edit`); await p.waitForLoadState('networkidle');
  await p.setInputFiles('input[type=file]', { name: 'cover.png', mimeType: 'image/png', buffer: png(64, 40) });
  await p.waitForFunction(() => [...document.querySelectorAll('input')].some(i => /\/api\/uploads\/[0-9a-f]{32}\.webp$/.test(i.value)), null, { timeout: 15000 })
    .then(() => ok('image upload filled the cover field with an /api/uploads/…webp URL'), () => bad('upload did not fill the field'));
  const loaded = await p.waitForFunction(() => { const i = [...document.querySelectorAll('img')].find(i => i.src.includes('/api/uploads/')); return i && i.complete && i.naturalWidth > 0; }, null, { timeout: 10000 }).then(() => true, () => false);
  loaded ? ok('uploaded image previews (served through the /api proxy)') : bad('preview did not load');
  await p.screenshot({ path: OUT + '/edit-upload.png', fullPage: true });
  for (let i = 0; i < 2; i++) { await p.getByRole('button', { name: /Continue/ }).click(); await p.waitForTimeout(500); }
  await p.getByText('Ticket Tiers').waitFor();
  const tiers = (await api(`/events/${paid.id}/tickets`)).body;
  const t0 = tiers[0];
  await p.getByRole('button', { name: `Edit ${t0.name}` }).click();
  await p.getByLabel('Price (₦)').fill(String(t0.price + 500));
  await p.getByRole('button', { name: 'Save', exact: true }).click();
  await p.waitForTimeout(1200);
  const after = (await api(`/events/${paid.id}/tickets`)).body.find(t => t.id === t0.id);
  after.price === t0.price + 500 ? ok(`tier price edited ${t0.price} → ${after.price}`) : bad('tier price not saved');
  await p.getByRole('button', { name: `Pause sales of ${t0.name}` }).click(); await p.waitForTimeout(1200);
  const pausedVisible = await p.getByText('sales paused').count();
  const publicTiers = (await api(`/events/${paid.id}/tickets`)).body;
  pausedVisible && !publicTiers.some(t => t.id === t0.id) ? ok('tier paused: hidden from buyers, still manageable') : bad('pause failed');
  await p.getByRole('button', { name: `Resume sales of ${t0.name}` }).click(); await p.waitForTimeout(800);
  await p.screenshot({ path: OUT + '/edit-tiers.png', fullPage: true });

  // ── Waitlist panel
  await api(`/events/${paid.id}`, { method: 'PATCH', body: JSON.stringify({ waitlist_enabled: true }) }, hostTok);
  for (let i = 0; i < 2; i++) {  // fresh people each run, so there's always someone waiting
    const u = 'wl' + Date.now().toString(36) + i;
    const t = (await api('/auth/register', { method: 'POST', body: JSON.stringify({ email: u + '@example.com', username: u, full_name: 'Wait Lister', password: 'password-123' }) })).body.access_token;
    await api(`/events/${paid.id}/waitlist`, { method: 'POST' }, t);
  }
  await p.goto(`${BASE}/organizer/events/${paid.id}/analytics`); await p.waitForLoadState('networkidle');
  await p.getByText(/Waitlist · \d+ waiting/).waitFor({ timeout: 10000 }).then(() => ok('waitlist panel lists waiting people'), () => bad('no waitlist panel'));
  await p.getByRole('button', { name: /Notify next 1/ }).click();
  await p.getByText(/Notified 1:/).waitFor({ timeout: 8000 }).then(() => ok('notify next 1 works'), () => bad('notify failed'));
  await p.screenshot({ path: OUT + '/waitlist.png', fullPage: true });

  // ── Community members
  const comm = (await api('/communities/my', {}, hostTok)).body.find(c => c.member_role === 'admin');
  const joiner = await login('chiamaka_lit'); await api(`/communities/${comm.slug}/join`, { method: 'POST' }, joiner);
  await p.goto(`${BASE}/communities/${comm.slug}/settings`); await p.waitForLoadState('networkidle');
  await p.getByText(/Members \(\d+\)/).waitFor();
  await p.getByLabel('Role for chiamaka_lit').selectOption('moderator'); await p.waitForTimeout(1200);
  const members = (await api(`/communities/${comm.slug}/members`, {}, hostTok)).body;
  members.find(m => m.username === 'chiamaka_lit')?.role === 'moderator' ? ok('member promoted to moderator from settings') : bad('role change failed');
  await p.screenshot({ path: OUT + '/community-members.png', fullPage: true });

  // ── Organizer profile form
  await p.goto(`${BASE}/organizer/verification`); await p.waitForLoadState('networkidle');
  await p.getByLabel('Organization name').fill('Hype House Events');
  await p.getByRole('button', { name: 'Save organizer profile' }).click();
  await p.getByText('Saved.').waitFor({ timeout: 8000 });
  const me = (await api('/auth/me', {}, hostTok)).body;
  me.organizer_profile.organization_name === 'Hype House Events' ? ok('organizer profile saved') : bad('organizer profile not saved');

  // ── Map on an event with coordinates, directions on all physical events
  const all = (await api('/events?limit=50')).body;
  await p.goto(`${BASE}/events/${all[0].slug}`); await p.waitForLoadState('networkidle');
  const dir = await p.getByRole('link', { name: /Get directions/ }).getAttribute('href').catch(() => null);
  dir && dir.startsWith('https://www.google.com/maps/search/') ? ok('event page has a directions link') : bad('no directions link');
  const iframe = await p.locator('iframe[src*="openstreetmap.org"]').count();
  console.log(`  (info) OSM map embed shown: ${iframe ? 'yes' : 'no (this event has no coordinates)'}`);
  await p.screenshot({ path: OUT + '/event-map.png', fullPage: false });
  await b.close();
})().catch(e => { console.error('✗ FAILED:', e.message); process.exit(1); });
