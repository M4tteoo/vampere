import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/inter'
import './index.css'
import App from './App.tsx'
import { useApp } from './store'
import { useIntro } from './intro/store'
import { useScreen } from './scene/twin/screen'

// Solo in sviluppo: lo script del video (web/scripts/demo-video.mjs) legge e comanda la demo da qui.
if (import.meta.env.DEV) Object.assign(window, { __vampere: { app: useApp, intro: useIntro, screen: useScreen } })

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
