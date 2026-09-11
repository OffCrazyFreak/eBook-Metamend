import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Five independent pages during the design round. Each keeps its own fonts,
// palette, layout and motion; they share only src/mock and src/types.
const root = fileURLToPath(new URL('.', import.meta.url))
const variations = ['blueprint', 'ledger', 'terminal', 'editorial', 'foundry']

export default defineConfig({
  // The site is served from the repository path on GitHub Pages.
  base: '/eBook-Metamend/',
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': resolve(root, 'src') },
  },
  build: {
    rollupOptions: {
      input: {
        main: resolve(root, 'index.html'),
        ...Object.fromEntries(
          variations.map((name) => [name, resolve(root, `variations/${name}/index.html`)]),
        ),
      },
    },
  },
})
