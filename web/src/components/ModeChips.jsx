import { useEffect, useState } from 'react'
import { CheckSquare } from 'lucide-react'
import { apiRequest } from '../supabase'

export default function ModeChips() {
  const [modes, setModes] = useState(null)
  const [access, setAccess] = useState(null)
  const [error, setError] = useState(false)

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
            <span>{mode.name}{!mode.available && ` · ${mode.status === 'live' ? 'Access required' : mode.status}`}</span>
          </>
          const className = `mode-chip${mode.available ? ' mode-chip--active' : ''}`
          return mode.available && mode.deep_link ? (
            <a key={mode.id} className={className} title={title} href={mode.deep_link}>
              {content}
            </a>
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
    </div>
  )
}
