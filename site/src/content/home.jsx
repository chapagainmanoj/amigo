/**
 * Every word on the home page, in the order the page says it.
 *
 * Section 5 of docs/landing-page-spec.md is the source for this copy, and
 * docs/capability-matrix.md governs what may be claimed: a roadmap item is never written in the
 * present tense. Check a change against both before shipping it.
 */

import { SITE } from './meta'
import { NON_CLINICAL_NOTE, RETENTION_PROMISE } from './shared'

export const HERO = {
  kicker: 'Invitation-only · Not yet open',
  // Split across two lines at a chosen point rather than wherever the column happens to break.
  titleLead: 'Most task apps are',
  titleRest: 'abandoned in a',
  titleEmphasis: 'month',
  lead:
    'Not because people stop caring. Because the app is one more thing to open, groom, and ' +
    'feel guilty about. Amigo doesn’t ask you to open anything.',
  micro: 'No newsletter, no launch countdown. One message when there is something real to try.',
}

// Two facts about the market, then the answer. The third cell breaks the pattern on purpose: it
// is the only one about Amigo, and the only one that carries --signal-deep.
export const STATS = [
  { value: 52, suffix: '%', caption: 'abandon their habit app within the first month' },
  { value: 70, suffix: '%', caption: 'quit lifestyle and wellbeing apps inside 100 days' },
  { value: 0, suffix: '', caption: 'new apps Amigo asks you to install', answer: true },
]

/**
 * The Telegram demo. One set of lines, rendered twice: as the animated bubbles and as the
 * visually-hidden transcript a screen reader gets. They cannot drift because they are the same
 * strings.
 */
export const DEMO = {
  heading: 'It lives in a chat you already have open.',
  text:
    'One sentence in, one reminder out, three buttons to close it. Nothing to install, nothing ' +
    'to organise, nothing to abandon.',
  bot: { avatar: 'A', name: 'Amigo', status: 'bot' },
  buttons: ['Done', 'Skip', 'Later'],
  pressed: 'Done',
  lines: {
    userAsk: { text: 'I need to send the proposal at 3 PM. Remind me then.', time: '2:14 PM' },
    botConfirm: {
      text: 'Got it — “Send the proposal”. I’ll remind you at 3:00 PM.',
      time: '2:14 PM',
    },
    divider: '3:00 PM',
    reminder: { text: 'Send the proposal', time: '3:00 PM' },
    botDone: { text: 'Nice. Marked done.', time: '3:01 PM' },
  },
  transcriptLabel: 'Telegram interaction demo transcript',
}

export const HOW_IT_WORKS = {
  title: 'How it works',
  steps: [
    {
      num: '01',
      title: 'Say it in passing',
      body:
        'Type the thing you need to do the way you’d say it to a friend. Amigo pulls out ' +
        'the task and the time.',
    },
    {
      num: '02',
      title: 'Get asked, once',
      body:
        'A reminder arrives in Telegram when you said you wanted it. Not a badge you’ll ' +
        'swipe away — a message you’ll actually read.',
    },
    {
      num: '03',
      title: 'Close it in one tap',
      body: 'Done, Skip, or Later. The dashboard keeps the record if you ever want to look.',
    },
  ],
}

export const WEDGE = {
  title: 'Every other tool adds a surface. This one removes it.',
  body: (
    <>
      <p>
        Focusmate books you a stranger. Finch gives you a pet. The new wave of AI companions gives
        you another chat window to remember. All of them assume you will come back to an app you
        have already stopped opening.
      </p>
      <p>
        <strong>
          Amigo starts in Telegram, where you already are — and the only time it appears is the
          moment you asked it to.
        </strong>{' '}
        No streaks to protect, no counter resetting to zero, nothing to feel bad about on the days
        you skip.
      </p>
    </>
  ),
}

/**
 * The wedge, drawn: a whole waking day, and the only marks on it are the moments you asked for.
 * The times are illustrative — a day someone might have asked for — not measured data.
 */
