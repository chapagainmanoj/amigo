import { useState } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import { MessageCircle, Smartphone } from 'lucide-react'

export default function ConnectView() {
  const [activeTab, setActiveTab] = useState('telegram')
  const mockToken = 'tg_onboard_8f72a9b1'
  const botLink = `https://t.me/amigo_agent_bot?start=${mockToken}`

  return (
    <div className="animate-slide-in">
      <div style={{ marginBottom: '32px' }}>
        <h1 className="display-text" style={{ fontSize: '2.5rem', marginBottom: '8px' }}>Connect Apps</h1>
        <p style={{ color: 'var(--mist)' }}>Link Amigo to your favorite messaging platforms.</p>
      </div>

      <div style={{ display: 'flex', gap: '24px', alignItems: 'flex-start' }}>
        
        {/* Tabs sidebar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', width: '200px' }}>
          <button 
            onClick={() => setActiveTab('telegram')}
            style={{ 
              padding: '12px 16px', borderRadius: '8px', display: 'flex', alignItems: 'center', gap: '12px',
              background: activeTab === 'telegram' ? 'var(--dusk)' : 'transparent',
              color: activeTab === 'telegram' ? 'var(--paper)' : 'var(--mist)',
              border: activeTab === 'telegram' ? '1px solid rgba(255,255,255,0.05)' : '1px solid transparent'
            }}
          >
            <MessageCircle size={20} color={activeTab === 'telegram' ? '#229ED9' : 'currentColor'} />
            <span style={{ fontWeight: 500 }}>Telegram</span>
          </button>

          <button 
            onClick={() => setActiveTab('whatsapp')}
            style={{ 
              padding: '12px 16px', borderRadius: '8px', display: 'flex', alignItems: 'center', gap: '12px',
              background: activeTab === 'whatsapp' ? 'var(--dusk)' : 'transparent',
              color: activeTab === 'whatsapp' ? 'var(--paper)' : 'var(--mist)',
              border: activeTab === 'whatsapp' ? '1px solid rgba(255,255,255,0.05)' : '1px solid transparent'
            }}
          >
            <Smartphone size={20} color={activeTab === 'whatsapp' ? '#25D366' : 'currentColor'} />
            <span style={{ fontWeight: 500 }}>WhatsApp</span>
          </button>
        </div>

        {/* Tab Content */}
        <div className="flat-card" style={{ flex: 1, padding: '40px', minHeight: '400px' }}>
          {activeTab === 'telegram' && (
            <div className="animate-slide-in">
              <h2 style={{ fontSize: '1.5rem', marginBottom: '16px' }}>Connect via Telegram</h2>
              <p style={{ color: 'var(--mist)', marginBottom: '32px', maxWidth: '400px' }}>
                Scan this QR code with your phone's camera, or click the button below to open Telegram and link your account.
              </p>
              
              <div style={{ display: 'inline-block', background: 'white', padding: '16px', borderRadius: '16px', marginBottom: '32px' }}>
                <QRCodeSVG value={botLink} size={200} level="M" />
              </div>
              
              <div>
                <a 
                  href={botLink} 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="btn-primary"
                  style={{ display: 'inline-block', textDecoration: 'none' }}
                >
                  Open in Telegram
                </a>
              </div>
            </div>
          )}

          {activeTab === 'whatsapp' && (
            <div className="animate-slide-in" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', textAlign: 'center', color: 'var(--mist)' }}>
              <div style={{ background: 'rgba(255,255,255,0.02)', padding: '24px', borderRadius: '50%', marginBottom: '24px' }}>
                <Smartphone size={48} opacity={0.5} />
              </div>
              <h2 style={{ fontSize: '1.5rem', color: 'var(--paper)', marginBottom: '12px' }}>Coming Soon</h2>
              <p style={{ maxWidth: '300px' }}>
                WhatsApp integration is currently on the roadmap. For now, please use Telegram to interact with Amigo.
              </p>
            </div>
          )}
        </div>

      </div>
    </div>
  )
}
