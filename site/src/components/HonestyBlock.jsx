import Reveal from './Reveal'

// Column 1 maps one-to-one to the "Shipped in the current prototype" column of
// docs/capability-matrix.md. Column 3 is direction, never a promise: no dates, no
// present tense, and the disclaimer is the column heading rather than a footnote.
const COLUMNS = [
  {
    heading: 'Working today',
    sub: 'in the prototype, right now',
    items: [
      'Telegram conversation, in plain language',
      'Tasks created from what you type',
      'Reminders at the time you ask for',
      'Done, Skip, and Later, in the chat',
      'A dashboard for your tasks and reminders',
    ],
  },
  {
    heading: 'Being proven now',
    sub: 'open questions we are answering before we open up',
    items: [
      'Reminder reliability under real load',
      'Task state staying consistent across surfaces',
      'Whether people can start without hand-holding',
      'Whether the loop stays useful without being annoying',
    ],
  },
  {
    heading: 'Where it goes',
    sub: 'direction, not promises — every one of these can end in "no"',
    direction: true,
    items: [
      'Amigo learns which nudges you actually act on',
      'Timing that adapts to you rather than a fixed clock',
      'Modes you switch on deliberately, never automatically',
      'Surfaces beyond Telegram, only if people ask for them',
    ],
  },
]

export default function HonestyBlock() {
  return (
    <section className="honesty-section" aria-labelledby="honesty-title">
      <Reveal>
        <h2 id="honesty-title" className="section-title">
          Where this actually is
        </h2>
        <p className="honesty-lead">
          Amigo is small and unfinished, and built in the open. Here is the real state of
          it.
        </p>

        <div className="honesty-grid">
          {COLUMNS.map((column) => (
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
          <p>
            Amigo is a non-clinical accountability companion. It is not therapy, diagnosis,
            treatment, or a crisis service, and it is not monitored. If you are in crisis,
            please contact your local emergency services.
          </p>
        </div>
      </Reveal>
    </section>
  )
}
