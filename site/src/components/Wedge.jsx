import Reveal from './Reveal'
import DayLine from './DayLine'

export default function Wedge() {
  return (
    <section className="wedge-section" aria-labelledby="wedge-title">
      <Reveal>
        <h2 id="wedge-title" className="section-title">
          Every other tool adds a surface. This one removes it.
        </h2>
        <div className="wedge-body">
          <p>
            Focusmate books you a stranger. Finch gives you a pet. The new wave of AI
            companions gives you another chat window to remember. All of them assume you
            will come back to an app you have already stopped opening.
          </p>
          <p>
            <strong>
              Amigo starts in Telegram, where you already are — and the only time it
              appears is the moment you asked it to.
            </strong>{' '}
            No streaks to protect, no counter resetting to zero, nothing to feel bad about
            on the days you skip.
          </p>
        </div>
      </Reveal>
      <DayLine />
    </section>
  )
}
