import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const here = fileURLToPath(new URL('.', import.meta.url))

// Multi-page, not a client-side router. Each page is its own HTML entry, so /products/ is a
// real URL that a static host serves directly — no SPA rewrite rule, no router bundle, and
// each page ships only the JS it uses.
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        home: resolve(here, 'index.html'),
        products: resolve(here, 'products/index.html'),
      },
    },
  },
})
