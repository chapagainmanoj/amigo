import { useEffect, useState } from 'react'

export default function SiteNav() {
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => {
      setScrolled(window.scrollY > 40)
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const handleJoinClick = (e) => {
    const target = document.getElementById('waitlist')
    if (target) {
      e.preventDefault()
      target.scrollIntoView({ behavior: 'smooth' })
      const input = target.querySelector('input[type="email"]')
      if (input) {
        // focus after small delay for smooth scroll completion
        setTimeout(() => input.focus(), 300)
      }
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
            href="https://github.com/chapagainmanoj/amigo"
            target="_blank"
            rel="noopener noreferrer"
            className="site-nav-link"
          >
            GitHub
          </a>
          <a
            href="#waitlist"
            onClick={handleJoinClick}
            className="site-nav-cta"
          >
            <span className="cta-full">Join the waitlist</span>
            <span className="cta-short" aria-hidden="true">Waitlist</span>
          </a>
        </div>
      </div>
    </header>
  )
}
