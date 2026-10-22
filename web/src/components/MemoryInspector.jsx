import { useCallback, useEffect, useRef, useState } from 'react'
import { Download, RefreshCw } from 'lucide-react'
import { apiRequest } from '../supabase'
import './CoachingRecords.css'
import './MemoryInspector.css'

const STATES = ['active', 'needs_confirmation', 'inactive', 'superseded', 'expired', 'forgotten']
const CATEGORIES = ['preference', 'routine', 'constraint', 'goal', 'project', 'context']
const MODES = ['daily', 'coach', 'reflect', 'recommender']
const PURPOSES = {
  personalize: 'Personalize wording using a confirmed fact',
  suggestion: 'Support a relevant suggestion',
  preference: 'Use a confirmed preference for the current request',
}
const FORGET_SCOPE = 'Saved Memory and its use history only. Conversation Messages, Session summaries and provider copies are separate.'
const NEW_DRAFT = { operation: 'save', category: 'preference', text: '', scopes: ['daily'], valid_until: '' }

function dateLabel(value) {
  if (!value) return 'None'
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function label(value) { return String(value || '').replaceAll('_', ' ') }

export function memoryCsv(records) {
  const rows = [
    { record_type: 'settings', ...records.settings },
    ...records.memories.map(row => ({ record_type: 'memory', ...row })),
    ...records.uses.map(row => ({ record_type: 'use', ...row })),
  ]
  const columns = [...new Set(rows.flatMap(row => Object.keys(row)))]
  const escape = value => {
    let text = value == null ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value)
    if (/^\s*[=+@-]/.test(text) || /^[\t\r\n]/.test(text)) text = `'${text}`
    return `"${text.replaceAll('"', '""')}"`
  }
  return [columns.map(escape).join(','), ...rows.map(row => columns.map(key => escape(row[key])).join(','))].join('\r\n')
}

