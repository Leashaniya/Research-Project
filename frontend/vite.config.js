import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// All requests are routed through the local gateway running on port 80
const gatewayTarget = process.env.GATEWAY_URL || 'http://127.0.0.1:80'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Proxy API routes through Gateway
    proxy: {
      '/guidance': {
        target: gatewayTarget,
        changeOrigin: true,
      },
      '/papers': {
        target: gatewayTarget,
        changeOrigin: true,
      },
      '/mcq': {
        target: gatewayTarget,
        changeOrigin: true,
      },
      '/essay': {
        target: gatewayTarget,
        changeOrigin: true,
      },
    },
  },
})
