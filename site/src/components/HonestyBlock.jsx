import Reveal from './Reveal'
import { HONESTY } from '../content/home'

export default function HonestyBlock() {
  return (
    <section className="honesty-section" aria-labelledby="honesty-title">
      <Reveal>
        <h2 id="honesty-title" className="section-title">
          {HONESTY.title}
        </h2>
        <p className="honesty-lead">{HONESTY.lead}</p>

        <div className="honesty-grid">
          {HONESTY.columns.map((column) => (
            <div
              key={column.heading}
              className={`honesty-col ${column.direction ? 'honesty-col--direction' : ''}`}
            >
              <h3 className="honesty-col-heading">
                {column.heading}
                <span className="honesty-col-sub">{column.sub}</span>
              </h3>
              <ul className="honesty-list">
                {column.items.map((item) => (
                  <li key={item} className="honesty-item">
                    <span className="honesty-glyph" aria-hidden="true">
                      {column.direction ? '→' : '—'}
                    </span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="honesty-boundary" role="note">
          <p>{HONESTY.boundary}</p>
        </div>
      </Reveal>
    </section>
  )
}
