import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { spawn, type ChildProcess } from 'node:child_process'
import { existsSync } from 'node:fs'
import { createConnection } from 'node:net'
import { resolve } from 'node:path'
import { defineConfig, type Plugin } from 'vite'

const ASSISTANT_PORT = 8787
const ROOT = resolve(import.meta.dirname, '..')

/** true se qualcosa ascolta già sulla porta (es. un assistente avviato a mano). */
const portInUse = (port: number) =>
  new Promise<boolean>((ok) => {
    const s = createConnection({ host: '127.0.0.1', port })
    s.once('connect', () => (s.destroy(), ok(true)))
    s.once('error', () => ok(false))
  })

/** In sviluppo avvia l'assistente (python -m assistant serve) insieme a Vite e lo chiude con Vite. */
function assistant(): Plugin {
  let child: ChildProcess | undefined
  const stop = () => {
    if (child && child.exitCode === null) child.kill('SIGTERM')
  }
  return {
    name: 'assistant-server',
    apply: 'serve',
    async configureServer(server) {
      if (await portInUse(ASSISTANT_PORT)) {
        server.config.logger.info(`[assistant] già attivo sulla porta ${ASSISTANT_PORT}, lo riuso`)
        return
      }
      const venv = resolve(ROOT, '.venv/bin/python')
      const python = existsSync(venv) ? venv : 'python3'
      child = spawn(python, ['-m', 'assistant', 'serve', '--port', String(ASSISTANT_PORT)], { cwd: ROOT, stdio: 'inherit' })
      child.on('error', (e) => server.config.logger.error(`[assistant] avvio fallito: ${e.message}`))
      child.on('exit', (code) => {
        if (code) server.config.logger.error(`[assistant] terminato con codice ${code}`)
      })
      server.httpServer?.once('close', stop)
      process.once('exit', stop)
      for (const sig of ['SIGINT', 'SIGTERM'] as const) process.once(sig, () => (stop(), process.exit()))
    },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), assistant()],
  // Chat: l'assistente (porta 8787) parte con `npm run dev`; in sviluppo /api passa da qui, senza CORS.
  server: { proxy: { '/api': `http://127.0.0.1:${ASSISTANT_PORT}` } },
})
