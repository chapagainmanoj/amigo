import { useEffect, useState } from 'react'

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

  // Both pages render a waitlist form with id="waitlist", so this normally scrolls in place. If a
  // page ever ships without one, the href is left alone and the browser navigates home to it.
  const handleJoinClick = (e) => {
    const target = document.getElementById('waitlist')
    if (!target) return

    e.preventDefault()
    const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    target.scrollIntoView({ behavior: prefersReduced ? 'auto' : 'smooth' })
    const input = target.querySelector('input[type="email"]')
    if (input) {
      // focus after small delay for smooth scroll completion
      setTimeout(() => input.focus(), prefersReduced ? 50 : 300)
    }
  }

  return (
    <header className={`site-nav ${scrolled ? 'scrolled' : ''}`}>
      <div className="site-nav-inner">
        <a href="/" className="site-nav-wordmark" aria-label="Amigo home">
          Amigo
        </a>
        <div className="site-nav-actions">
          <a
            href="/products/"
            className={`site-nav-link ${active === 'products' ? 'site-nav-link--current' : ''}`}
            aria-current={active === 'products' ? 'page' : undefined}
          >
            Products
          </a>
          <a href="/#waitlist" onClick={handleJoinClick} className="site-nav-cta">
            <span className="cta-full">Join the waitlist</span>
            <span className="cta-short" aria-hidden="true">Waitlist</span>
          </a>
        </div>
      </div>
    </header>
  )
}
