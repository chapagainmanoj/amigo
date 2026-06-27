import { useState, useEffect } from 'react'
import { supabase, isSupabaseConfigured } from './supabase'
import AuthView from './components/AuthView'
import AppShell from './components/AppShell'

function App() {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!isSupabaseConfigured) {
      setLoading(false)
      return
    }

    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session)
      setLoading(false)
    })

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session)
    })

    return () => subscription.unsubscribe()
  }, [])

  if (loading) {
    return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', color: 'var(--mist)' }}>Loading...</div>
  }

  if (!session) {
    return <AuthView />
  }

  return <AppShell session={session} />
}

export default App
