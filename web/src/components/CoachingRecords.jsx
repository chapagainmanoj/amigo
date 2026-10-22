import { useCallback, useEffect, useState } from 'react'
import { Download, RefreshCw, Trash2 } from 'lucide-react'
import { apiRequest } from '../supabase'
import './CoachingRecords.css'

const DELETE_SCOPE = 'Program records and entries only; conversation Messages/provider copies remain.'
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function dateLabel(value) {
  if (!value) return 'Not started'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function entryLabel(entry) {
  const labels = {
    draft: 'Draft created', activate: 'Approved', pause: 'Paused', resume: 'Resumed',
    stop: 'Stopped', extend: 'Term extended', revise: 'Draft revised', complete: 'Completed',
  }
  if (entry.kind === 'progress') return 'Reported progress'
  if (entry.kind === 'weekly_choice') return 'Weekly choice'
  return labels[entry.action] || entry.action || entry.kind
}

export default function CoachingRecords({ request = apiRequest }) {
  const [records, setRecords] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showDelete, setShowDelete] = useState(false)
  const [confirmed, setConfirmed] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [notice, setNotice] = useState('')
  const [deletionUnconfirmed, setDeletionUnconfirmed] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await request('/api/coaching')
      if (!Array.isArray(data.programs) || !Array.isArray(data.entries)) {
        throw new Error('Unexpected records response')
      }
      setRecords(data)
      setDeletionUnconfirmed(false)
    } catch {
      setError('Coaching records could not be loaded. Check your connection and try again.')
    } finally {
      setLoading(false)
    }
  }, [request])

  useEffect(() => { load() }, [load])

  function exportRecords() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(records, null, 2)], {
      type: 'application/json',
    }))
    const link = document.createElement('a')
    link.href = url
    link.download = 'coaching-records.json'
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
    setNotice('Coaching records exported as JSON.')
  }

  async function deleteRecords(event) {
    event.preventDefault()
    if (!confirmed || deleting) return
    setDeleting(true)
    setError('')
    setNotice('')
    try {
      await request('/api/coaching/delete', {
        method: 'POST', body: JSON.stringify({ confirmation: 'delete my coaching records' }),
      })
      setRecords({ programs: [], entries: [] })
      setShowDelete(false)
      setConfirmed(false)
      setNotice(`Coaching records deleted. ${DELETE_SCOPE}`)
    } catch {
      setError('Deletion could not be confirmed. Refresh records before trying again.')
      setDeletionUnconfirmed(true)
      setShowDelete(false)
      setConfirmed(false)
    } finally {
      setDeleting(false)
    }
  }

  const hasRecords = Boolean(records?.programs.length || records?.entries.length)

  return (
    <section className="coaching-records" aria-labelledby="coaching-records-heading">
      <header className="coaching-records-header">
        <div>
          <h1 id="coaching-records-heading">Coaching records</h1>
          <p>Your program details and recorded history. Viewing records does not start coaching.</p>
        </div>
        <button type="button" className="coaching-button" onClick={exportRecords}
          disabled={!hasRecords || loading || deleting || Boolean(error)}>
          <Download size={17} aria-hidden="true" /> Export JSON
        </button>
      </header>

      {notice && <p className="coaching-notice" role="status">{notice}</p>}
      {error && <div className="coaching-error" role="alert">
        <p>{error}</p>
        {!showDelete && <button type="button" className="coaching-button" onClick={load}
          disabled={loading}><RefreshCw size={16} aria-hidden="true" /> {deletionUnconfirmed ? 'Refresh records' : 'Retry loading'}</button>}
      </div>}
      {loading && <p className="coaching-loading" role="status">Loading Coaching records…</p>}

      {!loading && records && <>
        {!hasRecords && <div className="coaching-empty">
          <h2>No Coaching records</h2>
          <p>There are no saved Coaching programs or entries on your account.</p>
          <p>When you create a program, its details and recorded history will appear here.</p>
        </div>}

        {records.programs.map(program => {
          const entries = records.entries.filter(entry => entry.program_id === program.program_id)
          return <article className="coaching-program" key={program.program_id}>
            <header className="coaching-program-heading">
              <h2>{program.goal}</h2>
              <span className="coaching-state">{program.state}</span>
            </header>
            <dl className="coaching-details">
              <div className="coaching-measure"><dt>Your success measure</dt><dd>{program.success_measure}</dd></div>
              <div><dt>Check-in schedule</dt><dd>
                {program.check_in_days.map(day => DAYS[day - 1] || day).join(', ')}
                {' · '}{program.check_in_time} · {program.timezone}
              </dd></div>
              <div><dt>Program term</dt><dd>{program.starts_at
                ? <>{dateLabel(program.starts_at)} – {dateLabel(program.ends_at)}</>
                : 'Not started'}</dd></div>
              <div><dt>Version</dt><dd>{program.version}</dd></div>
            </dl>
            <h3>Recorded history</h3>
            {entries.length === 0 ? <p className="coaching-muted">No entries recorded.</p> :
              <ol className="coaching-history">{entries.map(entry => <li key={entry.entry_id}>
                <div className="coaching-entry-heading">
                  <strong>{entryLabel(entry)}</strong>
                  <time dateTime={entry.created_at}>{dateLabel(entry.created_at)}</time>
                </div>
                {entry.participant_text && <p>{entry.participant_text}</p>}
                {entry.choice && <p>Choice: {entry.choice}</p>}
                {entry.extension_days != null && <p>Extension: {entry.extension_days} days</p>}
              </li>)}</ol>}
          </article>
        })}

        {hasRecords && <footer className="coaching-data-controls">
          <h2>Manage Coaching records</h2>
          <p>{DELETE_SCOPE}</p>
          {!showDelete ? <button type="button" className="coaching-button coaching-delete"
            disabled={Boolean(error)} onClick={() => { setShowDelete(true); setNotice('') }}>
            <Trash2 size={17} aria-hidden="true" /> Delete Coaching records
          </button> : <form className="coaching-confirm" onSubmit={deleteRecords}>
            <label><input type="checkbox" checked={confirmed} disabled={deleting}
              onChange={event => setConfirmed(event.target.checked)} required />
              <span>I understand this permanently deletes my Coaching program records and entries.</span>
            </label>
            <div className="coaching-confirm-actions">
              <button type="submit" className="coaching-button coaching-delete"
                disabled={!confirmed || deleting}>{deleting ? 'Deleting records…' : 'Delete program records and entries'}</button>
              <button type="button" className="coaching-button" disabled={deleting}
                onClick={() => { setShowDelete(false); setConfirmed(false); setError('') }}>Cancel</button>
            </div>
          </form>}
        </footer>}
      </>}
    </section>
  )
}
