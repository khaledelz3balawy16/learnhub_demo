import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'
import { visualizer } from 'rollup-plugin-visualizer'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [
    react(),
    tailwindcss(),
    // `npm run build -- --mode analyze` writes dist/stats.html (what is in each chunk)
    mode === 'analyze' && visualizer({ filename: 'dist/stats.html', gzipSize: true }),
  ],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  build: {
    target: 'es2022',
    rolldownOptions: {
      output: {
        // Long-lived vendor chunks: they cache across deploys and keep the entry chunk small.
        codeSplitting: {
          groups: [
            { name: 'vendor-react', test: /node_modules[\\/](react|react-dom|scheduler|react-router|react-router-dom)[\\/]/, priority: 3 },
            { name: 'vendor-query', test: /node_modules[\\/]@tanstack[\\/]/, priority: 2 },
            { name: 'vendor-radix', test: /node_modules[\\/](@radix-ui|@floating-ui)[\\/]/, priority: 1 },
          ],
        },
      },
    },
  },
  server: {
    // Invitation emails are often opened on a phone during local testing. Bind to
    // the LAN interface so a configured FRONTEND_URL can reach this dev server.
    host: '0.0.0.0',
    port: 5173,
    // Same-origin in dev: session cookies + CSRF work without CORS tricks.
    proxy: {
      '/api': 'http://localhost:8000',
      '/_allauth': 'http://localhost:8000',
    },
  },
}))
