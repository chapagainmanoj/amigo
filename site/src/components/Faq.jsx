import Reveal from './Reveal'
import { FAQ } from '../content/home'

export default function Faq() {
  return (
    <section className="faq-section" aria-labelledby="faq-title">
      <Reveal>
        <h2 id="faq-title" className="section-title">
          {FAQ.title}
        </h2>
        <div className="faq-list">
          {FAQ.items.map((item) => (
            <details key={item.q} className="faq-item">
              <summary className="faq-question">{item.q}</summary>
              <div className="faq-answer">
                <p>{item.a}</p>
              </div>
            </details>
          ))}
        </div>
      </Reveal>
    </section>
  )
}
