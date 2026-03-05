import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Use 127.0.0.1 to avoid Windows IPv6 ::1 resolution (ECONNREFUSED)
// With Docker: set GATEWAY_URL=http://127.0.0.1:80 before npm run dev
// Without Docker: proxy directly to each service (default)
const gatewayTarget = process.env.GATEWAY_URL || 'http://127.0.0.1:80'
const useGateway = !!process.env.GATEWAY_URL
const guidanceTarget = useGateway ? gatewayTarget : 'http://127.0.0.1:8000'
const papersTarget = useGateway ? gatewayTarget : 'http://127.0.0.1:8001'
const mcqTarget = process.env.VITE_MCQ_PROXY_TARGET || 'http://127.0.0.1:8002'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Proxy API routes
    proxy: {
      '/guidance': {
        target: guidanceTarget,
        changeOrigin: true,
        ...(useGateway ? {} : { rewrite: (path) => path.replace(/^\/guidance/, '') }),
      },
      '/papers': {
        target: papersTarget,
        changeOrigin: true,
        ...(useGateway ? {} : { rewrite: (path) => path.replace(/^\/papers/, '') }),
      },
      // MCQ: proxy directly to FastAPI service (no gateway needed)
      // Strip /mcq prefix so backend receives /api/dashboard/ not /mcq/api/dashboard/
      '/mcq': {
        target: mcqTarget,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/mcq/, ''),
      },
    },
  },
})
