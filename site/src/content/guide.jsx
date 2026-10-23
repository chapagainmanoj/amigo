/**
 * The how-to-use guide: what a first-time participant does, in order, and nothing Amigo cannot
 * do today. The bot's /help command links here, so keep the commands in step with src/access.py.
 *
 * Trial numbers mirror TRIAL_MESSAGE_LIMIT's default. Change both together.
 */

import { SITE } from './meta'
import { NON_CLINICAL_NOTE } from './shared'

const Say = ({ children }) => <code className="guide-say">{children}</code>

export const GUIDE_PAGE = {
  title: 'How to use Amigo',
  lead: (
    <>
      Amigo lives in Telegram. You tell it what you mean to do, and it asks you about it once, at
      the time you chose. Setup takes about five minutes.
    </>
  ),
  sections: [
    {
      id: 'account',
      heading: '1. Create your account',
      body: (
        <ul className="legal-list">
          <li>Open the Amigo dashboard and sign up with your email address.</li>
          <li>Confirm the email Amigo sends you, then sign in.</li>
          <li>Read and accept the beta limits.</li>
          <li>
            Fill in your name and timezone. Amigo uses your timezone for every Reminder, so check it
            is right.
          </li>
        </ul>
      ),
    },
    {
      id: 'telegram',
      heading: '2. Connect Telegram',
      body: (
        <ul className="legal-list">
          <li>
            On the dashboard, choose <strong>Connect Telegram</strong>, then{' '}
            <strong>Open Telegram</strong>. It opens Amigo with a one-time pairing link; tap{' '}
            <strong>Start</strong>.
          </li>
          <li>
            Amigo sends a private test Reminder. Answer it with Done, Skip or Later, and setup is
            complete once the dashboard shows your answer.
          </li>
          <li>
            Pairing links expire after a short while. If yours has, go back to the dashboard and
            make a new one.
          </li>
        </ul>
      ),
    },
    {
      id: 'daily',
      heading: '3. Your first messages',
      body: (
        <>
          <p>
            You start in <strong>Daily</strong>. Write the way you would to a friend; there is no
            special syntax.
          </p>
          <ul className="legal-list">
            <li><Say>remind me to call mom at 6</Say> — a Task plus a Reminder at 6 pm.</li>
            <li><Say>I need to finish the report and pay rent today</Say> — two Tasks.</li>
            <li><Say>what&rsquo;s on today?</Say> — today&rsquo;s Tasks.</li>
            <li><Say>move the report to tomorrow</Say> — changes a Task&rsquo;s day.</li>
            <li><Say>done with rent</Say> — marks it done.</li>
          </ul>
          <p>
            Amigo only sets the Reminders you ask for. If something is unclear, such as a time, it
            asks rather than guessing.
          </p>
        </>
      ),
    },
    {
      id: 'reminders',
      heading: '4. When a Reminder arrives',
      body: (
        <ul className="legal-list">
          <li><strong>Done</strong> — marks the Task done.</li>
          <li><strong>Later</strong> — asks again later.</li>
          <li><strong>Skip</strong> — lets it go for today, no questions.</li>
        </ul>
      ),
    },
    {
      id: 'modes',
      heading: '5. Modes',
      body: (
        <>
          <p>
            A Mode is a focused way of working with Amigo. Daily is the default. Send{' '}
            <Say>/mode</Say> to see the Modes open to you, <Say>/mode coach</Say> to switch, and{' '}
            <Say>/daily</Say> to come back.
          </p>
          <ul className="legal-list">
            <li><strong>Daily</strong> — Tasks and Reminders for today.</li>
            <li>
              <strong>Coach</strong> — one goal or habit you choose, a plan you approve, and
              check-ins on the days you pick.
            </li>
            <li>
              <strong>Reflect</strong> and <strong>Recommender</strong> — available with full
              access.
            </li>
          </ul>
        </>
      ),
    },
    {
      id: 'coach',
      heading: '6. Starting Coach',
      body: (
        <ul className="legal-list">
          <li>
            Send <Say>/mode coach</Say>. The first time, Amigo shows how Coach handles your data;
            tap <strong>I agree</strong> if you are happy with it.
          </li>
          <li>
            Say what you want to work on, for example{' '}
            <Say>I want to walk 20 minutes most days</Say>.
          </li>
          <li>
            Coach asks how you will measure it and which days to check in, then shows a draft plan.
          </li>
          <li>
            Nothing starts until you tap <strong>Approve</strong>. Send <Say>/program</Say> any time
            to see, pause or stop your plan.
          </li>
        </ul>
      ),
    },
    {
      id: 'trial',
      heading: '7. Your trial and full access',
      body: (
        <>
          <p>
            New accounts get a free trial of <strong>30 messages</strong> across Daily and Coach.
            The dashboard shows how many you have used. Commands such as <Say>/help</Say> and
            Reminder buttons do not count.
          </p>
          <p>
            When the trial ends, Amigo tells you and gives you a reference number. To continue,{' '}
            <a href="/contact/" className="legal-link">contact us</a> at{' '}
            <a href={`mailto:${SITE.contactEmail}`} className="legal-link">{SITE.contactEmail}</a>{' '}
            and include that reference. Full access opens every Mode with no message limit.
          </p>
        </>
      ),
    },
    {
      id: 'limits',
      heading: '8. Limits and safety',
      body: (
        <>
          <p>{NON_CLINICAL_NOTE}</p>
          <p>
            Amigo is experimental and can make mistakes; check anything important. It does not act
            outside the chat: no purchases, bookings or messages to other people. What happens to
            your data is on the{' '}
            <a href="/privacy/" className="legal-link">privacy page</a>.
          </p>
        </>
      ),
    },
    {
      id: 'commands',
      heading: '9. Commands',
      body: (
        <ul className="legal-list">
          <li><Say>/help</Say> — this list and a link to the guide.</li>
          <li><Say>/mode</Say> — see and switch Modes.</li>
          <li><Say>/daily</Say> — back to Daily.</li>
          <li><Say>/program</Say> — your Coach plan.</li>
          <li><Say>/memory</Say> — what Amigo has saved, and how to pause or clear it.</li>
          <li><Say>/feedback</Say> followed by your note — tell us something.</li>
        </ul>
      ),
    },
  ],
}
