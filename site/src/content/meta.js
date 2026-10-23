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
  // Where participants sign up, pair Telegram and see their Tasks.
  dashboard: 'https://amigo-dashboard.onrender.com/',
  signup: 'https://amigo-dashboard.onrender.com/?signup',
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
      'Amigo is built around Modes you switch on yourself. Daily and Coach work today. ' +
      'Reflect and Recommender are planned, and each one can still end in no.',
    image: '/og-products.png',
    imageAlt: 'Amigo modes — four modes, one of them exists',
    social: {
      description:
        'Four modes. Two of them exist. Here is what each one is for, and what the others ' +
        'still have to prove.',
    },
  },
  guide: {
    path: '/guide/',
    html: 'guide/index.html',
    title: 'How to use Amigo',
    description:
      'Set up Amigo in five minutes: create an account, connect Telegram, send your first ' +
      'Tasks, answer Reminders, and switch Modes.',
    image: '/og.png',
    imageAlt: 'Amigo — accountability that lives in your chat',
  },
  contact: {
    path: '/contact/',
    html: 'contact/index.html',
    title: 'Contact — Amigo',
    description:
      'One address, read by a person. What to write to Amigo about, when you will hear back, ' +
      'and what this address is not for.',
    image: '/og.png',
    imageAlt: 'Amigo — accountability that lives in your chat',
  },
  privacy: {
    path: '/privacy/',
    html: 'privacy/index.html',
    title: 'Privacy — Amigo',
    description:
      'What Amigo collects through the Telegram bot, the dashboard and this website, who ' +
      'processes it, how long it is kept, and how to export or delete it.',
    image: '/og.png',
    imageAlt: 'Amigo — accountability that lives in your chat',
  },
}

export const absolute = (path) => new URL(path, SITE.origin).href
