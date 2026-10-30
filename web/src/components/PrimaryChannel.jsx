import { useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../supabase'
import './CoachingRecords.css'
import './PrimaryChannel.css'

const LABELS = { telegram: 'Telegram', cli: 'Local CLI' }
const label = channel => LABELS[channel] ?? channel.charAt(0).toUpperCase() + channel.slice(1)

// Shown only once a participant has linked more than one messaging app.
export default function PrimaryChannel({ request = apiRequest }) {
  const [state, setState] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    setBusy(true)
    setError('')
    try {
      const data = await request('/api/channels')
      if (typeof data.primary_channel !== 'string' || !Array.isArray(data.linked)) {
        throw new Error('Invalid channels')
      }
      setState(data)
    } catch {
      setError('Messaging app settings could not be loaded. Refresh settings to try again.')
    } finally { setBusy(false) }
  }, [request])

  useEffect(() => { load() }, [load])

  async function choose(channel) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const data = await request('/api/channels/primary', {
        method: 'POST', body: JSON.stringify({ channel }),
      })
      if (data.primary_channel !== channel) throw new Error('Not confirmed')
      setState(data)
      setNotice(`Reminders and check-ins now go to ${label(channel)}.`)
    } catch {
      setError('The change could not be confirmed. Refresh settings before making another change.')
    } finally { setBusy(false) }
  }

  if (!error && (!state || state.linked.length < 2)) return null

  return <section className="primary-channel" aria-labelledby="primary-channel-setting">
    <h2 id="primary-channel-setting">Where Amigo reaches you</h2>
    <p>Reminders and check-ins go to one app. You can still message Amigo from any linked app.</p>
    {state && <div role="radiogroup" aria-labelledby="primary-channel-setting">
      {state.linked.map(channel => <label key={channel}>
        <input type="radio" name="primary-channel" value={channel}
          checked={state.primary_channel === channel}
          disabled={busy || Boolean(error)} onChange={() => choose(channel)} />
        <span>{label(channel)}</span>
      </label>)}
    </div>}
    {busy && <p role="status">Updating messaging app settings…</p>}
    {notice && <p role="status">{notice}</p>}
    {error && <div className="coaching-error" role="alert"><p>{error}</p><button className="coaching-button" type="button" disabled={busy} onClick={load}>Refresh settings</button></div>}
  </section>
}
