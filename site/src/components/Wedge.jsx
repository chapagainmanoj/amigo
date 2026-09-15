import Reveal from './Reveal'
import DayLine from './DayLine'
import { WEDGE } from '../content/home'

export default function Wedge() {
  return (
    <section className="wedge-section" aria-labelledby="wedge-title">
      <Reveal>
        <h2 id="wedge-title" className="section-title">
          {WEDGE.title}
        </h2>
        <div className="wedge-body">{WEDGE.body}</div>
      </Reveal>
      <DayLine />
    </section>
  )
}
