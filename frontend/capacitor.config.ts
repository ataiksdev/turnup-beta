import fs from 'fs';
import path from 'path';
import type { CapacitorConfig } from '@capacitor/cli';

// Local-only override for live-reload against a dev server instead of the bundled
// static export: set CAPACITOR_DEV_SERVER_URL in .env.local (gitignored, never commit a real
// value: it's a machine-specific LAN address) and sync with `npm run cap:live`. A plain
// `npx cap sync android` refuses while it's set, so it can't produce a live-reload app by accident.
function readDevServerUrl(): string | undefined {
  if (process.env.CAPACITOR_DEV_SERVER_URL) return process.env.CAPACITOR_DEV_SERVER_URL;

  for (const file of ['.env.local', '.env']) {
    const envPath = path.join(__dirname, file);
    if (!fs.existsSync(envPath)) continue;
    const match = fs.readFileSync(envPath, 'utf-8')
      .split('\n')
      .find((line) => line.trim().startsWith('CAPACITOR_DEV_SERVER_URL='));
    if (match) return match.split('=').slice(1).join('=').trim();
  }
  return undefined;
}

const foundDevServerUrl = readDevServerUrl();
// Live reload only when asked for explicitly (npm run cap:live). A CAPACITOR_DEV_SERVER_URL left
// in the shell, .env.local or .env used to turn every sync into a live-reload shell without
// saying so: the app then showed "Web page not available" whenever that computer's dev server
// wasn't reachable, and nothing was bundled. Now that's an error, so it can't happen silently.
const liveReload = process.env.CAPACITOR_LIVE_RELOAD === 'true';
if (foundDevServerUrl && !liveReload) {
  throw new Error(
    `\n[capacitor] Stopped: CAPACITOR_DEV_SERVER_URL is set (${foundDevServerUrl}), which would make\n` +
    `  the app a live-reload shell for that address instead of the bundled app.\n` +
    `  - For the normal bundled app: remove CAPACITOR_DEV_SERVER_URL from your shell, frontend/.env.local\n` +
    `    and frontend/.env, then run: npm run build:capacitor && npx cap sync android\n` +
    `  - For live reload on purpose: npm run cap:live\n`,
  );
}
if (liveReload && !foundDevServerUrl) {
  throw new Error(
    "\n[capacitor] Live reload asked for, but CAPACITOR_DEV_SERVER_URL isn't set. Set it to your\n" +
    "  computer's LAN address, e.g. CAPACITOR_DEV_SERVER_URL=http://192.168.1.20:3003\n",
  );
}
const devServerUrl = liveReload ? foundDevServerUrl : undefined;

// Say which mode this sync produces.
if (devServerUrl) {
  let host = '';
  try { host = new URL(devServerUrl).hostname; } catch { /* reported by Capacitor */ }
  console.log(`[capacitor] LIVE RELOAD: the app will load ${devServerUrl} (from CAPACITOR_DEV_SERVER_URL).`);
  if (['localhost', '127.0.0.1', '0.0.0.0', '::1'].includes(host)) {
    console.warn(
      `[capacitor] WARNING: "${host}" is the phone itself, not your computer, so the app will show\n` +
      `  "Web page not available". Use your computer's LAN IP (e.g. http://192.168.1.20:3003),\n` +
      `  or run "adb reverse tcp:3003 tcp:3003" first.`,
    );
  }
} else {
  console.log("[capacitor] Bundled build: the app loads the static export in out/ (no dev server).");
}

const config: CapacitorConfig = {
  appId: 'com.turnupp.app',
  appName: 'turnup',
  webDir: 'out',
  // The splash's dark background, so the WebView never flashes white before the page paints.
  backgroundColor: '#0C0A12',
  server: devServerUrl
    ? { url: devServerUrl, cleartext: true }
    : { androidScheme: 'http' },
};

export default config;
