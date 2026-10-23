import { useEffect, useState } from 'react'
import { Check, CheckSquare } from 'lucide-react'
import { apiRequest } from '../supabase'
import CoachTemplates from './CoachTemplates'

const command = (mode) => (mode.id === 'daily' ? '/daily' : `/mode ${mode.id}`)

export default function ModeChips() {
  const [modes, setModes] = useState(null)
  const [access, setAccess] = useState(null)
  const [error, setError] = useState(false)
  const [busyId, setBusyId] = useState(null)
  // What the last click did: { id, opened, message }.
  const [result, setResult] = useState(null)
  const [current, setCurrent] = useState(null)

  useEffect(() => {
    let cancelled = false
    const load = () => apiRequest('/api/modes').then((data) => {
      if (!cancelled) {
        setModes(data.modes)
        setAccess(data.access ?? null)
        setCurrent(data.current_mode ?? null)
        setError(false)
      }
    }).catch(() => {
      if (!cancelled) setError(true)
    })
    load()
    // /mode or /daily typed in Telegram changes the current Mode; catch up on return to the tab.
    const onVisible = () => { if (document.visibilityState === 'visible') load() }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      cancelled = true
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [])

  // Same as typing the command in Telegram: the server switches the chat and sends the intro.
  const openMode = async (mode, templateId) => {
    if (mode.id === current && !templateId) {
      setResult({ id: mode.id, opened: true, already: true })
      return true
    }
    setBusyId(mode.id)
    try {
      const data = await apiRequest(`/api/modes/${mode.id}/open`, {
        method: 'POST',
        body: JSON.stringify(templateId ? { template_id: templateId } : {}),
      })
      const opened = data.status === 'opened'
      if (opened) setCurrent(mode.id)
      setResult({ id: mode.id, opened, message: data.message })
      return opened
    } catch (err) {
      setResult({ id: mode.id, opened: false, message: err.message || 'Could not switch. Try again.' })
      return false
    } finally {
      setBusyId(null)
    }
  }

  const shown = modes?.find((mode) => mode.id === result?.id)
  const coach = modes?.find((mode) => mode.id === 'coach' && mode.available)

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
          const isCurrent = mode.id === current
          const content = <>
            {isCurrent
              ? <Check size={14} strokeWidth={2.2} />
              : mode.id === 'daily' && <CheckSquare size={14} strokeWidth={1.8} />}
            <span>
              {busyId === mode.id ? `Switching to ${mode.name}…` : mode.name}
              {isCurrent && ' · current'}
              {mode.available && mode.consent_required && ' · agree in Telegram'}
              {!mode.available && ` · ${mode.status === 'live' ? 'Full access' : mode.status}`}
            </span>
          </>
          const className = `mode-chip${isCurrent ? ' mode-chip--current' : ''}${mode.available ? '' : ' mode-chip--locked'}`
          return mode.available ? (
            <button
              key={mode.id}
              type="button"
              className={className}
              title={title}
              disabled={busyId !== null}
              aria-pressed={isCurrent}
              aria-controls="mode-howto"
              onClick={() => openMode(mode)}
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
      {shown && (
        <div id="mode-howto" className="mode-howto" role="status" aria-label={`${shown.name} status`}>
          <p className="mode-howto-title">
            {result.opened ? `You're in ${shown.name}` : `${shown.name} didn't open`}
          </p>
          {!result.opened && <p>{result.message}</p>}
          {result.already && <p>Your Telegram chat is already in {shown.name}.</p>}
          {result.opened && !result.already && (
            <p>
              Amigo sent you a message there with a few things to try.
              {shown.deep_link && <> <a href={shown.deep_link} target="_blank" rel="noreferrer">Open chat</a></>}
            </p>
          )}
          <p className="mode-howto-note">
            Prefer typing? Send <code>{command(shown)}</code> in the chat
            {shown.id !== 'daily' && <>, and <code>/daily</code> to switch back</>}.
          </p>
        </div>
      )}
      {coach && <CoachTemplates onPick={(templateId) => openMode(coach, templateId)} busy={busyId !== null} />}
    </div>
  )
}
