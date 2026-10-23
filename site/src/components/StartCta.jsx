import { SITE } from '../content/meta'
import { START_CTA } from '../content/shared'

// Signup lives on the dashboard; the site only links to it and sends nothing itself.
export default function StartCta() {
  return (
    <div className="start-cta">
      <a href={SITE.signup} className="start-cta-button">
        {START_CTA.primary}
      </a>
      <a href="/guide/" className="start-cta-secondary">
        {START_CTA.secondary}
      </a>
    </div>
  )
}
