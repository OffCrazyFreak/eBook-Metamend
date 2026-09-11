import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import '@fontsource/martian-mono/400.css'
import '@fontsource/martian-mono/600.css'
import '@fontsource/martian-mono/800.css'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/400-italic.css'
import '@fontsource/ibm-plex-mono/500.css'
import '@/styles/base.css'
import './styles.css'

import { App } from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
