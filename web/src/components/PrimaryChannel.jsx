import { useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../supabase'
import './CoachingRecords.css'
import './PrimaryChannel.css'

const LABELS = { telegram: 'Telegram', discord: 'Discord', cli: 'Local CLI' }
const label = channel => LABELS[channel] ?? channel.charAt(0).toUpperCase() + channel.slice(1)

// Shown once a participant has linked more than one messaging app, or may connect another.
export default function PrimaryChannel({ request = apiRequest }) {
  const [state, setState] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [pairing, setPairing] = useState(null)

  const load = useCallback(async () => {
    setBusy(true)
    setError('')
    try {
      const data = await request('/api/channels')
      if (typeof data.primary_channel !== 'string' || !Array.isArray(data.linked)) {
        throw new Error('Invalid channels')
      }
      setState({ ...data, available: Array.isArray(data.available) ? data.available : [] })
      setPairing(current => (current && data.linked.includes(current.channel) ? null : current))
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
      setState({ ...data, available: Array.isArray(data.available) ? data.available : [] })
      setNotice(`Reminders and check-ins now go to ${label(channel)}.`)
    } catch {
      setError('The change could not be confirmed. Refresh settings before making another change.')
    } finally { setBusy(false) }
  }

  async function connect(channel) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const data = await request(`/api/channels/${encodeURIComponent(channel)}/pairing-token`, {
        method: 'POST',
      })
      if (typeof data.command !== 'string') throw new Error('Invalid code')
      setPairing({ channel, ...data })
    } catch {
      setError(`A ${label(channel)} code could not be created. Refresh settings to try again.`)
    } finally { setBusy(false) }
  }

  // A failed first load must not surface the control to single-app participants.
  if (!state || (state.linked.length < 2 && state.available.length === 0)) return null

  return <section className="primary-channel" aria-labelledby="primary-channel-setting">
    <h2 id="primary-channel-setting">Where Amigo reaches you</h2>
    <p>Reminders and check-ins go to one app. You can still message Amigo from any linked app.</p>
    {state.linked.length >= 2 && <div role="radiogroup" aria-labelledby="primary-channel-setting">
      {state.linked.map(channel => <label key={channel}>
        <input type="radio" name="primary-channel" value={channel}
          checked={state.primary_channel === channel}
          disabled={busy || Boolean(error)} onChange={() => choose(channel)} />
        <span>{label(channel)}</span>
      </label>)}
    </div>}
    {state.available.length > 0 && <div className="primary-channel-connect">
      <h3>Connect another app</h3>
      {state.available.map(channel => <button key={channel} className="coaching-button" type="button"
        disabled={busy} onClick={() => connect(channel)}>Connect {label(channel)}</button>)}
      {pairing && <ol>
        {pairing.app_link && <li><a href={pairing.app_link} target="_blank" rel="noreferrer">Add Amigo in {label(pairing.channel)}</a>.</li>}
        <li>Send Amigo this message in {label(pairing.channel)}: <code>{pairing.command}</code></li>
        <li>Then <button className="coaching-button" type="button" disabled={busy} onClick={load}>refresh settings</button>. The code works once and expires in a few minutes.</li>
      </ol>}
    </div>}
    <p role="status">{busy ? 'Updating messaging app settings…' : notice}</p>
    {error && <div className="coaching-error" role="alert"><p>{error}</p><button className="coaching-button" type="button" disabled={busy} onClick={load}>Refresh settings</button></div>}
  </section>
}
