import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { viteStaticCopy } from 'vite-plugin-static-copy'

const root = fileURLToPath(new URL('.', import.meta.url))

export default defineConfig({
  // The site is served from the repository path on GitHub Pages.
  base: '/eBook-Metamend/',
  plugins: [
    react(),
    tailwindcss(),
    // The interpreter ships from the npm package into the site at build time, so
    // nothing large enters git and the page never calls a CDN.
    viteStaticCopy({
      targets: [
        {
          src: ['node_modules/pyodide/*', '!**/*.{md,html,map}', '!**/*.d.ts', '!**/package.json'],
          dest: 'pyodide',
          rename: { stripBase: true },
        },
      ],
    }),
  ],
  // Pyodide loads itself at runtime; pre-bundling it breaks its file lookups.
  optimizeDeps: { exclude: ['pyodide'] },
  resolve: {
    alias: { '@': resolve(root, 'src') },
  },
  worker: { format: 'es' },
})
