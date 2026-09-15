import SiteNav from './components/SiteNav'
import ModeList from './components/ModeList'
import GateTrack from './components/GateTrack'
import Reveal from './components/Reveal'
import ClosingCta from './components/ClosingCta'
import SiteFooter from './components/SiteFooter'
import { GATE_BAND, GATE_TRACK, MODES_HEADER, MODE_RULES } from './content/modes'

export default function ProductsApp() {
  return (
    <div className="site-app">
      <SiteNav active="products" />
      <main>
        <div className="site-container">
          <section className="modes-header" aria-labelledby="modes-title">
            <Reveal>
              <h1 id="modes-title" className="modes-title">
                {MODES_HEADER.titleLead} <em>{MODES_HEADER.titleEmphasis}</em>.
              </h1>
              <p className="modes-lead">{MODES_HEADER.lead}</p>
            </Reveal>
          </section>

          <ModeList />

          <section className="mode-rules-section" aria-labelledby="mode-rules-title">
            <Reveal>
              <h2 id="mode-rules-title" className="section-title">
                {MODE_RULES.title}
              </h2>
              <ul className="mode-rules">
                {MODE_RULES.items.map((rule) => (
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
                {GATE_BAND.title}
              </h2>
              <p className="gate-lead">{GATE_BAND.lead}</p>
              <p className="gate-close">{GATE_BAND.close}</p>
            </Reveal>
          </div>
        </section>

        <div className="site-container">
          <section className="gate-track-section" aria-labelledby="gate-track-title">
            <h2 id="gate-track-title" className="sr-only">
              {GATE_TRACK.srTitle}
            </h2>
            <GateTrack />
          </section>

          <ClosingCta titleId="modes-cta-title" anchorId="waitlist" />
        </div>
      </main>
      <SiteFooter />
    </div>
  )
}
