import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Backend port can be overridden (start.ps1 sets this when 8001 is taken)
const backendPort = process.env.BACKEND_PORT ?? '8001'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': `http://localhost:${backendPort}`,
    },
  },
})
