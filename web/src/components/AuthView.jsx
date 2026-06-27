import { useState } from 'react'
import { supabase, isSupabaseConfigured } from '../supabase'

export default function AuthView() {
  const [isSignUp, setIsSignUp] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [message, setMessage] = useState(null)

  const handleAuth = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setMessage(null)

    const { error: authError } = isSignUp 
      ? await supabase.auth.signUp({ email, password })
      : await supabase.auth.signInWithPassword({ email, password })

    if (authError) {
      setError(authError.message)
    } else if (isSignUp) {
      setMessage('Check your email to confirm your account!')
    }
    setLoading(false)
  }

  if (!isSupabaseConfigured) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px' }}>
        <div className="flat-card" style={{ padding: '32px', maxWidth: '400px', width: '100%' }}>
          <h2 style={{ marginBottom: '16px', color: 'var(--ember)' }}>Configuration Required</h2>
          <p style={{ color: 'var(--mist)', marginBottom: '16px' }}>
            It looks like Supabase is not configured. 
          </p>
          <p style={{ color: 'var(--mist)' }}>
            Please create a <code>.env</code> file in the <code>web/</code> directory with your <code>VITE_SUPABASE_URL</code> and <code>VITE_SUPABASE_ANON_KEY</code> to enable authentication.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px', background: 'radial-gradient(circle at top right, rgba(255,138,91,0.1), transparent 40%)' }}>
      <div className="glass-panel animate-slide-in" style={{ padding: '40px', maxWidth: '400px', width: '100%' }}>
        <div style={{ textAlign: 'center', marginBottom: '32px' }}>
          <h1 className="display-text" style={{ fontSize: '2rem', marginBottom: '8px' }}>Amigo</h1>
          <p style={{ color: 'var(--mist)' }}>Your proactive daily planner</p>
        </div>

        <div style={{ display: 'flex', gap: '8px', marginBottom: '24px', background: 'rgba(0,0,0,0.2)', padding: '4px', borderRadius: '10px' }}>
          <button 
            style={{ flex: 1, padding: '8px', borderRadius: '6px', background: !isSignUp ? 'var(--dusk)' : 'transparent', color: !isSignUp ? 'var(--paper)' : 'var(--mist)' }}
            onClick={() => { setIsSignUp(false); setError(null); setMessage(null); }}
          >
            Sign In
          </button>
          <button 
            style={{ flex: 1, padding: '8px', borderRadius: '6px', background: isSignUp ? 'var(--dusk)' : 'transparent', color: isSignUp ? 'var(--paper)' : 'var(--mist)' }}
            onClick={() => { setIsSignUp(true); setError(null); setMessage(null); }}
          >
            Create Account
          </button>
        </div>

        {error && <div style={{ background: 'rgba(232,99,63,0.1)', color: 'var(--ember-deep)', padding: '12px', borderRadius: '8px', marginBottom: '16px', fontSize: '0.9rem' }}>{error}</div>}
        {message && <div style={{ background: 'rgba(243,194,106,0.1)', color: 'var(--gold)', padding: '12px', borderRadius: '8px', marginBottom: '16px', fontSize: '0.9rem' }}>{message}</div>}

        <form onSubmit={handleAuth}>
          <div className="form-group">
            <label>Email</label>
            <input 
              type="email" 
              value={email} 
              onChange={(e) => setEmail(e.target.value)} 
              placeholder="you@example.com" 
              required 
            />
          </div>
          <div className="form-group" style={{ marginBottom: '24px' }}>
            <label>Password</label>
            <input 
              type="password" 
              value={password} 
              onChange={(e) => setPassword(e.target.value)} 
              placeholder="••••••••" 
              required 
            />
          </div>
          <button type="submit" className="btn-primary" style={{ width: '100%' }} disabled={loading}>
            {loading ? 'Processing...' : isSignUp ? 'Sign Up' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  )
}
