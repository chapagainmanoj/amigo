/**
 * The contact page.
 *
 * One address and no form. A form would mean a second processor holding whatever people type,
 * disclosed on /privacy/ and contradicting the claim that submitting the waitlist is the only
 * network request the site makes. A mailto costs a click and keeps that claim true.
 *
 * Response times come from decision 03 (one business day for support) and decision 04 (seven
 * calendar days to finish a data request). Nothing here invents a commitment that is not already
 * written down.
 */

import { SITE } from './meta'
import { NON_CLINICAL_NOTE } from './shared'

export const CONTACT_PAGE = {
  title: 'Contact',
  address: SITE.contactEmail,
  lead: (
    <>
      One address, read by a person. No ticket number, no queue, and no bot in front of it — Amigo
      is small enough that you reach whoever built the thing you are writing about.
    </>
  ),
  sections: [
    {
      heading: 'What to write about',
      body: (
        <ul className="legal-list">
          <li>
            Something is broken, or Amigo behaved in a way you did not expect. The more exactly you
            can say what you did and what happened, the better.
          </li>
          <li>
            A question about what Amigo does or does not do. The{' '}
            <a
              href={SITE.capabilityMatrix}
              target="_blank"
              rel="noopener noreferrer"
              className="legal-link"
            >
              capability matrix
            </a>{' '}
            is the longer answer, and it is kept honest.
          </li>
          <li>
            Anything about your data — what we hold, correcting it, deleting it. What we hold and
            why is set out on the{' '}
            <a href="/privacy/" className="legal-link">
              privacy page
            </a>
            .
          </li>
          <li>
            <strong>A security problem.</strong> Please write here first rather than opening a
            public issue, and give us a reasonable chance to fix it before you publish.
          </li>
        </ul>
      ),
    },
    {
      heading: 'When you will hear back',
      body: (
        <ul className="legal-list">
          <li>
            <strong>Anything about your data</strong> — a reply within one business day, and the
            request finished within seven.
          </li>
          <li>
            <strong>Security reports</strong> — as soon as we reasonably can, and we will tell you
            what we did.
          </li>
          <li>
            <strong>Everything else</strong> — read, and answered when there is something useful to
            say. We would rather not publish a response time we cannot keep.
          </li>
        </ul>
      ),
    },
    {
      heading: 'What this is not',
      body: (
        <>
          <p>{NON_CLINICAL_NOTE}</p>
          <p>
            Nobody is watching this address out of hours, and it is not a support line for anything
            urgent. Please do not use it for something that cannot wait.
          </p>
        </>
      ),
    },
    {
      heading: 'Asking to be let in early',
      body: (
        <p>
          It will not work, and we would rather say so than ignore the mail. The first cohort is by
          invitation and small, and it is chosen against written criteria rather than by who asked
          first. The{' '}
          <a href="/#waitlist" className="legal-link">
            waitlist
          </a>{' '}
          is the only route, and joining it is not a place in that cohort — it means one email when
          Amigo opens to everyone.
        </p>
      ),
    },
    {
      heading: 'Code and issues',
      body: (
        <p>
          Amigo is public under {SITE.licence}. Bugs and feature arguments are welcome{' '}
          <a href={SITE.repo} target="_blank" rel="noopener noreferrer" className="legal-link">
            in the open
          </a>{' '}
          — security reports being the one exception above.
        </p>
      ),
    },
  ],
}
