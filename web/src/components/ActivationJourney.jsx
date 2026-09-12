import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Check, Clock3, ExternalLink, RefreshCw } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { apiRequest, supabase } from '../supabase'

const STEPS = [
  ['account', 'Account'],
  ['limits', 'Limits'],
  ['telegram', 'Telegram'],
  ['profile', 'Profile'],
  ['test_reminder', 'Test Reminder'],
  ['resolve', 'Resolve'],
  ['dashboard', 'Dashboard'],
]

const STEP_INDEX = Object.fromEntries(STEPS.map(([key], index) => [key, index]))
const POLICY_VERSION = '2026-08-29'

function Progress({ step, expanded }) {
  const active = step === 'email_verification' ? 0 : (STEP_INDEX[step] ?? 0)
  return (
    <div className="activation-progress" aria-label={`Setup step ${active + 1} of ${STEPS.length}`}>
      <div className="activation-progress__summary">
        <span>Step {active + 1} of {STEPS.length}</span>
        <strong>{STEPS[active][1]}</strong>
      </div>
      <div className="activation-progress__track" aria-hidden="true">
        <span style={{ width: `${((active + 1) / STEPS.length) * 100}%` }} />
      </div>
      {expanded && (
        <ol className="activation-progress__details" aria-label="Setup recovery checklist">
          {STEPS.map(([key, label], index) => (
            <li key={key} className={index <= active ? 'is-complete' : ''}>
              <span aria-hidden="true">{index < active ? <Check size={13} /> : index + 1}</span>
              {label}
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

function ErrorMessage({ error }) {
  if (!error) return null
  return <div className="activation-error" role="alert">{error}</div>
}

export default function ActivationJourney({ session, state, refresh, onFinish }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [pairing, setPairing] = useState(null)
  const [now, setNow] = useState(Date.now())
  const cardRef = useRef(null)
  const resumed = state.journey_version > 1 && !sessionStorage.getItem('amigo-activation-active')
  const recovery = resumed || Boolean(error) || ['expired', 'replaced'].includes(state.pairing.status)
    || ['failed', 'late', 'missed', 'cancelled'].includes(state.test?.delivery_state)
  const [checks, setChecks] = useState({
    beta_limits: false,
    privacy_and_retention: false,
    participant_rights: false,
    non_clinical: false,
  })
  const [profile, setProfile] = useState(() => ({
    preferred_name: '',
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
    wake_time: '07:30',
    sleep_time: '23:00',
  }))

  useEffect(() => {
    sessionStorage.setItem('amigo-activation-active', 'true')
  }, [])

  useEffect(() => {
    cardRef.current?.focus()
  }, [state.step])

  const act = useCallback(async (work) => {
    setBusy(true)
    setError(null)
    try {
      await work()
    } catch (err) {
      setError(err.message || 'Setup could not continue. Please retry.')
    } finally {
      setBusy(false)
    }
  }, [])

  const fetchPairing = useCallback(() => act(async () => {
    const data = await apiRequest('/api/pairing-token', { method: 'POST' })
    setPairing(data)
  }), [act])

  useEffect(() => {
    if (state.step === 'telegram' && !pairing && state.pairing.status !== 'active') {
      fetchPairing()
    }
  }, [fetchPairing, pairing, state.pairing.status, state.step])

  useEffect(() => {
    if (!['telegram', 'resolve'].includes(state.step)) return undefined
    const timer = setInterval(refresh, 2000)
    return () => clearInterval(timer)
  }, [refresh, state.step])

  useEffect(() => {
    if (!pairing?.expires_at) return undefined
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [pairing?.expires_at])

  const secondsLeft = useMemo(() => {
    if (!pairing?.expires_at) return null
    return Math.max(0, Math.ceil((new Date(pairing.expires_at).getTime() - now) / 1000))
  }, [now, pairing?.expires_at])

  const acknowledge = () => act(async () => {
    await apiRequest('/api/activation/acknowledge', {
      method: 'POST',
      body: JSON.stringify({ policy_version: POLICY_VERSION, ...checks }),
    })
    await refresh()
  })

  const saveProfile = (event) => {
    event.preventDefault()
    act(async () => {
      await apiRequest('/api/activation/profile', {
        method: 'POST',
        body: JSON.stringify(profile),
      })
      await refresh()
    })
  }

  const createTest = (retry = false) => act(async () => {
    const proposal = state.proposal
    if (!proposal) throw new Error('Refresh the exact Reminder time before confirming.')
    await apiRequest('/api/activation/test-reminder', {
      method: 'POST',
      headers: { 'Idempotency-Key': crypto.randomUUID() },
      body: JSON.stringify({
        scheduled_at: proposal.scheduled_at,
        timezone: proposal.timezone,
        exact_time_confirmed: true,
        retry,
      }),
    })
    await refresh()
  })

  const resendVerification = () => act(async () => {
    const { error: resendError } = await supabase.auth.resend({
      type: 'signup',
      email: session.user.email,
    })
    if (resendError) throw resendError
  })

  return (
    <main className="activation-shell">
      <header className="activation-brand">Amigo</header>
      <div className="activation-layout">
        <Progress step={state.step} expanded={recovery} />
        <section ref={cardRef} tabIndex="-1" className="activation-card animate-slide-in">
          <ErrorMessage error={error} />
          <p className="sr-only" aria-live="polite">
            Setup step {STEP_INDEX[state.step] + 1 || 1}: {state.step.replaceAll('_', ' ')}.
            {state.test?.delivery_state ? ` Delivery ${state.test.delivery_state}.` : ''}
            {state.test?.resolution ? ` Result ${state.test.resolution}.` : ''}
          </p>

          {state.step === 'email_verification' && (
            <>
              <p className="activation-kicker">Account</p>
              <h1>Verify your email</h1>
              <p>Open the confirmation message sent to {session.user.email}, then return here.</p>
              <div className="activation-actions">
                <button className="btn-primary" onClick={refresh} disabled={busy}>I verified — check again</button>
                <button className="btn-secondary" onClick={resendVerification} disabled={busy}>Resend email</button>
              </div>
            </>
          )}

          {state.step === 'limits' && (
            <>
              <p className="activation-kicker">Before connecting Telegram</p>
              <h1>Know what this beta can do</h1>
              <p>Amigo turns conversations into everyday Tasks and Telegram Reminders. It is an early beta, not an emergency, monitoring, medical, or clinical service.</p>
              <div className="activation-checks">
                {[
                  ['beta_limits', 'I understand the beta can fail and I will verify important reminders.'],
                  ['privacy_and_retention', 'I understand messages and task data are stored to provide the service.'],
                  ['participant_rights', 'I can ask for support, export, correction, or deletion of my data.'],
                  ['non_clinical', 'I understand Amigo does not diagnose, treat, supervise, or keep me safe.'],
                ].map(([key, label]) => (
                  <label key={key} className="activation-checkbox">
                    <input type="checkbox" checked={checks[key]} onChange={(event) => setChecks({ ...checks, [key]: event.target.checked })} />
                    <span>{label}</span>
                  </label>
                ))}
              </div>
              <button className="btn-primary" onClick={acknowledge} disabled={busy || Object.values(checks).some((value) => !value)}>
                Accept and connect Telegram
              </button>
            </>
          )}

          {state.step === 'telegram' && (
            <>
              <p className="activation-kicker">Telegram handoff</p>
              <h1>Connect Telegram</h1>
              <p>This securely links your verified dashboard account so Amigo can deliver Reminders and show the same Tasks here. The link is single-use.</p>
              {pairing && secondsLeft > 0 ? (
                <div className="activation-pairing">
                  <div className="activation-qr"><QRCodeSVG value={pairing.bot_link} size={190} level="M" /></div>
                  <p><Clock3 size={16} /> Expires in {Math.floor(secondsLeft / 60)}:{String(secondsLeft % 60).padStart(2, '0')}</p>
                  <a className="btn-primary" href={pairing.bot_link} target="_blank" rel="noreferrer">Open Telegram <ExternalLink size={16} /></a>
                </div>
              ) : (
                <button className="btn-primary" onClick={fetchPairing} disabled={busy}>Generate new single-use link</button>
              )}
              <p className="activation-help">This page detects Pairing automatically. If Telegram says the link expired or was already used, generate a new one here.</p>
            </>
          )}

          {state.step === 'profile' && (
            <form onSubmit={saveProfile}>
              <p className="activation-kicker">Reminder settings</p>
              <h1>Set your profile and quiet hours</h1>
              <p>Use an explicit IANA timezone. Amigo will avoid automatic reminders between quiet-hour start and wake time.</p>
              <div className="form-group"><label htmlFor="preferred-name">Preferred name</label><input id="preferred-name" value={profile.preferred_name} onChange={(event) => setProfile({ ...profile, preferred_name: event.target.value })} required /></div>
              <div className="form-group"><label htmlFor="timezone">IANA timezone</label><input id="timezone" value={profile.timezone} onChange={(event) => setProfile({ ...profile, timezone: event.target.value })} placeholder="America/Toronto" required /></div>
              <div className="activation-time-grid">
                <div className="form-group"><label htmlFor="wake-time">Wake time</label><input id="wake-time" type="time" value={profile.wake_time} onChange={(event) => setProfile({ ...profile, wake_time: event.target.value })} required /></div>
                <div className="form-group"><label htmlFor="sleep-time">Quiet hours start</label><input id="sleep-time" type="time" value={profile.sleep_time} onChange={(event) => setProfile({ ...profile, sleep_time: event.target.value })} required /></div>
              </div>
              <button className="btn-primary" type="submit" disabled={busy}>Save and continue</button>
            </form>
          )}

          {state.step === 'test_reminder' && state.proposal && (
            <>
              <p className="activation-kicker">Private delivery test</p>
              <h1>Confirm a Reminder two minutes ahead</h1>
              <p>This creates one clearly labelled private test Task. Confirm the exact local date, time, and timezone before it is scheduled.</p>
              <div className="activation-time-confirm">
                <strong>{state.proposal.local_date}</strong>
                <strong>{state.proposal.local_time.slice(0, 5)}</strong>
                <span>{state.proposal.timezone}</span>
              </div>
              <p className="activation-help">This proposal must be confirmed within about one minute. Refresh it if it expires.</p>
              <div className="activation-actions">
                <button className="btn-primary" onClick={() => createTest(false)} disabled={busy}>Confirm exact time and schedule test</button>
                <button className="btn-secondary" onClick={refresh} disabled={busy}><RefreshCw size={16} /> Refresh exact time</button>
              </div>
            </>
          )}

          {state.step === 'resolve' && (
            <>
              <p className="activation-kicker">Telegram delivery</p>
              <h1>{state.test.delivered ? 'Resolve the test in Telegram' : 'Waiting for Telegram delivery'}</h1>
              <p>Open Telegram and choose Done, Skip, or Later. Setup completes only after delivery and that result appear here.</p>
              <div className={`activation-status activation-status--${state.test.delivery_state}`}>
                Delivery: {state.test.delivery_state.replaceAll('_', ' ')}
              </div>
              <div className="activation-actions">
                <a className="btn-primary" href="https://t.me/amigo_agent_bot" target="_blank" rel="noreferrer">Open Telegram <ExternalLink size={16} /></a>
                <button className="btn-secondary" onClick={refresh} disabled={busy}><RefreshCw size={16} /> Check status</button>
              </div>
              {state.test.can_retry && state.proposal && (
                <button className="btn-secondary" onClick={() => createTest(true)} disabled={busy}>Retry with a new two-minute Reminder</button>
              )}
              {state.test.delivery_state === 'late' || state.test.delivery_state === 'failed' ? (
                <p className="activation-help">Activation has not completed. Retry once, or contact beta support if delivery remains unavailable.</p>
              ) : null}
            </>
          )}

          {state.step === 'dashboard' && (
            <>
              <p className="activation-kicker">Private test complete</p>
              <h1>Your Telegram result reached Amigo</h1>
              <p>
                Delivery and your {state.test.resolution === 'later' ? 'Later' : state.test.resolution === 'skip' ? 'Skip' : 'Done'} action are both recorded. Your dashboard is now unlocked.
              </p>
              <button className="btn-primary" onClick={onFinish}>Open dashboard and add a real Task</button>
            </>
          )}
        </section>
      </div>
    </main>
  )
}
