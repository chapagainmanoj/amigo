import Reveal from './Reveal'
import { HOW_IT_WORKS } from '../content/home'

export default function HowItWorks() {
  return (
    <section className="how-it-works-section" aria-labelledby="how-it-works-title">
      <Reveal>
        <h2 id="how-it-works-title" className="section-title">
          {HOW_IT_WORKS.title}
        </h2>
        <div className="how-grid">
          {HOW_IT_WORKS.steps.map((step) => (
            <div key={step.num} className="how-cell">
              <span className="how-num">{step.num}</span>
              <h3 className="how-title">{step.title}</h3>
              <p className="how-body">{step.body}</p>
            </div>
          ))}
        </div>
      </Reveal>
    </section>
  )
}
