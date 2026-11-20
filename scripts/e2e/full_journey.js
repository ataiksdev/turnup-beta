// Full user journey, signup to door check-in, in a real browser (production build).
// Needs: backend seeded (`python -m app.cli seed`, DEBUG=true so Paystack is in mock mode and
// emails print to the backend log), PUBLIC_BASE_URL/FRONTEND_URL=http://localhost:3003,
// relaxed RATE_LIMIT_LOGIN/RATE_LIMIT_REGISTER; frontend on :3003; ffmpeg installed.
// Run: node scripts/e2e/full_journey.js <screenshot dir> <backend log file>
//
// Paystack's popup can't load offline, so a stand-in reports a successful payment and the app
// then verifies it with the API (mock mode), exactly as after a real payment. The door scan
// uses Chromium's fake camera fed with a video made from the saved ticket image.
const { chromium } = require('playwright');
const { execFileSync } = require('child_process');
const fs = require('fs');
const BASE = 'http://localhost:3003', API = 'http://localhost:8000/api';
const OUT = process.argv[2] || '.';
const LOG = process.argv[3];
const run = Date.now().toString(36);
const findings = [];
const ok = (m) => console.log('✓', m);
const bad = (m) => { console.log('✗', m); findings.push(m); process.exitCode = 1; };
let shot = 0;
const snap = (p, name) => p.screenshot({ path: `${OUT}/${String(++shot).padStart(2, '0')}-${name}.png`, fullPage: true }).catch(() => {});

// Every step ends with a screenshot of where the page is, pass or fail.
async function step(name, page, fn) {
  const slug = name.replace(/\W+/g, '-').replace(/^-|-$/g, '').slice(0, 60);
  try { await fn(); ok(name); await snap(page, slug); }
  catch (e) { bad(`${name}: ${e.message.split('\n')[0]}`); await snap(page, 'FAIL-' + slug); }
}
async function api(path, opts = {}, token) {
  const r = await fetch(API + path, { ...opts, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) } });
  const t = await r.text(); try { return { status: r.status, body: JSON.parse(t) }; } catch { return { status: r.status, body: t }; }
}
function emailLink(to, kind) {
  const lines = fs.readFileSync(LOG, 'utf8').split('\n');
  for (let i = lines.length - 1; i >= 0; i--) {
    if (lines[i].includes('[EMAIL] Link:') && lines[i].includes(kind) && lines.slice(Math.max(0, i - 3), i).some((l) => l.includes(to))) {
      return lines[i].split('Link: ')[1].trim();
    }
  }
  return null;
}
async function newPage(b, opts = {}) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, acceptDownloads: true, serviceWorkers: 'block', ...opts });
  const p = await ctx.newPage();
  p.on('pageerror', (e) => bad(`page error on ${p.url()}: ${e.message}`));
  p.on('console', (m) => { if (m.type() === 'error' && !/Failed to load resource|ERR_NAME|net::ERR/.test(m.text())) console.log('  console error:', m.text().slice(0, 160)); });
  // Paystack popup stand-in: reports a completed payment.
  await p.route('https://js.paystack.co/**', (r) => r.fulfill({ contentType: 'text/javascript',
    body: 'window.PaystackPop={setup:function(o){return{openIframe:function(){setTimeout(function(){o.callback({reference:o.ref})},300)}}}}' }));
  return p;
}
async function signup(p, { role, name, username, email }) {
  await p.goto(BASE + '/signup'); await p.waitForLoadState('networkidle');
  await p.getByText(role === 'organizer' ? 'Host events' : 'Discover events', { exact: false }).first().click();
  await p.getByRole('button', { name: 'Continue' }).click();
  await p.getByLabel('Full Name').fill(name);
  await p.getByLabel('Username').fill(username);
  await p.getByLabel('Email').fill(email);
  await p.getByLabel('Password').fill('Sup3r-secret-pass');
  await p.getByRole('button', { name: /create|sign up/i }).click();
  await p.waitForURL((u) => !u.pathname.startsWith('/signup'), { timeout: 15000 });
}

