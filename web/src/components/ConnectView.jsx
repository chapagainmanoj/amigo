import { useEffect, useState } from 'react'
import { CheckCircle, MessageCircle } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { apiRequest } from '../supabase'

export default function ConnectView({ pairedUser, onPairSuccess }) {
  const [pairingData, setPairingData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const fetchPairingToken = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await apiRequest('/api/pairing-token', { method: 'POST' })
      setPairingData(data)
    } catch (err) {
      setError(err.message || 'Failed to generate pairing link')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!pairedUser) {
      fetchPairingToken()
    }
  }, [pairedUser])

  useEffect(() => {
    if (!pairingData || pairedUser) return

    const interval = setInterval(async () => {
      try {
        await onPairSuccess()
      } catch {
        // Pairing is not complete yet; keep polling until the view unmounts.
      }
    }, 3000)

    return () => clearInterval(interval)
  }, [pairingData, pairedUser, onPairSuccess])

  const botLink = pairingData?.bot_link || 'https://t.me/amigo_agent_bot'

  return (
    <div className="animate-slide-in">
      <div style={{ marginBottom: '32px' }}>
        <h1 className="display-text" style={{ fontSize: '2.5rem', marginBottom: '8px' }}>
          Connect Telegram
        </h1>
        <p style={{ color: 'var(--mist)' }}>
          Pair Telegram to chat with Amigo and receive reminders.
        </p>
      </div>

      <div className="flat-card" style={{ padding: '40px', minHeight: '400px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
          <MessageCircle size={24} color="#229ED9" />
          <h2 style={{ fontSize: '1.5rem' }}>Telegram</h2>
        </div>

        {pairedUser ? (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '40px 0',
              textAlign: 'center',
            }}
          >
            <div
              style={{
                background: 'rgba(29, 158, 117, 0.1)',
                padding: '24px',
                borderRadius: '50%',
                marginBottom: '24px',
                color: '#1D9E75',
              }}
            >
              <CheckCircle size={48} />
            </div>
            <h3 style={{ fontSize: '1.25rem', marginBottom: '8px', color: 'var(--paper)' }}>
              Telegram connected
            </h3>
            <p style={{ color: 'var(--mist)' }}>
              Ready for tasks and reminders in Telegram.
            </p>
          </div>
        ) : (
          <>
            <p style={{ color: 'var(--mist)', marginBottom: '32px', maxWidth: '440px' }}>
              Scan the QR code with your phone, or open Telegram below. The link pairs this
              dashboard account with the Amigo bot.
            </p>

            {loading && (
              <div style={{ color: 'var(--mist)', marginBottom: '32px' }}>
                Generating pairing link...
              </div>
            )}
            {error && (
              <div style={{ marginBottom: '24px' }}>
                <div style={{ color: 'var(--ember)', marginBottom: '8px' }}>{error}</div>
                <button
                  onClick={fetchPairingToken}
                  className="btn-secondary"
                  style={{ fontSize: '0.85rem' }}
                >
                  Retry
                </button>
              </div>
            )}

            {pairingData && (
              <>
                <div
                  style={{
                    display: 'inline-block',
                    background: 'white',
                    padding: '16px',
                    borderRadius: '16px',
                    marginBottom: '32px',
                  }}
                >
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
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}

