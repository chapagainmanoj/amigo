import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@fontsource-variable/inter/latin.css': fileURLToPath(
        new URL('./src/styles/inter-latin.css', import.meta.url)
      ),
    },
  },
})
