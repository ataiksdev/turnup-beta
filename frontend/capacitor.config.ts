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

const config: CapacitorConfig = {
  appId: 'com.turnupp.app',
  appName: 'turnup',
  webDir: 'out',
  server: devServerUrl
    ? { url: devServerUrl, cleartext: true }
    : { androidScheme: 'http' },
};

export default config;
