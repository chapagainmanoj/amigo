/**
 * Every word on the modes page.
 *
 * Every claim below traces to .scratch/amigo-complete-product/decisions/14-mode-and-adaptation-contract.md
 * and the "Roadmap, not available" column of docs/capability-matrix.md. Daily is the only Mode in
 * the shipped column, so it is the only one written in the present tense. The other three use
 * "would" throughout, on purpose: the contract says a roadmap item must never be described in the
 * present tense, and that each Mode can still end in a documented "do not build".
 */

import { NON_CLINICAL_BOUNDARY } from './shared'

export const MODES_HEADER = {
  titleLead: 'Four modes. One of them',
  titleEmphasis: 'exists',
  lead:
    'Amigo is not meant to stay a reminder bot. The plan is a small set of modes you switch on ' +
    'deliberately, each with its own contract for what it may and may not do. Daily is built and ' +
    'working. The other three are written down, argued over, and unbuilt — and each one can ' +
    'still end in a documented no.',
}

export const MODES = [
  {
    name: 'Daily',
    status: 'Working today',
    shipped: true,
    job: 'Decide, remember, and follow through on what I meant to do today.',
    body:
      'The loop the whole product is built on. You say the thing in passing, Amigo pulls out the ' +
      'task and the time, and the reminder arrives when you asked for it — Done, Skip, or ' +
      'Later, in the chat.',
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
      'Closest to what Amigo already promises, so it is first in line. One program at a time, ' +
      'fourteen days by default, on the days and at the time you choose. Progress is what you ' +
      'report — not a number Amigo infers about you.',
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
      'A short debrief, a decision reflection, or a weekly review. One question at a time, at the ' +
      'depth you choose. What comes out is your summary and your takeaway — Amigo does not ' +
      'score it.',
    can: [
      'Would ask one question at a time, brief or guided as you pick',
      'Would leave you a summary you own',
      'Would turn a takeaway into a Task only through a handoff you confirm',
    ],
    cannot: [
      NON_CLINICAL_BOUNDARY,
      'Would create no mood score, no label, and no emotional profile',
      'Would never become durable memory on its own',
    ],
    gate: 'Cannot begin until the separate non-clinical wellbeing and crisis-resource review is approved.',
  },
  {
    name: 'Recommender',
    status: 'Planned · dormant',
    job:
      'Choose between options in one narrow area, using what I have said I want, with the ' +
      'trade-offs shown.',
    body:
      'One approved area, not everything. The point would be the reasoning you can check — ' +
      'sourced options, stated preferences, trade-offs written out — rather than a ranked ' +
      'list you have to trust.',
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

export const MODE_BOUND_HEADINGS = {
  shipped: { can: 'What it does', cannot: 'Where it stops' },
  planned: { can: 'What it would do', cannot: 'Where it would stop' },
}

export const MODE_RULES = {
  title: 'The rules every mode inherits',
  items: [
    'You turn a mode on. Amigo never moves you into one on its own — automatic routing is excluded from the first release.',
    'One specialised mode at a time, and every new conversation starts back in Daily.',
    'Entering a mode never hides, moves, or edits the Tasks and Reminders you already have.',
    'Ask for an ordinary reminder inside a mode and you get a visible handoff back to Daily that you confirm.',
    'What you do inside one mode does not flow into another, or into anything durable, unless you say so.',
  ],
}

export const GATE_BAND = {
  title: 'How a mode stops being a plan',
  lead:
    'None of the three ship because they sound good. Each passes the same four-stage gate on its ' +
    'own evidence, and none of them has entered it yet.',
  close: (
    <>
      A documented &ldquo;do not build&rdquo; is a valid outcome. We would rather delete a mode
      than ship one that makes the loop worse.
    </>
  ),
}

/**
 * The release gate from decision 14, drawn.
 *
 * Daily is deliberately absent: it is the default workspace, not a specialised Mode, so it never
 * enters this track. All three specialised Modes genuinely sit before stage one — that is the
 * honest picture, and the difference between them is which thing is holding them there.
 */
export const GATE_TRACK = {
  srTitle: 'Current status of each mode against the release gate',
  caption: 'Where the three specialised modes actually are',
  waitingLabel: 'Not started',
  waiting: [
    { name: 'Coach', why: 'Next in line. Waiting on the demand evidence.' },
    { name: 'Reflect', why: 'Blocked by the non-clinical wellbeing review.' },
    { name: 'Recommender', why: 'Dormant until a first narrow area is chosen.' },
  ],
  stages: [
    { n: '1', label: 'Demand evidence', note: 'Three separate people, same recurring problem' },
    {
      n: '2',
      label: 'Contract tests',
      note: 'Tools, data, transitions and retention, enforced in code',
    },
    { n: '3', label: 'Evaluation', note: 'A model evaluation run, then five moderated sessions' },
    { n: '4', label: 'Opt-in trial', note: 'Fourteen days, five participants, one Mode at a time' },
  ],
  foot: (
    <>
      Every stage is passed on a mode&rsquo;s own evidence. Evidence for one never counts for
      another, and any stage can end the branch.
    </>
  ),
}
