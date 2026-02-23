import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  server: {
    allowedHosts: ['ca.vuedapt.com'],
    host: '0.0.0.0',
    port: 3333,
  },
  plugins: [react()],
})
