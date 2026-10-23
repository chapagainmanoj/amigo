import { useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../supabase'

// Ready-made Coach goals. Picking one opens Coach in Telegram with the goal and measure filled
// in; the participant replies there with their check-in time. One Program at a time.
export default function CoachTemplates({ onPick, busy }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(false)
  const [picked, setPicked] = useState(null)

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

  if (error || data === null) return null
  const current = data.current_program

  return (
    <section className="coach-templates" aria-labelledby="coach-templates-title">
      <p id="coach-templates-title" className="mode-chips-label">Start a Coach program</p>
      {current ? (
        <p className="coach-templates-note">
          Your current program: <strong>{current.goal}</strong> ({current.state}). One program at a
          time: stop it in Telegram before picking another.
        </p>
      ) : (
        <p className="coach-templates-note">
          Pick one and Coach opens in Telegram with it filled in. Reply there with your check-in time,
          or change anything.
        </p>
      )}
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
