import Reveal from './Reveal'

// Every claim below traces to .scratch/amigo-complete-product/decisions/14-mode-and-adaptation-contract.md
// and the "Roadmap, not available" column of docs/capability-matrix.md. Daily is the only Mode in
// the shipped column, so it is the only one written in the present tense. The other three use
// "would" throughout, on purpose: the contract says a roadmap item must never be described in the
// present tense, and that each Mode can still end in a documented "do not build".
const MODES = [
  {
    name: 'Daily',
    status: 'Working today',
    shipped: true,
    job: 'Decide, remember, and follow through on what I meant to do today.',
    body:
      'The loop the whole product is built on. You say the thing in passing, Amigo pulls out the task and the time, and the reminder arrives when you asked for it — Done, Skip, or Later, in the chat.',
    can: [
      'Creates Tasks from what you type',
      'Schedules the Reminders you ask for',
      'Closes them with Done, Skip, or Later',
    ],
    cannot: [
      'Does not start conversations you did not ask for',
      'Does not keep a durable profile of you',
    ],
  },
  {
    name: 'Coach',
    status: 'Planned · next candidate',
    job: 'Pursue one goal I picked, with a plan, a check-in rhythm I set, and an honest review.',
    body:
      'Closest to what Amigo already promises, so it is first in line. One program at a time, fourteen days by default, on the days and at the time you choose. Progress is what you report — not a number Amigo infers about you.',
    can: [
      'Would hold one program: goal, cadence, check-ins, progress',
      'Would cap itself at one message a day, inside your quiet hours',
      'Would run a weekly review: continue, adjust, pause, or stop',
    ],
    cannot: [
      'Would not create ordinary Tasks or Reminders without handing back to Daily first',
      'Would make no expert claim, and use no guilt or streak-loss pressure',
    ],
    gate: 'Needs three separate people to show the same recurring problem before design starts.',
  },
  {
    name: 'Reflect',
    status: 'Planned · blocked',
    job: 'Look back at something privately, work out my own takeaway, and maybe pick a next step.',
    body:
      'A short debrief, a decision reflection, or a weekly review. One question at a time, at the depth you choose. What comes out is your summary and your takeaway — Amigo does not score it.',
    can: [
      'Would ask one question at a time, brief or guided as you pick',
      'Would leave you a summary you own',
      'Would turn a takeaway into a Task only through a handoff you confirm',
    ],
    cannot: [
      'Amigo is a non-clinical accountability companion. It is not therapy, diagnosis, treatment, or a crisis service.',
      'Would create no mood score, no label, and no emotional profile',
      'Would never become durable memory on its own',
    ],
    gate: 'Cannot begin until the separate non-clinical wellbeing and crisis-resource review is approved.',
  },
  {
    name: 'Recommender',
    status: 'Planned · dormant',
    job: 'Choose between options in one narrow area, using what I have said I want, with the trade-offs shown.',
    body:
      'One approved area, not everything. The point would be the reasoning you can check — sourced options, stated preferences, trade-offs written out — rather than a ranked list you have to trust.',
    can: [
      'Would read the preferences you stated and sourced option data',
      'Would show its trade-offs and where each option came from',
    ],
    cannot: [
      'Would not buy, book, contact, or transact on your behalf',
      'A general-purpose recommender is excluded outright',
    ],
    gate: 'Dormant until real evidence picks the first narrow area and a data source is approved.',
  },
]

function ModeRow({ mode }) {
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
            <h3 className="mode-bound-heading">
              {mode.shipped ? 'What it does' : 'What it would do'}
            </h3>
            <ul className="mode-listing">
              {mode.can.map((item) => (
                <li key={item} className="mode-listing-item">
                  {item}
                </li>
              ))}
            </ul>
          </div>
          <div className="mode-bound">
            <h3 className="mode-bound-heading">
              {mode.shipped ? 'Where it stops' : 'Where it would stop'}
            </h3>
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
