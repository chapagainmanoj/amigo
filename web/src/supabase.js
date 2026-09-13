import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY
const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const isSupabaseConfigured = Boolean(supabaseUrl && supabaseAnonKey)

// Fallback to placeholder if not configured so client creation doesn't throw
export const supabase = createClient(
  supabaseUrl || 'https://placeholder.supabase.co',
  supabaseAnonKey || 'placeholder-key'
)

export async function apiRequest(path, options = {}) {
  const { data: { session } } = await supabase.auth.getSession()
  const token = session?.access_token

  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  }

  const response = await fetch(`${apiUrl}${path}`, {
    ...options,
    headers,
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    const error = new Error(errorData.detail || `API request failed with status ${response.status}`)
    error.status = response.status
    // The server marks a conflict that resolves itself on a second attempt, so callers can
    // retry rather than showing the participant an error they cannot act on.
    error.retryable = response.headers.get('X-Retryable') === 'true'
    throw error
  }

  return response.json()
}

