import { useEffect, useState } from 'react'
import { SITE } from '../content/meta'
import { NAV } from '../content/shared'

export default function SiteNav({ active = 'home' }) {
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => {
      setScrolled(window.scrollY > 40)
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <header className={`site-nav ${scrolled ? 'scrolled' : ''}`}>
      <div className="site-nav-inner">
        <a href="/" className="site-nav-wordmark" aria-label={NAV.wordmarkLabel}>
          Amigo
        </a>
        <div className="site-nav-actions">
          <a
            href="/products/"
            className={`site-nav-link site-nav-link--secondary ${active === 'products' ? 'site-nav-link--current' : ''}`}
            aria-current={active === 'products' ? 'page' : undefined}
          >
            {NAV.products}
          </a>
          <a
            href="/guide/"
            className={`site-nav-link ${active === 'guide' ? 'site-nav-link--current' : ''}`}
            aria-current={active === 'guide' ? 'page' : undefined}
          >
            {NAV.guide}
          </a>
          <a href={SITE.dashboard} className="site-nav-link">
            {NAV.dashboard}
          </a>
          <a href={SITE.signup} className="site-nav-cta">
            <span className="cta-full">{NAV.cta}</span>
            <span className="cta-short" aria-hidden="true">{NAV.ctaShort}</span>
          </a>
        </div>
      </div>
    </header>
  )
}
