export default function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="site-footer-inner">
        <div className="site-footer-meta">
          <span className="site-footer-wordmark">Amigo</span>
          <span>&copy; 2026 Amigo</span>
          <span>AGPL-3.0</span>
        </div>
        <div className="site-footer-links">
          {/* No "Privacy" link until there is a privacy page to point it at. Pointing it at
              SECURITY.md would label vulnerability-reporting instructions as a privacy
              statement, on a page that collects email addresses under a consent checkbox. */}
          <a
            href="https://github.com/chapagainmanoj/amigo"
            target="_blank"
            rel="noopener noreferrer"
            className="site-footer-link"
          >
            GitHub
          </a>
          <a
            href="https://github.com/chapagainmanoj/amigo/blob/develop/docs/capability-matrix.md"
            target="_blank"
            rel="noopener noreferrer"
            className="site-footer-link"
          >
            Capability matrix
          </a>
        </div>
      </div>
    </footer>
  )
}
