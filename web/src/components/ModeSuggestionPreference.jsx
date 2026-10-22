import { useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../supabase'
import './CoachingRecords.css'
import './ModeSuggestionPreference.css'

export default function ModeSuggestionPreference({ request = apiRequest }) {
  const [enabled, setEnabled] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    setBusy(true)
    setError('')
    try {
      const data = await request('/api/mode-suggestions/preference')
      if (typeof data.enabled !== 'boolean') throw new Error('Invalid preference')
      setEnabled(data.enabled)
    } catch {
      setError('Mode suggestion settings could not be loaded. Refresh settings to try again.')
    } finally { setBusy(false) }
  }, [request])

  useEffect(() => { load() }, [load])

  async function change(value) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const data = await request('/api/mode-suggestions/preference', {
        method: 'POST', body: JSON.stringify({ enabled: value }),
      })
      if (typeof data.enabled !== 'boolean') throw new Error('Invalid preference')
      setEnabled(data.enabled)
      setNotice(data.enabled ? 'Mode suggestions allowed when available.' : 'Mode suggestions are off.')
    } catch {
      setError('The change could not be confirmed. Refresh settings before making another change.')
    } finally { setBusy(false) }
  }

  return <section className="mode-suggestion-preference" aria-labelledby="mode-suggestion-setting">
    <label id="mode-suggestion-setting"><input type="checkbox" checked={enabled === true}
      disabled={busy || enabled === null || Boolean(error)} onChange={event => change(event.target.checked)} />
      <span>Allow Mode suggestions</span></label>
    <p>Optional and off by default. Each offer needs your confirmation; availability still depends on release approval.</p>
    {busy && <p role="status">Updating Mode suggestion settings…</p>}
    {notice && <p role="status">{notice}</p>}
    {error && <div className="coaching-error" role="alert"><p>{error}</p><button className="coaching-button" type="button" disabled={busy} onClick={load}>Refresh settings</button></div>}
  </section>
}
