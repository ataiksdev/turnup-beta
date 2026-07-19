import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.turnupp.app',
  appName: 'turnup',
  webDir: 'out',
  server: {
    androidScheme: 'https'
  }
};

export default config;
