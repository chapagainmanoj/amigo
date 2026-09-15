import Reveal from './Reveal'
import StatRow from './StatRow'
import WaitlistForm from './WaitlistForm'
import { HERO } from '../content/home'

export default function Hero() {
  return (
    <section className="hero-section" aria-label="Introduction">
      <Reveal>
        <p className="kicker hero-kicker">{HERO.kicker}</p>
        <h1 className="hero-title">
          {HERO.titleLead}
          <br className="hero-br" /> {HERO.titleRest} <em>{HERO.titleEmphasis}</em>.
        </h1>
        <p className="hero-lead">{HERO.lead}</p>
        <WaitlistForm variant="hero" />
        <p className="hero-micro">{HERO.micro}</p>
      </Reveal>
      <StatRow />
    </section>
  )
}
