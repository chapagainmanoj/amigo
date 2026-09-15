import Reveal from './Reveal'

// The release gate from decisions/14-mode-and-adaptation-contract.md, drawn.
//
// Daily is deliberately absent: it is the default workspace, not a specialised Mode, so it never
// enters this track. All three specialised Modes genuinely sit before stage one — that is the
// honest picture, and the difference between them is which thing is holding them there.
const STAGES = [
  { n: '1', label: 'Demand evidence', note: 'Three separate people, same recurring problem' },
  { n: '2', label: 'Contract tests', note: 'Tools, data, transitions and retention, enforced in code' },
  { n: '3', label: 'Evaluation', note: 'A model evaluation run, then five moderated sessions' },
  { n: '4', label: 'Opt-in trial', note: 'Fourteen days, five participants, one Mode at a time' },
]

const WAITING = [
  { name: 'Coach', why: 'Next in line. Waiting on the demand evidence.' },
  { name: 'Reflect', why: 'Blocked by the non-clinical wellbeing review.' },
  { name: 'Recommender', why: 'Dormant until a first narrow area is chosen.' },
]

export default function GateTrack() {
  return (
    <Reveal className="gate-track" as="figure">
      <figcaption className="gate-track-caption">
        Where the three specialised modes actually are
      </figcaption>

      <div className="gate-track-grid">
        <div className="gate-waiting">
          <p className="gate-waiting-label">Not started</p>
          <ul className="gate-waiting-list">
            {WAITING.map((mode) => (
              <li key={mode.name} className="gate-waiting-item">
                <span className="gate-waiting-name">{mode.name}</span>
                <span className="gate-waiting-why">{mode.why}</span>
              </li>
            ))}
          </ul>
        </div>

        <ol className="gate-stages">
          {STAGES.map((stage) => (
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

      <p className="gate-track-foot">
        Every stage is passed on a mode&rsquo;s own evidence. Evidence for one never counts for
        another, and any stage can end the branch.
      </p>
    </Reveal>
  )
}
