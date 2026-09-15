import SiteNav from './components/SiteNav'
import SiteFooter from './components/SiteFooter'
import { PRIVACY } from './content/legal'

export default function PrivacyApp() {
  return (
    <div className="site-app">
      <SiteNav />
      <main>
        <div className="site-container">
          <article className="legal">
            <h1 className="legal-title">{PRIVACY.title}</h1>
            <p className="legal-meta">Effective {PRIVACY.effective}</p>
            <p className="legal-lead">{PRIVACY.lead}</p>

            {PRIVACY.sections.map((section) => (
              <section key={section.heading}>
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
