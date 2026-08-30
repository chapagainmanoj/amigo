import { useCallback, useEffect, useState } from 'react'
import { LayoutDashboard, Link2, LogOut } from 'lucide-react'
import { supabase, apiRequest } from '../supabase'
import DashboardView from './DashboardView'
import ConnectView from './ConnectView'

export default function AppShell({ session }) {
  const [activeView, setActiveView] = useState('dashboard')
  const [pairedUser, setPairedUser] = useState(null)
  const [checkingPairing, setCheckingPairing] = useState(true)

  const checkPairing = useCallback(async () => {
    try {
      const user = await apiRequest('/api/me')
      setPairedUser(user)
    } catch {
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
    return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', color: 'var(--mist)' }}>Checking pairing status...</div>
  }

  const effectiveView = pairedUser ? activeView : 'connect'

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      {/* Desktop Sidebar */}
      <aside style={{
        width: '240px',
        borderRight: '1px solid rgba(255,255,255,0.04)',
        display: 'flex',
        flexDirection: 'column',
        padding: '24px 16px',
        backgroundColor: 'var(--ink)'
      }}>
        <div style={{ marginBottom: '40px', padding: '0 8px' }}>
          <h2 className="display-text" style={{ fontSize: '1.5rem', color: 'var(--paper)' }}>Amigo</h2>
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

        <div style={{ marginTop: 'auto', borderTop: '1px solid rgba(255,255,255,0.04)', paddingTop: '24px' }}>
          <div style={{ padding: '0 12px', marginBottom: '16px', color: 'var(--mist)', fontSize: '0.85rem', wordBreak: 'break-all' }}>
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
      <main style={{ flex: 1, overflowY: 'auto', backgroundColor: 'var(--ink)' }}>
        <div style={{ maxWidth: '800px', margin: '0 auto', padding: '40px 24px' }}>
          {!pairedUser && (
            <div style={{ background: 'rgba(255, 138, 91, 0.1)', border: '1px solid rgba(255, 138, 91, 0.2)', padding: '16px', borderRadius: '8px', marginBottom: '24px', color: '#FF8A5B' }}>
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
