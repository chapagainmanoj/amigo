import Reveal from './Reveal'
import WaitlistForm from './WaitlistForm'
import { CLOSING_CTA } from '../content/shared'

// Closes both pages. The home page's hero already owns #waitlist, so only the modes page asks
// this form to claim the anchor the nav scrolls to.
export default function ClosingCta({ titleId, anchorId }) {
  return (
    <section className="closing-cta-section" aria-labelledby={titleId}>
      <Reveal className="closing-cta-content">
        <h2 id={titleId} className="closing-cta-title">
          {CLOSING_CTA.title}
        </h2>
        <p className="closing-cta-lead">{CLOSING_CTA.lead}</p>
        <WaitlistForm variant="closing" anchorId={anchorId} />
      </Reveal>
    </section>
  )
}