(async () => {
  const b = await chromium.launch();
  const att = { name: 'Ngozi Test', username: `ngozi_${run}`, email: `ngozi_${run}@example.com` };
  const org = { name: 'Kunle Promoter', username: `kunle_${run}`, email: `kunle_${run}@example.com` };
  const fan = await newPage(b);

  // ── 1. Attendee signs up, verifies email, onboards ────────────────────────────
  await step('attendee signs up', fan, async () => { await signup(fan, { role: 'attendee', ...att }); });
  console.log('  landed on', new URL(fan.url()).pathname);
  await step('onboarding: interests, city, preferences', fan, async () => {
    if (!fan.url().includes('/onboarding')) await fan.goto(BASE + '/onboarding');
    await fan.waitForLoadState('networkidle');
    await fan.getByRole('button', { name: /music/i }).first().click();
    await fan.getByRole('button', { name: /nightlife/i }).first().click();
    await snap(fan, 'onboarding-1-interests');
    await fan.getByRole('button', { name: /Continue/ }).click();
    await fan.getByRole('button', { name: /^Lagos$/ }).first().click();
    await fan.getByRole('button', { name: /Weekends/ }).click();
    await snap(fan, 'onboarding-2-where-when');
    await fan.getByRole('button', { name: /Continue/ }).click();
    await fan.getByRole('button', { name: /Mid-range/ }).click();
    await fan.getByRole('button', { name: /In-person/ }).click();
    await snap(fan, 'onboarding-3-budget-format');
    await fan.getByRole('button', { name: "Let's go!" }).click();
    await fan.waitForURL((u) => !u.pathname.startsWith('/onboarding'), { timeout: 15000 });
    await fan.waitForLoadState('networkidle');
  });
  await step('verification email is sent and its link verifies the address', fan, async () => {
    const link = emailLink(att.email, 'verify');
    if (!link) throw new Error('no verification link in the backend log');
    await fan.goto(link.replace(/^https?:\/\/[^/]+/, BASE)); await fan.waitForLoadState('networkidle');
    await fan.getByText(/verified/i).first().waitFor({ timeout: 10000 });
  });

  await step('an attendee opening organizer screens is offered organizer tools first', fan, async () => {
    await fan.goto(BASE + '/organizer/create'); await fan.waitForLoadState('networkidle');
    await fan.getByRole('button', { name: 'Become an organizer' }).waitFor({ timeout: 10000 });
    if (await fan.getByPlaceholder('e.g. Neon Nights: Summer Edition').count()) throw new Error('event form shown to a non-organizer');
  });

  // ── 2. Organizer signs up and creates a paid event ────────────────────────────
  const host = await newPage(b);
  await step('organizer signs up', host, async () => { await signup(host, { role: 'organizer', ...org }); });
  await step('organizer finishes the organizer profile', host, async () => {
    await host.waitForLoadState('networkidle');
    await host.getByPlaceholder(/Neon Nights Events/).fill('Kunle Live');
    await host.getByPlaceholder(/short description/).fill('Live music nights in Lagos.');
    await host.getByRole('button', { name: 'Finish Setup' }).click();
    await host.waitForURL(/organizer\/dashboard/, { timeout: 15000 });
    await host.waitForLoadState('networkidle');
  });
  console.log('  organizer landed on', new URL(host.url()).pathname);
  const title = `Rooftop Jam ${run}`;
  await step('organizer creates an event with a paid ticket tier', host, async () => {
    await host.goto(BASE + '/organizer/create'); await host.waitForLoadState('networkidle');
    await host.getByPlaceholder('e.g. Neon Nights: Summer Edition').fill(title);
    await host.getByPlaceholder(/Tell people what to expect/).fill('An evening of live music on a Lagos rooftop with friends, food and great views.');
    await snap(host, 'create-1-basics');
    await host.getByRole('button', { name: /Continue/ }).click();
    await host.getByPlaceholder(/Warehouse 23/).fill('Skyline Rooftop');
    await host.getByPlaceholder('123 Main St').fill('4 Akin Adesola Street, Victoria Island');
    await host.getByPlaceholder('Lagos').fill('Lagos');
    const start = new Date(Date.now() + 5 * 864e5); start.setHours(18, 0, 0, 0);
    const end = new Date(start.getTime() + 5 * 36e5);
    const fmt = (d) => new Date(d.getTime() - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 16);
    const dts = host.locator('input[type=datetime-local]');
    await dts.nth(0).fill(fmt(start)); await dts.nth(1).fill(fmt(end));
    await snap(host, 'create-2-time-place');
    await host.getByRole('button', { name: /Continue/ }).click();
    await host.getByRole('button', { name: /This event is free/ }).click();
    const tierName = host.getByPlaceholder('e.g. Early Bird, VIP, General Admission');
    if (!(await tierName.count())) await host.getByRole('button', { name: /Add tier/ }).click();
    await tierName.first().fill('General');
    await host.getByPlaceholder('0.00').first().fill('5000');
    await host.getByPlaceholder('Unlimited').first().fill('100');
    await snap(host, 'create-3-tickets');
    await host.getByRole('button', { name: /Continue/ }).click();
    await snap(host, 'create-4-review');
    if (!(await host.getByText('₦5,000').count())) throw new Error('review step does not show ₦5,000');
    if (await host.getByText(/\$5000/).count()) throw new Error('review step shows prices in dollars');
    await host.getByRole('button', { name: 'Publish Event' }).click();
    await host.waitForTimeout(2500);
  });
  const orgToken = (await api('/auth/login', { method: 'POST', body: JSON.stringify({ identifier: org.username, password: 'Sup3r-secret-pass' }) })).body.access_token;
  const mine = (await api('/organizer/events', {}, orgToken)).body;
  const ev = Array.isArray(mine) ? mine.find((e) => e.title === title) : null;
  ev ? ok(`event saved (status ${ev.status}, review ${ev.review_status})`) : bad('event was not saved');
  const tiers = ev ? (await api(`/events/${ev.id}/tickets?include_inactive=true`, {}, orgToken)).body : [];
  Array.isArray(tiers) && tiers.some((t) => t.price === 5000) ? ok('paid tier ₦5,000 saved') : bad(`paid tier not saved: ${JSON.stringify(tiers).slice(0, 200)}`);

  await step('My Events shows the event as waiting for approval, not a draft', host, async () => {
    await host.goto(BASE + '/organizer/events'); await host.waitForLoadState('networkidle');
    await host.getByText(/Waiting for approval/).waitFor({ timeout: 10000 });
    if (await host.getByText(/^Drafts/).count()) throw new Error('submitted event listed under Drafts');
  });

  // ── 3. Admin approves ─────────────────────────────────────────────────────────
  const admin = await newPage(b, { viewport: { width: 1280, height: 900 } });
  await step('admin approves the event from the queue', admin, async () => {
    await admin.goto(BASE + '/login'); await admin.waitForLoadState('networkidle');
    await admin.getByLabel('Email or username').fill('turnup_admin'); await admin.getByLabel('Password').fill('password123');
    await admin.getByRole('button', { name: 'Log In' }).click(); await admin.waitForURL((u) => !u.pathname.startsWith('/login'));
    await admin.goto(BASE + '/admin/events'); await admin.waitForLoadState('networkidle');
    const card = admin.locator('div').filter({ hasText: title }).filter({ has: admin.getByRole('button', { name: 'Approve' }) }).last();
    await card.getByRole('button', { name: 'Approve' }).click();
    await admin.waitForTimeout(1500);
    const after = (await api(`/events/${ev.id}`)).body;
    if (after.review_status !== 'approved' || after.status !== 'published') throw new Error(`still ${after.status}/${after.review_status}`);
  });
  await step('organizer is notified of the approval', host, async () => {
    const n = (await api('/social/notifications', {}, orgToken)).body;
    if (!Array.isArray(n) || !n.some((x) => /approved/i.test(x.title))) throw new Error('no approval notification');
  });

  // ── 4. Attendee finds and buys tickets ────────────────────────────────────────
  await step('attendee finds the event in search', fan, async () => {
    await fan.goto(BASE + '/search'); await fan.waitForLoadState('networkidle');
    await fan.getByPlaceholder(/Events, venues, cities/).fill('Rooftop Jam');
    await fan.waitForTimeout(1500);
    await fan.getByText(title).first().click();
    await fan.waitForURL(/\/events\//);
  });
  await step('attendee buys 2 tickets (₦10,000)', fan, async () => {
    await fan.waitForLoadState('networkidle');
    await snap(fan, 'event-page');
    const plus = fan.locator('button:has(svg.lucide-plus)').first();
    await plus.click(); await plus.click();
    await fan.getByRole('button', { name: /pay ₦10,000/i }).click();
    await fan.getByText(/ticket confirmed|you're going/i).first().waitFor({ timeout: 15000 });
    await fan.getByRole('button', { name: /Going ✓/ }).waitFor({ timeout: 10000 });
    if (!(await fan.getByText('₦5,000').count())) throw new Error('ticket price not shown as ₦5,000');
  });
  await step('ticket email is sent', fan, async () => {
    const log = fs.readFileSync(LOG, 'utf8');
    if (!new RegExp(`TO: ${att.email}[\\s\\S]{0,200}ticket`, 'i').test(log) && !log.includes(`To: ${att.email} | Subject: Your ticket`)) {
      const subj = log.split('\n').filter((l) => l.includes(att.email)).slice(-3).join(' | ');
      throw new Error(`no ticket email for the buyer (emails to them: ${subj || 'none'})`);
    }
  });
  let orderId = null;
  await step('ticket appears in My Tickets and opens', fan, async () => {
    await fan.goto(BASE + '/tickets'); await fan.waitForLoadState('networkidle');
    await fan.getByText(title).first().waitFor({ timeout: 10000 });
    await snap(fan, 'my-tickets');
    await fan.locator('a[href^="/tickets/"]').filter({ hasText: title }).getByText(/confirmed/i).click();
    await fan.waitForURL(/\/tickets\//); await fan.waitForLoadState('networkidle');
    orderId = fan.url().split('/').pop();
    await fan.getByText(/entry qr code/i).waitFor();
  });
  const ticketPng = `${OUT}/saved-ticket.png`;
  await step('attendee saves the ticket image', fan, async () => {
    const [dl] = await Promise.all([fan.waitForEvent('download'), fan.getByRole('button', { name: 'Save ticket' }).click()]);
    await dl.saveAs(ticketPng);
  });

  // ── 5. Door check-in by camera ────────────────────────────────────────────────
  const video = `${OUT}/ticket-camera.y4m`;
  if (!fs.existsSync(ticketPng)) { bad('no saved ticket image, so the camera scan can\'t be tested'); console.log('\n' + findings.join('\n- ')); await b.close(); return; }
  execFileSync('ffmpeg', ['-y', '-v', 'error', '-loop', '1', '-i', ticketPng, '-vf', 'crop=560:560:50:1250,scale=640:480:force_original_aspect_ratio=decrease,pad=640:480:(ow-iw)/2:(oh-ih)/2:white', '-t', '6', '-r', '10', '-pix_fmt', 'yuv420p', video]);
  const cam = await chromium.launch({ args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-video-capture=${video}`] });
  const door = await newPage(cam);
  await step('organizer opens check-in; the camera scan asks how many of the 2 are here', door, async () => {
    await door.goto(BASE + '/login'); await door.waitForLoadState('networkidle');
    await door.getByLabel('Email or username').fill(org.username); await door.getByLabel('Password').fill('Sup3r-secret-pass');
    await door.getByRole('button', { name: 'Log In' }).click(); await door.waitForURL((u) => !u.pathname.startsWith('/login'));
    await door.goto(`${BASE}/organizer/events/${ev.id}/checkin`); await door.waitForLoadState('networkidle');
    await door.getByText('0', { exact: true }).first().waitFor({ timeout: 10000 });
    await door.getByRole('button', { name: /start camera/i }).click();
    await door.getByText(/2 of 2 still to come in/).waitFor({ timeout: 15000 });
  });
  await step('door admits 1 now; the live count shows 1 / 2 in', door, async () => {
    await door.getByRole('button', { name: 'One fewer' }).click();
    await door.getByRole('button', { name: 'Admit 1' }).click();
    await door.getByText(/1 of 2 in/).first().waitFor({ timeout: 10000 });
    await door.getByText('/ 2 in').waitFor({ timeout: 10000 });
  });
  await step('scanning again admits the second person straight away', door, async () => {
    await door.getByText(/2 of 2 in/).first().waitFor({ timeout: 15000 });
  });
  await step('a third scan is refused: all 2 are in', door, async () => {
    await door.getByText(/already checked in \(all 2 in\)/i).first().waitFor({ timeout: 15000 });
  });
  await step("attendee's ticket now shows checked in", fan, async () => {
    await fan.reload(); await fan.waitForLoadState('networkidle');
    await fan.getByText(/checked in/i).first().waitFor({ timeout: 10000 });
  });

  console.log('\n' + (findings.length ? `${findings.length} problem(s):\n- ` + findings.join('\n- ') : 'No problems found.'));
  await cam.close(); await b.close();
})();
