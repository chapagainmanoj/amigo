import { useEffect, useState } from 'react'
import { CheckSquare } from 'lucide-react'
import { apiRequest } from '../supabase'

export default function ModeChips() {
  const [modes, setModes] = useState(null)
  const [access, setAccess] = useState(null)
  const [error, setError] = useState(false)
  const [openId, setOpenId] = useState(null)
  const [copied, setCopied] = useState(null)

  useEffect(() => {
    let cancelled = false
    apiRequest('/api/modes').then((data) => {
      if (!cancelled) {
        setModes(data.modes)
        setAccess(data.access ?? null)
      }
    }).catch(() => {
      if (!cancelled) setError(true)
    })
    return () => { cancelled = true }
  }, [])

  const command = (mode) => (mode.id === 'daily' ? '/daily' : `/mode ${mode.id}`)
  const copyCommand = async (mode) => {
    try {
      await navigator.clipboard.writeText(command(mode))
      setCopied(mode.id)
    } catch {
      // Clipboard can be blocked; the command is visible to type instead.
    }
  }
  const open = modes?.find((mode) => mode.id === openId)

  return (
    <div className="mode-chips-bar" aria-label="Amigo modes">
      <span className="mode-chips-label">Your modes</span>
      <div className="mode-chips-row">
        {error && <span role="status">Modes unavailable. Refresh to retry.</span>}
        {!error && modes === null && <span role="status">Loading modes…</span>}
        {modes?.map((mode) => {
          const title = [
            mode.purpose,
            mode.grant_expires_at ? `Access until ${new Date(mode.grant_expires_at).toLocaleDateString()}` : null,
          ].filter(Boolean).join(' · ')
          const content = <>
            {mode.id === 'daily' && <CheckSquare size={14} strokeWidth={1.8} />}
            <span>
              {mode.name}
              {mode.available && mode.consent_required && ' · agree in Telegram'}
              {!mode.available && ` · ${mode.status === 'live' ? 'Full access' : mode.status}`}
            </span>
          </>
          const className = `mode-chip${mode.available ? ' mode-chip--active' : ''}`
          return mode.available ? (
            <button
              key={mode.id}
              type="button"
              className={className}
              title={title}
              aria-expanded={openId === mode.id}
              aria-controls="mode-howto"
              onClick={() => { setOpenId(openId === mode.id ? null : mode.id); setCopied(null) }}
            >
              {content}
            </button>
          ) : (
            <span key={mode.id} className={className} title={title}>{content}</span>
          )
        })}
      </div>
      {access?.tier === 'trial' && (
        <span className="mode-chips-trial" role="status">
          {access.messages_used >= access.message_limit
            ? <>Trial finished · <a href="https://amigo.manojc.link/contact/">Contact us for full access</a></>
            : `Trial: ${access.messages_used} of ${access.message_limit} messages used`}
        </span>
      )}
      {open && (
        <div id="mode-howto" className="mode-howto" role="region" aria-label={`Start ${open.name}`}>
          <p className="mode-howto-title">Start {open.name} in Telegram</p>
          <ol>
            <li>
              Open Amigo in Telegram
              {open.deep_link && <> — <a href={open.deep_link} target="_blank" rel="noreferrer">open chat</a></>}
            </li>
            <li>
              Send <code>{command(open)}</code>{' '}
              <button type="button" className="mode-howto-copy" onClick={() => copyCommand(open)}>
                {copied === open.id ? 'Copied' : 'Copy'}
              </button>
            </li>
            {open.consent_required && <li>Read the note about your data and tap <strong>I agree</strong></li>}
          </ol>
          {open.id !== 'daily' && <p className="mode-howto-note">Send <code>/daily</code> any time to switch back.</p>}
        </div>
      )}
    </div>
  )
}
