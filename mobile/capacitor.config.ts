import type { CapacitorConfig } from '@capacitor/cli'

const config: CapacitorConfig = {
  appId: 'br.com.syncrofin.mobile',
  appName: 'SyncroFin',
  webDir: 'dist',
  server: {
    // The WebView is served from https://localhost; the SyncroFin server is a different origin.
    androidScheme: 'https',
  },
  plugins: {
    // Native HTTP instead of the WebView's fetch: the server's CORS only allows its own web
    // address, and a WebView on https://localhost is not that. Native requests have no CORS.
    CapacitorHttp: { enabled: true },
  },
}

export default config
