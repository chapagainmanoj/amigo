/**
 * Site identity and per-page SEO. The one file that knows what each page is called.
 *
 * Deliberately plain JavaScript with no JSX and no React import: vite.config.js imports this at
 * build time to write the <head> of every entry HTML and to generate sitemap.xml. A JSX import
 * here would break the config, so keep this file to strings.
 *
 * Adding a page means adding an entry here, a rollup input in vite.config.js, and the HTML file.
 * Miss this file and the build fails loudly rather than shipping a page with no title.
 */

export const SITE = {
  name: 'Amigo',
  // Absolute, because og:image and og:url must be: Slack, Twitter and Facebook do not resolve
  // relative paths, and a relative og:image is silently dropped rather than reported.
  origin: 'https://amigo.manojc.link',
  themeColor: '#FBF8F2',
  locale: 'en',
  contactEmail: 'amigo@manojc.link',
  repo: 'https://github.com/chapagainmanoj/amigo',
  capabilityMatrix:
    'https://github.com/chapagainmanoj/amigo/blob/develop/docs/capability-matrix.md',
  licence: 'AGPL-3.0',
}

/**
 * One entry per page.
 *
 * `title` is the browser tab and the search result. `description` is the search snippet, so it is
 * written to be read on its own. `social` overrides title/description for link previews, where
 * the reader has no search query for context and a sharper line wins; omit it to reuse both.
 */
export const PAGES = {
  home: {
    path: '/',
    html: 'index.html',
    title: 'Amigo — Accountability that lives in your chat',
    description:
      'Most task apps are abandoned in a month. Amigo lives in Telegram: tell it what you ' +
      'need to do, and it asks you once, when you said to.',
    image: '/og.png',
    imageAlt: 'Amigo — accountability that lives in your chat',
  },
  products: {
    path: '/products/',
    html: 'products/index.html',
    title: 'Modes — Amigo',
    description:
      'Amigo is built around Modes you switch on yourself. Daily is the one that works today. ' +
      'Coach, Reflect and Recommender are planned, and each one can still end in no.',
    image: '/og-products.png',
    imageAlt: 'Amigo modes — four modes, one of them exists',
    social: {
      description:
        'Four modes. One of them exists. Here is what each one is for, and what each still ' +
        'has to prove.',
    },
  },
  privacy: {
    path: '/privacy/',
    html: 'privacy/index.html',
    title: 'Privacy — Amigo',
    description:
      'What the Amigo website collects: an email address, if you give us one. No cookies, ' +
      'no analytics, no third-party scripts.',
    image: '/og.png',
    imageAlt: 'Amigo — accountability that lives in your chat',
  },
}

export const absolute = (path) => new URL(path, SITE.origin).href
