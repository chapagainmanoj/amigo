import { useEffect, useRef, useState } from 'react'

export default function TelegramDemo() {
  const containerRef = useRef(null)
  const [step, setStep] = useState(0) // 0 to 9
  const [hasStarted, setHasStarted] = useState(false)
  const [reducedMotion, setReducedMotion] = useState(false)

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (mediaQuery.matches) {
      setReducedMotion(true)
      setStep(9)
      return
    }

    const node = containerRef.current
    if (!node) return

    if (!('IntersectionObserver' in window)) {
      setHasStarted(true)
      return
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setHasStarted(true)
          observer.disconnect()
        }
      },
      { threshold: 0.4 }
    )

    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (reducedMotion || !hasStarted) return

    let timeoutId
    let loops = 0

    const advance = (currentStep) => {
      if (currentStep < 9) {
        timeoutId = setTimeout(() => {
          setStep(currentStep + 1)
          advance(currentStep + 1)
        }, 700)
      } else {
        // Hold final state after 1 loop
        if (loops === 0) {
          timeoutId = setTimeout(() => {
            loops += 1
            setStep(0)
            timeoutId = setTimeout(() => {
              setStep(1)
              advance(1)
            }, 700)
          }, 3500)
        }
      }
    }

    // Start sequence from step 1
    timeoutId = setTimeout(() => {
      setStep(1)
      advance(1)
    }, 400)

    return () => clearTimeout(timeoutId)
  }, [hasStarted, reducedMotion])

  return (
    <div className="telegram-demo-wrapper" ref={containerRef}>
      {/* Visually-hidden accessible transcript for screen readers */}
      <div className="sr-only">
        <p>Telegram Interaction Demo Transcript</p>
        <ol>
          <li>You: I need to send the proposal at 3 PM. Remind me then.</li>
          <li>Amigo: Got it — "Send the proposal". I'll remind you at 3:00 PM.</li>
          <li>Time: 3:00 PM</li>
          <li>Amigo: Send the proposal (Actions: Done, Skip, Later)</li>
          <li>You tapped: Done</li>
          <li>Amigo: Nice. Marked done.</li>
        </ol>
      </div>

      <div className="telegram-demo-grid">
        <div className="telegram-demo-caption">
          <h2 className="telegram-demo-heading">It lives in a chat you already have open.</h2>
          <p className="telegram-demo-text">
            One sentence in, one reminder out, three buttons to close it. Nothing to install, nothing to
            organise, nothing to abandon.
          </p>
        </div>

        {/* Visual phone card mock */}
        <div className="telegram-phone-card" aria-hidden="true">
          <div className="telegram-phone-header">
            <div className="telegram-bot-avatar">A</div>
            <div className="telegram-bot-meta">
              <span className="telegram-bot-name">Amigo</span>
              <span className="telegram-bot-status">bot</span>
            </div>
          </div>

          <div className="telegram-phone-body">
            {/* Step 1: User message */}
            {step >= 1 && (
              <div className="telegram-message telegram-user animate-fade-in">
                <div className="telegram-bubble">
                  I need to send the proposal at 3 PM. Remind me then.
                  <span className="telegram-time">2:14 PM</span>
                </div>
              </div>
            )}

            {/* Step 2: Amigo typing indicator */}
            {step === 2 && (
              <div className="telegram-message telegram-amigo">
                <div className="telegram-bubble telegram-typing">
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                </div>
              </div>
            )}

            {/* Step 3+: Amigo response */}
            {step >= 3 && (
              <div className="telegram-message telegram-amigo animate-fade-in">
                <div className="telegram-bubble">
                  Got it — &ldquo;Send the proposal&rdquo;. I'll remind you at 3:00 PM.
                  <span className="telegram-time">2:14 PM</span>
                </div>
              </div>
            )}

            {/* Step 4+: Timestamp divider */}
            {step >= 4 && (
              <div className="telegram-divider animate-fade-in">
                <span>3:00 PM</span>
              </div>
            )}

            {/* Step 5: Amigo typing indicator */}
            {step === 5 && (
              <div className="telegram-message telegram-amigo">
                <div className="telegram-bubble telegram-typing">
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                </div>
              </div>
            )}

            {/* Step 6+: Amigo reminder with action buttons */}
            {step >= 6 && (
              <div className="telegram-message telegram-amigo animate-fade-in">
                {/* The one place --signal is spent besides the CTA: the moment the
                    product actually exists for the user. */}
                <div className="telegram-bubble telegram-bubble--reminder">
                  Send the proposal
                  <span className="telegram-time">3:00 PM</span>
                </div>
                <div className="telegram-inline-keyboard">
                  <button
                    type="button"
                    tabIndex={-1}
                    className={`telegram-kbd-btn ${step >= 7 ? 'telegram-kbd-btn-active' : ''}`}
                  >
                    Done
                  </button>
                  <button type="button" tabIndex={-1} className="telegram-kbd-btn">
                    Skip
                  </button>
                  <button type="button" tabIndex={-1} className="telegram-kbd-btn">
                    Later
                  </button>
                </div>
              </div>
            )}

            {/* Step 8: Amigo typing indicator */}
            {step === 8 && (
              <div className="telegram-message telegram-amigo">
                <div className="telegram-bubble telegram-typing">
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                </div>
              </div>
            )}

            {/* Step 9: Amigo marked done */}
            {step >= 9 && (
              <div className="telegram-message telegram-amigo animate-fade-in">
                <div className="telegram-bubble">
                  Nice. Marked done.
                  <span className="telegram-time">3:01 PM</span>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
