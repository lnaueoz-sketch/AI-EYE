import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// 백엔드(FastAPI)가 8000번 포트에서 돈다고 가정.
// 프록시 덕분에 프론트는 /api, /snapshots 로만 호출하면 되고 CORS 문제도 생기지 않음.
const BACKEND = 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // 팀원 공유용: 같은 와이파이 IP 접속 / Cloudflare·ngrok 터널 주소 접속 허용
    allowedHosts: true,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true },
      '/snapshots': { target: BACKEND, changeOrigin: true },
    },
  },
})
