import SiteNav from './components/SiteNav'
import SiteFooter from './components/SiteFooter'
import { CONTACT_PAGE } from './content/contact'

export default function ContactApp() {
  return (
    <div className="site-app">
      <SiteNav />
      <main>
        <div className="site-container">
          <article className="legal">
            <h1 className="legal-title">{CONTACT_PAGE.title}</h1>
            <p className="legal-lead">{CONTACT_PAGE.lead}</p>

            <a href={`mailto:${CONTACT_PAGE.address}`} className="contact-address">
              {CONTACT_PAGE.address}
            </a>

            {CONTACT_PAGE.sections.map((section) => (
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
