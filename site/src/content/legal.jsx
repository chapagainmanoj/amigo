/**
 * The privacy notice, in full: this website, the Telegram bot and the dashboard.
 *
 * Every commitment below comes from decision 04 (beta privacy and retention) and has to be true
 * of the code today. tests/test_privacy_page.py checks the parts that can be checked
 * mechanically. A material change to processors, purposes or retention needs a new effective
 * date and a matching bump of ACTIVATION_POLICY_VERSION, so participants acknowledge it again.
 */

import { SITE } from './meta'
import { NON_CLINICAL_NOTE, RETENTION_PROMISE } from './shared'

/**
 * The provider that holds the list. Decision 04 requires every processor to be disclosed before
 * it receives anything, so this is named here before the form accepts an address rather than
 * after. tests/test_privacy_page.py holds the two in step: setting this back to null while an
 * endpoint ships is what the guard catches.
 */
export const WAITLIST_PROCESSOR = 'Loops'

const CONTACT = SITE.contactEmail

const ContactLink = () => (
  <a href={`mailto:${CONTACT}`} className="legal-link">
    {CONTACT}
  </a>
)

export const PRIVACY = {
  title: 'Privacy',
  effective: '23 October 2026',
  lead: (
    <>
      This notice covers <strong>the Amigo Telegram bot</strong>, <strong>the dashboard</strong>,
      and <strong>this website</strong>. Amigo is a small, experimental accountability companion
      run by its founder. It is for adults (18 and over). Questions go to <ContactLink />.
    </>
  ),
  sections: [
    {
      heading: 'What we collect when you use Amigo',
      body: (
        <ul className="legal-list">
          <li>
            <strong>Your dashboard account</strong> — email address, sign-in identifiers, and when
            you signed up and signed in.
          </li>
          <li>
            <strong>Telegram</strong> — your chat ID and whether your account is paired. We do not
            see your Telegram contacts.
          </li>
          <li>
            <strong>Your profile</strong> — preferred name, timezone and quiet hours.
          </li>
          <li>
            <strong>Conversations and plans</strong> — the messages you send and Amigo&rsquo;s
            replies, your Tasks and Reminders and whether you marked them Done, Skip or Later, and
            short Session summaries.
          </li>
          <li>
            <strong>Coach</strong>, only if you agree to it — your goal, how you measure it, your
            check-in days, your check-ins and the plan&rsquo;s history.
          </li>
          <li>
            <strong>Saved Memory</strong>, only if you turn it on and confirm each item.
          </li>
          <li>
            <strong>Feedback</strong> you send with /feedback.
          </li>
          <li>
            <strong>Operational records</strong> — delivery times, model usage and cost, errors
            with message content removed, security and audit events, and how many trial messages
            you have used.
          </li>
        </ul>
      ),
    },
    {
      heading: 'What we do not collect',
      body: (
        <>
          <p>
            No contacts, precise location, payment details, government IDs, photos, audio, files
            or medical records. Amigo does not infer diagnoses, mood scores or health profiles.
          </p>
          <p>
            Please do not send Amigo medical, financial, identity or emergency information. It does
            not need it to work.
          </p>
        </>
      ),
    },
    {
      heading: 'What we use it for',
      body: (
        <>
          <ul className="legal-list">
            <li>Signing you in and pairing Telegram.</li>
            <li>Running your conversations, Tasks, Reminders, Modes and the dashboard.</li>
            <li>Support, and exporting or deleting your data when you ask.</li>
            <li>Security and preventing abuse.</li>
            <li>
              Measuring reliability, cost and how the beta is going, in privacy-minimised and
              aggregate form.
            </li>
          </ul>
          <p>
            We do not sell your data, advertise with it, build profiles of you for anything else,
            train a general AI model on your content, or publish anything that identifies you. Using
            your data for a new purpose needs your fresh consent.
          </p>
        </>
      ),
    },
    {
      heading: 'AI processing',
      body: (
        <p>
          To write a reply, Amigo sends your message and the context it needs — such as today&rsquo;s
          Tasks — to Google&rsquo;s Gemini API. We use Google&rsquo;s paid API, under terms that do
          not let Google use that content to improve its products. No other AI provider processes
          your content. Message content is kept out of our routine logs and analytics.
        </p>
      ),
    },
    {
      heading: 'Who else processes it',
      body: (
        <>
          <ul className="legal-list">
            <li>
              <strong>Telegram</strong> — carries messages and buttons between you and Amigo.
            </li>
            <li>
              <strong>Supabase</strong> — accounts, the database and its backups.
            </li>
            <li>
              <strong>Google</strong> — Gemini AI processing, as above.
            </li>
            <li>
              <strong>Render</strong> — hosts Amigo, the dashboard and this site, and keeps standard
              server logs.
            </li>
            <li>
              {WAITLIST_PROCESSOR ? (
                <>
                  <strong>{WAITLIST_PROCESSOR}</strong> — only if you join the waitlist: stores your
                  address and sends the confirmation and announcement emails.
                </>
              ) : (
                <>
                  <strong>An email provider, not yet chosen.</strong> We will name it here before
                  the waitlist form accepts a single address.
                </>
              )}
            </li>
          </ul>
          <p>
            Each one receives only what it needs for its job. Your data may be stored or processed
            outside your country; we do not promise otherwise.
          </p>
        </>
      ),
    },
    {
      heading: 'How long we keep it',
      body: (
        <ul className="legal-list">
          <li>Pairing links expire after 15 minutes; used or expired ones are purged within 7 days.</li>
          <li>
            Your profile, messages, Tasks, Reminders and Sessions are kept while you use Amigo and
            deleted within 30 days after you leave.
          </li>
          <li>Error logs, with content removed: 30 days.</li>
          <li>Security and audit events, and usage records that identify you: 90 days.</li>
          <li>Totals that contain no content and identify nobody: up to 12 months.</li>
          <li>A minimal record that a deletion happened, with no content: 12 months.</li>
          <li>Backups age out within 30 days, and a restore reapplies completed deletions.</li>
          <li>
            The waitlist: until you unsubscribe, ask us to delete your address, or the announcement
            has gone out. {RETENTION_PROMISE}
          </li>
        </ul>
      ),
    },
    {
      heading: 'What you can ask for',
      body: (
        <>
          <p>
            Write to <ContactLink /> to see, export, correct or delete your data. We reply within
            one business day and finish within seven, and we will not ask you why. Coach and saved
            Memory also have their own export and delete controls on the dashboard.
          </p>
          <p>
            Deleting your account stops new messages, cancels your Reminders and unlinks Telegram.
            It cannot remove copies that Telegram or your email provider keep on their own.
          </p>
          <p>
            If you are in the UK or the EU, the GDPR gives you those rights explicitly, along with
            the right to object to processing, to receive your data in a portable form, and to
            complain to your data protection authority.
          </p>
        </>
      ),
    },
    {
      heading: 'Why we are allowed to',
      body: (
        <p>
          Running Amigo needs the processing above; you acknowledge it when you sign up, and Amigo
          cannot work without it. Coach, saved Memory and the waitlist each rely on a separate
          consent you can withdraw at any time. Withdrawing stops future processing, except what we
          need to finish a deletion, prevent fraud, or meet a genuine legal obligation.
        </p>
      ),
    },
    {
      heading: 'Free trial and full access',
      body: (
        <p>
          New accounts get a trial of 30 messages. We count them; we do not read them to do so. If
          you write to us for full access, we use the reference you send — your Telegram chat ID —
          only to find and upgrade your account.
        </p>
      ),
    },
    {
      heading: 'Not a crisis service',
      body: <p>{NON_CLINICAL_NOTE}</p>,
    },
    {
      heading: 'If something goes wrong',
      body: (
        <p>
          If we suspect your data has been exposed, we pause the affected part of Amigo, start
          looking into it within 24 hours, and tell you without unreasonable delay once we know it
          matters: what happened, what data, what we did, and what you can do.
        </p>
      ),
    },
    {
      heading: 'This website',
      body: (
        <>
          <ul className="legal-list">
            <li>
              <strong>No cookies.</strong> This site sets none at all.
            </li>
            <li>
              <strong>No analytics and no tracking pixels.</strong> We do not know how many people
              visit this page, and we have decided we do not need to.
            </li>
            <li>
              <strong>No third-party scripts.</strong> Fonts are served from this domain, not from
              a font network.
            </li>
          </ul>
          <p>
            Submitting the waitlist form is the only network request this site makes, and only
            with the consent box ticked. You do not have to take our word for it — the source is
            public under {SITE.licence}.
          </p>
        </>
      ),
    },
    {
      heading: 'Age',
      body: <p>Amigo is for adults. Please do not sign up or join the waitlist if you are under 18.</p>,
    },
    {
      heading: 'Changes',
      body: (
        <p>
          If this notice changes materially, we change the effective date above and ask you to
          acknowledge the new version on the dashboard before you carry on using Amigo. Waitlist
          members are told by email rather than by a quiet edit.
        </p>
      ),
    },
    {
      heading: 'Contact',
      body: (
        <p>
          <ContactLink /> reaches us, and{' '}
          <a href="/contact/" className="legal-link">
            the contact page
          </a>{' '}
          says what else that address is and is not for.
        </p>
      ),
    },
  ],
}
