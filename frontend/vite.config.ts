import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/ws': { target: 'ws://localhost:8000', ws: true, changeOrigin: true },
      '/audio': { target: 'http://localhost:8000', changeOrigin: true },
      '/scenarios': { target: 'http://localhost:8000', changeOrigin: true },
      '/tts': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
