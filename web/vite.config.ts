import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const root = fileURLToPath(new URL('.', import.meta.url))

export default defineConfig({
  // The site is served from the repository path on GitHub Pages.
  base: '/eBook-Metamend/',
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': resolve(root, 'src') },
  },
})
