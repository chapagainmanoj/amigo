import Reveal from './Reveal'
import StartCta from './StartCta'
import { CLOSING_CTA } from '../content/shared'

// Closes both the home page and the modes page.
export default function ClosingCta({ titleId }) {
  return (
    <section className="closing-cta-section" aria-labelledby={titleId}>
      <Reveal className="closing-cta-content">
        <h2 id={titleId} className="closing-cta-title">
          {CLOSING_CTA.title}
        </h2>
        <p className="closing-cta-lead">{CLOSING_CTA.lead}</p>
        <StartCta />
      </Reveal>
    </section>
  )
}
