import { useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../supabase'

// Ready-made Coach goals. Picking one opens Coach in Telegram with the goal and measure filled
// in; the participant replies there with their check-in time. One Program at a time, so the
// current one can be stopped here first.
export default function CoachTemplates({ onPick, busy, collapsed = false }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(false)
  const [picked, setPicked] = useState(null)
  const [expanded, setExpanded] = useState(!collapsed)
  const [confirming, setConfirming] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [stopError, setStopError] = useState(null)

  const load = useCallback(async () => {
    try {
      setData(await apiRequest('/api/coaching/templates'))
      setError(false)
    } catch {
      setError(true)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const pick = async (template) => {
    setPicked(null)
    if (await onPick(template.id)) setPicked(template)
    load()
  }

  const stop = async () => {
    setStopping(true)
    setStopError(null)
    try {
      await apiRequest('/api/coaching/program/stop', {
        method: 'POST',
        headers: { 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({
          program_id: data.current_program.program_id,
          expected_version: data.current_program.version,
        }),
      })
      setConfirming(false)
    } catch (stopFailure) {
      setStopError(
        stopFailure.status === 409
          ? 'The program changed in Telegram. Check it and try again.'
          : 'Could not stop the program. Try again.',
      )
    } finally {
      setStopping(false)
      load()
    }
  }

  if (error || data === null) return null
  const current = data.current_program

  if (!expanded) {
    return (
      <p className="coach-templates-note coach-templates-collapsed">
        {current
          ? <>Coach program running: <strong>{current.goal}</strong>.</>
          : 'Want a coaching program?'}{' '}
        <button type="button" className="mode-howto-copy" onClick={() => setExpanded(true)}>
          Browse templates
        </button>
      </p>
    )
  }

  return (
    <section className="coach-templates" aria-labelledby="coach-templates-title">
      <p id="coach-templates-title" className="mode-chips-label">Start a Coach program</p>
      {current ? (
        <p className="coach-templates-note">
          Your current program: <strong>{current.goal}</strong> ({current.state}). One program at a
          time: stop it before picking another.{' '}
          {confirming ? (
            <>
              Stop “{current.goal}”? Its records stay.{' '}
              <button type="button" className="mode-howto-copy" disabled={stopping} onClick={stop}>
                {stopping ? 'Stopping…' : 'Yes, stop it'}
              </button>
              <button
                type="button"
                className="mode-howto-copy"
                disabled={stopping}
                onClick={() => setConfirming(false)}
              >
                Keep it
              </button>
            </>
          ) : (
            <button type="button" className="mode-howto-copy" onClick={() => setConfirming(true)}>
              Stop program
            </button>
          )}
        </p>
      ) : (
        <p className="coach-templates-note">
          Pick one and Coach opens in Telegram with it filled in. Reply there with your check-in time,
          or change anything.
        </p>
      )}
      {stopError && <p className="coach-templates-note" role="alert">{stopError}</p>}
      {picked && (
        <p className="coach-templates-note" role="status">
          Sent “{picked.title}” to Telegram. Reply there to finish setting it up.
        </p>
      )}
      <div className="coach-templates-grid">
        {data.templates.map((template) => (
          <button
            key={template.id}
            type="button"
            className="coach-template"
            disabled={busy || Boolean(current)}
            onClick={() => pick(template)}
          >
            <span className="coach-template-title">{template.title}</span>
            <span className="coach-template-detail">{template.success_measure}</span>
            <span className="coach-template-days">{template.check_in_days}</span>
          </button>
        ))}
      </div>
    </section>
  )
}
