import Reveal from './Reveal'
import { GATE_TRACK } from '../content/modes'

export default function GateTrack() {
  return (
    <Reveal className="gate-track" as="figure">
      <figcaption className="gate-track-caption">{GATE_TRACK.caption}</figcaption>

      <div className="gate-track-grid">
        <div className="gate-waiting">
          <p className="gate-waiting-label">{GATE_TRACK.waitingLabel}</p>
          <ul className="gate-waiting-list">
            {GATE_TRACK.waiting.map((mode) => (
              <li key={mode.name} className="gate-waiting-item">
                <span className="gate-waiting-name">{mode.name}</span>
                <span className="gate-waiting-why">{mode.why}</span>
              </li>
            ))}
          </ul>
        </div>

        <ol className="gate-stages">
          {GATE_TRACK.stages.map((stage) => (
            <li key={stage.n} className="gate-stage">
              <span className="gate-stage-n" aria-hidden="true">
                {stage.n}
              </span>
              <span className="gate-stage-label">{stage.label}</span>
              <span className="gate-stage-note">{stage.note}</span>
            </li>
          ))}
        </ol>
      </div>

      <p className="gate-track-foot">{GATE_TRACK.foot}</p>
    </Reveal>
  )
}
