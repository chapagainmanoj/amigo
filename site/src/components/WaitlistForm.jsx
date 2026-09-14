import { useEffect, useRef, useState } from 'react'
import { isWaitlistConfigured, submitWaitlist } from '../lib/waitlist'

export default function WaitlistForm({ variant = 'hero' }) {
  const idPrefix = `waitlist-${variant}`
  const emailInputId = `${idPrefix}-email`
  const consentId = `${idPrefix}-consent`
  const errorId = `${idPrefix}-error`

  // The nav's "Join the waitlist" scrolls to #waitlist. The anchor has to exist in every
  // state of this component, including the unconfigured one the site ships in before the
  // founder sets VITE_WAITLIST_ENDPOINT — otherwise the primary CTA silently does nothing.
  const anchorId = variant === 'hero' ? 'waitlist' : undefined

  const configured = isWaitlistConfigured()
  const [email, setEmail] = useState('')
  const [consent, setConsent] = useState(false)
  const [status, setStatus] = useState(configured ? 'idle' : 'unconfigured')
  const [errorMessage, setErrorMessage] = useState('')

  const successRef = useRef(null)

  useEffect(() => {
    if (status === 'success' && successRef.current) {
      successRef.current.focus()
    }
  }, [status])

  const clearError = () => {
    if (status === 'error') {
      setStatus('idle')
      setErrorMessage('')
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!configured || status === 'submitting') return

    if (!consent) {
      setErrorMessage('Please tick the box so we know you want the email.')
      setStatus('error')
      return
    }

    const trimmedEmail = email.trim()
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedEmail)) {
      setErrorMessage('Please enter a valid email address.')
      setStatus('error')
      return
    }

    setStatus('submitting')
    setErrorMessage('')

    try {
      await submitWaitlist(trimmedEmail)
      setStatus('success')
    } catch (err) {
      setStatus('error')
      setErrorMessage(err.message || "That didn't go through — try again in a moment.")
    }
  }

  if (status === 'success') {
    return (
      <div
        id={anchorId}
        className={`waitlist-success waitlist-success-${variant}`}
        ref={successRef}
        tabIndex={-1}
        role="status"
      >
        <p className="waitlist-success-text">
          Check your inbox. Click the link in the confirmation email and you&rsquo;re on the
          list.
        </p>
      </div>
    )
  }

  if (status === 'unconfigured') {
    return (
      <div id={anchorId} className={`waitlist-form-container waitlist-${variant}`}>
        <form className="waitlist-form" onSubmit={(e) => e.preventDefault()}>
          <div className="waitlist-inputs">
            <label htmlFor={emailInputId} className="sr-only">
              Email address
            </label>
            <input
              id={emailInputId}
              type="email"
              disabled
              placeholder="you@example.com"
              className="waitlist-input"
            />
            <button type="button" disabled className="waitlist-button">
              Join the waitlist
            </button>
          </div>
          <p className="waitlist-notice" role="status">
            Waitlist signup isn&rsquo;t configured yet.
          </p>
        </form>
      </div>
    )
  }

  return (
    <div id={anchorId} className={`waitlist-form-container waitlist-${variant}`}>
      <form className="waitlist-form" onSubmit={handleSubmit} noValidate>
        <div className="waitlist-inputs">
          <label htmlFor={emailInputId} className="sr-only">
            Email address
          </label>
          <input
            id={emailInputId}
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value)
              clearError()
            }}
            placeholder="you@example.com"
            className={`waitlist-input ${status === 'error' ? 'waitlist-input-error' : ''}`}
            aria-describedby={status === 'error' ? errorId : undefined}
            disabled={status === 'submitting'}
          />
          <button type="submit" disabled={status === 'submitting'} className="waitlist-button">
            {status === 'submitting' ? (
              <span className="waitlist-button-loading">
                <span className="spinner" aria-hidden="true" />
                Sending
              </span>
            ) : (
              'Join the waitlist'
            )}
          </button>
        </div>

        <div className="waitlist-consent">
          <input
            id={consentId}
            type="checkbox"
            required
            checked={consent}
            onChange={(e) => {
              setConsent(e.target.checked)
              clearError()
            }}
            disabled={status === 'submitting'}
            className="waitlist-checkbox"
          />
          <label htmlFor={consentId} className="waitlist-consent-label">
            Email me once, when Amigo opens.
          </label>
        </div>

        {status === 'error' && (
          <p id={errorId} className="waitlist-error" role="alert">
            {errorMessage}
          </p>
        )}
      </form>
    </div>
  )
}
