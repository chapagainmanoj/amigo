import { useCallback, useEffect, useState } from 'react'
import { LayoutDashboard, Link2, LogOut } from 'lucide-react'
import { supabase, apiRequest } from '../supabase'
import DashboardView from './DashboardView'
import ConnectView from './ConnectView'
import ActivationJourney from './ActivationJourney'

export default function AppShell({ session }) {
  const [activeView, setActiveView] = useState('dashboard')
  const [pairedUser, setPairedUser] = useState(null)
  const [checkingPairing, setCheckingPairing] = useState(true)
  const [activation, setActivation] = useState(null)
  const activationResultKey = `amigo-activation-result:${session.user.id}`
  const [activationResultSeen, setActivationResultSeen] = useState(
    () => localStorage.getItem(activationResultKey) === 'seen',
  )

  const checkPairing = useCallback(async () => {
    try {
      const nextActivation = await apiRequest('/api/activation')
      setActivation(nextActivation)
      setPairedUser(nextActivation.completed ? nextActivation.profile : null)
    } catch {
      setActivation(null)
      setPairedUser(null)
    } finally {
      setCheckingPairing(false)
    }
  }, [])

  useEffect(() => {
    checkPairing()
  }, [checkPairing])

  const handleSignOut = async () => {
    await supabase.auth.signOut()
  }

  if (checkingPairing) {
    return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', color: 'var(--ink-2)' }}>Checking pairing status...</div>
  }

  if (!activation) {
    return <div className="activation-shell"><div className="activation-error" role="alert">Setup status is unavailable. Check your connection and refresh this page.</div></div>
  }

  if (!activation.completed || !activationResultSeen) {
    return (
      <ActivationJourney
        session={session}
        state={activation}
        refresh={checkPairing}
        onFinish={() => {
          localStorage.setItem(activationResultKey, 'seen')
          setActivationResultSeen(true)
        }}
      />
    )
  }

  const effectiveView = pairedUser ? activeView : 'connect'

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      {/* Desktop Sidebar */}
      <aside style={{
        width: '240px',
        borderRight: '1px solid var(--rule)',
        display: 'flex',
        flexDirection: 'column',
        padding: '24px 16px',
        backgroundColor: 'var(--oat)'
      }}>
        <div style={{ marginBottom: '40px', padding: '0 8px' }}>
          <h2 className="display-text" style={{ fontSize: '1.5rem', color: 'var(--ink)' }}>Amigo</h2>
        </div>
        
        <nav style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <button 
            onClick={() => pairedUser && setActiveView('dashboard')}
            className={`nav-item ${effectiveView === 'dashboard' ? 'nav-item--active' : ''}`}
            disabled={!pairedUser}
            style={{ opacity: pairedUser ? 1 : 0.5, cursor: pairedUser ? 'pointer' : 'not-allowed' }}
          >
            <LayoutDashboard size={20} />
            <span style={{ fontWeight: 500 }}>Dashboard</span>
          </button>
          
          <button 
            onClick={() => setActiveView('connect')}
            className={`nav-item ${effectiveView === 'connect' ? 'nav-item--active' : ''}`}
          >
            <Link2 size={20} />
            <span style={{ fontWeight: 500 }}>Connect Telegram</span>
          </button>
        </nav>

        <div style={{ marginTop: 'auto', borderTop: '1px solid var(--rule)', paddingTop: '24px' }}>
          <div style={{ padding: '0 12px', marginBottom: '16px', color: 'var(--ink-2)', fontSize: '0.85rem', wordBreak: 'break-all' }}>
            {session?.user?.email}
          </div>
          <button 
            onClick={handleSignOut}
            className="nav-item"
          >
            <LogOut size={20} />
            <span style={{ fontWeight: 500 }}>Sign out</span>
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <main style={{ flex: 1, overflowY: 'auto', backgroundColor: 'var(--oat)' }}>
        <div style={{ maxWidth: '800px', margin: '0 auto', padding: '40px 24px' }}>
          {!pairedUser && (
            <div style={{ background: 'var(--sand)', border: '1px solid var(--rule)', padding: '16px', borderRadius: '8px', marginBottom: '24px', color: 'var(--signal-deep)' }}>
              <strong>Connect Telegram to continue.</strong> Pair your account to chat with Amigo, schedule reminders, and view your dashboard.
            </div>
          )}
          {effectiveView === 'dashboard' ? (
            <DashboardView pairedUser={pairedUser} />
          ) : (
            <ConnectView pairedUser={pairedUser} onPairSuccess={checkPairing} />
          )}
        </div>
      </main>
    </div>
  )
}
