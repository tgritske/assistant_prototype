import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true, changeOrigin: true },
      '/audio': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/scenarios': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/tts': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
