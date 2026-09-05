import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        // Keep the message catalog cacheable independently from the application shell.
        // This also leaves room for reviewed copy and additional locales without making
        // every first-page JavaScript update carry the complete English catalog again.
        manualChunks(id) {
          if (id.endsWith('/src/i18n/en-US.json')) return 'locale-en-US'
        },
      },
    },
  },
  server: {
    port: 3200,
    proxy: {
      '/api': 'http://localhost:8000',
      '/_allauth': 'http://localhost:8000',
    },
  },
})
