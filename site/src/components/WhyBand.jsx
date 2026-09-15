import Reveal from './Reveal'
import { WHY } from '../content/home'

export default function WhyBand() {
  return (
    <section className="why-band" aria-labelledby="why-title">
      <div className="why-band-inner">
        <Reveal>
          <h2 id="why-title" className="section-title">
            {WHY.title}
          </h2>
          <div className="why-body">{WHY.body}</div>
        </Reveal>
      </div>
    </section>
  )
}
