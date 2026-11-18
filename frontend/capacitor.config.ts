import fs from 'fs';
import path from 'path';
import type { CapacitorConfig } from '@capacitor/cli';

// Local-only override for live-reload against a dev server instead of the bundled
// static export. Set CAPACITOR_DEV_SERVER_URL in .env.local (gitignored) — never
// commit a real value here, since it'd be a machine-specific LAN address.
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

const devServerUrl = readDevServerUrl();

// Say which mode this sync produces: a stray CAPACITOR_DEV_SERVER_URL silently turns the app
// into a live-reload shell that shows "Web page not available" when the server isn't reachable.
if (devServerUrl) {
  let host = '';
  try { host = new URL(devServerUrl).hostname; } catch { /* reported by Capacitor */ }
  console.log(`[capacitor] LIVE RELOAD: the app will load ${devServerUrl} (from CAPACITOR_DEV_SERVER_URL).`);
  if (['localhost', '127.0.0.1', '0.0.0.0', '::1'].includes(host)) {
    console.warn(
      `[capacitor] WARNING: "${host}" is the phone itself, not your computer, so the app will show\n` +
      `  "Web page not available". Use your computer's LAN IP (e.g. http://192.168.1.20:3003),\n` +
      `  or run "adb reverse tcp:3003 tcp:3003" first. For the bundled build, unset\n` +
      `  CAPACITOR_DEV_SERVER_URL (shell, .env.local, .env) and run "npx cap sync android" again.`,
    );
  }
} else {
  console.log("[capacitor] Bundled build: the app loads the static export in out/ (no dev server).");
}

const config: CapacitorConfig = {
  appId: 'com.turnupp.app',
  appName: 'turnup',
  webDir: 'out',
  server: devServerUrl
    ? { url: devServerUrl, cleartext: true }
    : { androidScheme: 'http' },
};

export default config;
