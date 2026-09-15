import SiteNav from './components/SiteNav'
import ModeList from './components/ModeList'
import GateTrack from './components/GateTrack'
import Reveal from './components/Reveal'
import WaitlistForm from './components/WaitlistForm'
import SiteFooter from './components/SiteFooter'

const RULES = [
  'You turn a mode on. Amigo never moves you into one on its own — automatic routing is excluded from the first release.',
  'One specialised mode at a time, and every new conversation starts back in Daily.',
  'Entering a mode never hides, moves, or edits the Tasks and Reminders you already have.',
  'Ask for an ordinary reminder inside a mode and you get a visible handoff back to Daily that you confirm.',
  'What you do inside one mode does not flow into another, or into anything durable, unless you say so.',
]


export default function ProductsApp() {
  return (
    <div className="site-app">
      <SiteNav active="products" />
      <main>
        <div className="site-container">
          <section className="modes-header" aria-labelledby="modes-title">
            <Reveal>
              <h1 id="modes-title" className="modes-title">
                Four modes. One of them <em>exists</em>.
              </h1>
              <p className="modes-lead">
                Amigo is not meant to stay a reminder bot. The plan is a small set of modes you
                switch on deliberately, each with its own contract for what it may and may not do.
                Daily is built and working. The other three are written down, argued over, and
                unbuilt — and each one can still end in a documented no.
              </p>
            </Reveal>
          </section>

          <ModeList />

          <section className="mode-rules-section" aria-labelledby="mode-rules-title">
            <Reveal>
              <h2 id="mode-rules-title" className="section-title">
                The rules every mode inherits
              </h2>
              <ul className="mode-rules">
                {RULES.map((rule) => (
                  <li key={rule} className="mode-rule">
                    {rule}
                  </li>
                ))}
              </ul>
            </Reveal>
          </section>
        </div>

        {/* Full-bleed: deliberately outside the content column, matching the home page's one inversion. */}
        <section className="why-band gate-band" aria-labelledby="gate-title">
          <div className="why-band-inner">
            <Reveal>
              <h2 id="gate-title" className="section-title">
                How a mode stops being a plan
              </h2>
              <p className="gate-lead">
                None of the three ship because they sound good. Each passes the same four-stage
                gate on its own evidence, and none of them has entered it yet.
              </p>
              <p className="gate-close">
                A documented &ldquo;do not build&rdquo; is a valid outcome. We would rather delete a
                mode than ship one that makes the loop worse.
              </p>
            </Reveal>
          </div>
        </section>

        <div className="site-container">
          <section className="gate-track-section" aria-labelledby="gate-track-title">
            <h2 id="gate-track-title" className="sr-only">
              Current status of each mode against the release gate
            </h2>
            <GateTrack />
          </section>

          <section className="closing-cta-section" aria-labelledby="modes-cta-title">
            <Reveal className="closing-cta-content">
              <h2 id="modes-cta-title" className="closing-cta-title">
                One message, when there is something to try.
              </h2>
              <p className="closing-cta-lead">
                No newsletter, no countdowns. We will not email you again until Amigo opens.
              </p>
              <WaitlistForm variant="closing" anchorId="waitlist" />
            </Reveal>
          </section>
        </div>
      </main>
      <SiteFooter />
    </div>
  )
}
