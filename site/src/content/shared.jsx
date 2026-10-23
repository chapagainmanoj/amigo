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
  guide: 'Guide',
  dashboard: 'Sign in',
  // The nav CTA is the narrowest element on the page; the short label takes over on phones.
  cta: 'Start free',
  ctaShort: 'Start',
}

export const FOOTER = {
  copyright: '© 2026 Amigo',
  licence: SITE.licence,
  links: [
    { label: 'Products', href: '/products/' },
    { label: 'Guide', href: '/guide/' },
    { label: 'Dashboard', href: SITE.dashboard },
    { label: 'Privacy', href: '/privacy/' },
    { label: 'Contact', href: '/contact/' },
    { label: 'GitHub', href: SITE.repo, external: true },
    { label: 'Capability matrix', href: SITE.capabilityMatrix, external: true },
  ],
}

/** The primary call to action: signup happens on the dashboard. */
export const START_CTA = {
  primary: 'Start free',
  secondary: 'See how it works',
}

/** Closes both the home page and the modes page. */
export const CLOSING_CTA = {
  title: 'Try it on something you actually need to do.',
  lead: 'The first 30 messages are free. Sign up, connect Telegram, and send the first one.',
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
