import SiteNav from './components/SiteNav'
import SiteFooter from './components/SiteFooter'
import { GUIDE_PAGE } from './content/guide'

export default function GuideApp() {
  return (
    <div className="site-app">
      <SiteNav active="guide" />
      <main>
        <div className="site-container">
          <article className="legal guide">
            <h1 className="legal-title">{GUIDE_PAGE.title}</h1>
            <p className="legal-lead">{GUIDE_PAGE.lead}</p>

            <nav className="guide-toc" aria-label="On this page">
              <ul>
                {GUIDE_PAGE.sections.map((section) => (
                  <li key={section.id}>
                    <a href={`#${section.id}`} className="legal-link">{section.heading}</a>
                  </li>
                ))}
              </ul>
            </nav>

            {GUIDE_PAGE.sections.map((section) => (
              <section key={section.id} id={section.id}>
                <h2 className="legal-h2">{section.heading}</h2>
                {section.body}
              </section>
            ))}
          </article>
        </div>
      </main>
      <SiteFooter />
    </div>
  )
}
