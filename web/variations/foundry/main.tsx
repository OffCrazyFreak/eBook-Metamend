import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import '@fontsource/archivo-black/400.css'
import '@fontsource/archivo/400.css'
import '@fontsource/archivo/500.css'
import '@fontsource/archivo/700.css'
import '@/styles/base.css'
import './styles.css'

import { App } from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
