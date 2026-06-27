import { useState } from 'react'
import { LayoutDashboard, Link2, LogOut } from 'lucide-react'
import { supabase } from '../supabase'
import DashboardView from './DashboardView'
import ConnectView from './ConnectView'

export default function AppShell({ session }) {
  const [activeView, setActiveView] = useState('dashboard')
  const [activeMode, setActiveMode] = useState('daily')

  const handleSignOut = async () => {
    await supabase.auth.signOut()
  }

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
            onClick={() => setActiveView('dashboard')}
            className={`nav-item ${activeView === 'dashboard' ? 'nav-item--active' : ''}`}
          >
            <LayoutDashboard size={20} />
            <span style={{ fontWeight: 500 }}>Dashboard</span>
          </button>
          
          <button 
            onClick={() => setActiveView('connect')}
            className={`nav-item ${activeView === 'connect' ? 'nav-item--active' : ''}`}
          >
            <Link2 size={20} />
            <span style={{ fontWeight: 500 }}>Connect Apps</span>
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
          {activeView === 'dashboard' ? <DashboardView activeMode={activeMode} setActiveMode={setActiveMode} /> : <ConnectView />}
        </div>
      </main>
    </div>
  )
}