function download(content, format) {
  const url = URL.createObjectURL(new Blob([content], { type: format === 'json' ? 'application/json' : 'text/csv;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `memory-records.${format}`
  document.body.append(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export default function MemoryInspector({ request = apiRequest }) {
  const [records, setRecords] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [stale, setStale] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [filter, setFilter] = useState('all')
  const [draft, setDraft] = useState(null)
  const [preview, setPreview] = useState(null)
  const [enable, setEnable] = useState(false)
  const [confirmAll, setConfirmAll] = useState(false)
  const [forget, setForget] = useState(null)
  const [confirmForget, setConfirmForget] = useState(false)
  const reviewHeading = useRef(null)
  const editorHeading = useRef(null)
  const forgetHeading = useRef(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await request('/api/memory')
      if (!Array.isArray(data.memories) || !Array.isArray(data.uses) || !data.settings || !data.availability) throw new Error('Invalid records')
      setRecords(data)
      setStale(false)
      setDraft(null)
      setPreview(null)
      setForget(null)
      setEnable(false)
      setConfirmAll(false)
      setConfirmForget(false)
    } catch {
      setError('Memory records could not be loaded. Refresh records to try again.')
      setStale(true)
    } finally { setLoading(false) }
  }, [request])

  useEffect(() => { load() }, [load])
  useEffect(() => { if (preview) reviewHeading.current?.focus() }, [preview])
  useEffect(() => { editorHeading.current?.focus() }, [draft?.operation, draft?.memory_id])
  useEffect(() => { forgetHeading.current?.focus() }, [forget?.memory_id])

  const locked = loading || busy || stale || !records
  const canSave = records?.availability.saving === true && !records.settings.learning_paused
  const latest = new Map()
  records?.memories.forEach(row => latest.set(row.memory_id, Math.max(row.version, latest.get(row.memory_id) || 0)))
  const hasMemory = records?.memories.some(row => row.state !== 'forgotten')
  const visible = records?.memories.filter(row => filter === 'all' || row.state === filter) || []

  async function post(path, body, { review = false, success = 'Memory records updated.' } = {}) {
    if (locked) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const result = await request(`/api/memory/${path}`, { method: 'POST', body: JSON.stringify(body) })
      if (review) {
        if (!result.token || !result.operation) throw new Error('Invalid preview')
        setPreview(result)
        setDraft(null)
        setEnable(false)
        setConfirmAll(false)
      } else {
        const next = await request('/api/memory')
        if (!Array.isArray(next.memories) || !Array.isArray(next.uses) || !next.settings || !next.availability) throw new Error('Invalid records')
        setRecords(next)
        setPreview(null)
        setDraft(null)
        setForget(null)
        setConfirmForget(false)
        setNotice(success)
      }
    } catch {
      setStale(true)
      setPreview(null)
      setDraft(null)
      setForget(null)
      setError('The action could not be confirmed or the records changed. Refresh records before another change or export.')
    } finally { setBusy(false) }
  }

  function beginEdit(row, operation) {
    setPreview(null)
    setForget(null)
    setDraft({ operation, memory_id: row.memory_id, expected_version: row.version,
      category: row.category, text: row.text, scopes: [...row.scopes], valid_until: row.valid_until || '' })
    setNotice('')
  }

  function requestPreview(event) {
    event.preventDefault()
    const body = { ...draft, valid_until: draft.valid_until || null }
    post('preview', body, { review: true })
  }

  function exportRecords(format) {
    if (locked) return
    const data = { settings: records.settings, memories: records.memories, uses: records.uses }
    download(format === 'json' ? JSON.stringify(data, null, 2) : memoryCsv(data), format)
    setNotice(`Complete Memory inventory, settings and use history exported as ${format.toUpperCase()}.`)
  }

  const editingMeaning = draft?.operation === 'save' || draft?.operation === 'correct'
  const sharing = draft?.operation === 'save' || draft?.operation === 'share'

  return <section className="coaching-records memory-inspector" aria-labelledby="memory-heading">
    <header className="coaching-records-header">
      <div><h1 id="memory-heading">Memory Inspector</h1>
        <p>See exactly what you saved, where it can be used, and when it was used.</p></div>
      <div className="memory-actions">
        <button className="coaching-button" type="button" disabled={locked} onClick={() => exportRecords('json')}><Download size={16} aria-hidden="true" /> Export JSON</button>
        <button className="coaching-button" type="button" disabled={locked} onClick={() => exportRecords('csv')}><Download size={16} aria-hidden="true" /> Export CSV</button>
      </div>
    </header>
    {notice && <p className="coaching-notice" role="status">{notice}</p>}
    {error && <div className="coaching-error" role="alert"><p>{error}</p>
      <button className="coaching-button" type="button" disabled={loading || busy} onClick={load}><RefreshCw size={16} aria-hidden="true" /> Refresh records</button></div>}
    {loading && <p role="status" className="coaching-loading">Loading Memory records…</p>}
    {busy && <p className="coaching-loading" role="status">Applying your Memory action…</p>}
    {records && <>
      <section className="memory-controls" aria-labelledby="memory-controls-heading">
        <h2 id="memory-controls-heading">Your controls</h2>
        <p>Memory is {records.settings.enabled ? 'enabled' : 'off'}. Learning and use can be paused separately. Pausing keeps saved records.</p>
        {!records.availability.saving && <p className="memory-availability">{records.availability.reason || 'Saving is unavailable while privacy and eligibility review is incomplete.'} Inspection, pause controls, export and forgetting remain available.</p>}
        <div className="memory-actions">
          <button className="coaching-button" type="button" disabled={locked || (records.settings.learning_paused && records.settings.use_paused)} onClick={() => post('settings', { expected_version: records.settings.version, learning: true, use: true })}>Pause all Memory</button>
          <button className="coaching-button" type="button" disabled={locked} onClick={() => post('settings', { expected_version: records.settings.version, learning: !records.settings.learning_paused })}>{records.settings.learning_paused ? 'Resume learning' : 'Pause learning'}</button>
          <button className="coaching-button" type="button" disabled={locked} onClick={() => post('settings', { expected_version: records.settings.version, use: !records.settings.use_paused })}>{records.settings.use_paused ? 'Resume use' : 'Pause use'}</button>
          <button className="coaching-button" type="button" disabled={locked || !canSave} onClick={() => { setDraft({ ...NEW_DRAFT, scopes: ['daily'] }); setPreview(null); setForget(null) }}>Save a Memory</button>
        </div>
        {records.settings.learning_paused && <p className="coaching-muted">Learning is paused. Resume learning before preparing a new save or correction.</p>}
      </section>

      {draft && <form className="memory-editor" onSubmit={requestPreview} aria-labelledby="memory-editor-heading">
        <h2 id="memory-editor-heading" tabIndex={-1} ref={editorHeading}>{draft.operation === 'save' ? 'Choose the exact Memory' : `${label(draft.operation)} Memory`}</h2>
        <p>Your changes are saved only after you review and confirm the exact preview.</p>
        <fieldset disabled={locked}>
          <label>Category<select value={draft.category} disabled={!editingMeaning} onChange={event => setDraft({ ...draft, category: event.target.value })}>{CATEGORIES.map(category => <option key={category} value={category}>{label(category)}</option>)}</select></label>
          <label>Exact content<textarea value={draft.text} required maxLength={2000} rows={4} readOnly={!editingMeaning} onChange={event => setDraft({ ...draft, text: event.target.value })} /></label>
          <fieldset className="memory-scope"><legend>Allowed Modes</legend>{MODES.map(mode => <label key={mode}><input type="checkbox" checked={draft.scopes.includes(mode)} disabled={!sharing || (draft.operation === 'save' && mode === 'daily')} onChange={event => setDraft({ ...draft, scopes: event.target.checked ? [...draft.scopes, mode] : draft.scopes.filter(value => value !== mode) })} />{label(mode)}</label>)}</fieldset>
          <p className="coaching-muted">New Memories start in Daily. Sharing requires this exact confirmation. Reflect does not retrieve Memory automatically.</p>
          <label>Valid through (optional)<input type="date" value={draft.valid_until} disabled={draft.operation === 'share'} onChange={event => setDraft({ ...draft, valid_until: event.target.value })} /></label>
          <div className="memory-actions"><button className="coaching-button" type="submit" disabled={!draft.text.trim() || draft.scopes.length === 0 || busy}>Review exact preview</button><button className="coaching-button" type="button" onClick={() => setDraft(null)}>Cancel</button></div>
        </fieldset>
      </form>}

      {preview && <section className="memory-preview" aria-labelledby="memory-review-heading">
        <h2 id="memory-review-heading" tabIndex={-1} ref={reviewHeading}>{preview.operation === 'forget_all' ? 'Review Forget all' : 'Review the exact Memory'}</h2>
        {preview.operation === 'forget_all' ? <><p>This forgets {preview.count} saved {preview.count === 1 ? 'Memory' : 'Memories'}, including their versions and use history.</p><p>{preview.scope || FORGET_SCOPE}</p></> : <>
          <p className="memory-exact">{preview.payload?.text}</p>
          <dl className="coaching-details"><div><dt>Category</dt><dd>{label(preview.payload?.category)}</dd></div><div><dt>Allowed Modes</dt><dd>{preview.payload?.scopes?.join(', ')}</dd></div><div><dt>Valid through</dt><dd>{preview.payload?.valid_until || 'Until reconfirmation: 180 days for preferences, 90 days for other categories'}</dd></div><div><dt>Source</dt><dd>{label(preview.payload?.creation_path)} · {preview.payload?.source_channel} · {preview.payload?.source_date}</dd></div></dl>
          <p>{preview.disclosure}</p>
        </>}
        <p className="coaching-muted">Preview expires {dateLabel(preview.expires_at)}.</p>
        {preview.requires_enable && <label className="memory-check"><input type="checkbox" checked={enable} disabled={locked} onChange={event => setEnable(event.target.checked)} /><span>I choose to enable optional Memory and save this exact first item. I have read the notice above.</span></label>}
        {preview.operation === 'forget_all' && <label className="memory-check"><input type="checkbox" checked={confirmAll} disabled={locked} onChange={event => setConfirmAll(event.target.checked)} /><span>I understand the scope and choose to forget all saved Memory and its use history.</span></label>}
        <div className="memory-actions"><button className={`coaching-button ${preview.operation === 'forget_all' ? 'coaching-delete' : ''}`} type="button" disabled={locked || (preview.requires_enable && !enable) || (preview.operation === 'forget_all' && !confirmAll)} onClick={() => post('confirm', { token: preview.token, enable_memory: preview.requires_enable ? enable : false, policy_version: preview.requires_enable ? preview.policy_version : null }, { success: preview.operation === 'forget_all' ? `Saved Memory forgotten. ${FORGET_SCOPE}` : 'Exact Memory confirmed.' })}>{busy ? 'Confirming…' : preview.operation === 'forget_all' ? 'Forget all saved Memory' : 'Confirm exact Memory'}</button><button className="coaching-button" type="button" disabled={busy} onClick={() => { setPreview(null); setEnable(false); setConfirmAll(false) }}>Cancel</button></div>
      </section>}

      {forget && <section className="memory-preview" aria-labelledby="memory-forget-heading">
        <h2 id="memory-forget-heading" tabIndex={-1} ref={forgetHeading}>Forget this Memory?</h2><p className="memory-exact">{forget.text}</p><p>Version {forget.version}. All versions of this item and its use history will be forgotten.</p><p>{FORGET_SCOPE}</p>
        <label className="memory-check"><input type="checkbox" checked={confirmForget} disabled={locked} onChange={event => setConfirmForget(event.target.checked)} /><span>I choose to forget this saved Memory and all its versions.</span></label>
        <div className="memory-actions"><button className="coaching-button coaching-delete" type="button" disabled={locked || !confirmForget} onClick={() => post('forget', { memory_id: forget.memory_id, expected_version: forget.version }, { success: `Memory forgotten. ${FORGET_SCOPE}` })}>Forget this Memory</button><button className="coaching-button" type="button" disabled={busy} onClick={() => { setForget(null); setConfirmForget(false) }}>Cancel</button></div>
      </section>}

      <section className="memory-inventory" aria-labelledby="memory-inventory-heading">
        <div className="memory-inventory-header"><h2 id="memory-inventory-heading">Saved inventory</h2><label>Show state<select value={filter} onChange={event => setFilter(event.target.value)}><option value="all">All states and versions</option>{STATES.map(state => <option key={state} value={state}>{label(state)}</option>)}</select></label></div>
        {records.memories.length === 0 ? <div className="coaching-empty"><h3>No saved Memory</h3><p>Only exact items you confirm appear here. Conversation Messages are separate.</p></div> : visible.length === 0 ? <p className="memory-empty">No Memory versions in this state. Choose another state to see more.</p> : visible.map(row => {
          const current = latest.get(row.memory_id) === row.version && row.state !== 'forgotten'
          const uses = records.uses.filter(use => use.memory_id === row.memory_id && use.version === row.version)
          return <article className="coaching-program" key={`${row.memory_id}:${row.version}`}>
            <div className="coaching-program-heading"><h3>{row.state === 'forgotten' ? 'Forgotten Memory' : label(row.category)}</h3><span className="coaching-state">{label(row.state)}</span></div>
            {row.text && <p className="memory-exact">{row.text}</p>}
            <dl className="coaching-details"><div><dt>Version</dt><dd>{row.version}{current ? ' · current version' : ''}</dd></div><div><dt>Allowed Modes</dt><dd>{row.scopes?.join(', ') || 'None'}</dd></div><div><dt>Source</dt><dd>{row.source_channel ? <>{label(row.creation_path)} · {row.source_channel} · {row.source_mode_id}</> : 'Source removed'}</dd></div><div><dt>Source date</dt><dd>{row.source_date || 'Removed'}</dd></div><div><dt>Source Message</dt><dd>{row.source_message_id || 'No Message reference'}</dd></div><div><dt>Confirmed</dt><dd>{dateLabel(row.confirmed_at)}</dd></div><div><dt>Valid through</dt><dd>{row.valid_until || 'No explicit date'}</dd></div><div><dt>Reconfirmation due</dt><dd>{dateLabel(row.reconfirm_at)}</dd></div>{row.category === 'goal' || row.category === 'project' ? <div><dt>Goal state</dt><dd>{row.goal_state}</dd></div> : null}</dl>
            {current && <div className="memory-actions">
              <button className="coaching-button" type="button" disabled={locked || !canSave} onClick={() => beginEdit(row, 'correct')}>Edit</button>
              <button className="coaching-button" type="button" disabled={locked || !canSave} onClick={() => beginEdit(row, 'reconfirm')}>Confirm again</button>
              <button className="coaching-button" type="button" disabled={locked || !canSave} onClick={() => beginEdit(row, 'share')}>Change allowed Modes</button>
              <button className="coaching-button" type="button" disabled={locked || (row.state !== 'active' && (row.state !== 'inactive' || row.goal_state !== 'ongoing' || !canSave))} onClick={() => post('action', { memory_id: row.memory_id, expected_version: row.version, action: row.state === 'active' ? 'inactive' : 'use_again' })}>{row.state === 'active' ? 'Do not use' : 'Use again'}</button>
              {(row.category === 'goal' || row.category === 'project') && row.goal_state === 'ongoing' && <><button className="coaching-button" type="button" disabled={locked} onClick={() => post('action', { memory_id: row.memory_id, expected_version: row.version, action: 'complete_goal' })}>Mark completed</button><button className="coaching-button" type="button" disabled={locked} onClick={() => post('action', { memory_id: row.memory_id, expected_version: row.version, action: 'cancel_goal' })}>Mark cancelled</button></>}
              <button className="coaching-button coaching-delete" type="button" disabled={locked} onClick={() => { setForget(row); setConfirmForget(false); setDraft(null); setPreview(null) }}>Forget</button>
            </div>}
            {current && row.state === 'needs_confirmation' && <p className="memory-state-reason">Confirmation is due. Choose Confirm again before this item can be used.</p>}
            {current && row.state === 'expired' && <p className="memory-state-reason">The validity date has passed. Choose Confirm again and review its current validity before use.</p>}
            {current && row.goal_state !== 'ongoing' && <p className="memory-state-reason">This {row.goal_state} goal stays excluded from use.</p>}
            {current && row.state === 'inactive' && row.goal_state === 'ongoing' && !canSave && <p className="memory-state-reason">Use again is unavailable while saving is unavailable or learning is paused.</p>}
            <details className="memory-use-history"><summary>Use history ({uses.length})</summary>{uses.length === 0 ? <p className="coaching-muted">No use recorded for this version.</p> : <ol className="coaching-history">{uses.map(use => <li key={`${use.turn_id}:${use.purpose}`}><strong>{PURPOSES[use.purpose] || 'Purpose unavailable'}</strong><p><time dateTime={use.used_at}>{dateLabel(use.used_at)}</time> · Turn {use.turn_id}</p></li>)}</ol>}</details>
          </article>
        })}
      </section>
      <footer className="coaching-data-controls"><h2>Forget all saved Memory</h2><p>{FORGET_SCOPE}</p><button className="coaching-button coaching-delete" type="button" disabled={locked || !hasMemory} onClick={() => { setForget(null); post('preview', { operation: 'forget_all' }, { review: true }) }}>Review Forget all</button></footer>
    </>}
  </section>
}
