import Reveal from './Reveal'
import { OPEN_SOURCE } from '../content/home'

export default function OpenSource() {
  return (
    <section className="open-source-section" aria-labelledby="open-source-title">
      <Reveal>
        <h2 id="open-source-title" className="section-title">
          {OPEN_SOURCE.title}
        </h2>
        <p className="open-source-body">{OPEN_SOURCE.body}</p>
        <div className="open-source-links">
          {OPEN_SOURCE.links.map((link) => (
            <a
              key={link.href}
              href={link.href}
              target="_blank"
              rel="noopener noreferrer"
              className="open-source-link"
            >
              {link.label}
            </a>
          ))}
        </div>
      </Reveal>
    </section>
  )
}
