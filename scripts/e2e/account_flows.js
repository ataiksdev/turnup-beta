// End-to-end check of the account screens in a real browser (Playwright):
// verify email, password login, 2FA setup + login, logout, forgot/reset password,
// magic link (+2FA), and the ?next= open-redirect guard.
//
// Run against a production build (next dev has a client-router quirk that can leave a
// repeated login on /login):
//   backend:  cd backend && DEBUG=true SECRET_KEY=<32+ chars> RATE_LIMIT_LOGIN=1000/minute \
//             RATE_LIMIT_2FA_VERIFY=1000/minute uvicorn app.main:app --port 8000 > /tmp/backend.log 2>&1
//   frontend: cd frontend && npx next build && PORT=3003 node .next/standalone/server.js
//             (copy .next/static and public into .next/standalone first)
//   test:     node scripts/e2e/account_flows.js /tmp/backend.log /tmp
// Emails are read from the backend log (DEBUG mode prints them instead of sending).
const { chromium } = require('playwright');
const crypto = require('crypto');
const fs = require('fs');
const LOG = process.argv[2], OUT = process.argv[3];
const BASE = 'http://localhost:3003';
function totp(secret) {
  const alpha = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'; let bits = '';
  for (const c of secret.replace(/=+$/, '')) bits += alpha.indexOf(c).toString(2).padStart(5, '0');
  const key = Buffer.from(bits.match(/.{8}/g).map(b => parseInt(b, 2)));
  const ctr = Buffer.alloc(8); ctr.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const h = crypto.createHmac('sha1', key).update(ctr).digest(); const o = h[19] & 15;
  return String(((h.readUInt32BE(o) & 0x7fffffff) % 1e6)).padStart(6, '0');
}
const lastLink = (re) => { const m = [...fs.readFileSync(LOG, 'utf8').matchAll(re)]; return m.length ? m[m.length - 1][0] : null; };
const step = (s) => console.log('✓', s);
(async () => {
  const u = 'e2e' + Date.now().toString(36);
  const email = `${u}@example.com`, pw = 'first-password-1', pw2 = 'second-password-2';
  const r = await fetch('http://localhost:8000/api/auth/register', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, username: u, full_name: 'E2E Tester', password: pw }) });
  if (!r.ok) throw new Error('register ' + r.status + await r.text());
  step('registered ' + u);

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 420, height: 900 } });
  page.on('pageerror', e => console.log('PAGE ERROR', e.message));

  // verify email from the emailed link
  const verify = lastLink(new RegExp(`http://localhost:3000/verify-email\\?token=[\\w-]+`, 'g'));
  await page.goto(verify.replace('http://localhost:3000', BASE));
  await page.getByText('Your email is verified').waitFor(); step('verify-email page verified the address');

  // password login
  await page.goto(BASE + '/login');
  await page.getByLabel('Email or username').fill(u);
  await page.getByLabel('Password').fill(pw);
  await page.getByRole('button', { name: 'Log In' }).click();
  await page.waitForURL(url => !url.pathname.startsWith('/login'));
  step('password login works');

  // settings: 2FA setup
  await page.goto(BASE + '/settings');
  await page.getByText('Appearance').first().waitFor();
  await page.getByText('Verified').waitFor(); step('settings shows email as verified');
  await page.getByRole('button', { name: 'Set up 2FA' }).click();
  const keyText = await page.getByText('Enter this key').textContent();
  const secret = keyText.split(':').pop().trim();
  await page.getByLabel('Code').fill(totp(secret));
  await page.getByRole('button', { name: 'Turn on 2FA' }).click();
  await page.getByText('Save these backup codes').waitFor(); step('2FA enabled, backup codes shown');
  await page.screenshot({ path: OUT + '/settings-backup-codes.png', fullPage: true });
  await page.getByRole('button', { name: "I've saved them" }).click();
  await page.getByText("you'll be asked for a code").waitFor();
  await page.screenshot({ path: OUT + '/settings.png', fullPage: true });

  // logout (server-side) then login requires 2FA
  await page.getByRole('button', { name: 'Log out' }).click();
  await page.waitForURL('**/login'); step('logout returns to login');
  await page.getByLabel('Email or username').fill(u);
  await page.getByLabel('Password').fill(pw);
  await page.getByRole('button', { name: 'Log In' }).click();
  await page.getByLabel('Authentication code').waitFor(); step('login now asks for 2FA code');
  await page.screenshot({ path: OUT + '/login-2fa.png' });
  await page.getByLabel('Authentication code').fill('000000');
  await page.getByRole('button', { name: 'Verify & Log In' }).click();
  await page.getByText('Invalid 2FA code').waitFor(); step('wrong code rejected');
  await page.getByLabel('Authentication code').fill(totp(secret));
  await page.getByRole('button', { name: 'Verify & Log In' }).click();
  await page.waitForURL(url => !url.pathname.startsWith('/login')); step('correct code logs in');

  // forgot / reset password (logged out context)
  const ctx2 = await browser.newContext(); const p2 = await ctx2.newPage();
  await p2.goto(BASE + '/login'); await p2.waitForLoadState('networkidle');
  await p2.getByRole('link', { name: 'Forgot password?' }).click();
  await p2.waitForURL('**/forgot-password'); await p2.waitForLoadState('networkidle');
  await p2.getByLabel('Email').fill(email);
  await p2.getByRole('button', { name: 'Send reset link' }).click();
  await p2.getByText('has a Turnup account').waitFor({timeout: 8000}).catch(async e => { console.log('URL', p2.url()); console.log((await p2.locator('body').innerText()).slice(0,500)); throw e; }); step('forgot-password sends link');
  await new Promise(r => setTimeout(r, 500));
  const reset = lastLink(/http:\/\/localhost:3000\/reset-password\?token=[\w-]+/g);
  await p2.goto(reset.replace('http://localhost:3000', BASE)); await p2.waitForLoadState('networkidle');
  await p2.getByLabel('New password', { exact: true }).fill(pw2);
  await p2.getByLabel('Confirm new password').fill(pw2);
  await p2.getByRole('button', { name: 'Update password' }).click();
  await p2.getByText('signed out everywhere').waitFor(); step('reset-password changes password');

  // the first browser's session was revoked by the reset
  const me = await page.evaluate(async () => {
    const t = JSON.parse(localStorage.getItem('turnup-auth')).state.token;
    return (await fetch('/api/auth/me', { headers: { Authorization: 'Bearer ' + t } })).status;
  });
  console.log(me === 401 ? '✓ reset revoked existing sessions' : '✗ old session still valid: ' + me);

  // magic link: requires 2FA afterwards
  await p2.goto(BASE + '/login'); await p2.waitForLoadState('networkidle');
  await p2.getByRole('button', { name: 'Email me a login link' }).click();
  await p2.getByLabel('Email').fill(email);
  await p2.getByRole('button', { name: 'Send login link' }).click();
  await p2.getByText('login link is on its way').waitFor();
  await new Promise(r => setTimeout(r, 500));
  const magic = lastLink(/http:\/\/localhost:3000\/auth\/magic\?token=[\w-]+/g);
  await p2.goto(magic.replace('http://localhost:3000', BASE));
  await p2.getByText('Two-factor authentication').waitFor(); step('magic link asks for 2FA');
  await p2.getByLabel('Authentication code').fill(totp(secret));
  await p2.getByRole('button', { name: 'Verify & Log In' }).click();
  await p2.waitForURL(url => !url.pathname.startsWith('/auth/magic')); step('magic link + 2FA logs in');

  // open redirect guard
  await page.goto(BASE + '/login?next=//evil.example'); await page.waitForLoadState('networkidle');
  await page.getByLabel('Email or username').fill(u);
  await page.getByLabel('Password').fill(pw2);
  await page.getByRole('button', { name: 'Log In' }).click();
  await page.getByLabel('Authentication code').fill(totp(secret));
  await page.getByRole('button', { name: 'Verify & Log In' }).click();
  await page.waitForURL(url => !url.pathname.startsWith('/login'));
  console.log(new URL(page.url()).host === 'localhost:3003' ? '✓ ?next=//evil.example stays on site' : '✗ redirected to ' + page.url());
  await browser.close();
})().catch(e => { console.error('✗ FAILED:', e.message); process.exit(1); });
