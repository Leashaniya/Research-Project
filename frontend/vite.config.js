import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Gateway URL for dev proxy (when using docker compose: gateway is on port 80)
const gatewayTarget = process.env.GATEWAY_URL || 'http://localhost:80'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Proxy API routes to the microservice gateway so relative /guidance and /papers work in dev
    proxy: {
      '/guidance': {
        target: gatewayTarget,
        changeOrigin: true,
      },
      '/papers': {
        target: gatewayTarget,
        changeOrigin: true,
      },
    },
  },
})
