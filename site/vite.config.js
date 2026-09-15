import { relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { PAGES, SITE, absolute } from './src/content/meta.js'

const here = fileURLToPath(new URL('.', import.meta.url))

const pagesByHtml = new Map(Object.values(PAGES).map((page) => [page.html, page]))

const escape = (value) =>
  String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;')

/**
 * The <head> of every page, written from src/content/meta.js.
 *
 * Search engines and link unfurlers read the HTML, not the bundle, and nothing here is
 * server-rendered — so this has to be in the file on disk rather than set by React on mount.
 * Generating it means the titles, descriptions and social cards have one source that a person
 * edits, instead of three hand-kept copies that drift.
 */
const renderHead = (page) => {
  const social = { title: page.title, description: page.description, ...(page.social ?? {}) }
  const url = absolute(page.path)
  const image = absolute(page.image)

  return [
    `<meta name="description" content="${escape(page.description)}" />`,
    `<meta name="theme-color" content="${SITE.themeColor}" />`,
    '<meta name="robots" content="index, follow" />',
    // Canonical and og:url are absolute for the same reason og:image is: a crawler that found
    // the page by another route needs to be told which URL is the real one.
    `<link rel="canonical" href="${url}" />`,
    '',
    '<meta property="og:type" content="website" />',
    `<meta property="og:site_name" content="${SITE.name}" />`,
    `<meta property="og:url" content="${url}" />`,
    `<meta property="og:title" content="${escape(social.title)}" />`,
    `<meta property="og:description" content="${escape(social.description)}" />`,
    `<meta property="og:image" content="${image}" />`,
    `<meta property="og:image:alt" content="${escape(page.imageAlt)}" />`,
    '',
    '<meta name="twitter:card" content="summary_large_image" />',
    `<meta name="twitter:title" content="${escape(social.title)}" />`,
    `<meta name="twitter:description" content="${escape(social.description)}" />`,
    `<meta name="twitter:image" content="${image}" />`,
    `<meta name="twitter:image:alt" content="${escape(page.imageAlt)}" />`,
    '',
    '<link rel="icon" type="image/svg+xml" href="/favicon.svg" />',
    `<title>${escape(page.title)}</title>`,
    // Blank entries are paragraph breaks in the head; do not leave them indented.
  ]
    .join('\n    ')
    .replace(/\n +\n/g, '\n\n')
}

/**
 * Replaces the <!--seo--> placeholder in each entry HTML, and emits sitemap.xml and robots.txt
 * from the same page list. A new page with no entry in meta.js fails the build here rather than
 * shipping untitled, and neither file can be left behind when a page is added or the domain
 * changes — which is exactly what happens when they sit in public/ as hand-written text.
 */
function seo() {
  return {
    name: 'amigo-seo',
    transformIndexHtml: {
      order: 'pre',
      handler(html, ctx) {
        const htmlPath = relative(here, ctx.filename).split(sep).join('/')
        const page = pagesByHtml.get(htmlPath)
        if (!page) {
          throw new Error(
            `${htmlPath} has no entry in src/content/meta.js. Add one (title, description, ` +
              'image) so the page ships with a title and a social card.'
          )
        }
        if (!html.includes('<!--seo-->')) {
          throw new Error(`${htmlPath} is missing the <!--seo--> placeholder in its <head>.`)
        }
        return html.replace('<!--seo-->', renderHead(page))
      },
    },
    generateBundle() {
      const urls = Object.values(PAGES)
        .map((page) => `  <url><loc>${absolute(page.path)}</loc></url>`)
        .join('\n')
      this.emitFile({
        type: 'asset',
        fileName: 'sitemap.xml',
        source:
          '<?xml version="1.0" encoding="UTF-8"?>\n' +
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
          `${urls}\n` +
          '</urlset>\n',
      })
      this.emitFile({
        type: 'asset',
        fileName: 'robots.txt',
        source: `User-agent: *\nAllow: /\n\nSitemap: ${absolute('/sitemap.xml')}\n`,
      })
    },
  }
}

// Multi-page, not a client-side router. Each page is its own HTML entry, so /products/ is a
// real URL that a static host serves directly — no SPA rewrite rule, no router bundle, and
// each page ships only the JS it uses.
export default defineConfig({
  plugins: [react(), seo()],
  build: {
    rollupOptions: {
      input: Object.fromEntries(
        Object.entries(PAGES).map(([name, page]) => [name, resolve(here, page.html)])
      ),
    },
  },
})
