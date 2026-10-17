import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

// `base: './'` because the app is served from the APK's assets, not from a domain root.
export default defineConfig({
  base: './',
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, 'src') } },
  build: { outDir: 'dist', sourcemap: false },
})
