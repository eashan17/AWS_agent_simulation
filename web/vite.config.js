import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The built files (web/dist) are served by FastAPI from the same server, so every call is a
// same-origin /api/... request. In development, Vite forwards /api to the local API.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { '/api': 'http://localhost:8000' } },
  preview: { proxy: { '/api': 'http://localhost:8000' } },
  build: { outDir: 'dist', emptyOutDir: true },
})
