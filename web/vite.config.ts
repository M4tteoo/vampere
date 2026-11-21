import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Chat: l'assistente gira a parte (python -m assistant serve, porta 8787); in sviluppo /api passa da qui, senza CORS.
  server: { proxy: { '/api': 'http://127.0.0.1:8787' } },
})
