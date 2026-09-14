import Reveal from './Reveal'
import StatRow from './StatRow'
import WaitlistForm from './WaitlistForm'

export default function Hero() {
  return (
    <section className="hero-section" aria-label="Introduction">
      <Reveal>
        <p className="kicker hero-kicker">Invitation-only · Not yet open</p>
        <h1 className="hero-title">
          Most task apps are
          <br className="hero-br" /> abandoned in a <em>month</em>.
        </h1>
        <p className="hero-lead">
          Not because people stop caring. Because the app is one more thing to open,
          groom, and feel guilty about. Amigo doesn&rsquo;t ask you to open anything.
        </p>
        <WaitlistForm variant="hero" />
        <p className="hero-micro">
          No newsletter, no launch countdown. One message when there is something real
          to try.
        </p>
      </Reveal>
      <StatRow />
    </section>
  )
}