export const DAY_LINE = {
  start: 7,
  end: 23,
  hours: [7, 11, 15, 19, 23],
  marks: [
    { at: 9, label: '9:00 AM' },
    { at: 14.5, label: '2:30 PM' },
    { at: 18.75, label: '6:45 PM' },
  ],
  caption:
    'One waking day. The three marks are reminders someone asked for — and they are ' +
    'Amigo’s entire presence in it. There is nothing else to open, and nothing accumulating ' +
    'while you are away.',
}

/**
 * Column 1 maps one-to-one to the "Shipped in the current prototype" column of
 * docs/capability-matrix.md. Column 3 is direction, never a promise: no dates, no present tense,
 * and the disclaimer is the column heading rather than a footnote.
 */
export const HONESTY = {
  title: 'Where this actually is',
  lead: 'Amigo is small and unfinished, and built in the open. Here is the real state of it.',
  columns: [
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
  ],
  boundary: NON_CLINICAL_NOTE,
}

// The page's single inversion. Written for the reader who is evaluating whether this is worth
// building, and readable by everyone else. Nothing here is claimed as shipped.
export const WHY = {
  title: 'Why this is worth building',
  body: (
    <>
      <p>
        Every accountability tool eventually learns the same thing: the hard part was never the
        list. It was the moment — the right question, asked while a person can still act on it.
      </p>
      <p>
        <strong>That moment is the only thing Amigo does.</strong> Each reminder that gets a Done,
        a Skip, or a Later is a small, specific fact about when this person can actually follow
        through — and that is the thing no task app has ever been positioned to learn, because
        nobody opens a task app at the moment of truth.
      </p>
      <p>
        We are building the boring parts first: delivery that doesn&rsquo;t drop, state that stays
        consistent across surfaces, and a bar for not being annoying. Then the interesting part
        gets a chance to be real.
      </p>
    </>
  ),
}

export const OPEN_SOURCE = {
  title: 'Built in the open',
  body: (
    <>
      Amigo&rsquo;s source and its full capability matrix are public under {SITE.licence}. If a
      claim on this page isn&rsquo;t backed by code, you can go and check.
    </>
  ),
  links: [
    { label: 'Read the source →', href: SITE.repo },
    { label: 'See the capability matrix →', href: SITE.capabilityMatrix },
  ],
}

export const FAQ = {
  title: 'Questions & answers',
  items: [
    {
      q: 'When does it open?',
      a: (
        <>
          We don&rsquo;t have a date, and we&rsquo;re not going to invent one. Security, reminder
          reliability, and privacy work come first. You&rsquo;ll get one email when there&rsquo;s
          something real to try.
        </>
      ),
    },
    {
      q: 'Why Telegram?',
      a: (
        <>
          Because you&rsquo;re already in it. A reminder in a chat you check beats a notification
          from an app you&rsquo;ve muted. Other channels are possible later; none are promised.
        </>
      ),
    },
    {
      q: 'What will it cost?',
      a: (
        <>
          Nothing during the invitation beta. Beyond that we&rsquo;re testing a hypothesis of about
          US$9 per month. That&rsquo;s research, not a price list.
        </>
      ),
    },
    {
      q: 'What do you do with my email?',
      a: (
        <>
          Store it to send you one message when Amigo opens, and nothing else. No newsletter, no
          sharing, no advertising. You can unsubscribe or ask us to delete it at any time.{' '}
          {RETENTION_PROMISE}{' '}
          <a href="/privacy/" className="faq-link">
            The full notice
          </a>{' '}
          covers the rest.
        </>
      ),
    },
    {
      q: 'Who is it for?',
      a: (
        <>
          Adults who keep abandoning task apps and would rather just say what they need to do.
          It&rsquo;s not built for safety-critical reminders like medication or medical
          appointments.
        </>
      ),
    },
    {
      q: 'Can I self-host it?',
      a: (
        <>
          The licence allows it. Supported self-hosting isn&rsquo;t something we promise yet.
        </>
      ),
    },
  ],
}
