import Reveal from './Reveal'
import { MODES, MODE_BOUND_HEADINGS } from '../content/modes'

function ModeRow({ mode }) {
  const headings = mode.shipped ? MODE_BOUND_HEADINGS.shipped : MODE_BOUND_HEADINGS.planned

  return (
    <Reveal className={`mode-row ${mode.shipped ? 'mode-row--shipped' : ''}`}>
      <div className="mode-rail">
        <h2 className="mode-name">{mode.name}</h2>
        <p className={`mode-status ${mode.shipped ? 'mode-status--shipped' : ''}`}>{mode.status}</p>
      </div>

      <div className="mode-content">
        <p className="mode-job">&ldquo;{mode.job}&rdquo;</p>
        <p className="mode-body">{mode.body}</p>

        <div className="mode-bounds">
          <div className="mode-bound">
            <h3 className="mode-bound-heading">{headings.can}</h3>
            <ul className="mode-listing">
              {mode.can.map((item) => (
                <li key={item} className="mode-listing-item">
                  {item}
                </li>
              ))}
            </ul>
          </div>
          <div className="mode-bound">
            <h3 className="mode-bound-heading">{headings.cannot}</h3>
            <ul className="mode-listing mode-listing--limits">
              {mode.cannot.map((item) => (
                <li key={item} className="mode-listing-item">
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </div>

        {mode.gate && <p className="mode-gate">{mode.gate}</p>}
      </div>
    </Reveal>
  )
}

export default function ModeList() {
  return (
    <section className="mode-list" aria-label="Amigo modes">
      {MODES.map((mode) => (
        <ModeRow key={mode.name} mode={mode} />
      ))}
    </section>
  )
}
