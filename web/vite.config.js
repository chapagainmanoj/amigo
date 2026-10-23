/* global process */
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

const REQUIRED_ENV = ['VITE_SUPABASE_URL', 'VITE_SUPABASE_ANON_KEY', 'VITE_API_URL']

// https://vitejs.dev/config/
export default defineConfig(({ command, mode }) => {
  // Render sets RENDER in its build environment. A deploy missing these would ship a dashboard
  // that signs in to a placeholder project and calls localhost, so fail the build instead.
  if (command === 'build' && process.env.RENDER) {
    const env = loadEnv(mode, process.cwd(), 'VITE_')
    const missing = REQUIRED_ENV.filter((key) => !env[key])
    if (missing.length) throw new Error(`Missing build env: ${missing.join(', ')}`)
  }
  return { plugins: [react()] }
})
