import { useEffect, useRef, useState } from 'react'
import { DEMO } from '../content/home'

const { userAsk, botConfirm, divider, reminder, botDone } = DEMO.lines

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
      {/* The same lines the bubbles animate, as a transcript for screen readers. Both read from
          DEMO, so the spoken version cannot drift from the seen one. */}
      <div className="sr-only">
        <p>{DEMO.transcriptLabel}</p>
        <ol>
          <li>You: {userAsk.text}</li>
          <li>
            {DEMO.bot.name}: {botConfirm.text}
          </li>
          <li>Time: {divider}</li>
          <li>
            {DEMO.bot.name}: {reminder.text} (Actions: {DEMO.buttons.join(', ')})
          </li>
          <li>You tapped: {DEMO.pressed}</li>
          <li>
            {DEMO.bot.name}: {botDone.text}
          </li>
        </ol>
      </div>

      <div className="telegram-demo-grid">
        <div className="telegram-demo-caption">
          <h2 className="telegram-demo-heading">{DEMO.heading}</h2>
          <p className="telegram-demo-text">{DEMO.text}</p>
        </div>

        {/* Visual phone card mock */}
        <div className="telegram-phone-card" aria-hidden="true">
          <div className="telegram-phone-header">
            <div className="telegram-bot-avatar">{DEMO.bot.avatar}</div>
            <div className="telegram-bot-meta">
              <span className="telegram-bot-name">{DEMO.bot.name}</span>
              <span className="telegram-bot-status">{DEMO.bot.status}</span>
            </div>
          </div>

          <div className="telegram-phone-body">
            {/* Step 1: User message */}
            {step >= 1 && (
              <div className="telegram-message telegram-user animate-fade-in">
                <div className="telegram-bubble">
                  {userAsk.text}
                  <span className="telegram-time">{userAsk.time}</span>
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
                  {botConfirm.text}
                  <span className="telegram-time">{botConfirm.time}</span>
                </div>
              </div>
            )}

            {/* Step 4+: Timestamp divider */}
            {step >= 4 && (
              <div className="telegram-divider animate-fade-in">
                <span>{divider}</span>
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
                  {reminder.text}
                  <span className="telegram-time">{reminder.time}</span>
                </div>
                <div className="telegram-inline-keyboard">
                  {DEMO.buttons.map((label) => {
                    // Step 7 is the tap: only the button the transcript says was pressed lights up.
                    const pressed = label === DEMO.pressed && step >= 7
                    return (
                      <button
                        key={label}
                        type="button"
                        tabIndex={-1}
                        className={`telegram-kbd-btn ${pressed ? 'telegram-kbd-btn-active' : ''}`}
                      >
                        {label}
                      </button>
                    )
                  })}
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
                  {botDone.text}
                  <span className="telegram-time">{botDone.time}</span>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
