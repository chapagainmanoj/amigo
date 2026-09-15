import { useState } from 'react'
import { isWaitlistConfigured, isWaitlistPreview, submitWaitlist } from '../lib/waitlist'
import { WAITLIST } from '../content/shared'

export default function WaitlistForm({ variant = 'hero', anchorId: anchorIdProp }) {
  const idPrefix = `waitlist-${variant}`
  const emailInputId = `${idPrefix}-email`
  const consentId = `${idPrefix}-consent`
  const errorId = `${idPrefix}-error`

  // The nav's "Join the waitlist" scrolls to #waitlist. The anchor has to exist in every
  // state of this component, including the unconfigured one the site ships in before the
  // founder sets VITE_WAITLIST_ENDPOINT — otherwise the primary CTA silently does nothing.
  // Pages without a hero (the modes page) pass anchorId explicitly so their own form owns it.
  const anchorId = anchorIdProp ?? (variant === 'hero' ? 'waitlist' : undefined)

  const configured = isWaitlistConfigured()
  const preview = isWaitlistPreview()
  const [email, setEmail] = useState('')
  const [consent, setConsent] = useState(false)
  const [status, setStatus] = useState(configured || preview ? 'idle' : 'unconfigured')
  const [errorMessage, setErrorMessage] = useState('')

  const clearError = () => {
    if (status === 'error') {
      setStatus('idle')
      setErrorMessage('')
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if ((!configured && !preview) || status === 'submitting') return

    if (!consent) {
      setErrorMessage(WAITLIST.errors.consent)
      setStatus('error')
      return
    }

    const trimmedEmail = email.trim()
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedEmail)) {
      setErrorMessage(WAITLIST.errors.email)
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
      setErrorMessage(err.message || WAITLIST.errors.network)
    }
  }

  if (status === 'success') {
    return (
      <div
        id={anchorId}
        className={`waitlist-success waitlist-success-${variant}`}
        role="status"
      >
        <p className="waitlist-success-text">{WAITLIST.success}</p>
      </div>
    )
  }

  if (status === 'unconfigured') {
    return (
      <div id={anchorId} className={`waitlist-form-container waitlist-${variant}`}>
        <div className="waitlist-unconfigured">
          <p className="waitlist-notice">{WAITLIST.unconfigured}</p>
        </div>
      </div>
    )
  }

  return (
    <div id={anchorId} className={`waitlist-form-container waitlist-${variant}`}>
      <form className="waitlist-form" onSubmit={handleSubmit} noValidate>
        <div className="waitlist-inputs">
          <label htmlFor={emailInputId} className="sr-only">
            {WAITLIST.emailLabel}
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
            placeholder={WAITLIST.emailPlaceholder}
            className={`waitlist-input ${status === 'error' ? 'waitlist-input-error' : ''}`}
            aria-describedby={status === 'error' ? errorId : undefined}
            disabled={status === 'submitting'}
          />
          <button type="submit" disabled={status === 'submitting'} className="waitlist-button">
            {status === 'submitting' ? (
              <span className="waitlist-button-loading">
                <span className="spinner" aria-hidden="true" />
                {WAITLIST.submitting}
              </span>
            ) : (
              WAITLIST.submit
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
            {WAITLIST.consent}{' '}
            <a href={WAITLIST.consentLink.href} className="waitlist-consent-link">
              {WAITLIST.consentLink.label}
            </a>
          </label>
        </div>

        {status === 'error' && (
          <p id={errorId} className="waitlist-error" role="alert">
            {errorMessage}
          </p>
        )}

        {import.meta.env.DEV && preview && (
          <p className="waitlist-preview-note">{WAITLIST.previewNote}</p>
        )}
      </form>
    </div>
  )
}
