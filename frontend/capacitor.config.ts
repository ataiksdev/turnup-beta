import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.turnupp.app',
  appName: 'turnup',
  webDir: 'out',
  server: {
    url: 'http://10.175.121.187:9000',
    cleartext: true
  }
};

export default config;
