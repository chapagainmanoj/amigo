/**
 * The privacy notice, in full.
 *
 * Scope is deliberately this website only. Decision 04 is the contract for the beta itself, and
 * publishing it here as though it were live policy would misdescribe a product nobody can use
 * yet. What this page says has to be true of the code in site/ today — tests/test_privacy_page.py
 * checks the parts that can be checked mechanically.
 */

import { SITE } from './meta'
import { RETENTION_PROMISE } from './shared'

/**
 * The email provider has not been chosen yet. Until it is, this page says so rather than naming a
 * placeholder — decision 04 requires every processor to be disclosed, and an address cannot be
 * collected before the disclosure is true. tests/test_privacy_page.py holds the two in step:
 * naming a provider here is what unblocks the waitlist going live.
 */
export const WAITLIST_PROCESSOR = null

const CONTACT = SITE.contactEmail

const ContactLink = () => (
  <a href={`mailto:${CONTACT}`} className="legal-link">
    {CONTACT}
  </a>
)

export const PRIVACY = {
  title: 'Privacy',
  effective: '15 September 2026',
  lead: (
    <>
      This page covers what <strong>this website</strong> collects, which today is one thing: an
      email address, if you choose to give us one. Amigo itself is not open yet. When it is, a
      fuller notice covering the Telegram bot and the dashboard will be published before anyone can
      use them.
    </>
  ),
  sections: [
    {
      heading: 'What we collect',
      body: (
        <>
          <p>Only what you type into the waitlist form, and only if you tick the consent box:</p>
          <ul className="legal-list">
            <li>Your email address.</li>
            <li>
              The date you signed up. That date is the record of your consent: the form does not
              submit without the box ticked, and no announcement is sent until you click the link
              in the confirmation email.
            </li>
            <li>
              Whatever our email provider records alongside it — normally an IP address and a
              timestamp, kept to stop the form being abused.
            </li>
          </ul>
        </>
      ),
    },
    {
      heading: 'What we do not collect',
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
            <li>
              <strong>No advertising, no data sharing, no selling.</strong> Not now and not later.
            </li>
          </ul>
          <p>
            Submitting the waitlist form is the only network request this page makes. You do not
            have to take our word for it — the source is public under {SITE.licence}.
          </p>
        </>
      ),
    },
    {
      heading: 'Why we hold your address',
      body: (
        <p>
          To send you one message, when Amigo opens. That is the entire purpose. There is no
          newsletter, no launch sequence and no drip campaign, and we will not use your address for
          anything we have not described here without asking you first.
        </p>
      ),
    },
    {
      heading: 'Who else processes it',
      body: (
        <>
          <ul className="legal-list">
            <li>
              <strong>Render</strong> — hosts this site and keeps standard server logs of requests
              to it.
            </li>
            <li>
              {WAITLIST_PROCESSOR ? (
                <>
                  <strong>{WAITLIST_PROCESSOR}</strong> — stores the waitlist and sends the
                  confirmation and announcement emails.
                </>
              ) : (
                <>
                  <strong>An email provider, not yet chosen.</strong> We will name it here before
                  the form accepts a single address.
                </>
              )}
            </li>
          </ul>
          <p>
            Each one receives only what it needs to do its job. Your data may be stored or processed
            outside your country; we do not promise otherwise.
          </p>
        </>
      ),
    },
    {
      heading: 'How long we keep it',
      body: (
        <p>
          Until you unsubscribe, until you ask us to delete it, or until the announcement has been
          sent and the list is closed — whichever comes first. {RETENTION_PROMISE}
        </p>
      ),
    },
    {
      heading: 'What you can ask for',
      body: (
        <>
          <p>
            Every email carries an unsubscribe link. Beyond that, write to <ContactLink /> and ask
            us to tell you what we hold, correct it, or delete it. We reply within one business day
            and finish within seven, and we will not ask you why.
          </p>
          <p>
            If you are in the UK or the EU, the GDPR gives you those rights explicitly, along with
            the right to object to processing, to receive your data in a portable form, and to
            complain to your data protection authority. We rely on your consent, which you gave by
            ticking the box and can withdraw at any time.
          </p>
        </>
      ),
    },
    {
      heading: 'Age',
      body: <p>Amigo is for adults. Please do not join the waitlist if you are under 18.</p>,
    },
    {
      heading: 'Changes',
      body: (
        <p>
          If this page changes materially while your address is on the list, we will tell you rather
          than quietly editing it. The effective date above is how you check.
        </p>
      ),
    },
    {
      heading: 'Contact',
      body: (
        <p>
          <ContactLink />
        </p>
      ),
    },
  ],
}
