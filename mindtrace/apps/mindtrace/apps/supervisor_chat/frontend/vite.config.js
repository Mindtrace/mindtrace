import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const BACKEND = process.env.VITE_BACKEND_URL || 'http://localhost:8095'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/chat':    { target: BACKEND, changeOrigin: true },
      '/welcome': { target: BACKEND, changeOrigin: true },
      '/events':  { target: BACKEND, changeOrigin: true },
    },
  },
})
