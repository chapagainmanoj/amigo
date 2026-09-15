import { FOOTER } from '../content/shared'

export default function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="site-footer-inner">
        <div className="site-footer-meta">
          <span className="site-footer-wordmark">Amigo</span>
          <span>{FOOTER.copyright}</span>
          <span>{FOOTER.licence}</span>
        </div>
        <div className="site-footer-links">
          {FOOTER.links.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="site-footer-link"
              {...(link.external ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
            >
              {link.label}
            </a>
          ))}
        </div>
      </div>
    </footer>
  )
}
