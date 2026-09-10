import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Localhost-only dev server (spec FR-002, SC-011). /api is proxied to the FastAPI
// backend so the browser always talks to one origin.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})