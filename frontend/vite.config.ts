import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: { chunkSizeWarningLimit: 1200 },
  server: {
    port: 3200,
    proxy: {
      '/api': 'http://localhost:8000',
      '/_allauth': 'http://localhost:8000',
    },
  },
})
