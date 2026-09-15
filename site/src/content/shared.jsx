/**
 * Copy that appears on more than one page, and the few sentences that have to match word for
 * word wherever they appear.
 *
 * A promise written twice is a promise that will eventually be two different promises. Anything
 * stated in two places — the retention rule, the non-clinical boundary — lives here once and is
 * quoted everywhere else. tests/test_privacy_page.py enforces that for the ones that are
 * commitments rather than decoration.
 *
 * Rich prose keeps its JSX rather than being flattened into strings: emphasis and links are part
 * of the copy, not of the layout, and a mini markup language to avoid a fragment would be worse
 * than the fragment.
 */

import { SITE } from './meta'

export const NAV = {
  wordmarkLabel: 'Amigo home',
  products: 'Products',
  // The nav CTA is the narrowest element on the page; the short label takes over on phones.
  cta: 'Join the waitlist',
  ctaShort: 'Waitlist',
}

export const FOOTER = {
  copyright: '© 2026 Amigo',
  licence: SITE.licence,
  links: [
    { label: 'Products', href: '/products/' },
    { label: 'Privacy', href: '/privacy/' },
    { label: 'GitHub', href: SITE.repo, external: true },
    { label: 'Capability matrix', href: SITE.capabilityMatrix, external: true },
  ],
}

/** The waitlist form, in every state it can be in. */
export const WAITLIST = {
  emailLabel: 'Email address',
  emailPlaceholder: 'you@example.com',
  submit: 'Join the waitlist',
  submitting: 'Sending',
  consent: 'Email me once, when Amigo opens.',
  // The notice belongs where consent is given, not only in the footer: this is the point at
  // which someone hands over an address.
  consentLink: { label: 'What we do with it', href: '/privacy/' },
  success: (
    <>
      Check your inbox. Click the link in the confirmation email and you&rsquo;re on the list.
    </>
  ),
  errors: {
    consent: 'Please tick the box so we know you want the email.',
    email: 'Please enter a valid email address.',
    // Deliberately the same line for every failure the network can produce. A visitor cannot act
    // on a status code, and a provider's own error text would leak whether an address is known.
    network: 'That didn\u2019t go through \u2014 try again in a moment.',
    unconfigured: 'Waitlist signup isn\u2019t configured yet.',
  },
  unconfigured: (
    <>
      We are not running open enrollment yet. You can track milestones and releases on{' '}
      <a href={SITE.repo} target="_blank" rel="noopener noreferrer" className="waitlist-fallback-link">
        GitHub
      </a>
      .
    </>
  ),
  previewNote:
    'Dev preview — no endpoint set, so nothing is sent. Add VITE_WAITLIST_ENDPOINT to site/.env ' +
    'to post for real.',
}

/** Closes both the home page and the modes page. */
export const CLOSING_CTA = {
  title: 'One message, when there is something to try.',
  lead: 'No newsletter, no countdowns. We will not email you again until Amigo opens.',
}

/**
 * Decision 15's non-clinical boundary. Stated on the home page and again against Reflect, the
 * mode closest to the line. The wording is the contract's, not ours to improvise.
 */
// Kept on one unbroken line on purpose. tests/test_landing_page.py exempts this exact sentence
// from its forbidden-claims scan, and a string split across a concatenation is no longer that
// sentence, so the scan would read its clinical words as an unshipped claim.
const BOUNDARY_CLAUSE = 'Amigo is a non-clinical accountability companion. It is not therapy, diagnosis, treatment, or a crisis service'

/** The boundary on its own, for a list of limits. */
export const NON_CLINICAL_BOUNDARY = `${BOUNDARY_CLAUSE}.`

/** The boundary plus the crisis routing, for the standing note on the home page. */
export const NON_CLINICAL_NOTE =
  `${BOUNDARY_CLAUSE}, and it is not monitored. If you are in crisis, please contact your ` +
  'local emergency services.'

/**
 * What happens to an address that never confirms. Said on the privacy page and quoted in the FAQ;
 * tests/test_privacy_page.py fails if the two drift apart.
 */
export const RETENTION_PROMISE =
  'An address that never confirms is never emailed, and is deleted when the announcement goes out.'
