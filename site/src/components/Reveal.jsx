import { useEffect, useRef, useState } from 'react'

export default function Reveal({ as: Component = 'div', className = '', children, ...props }) {
  const ref = useRef(null)
  const [revealed, setRevealed] = useState(false)

  useEffect(() => {
    // Under prefers-reduced-motion: reduce, reveal immediately
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (mediaQuery.matches) {
      setRevealed(true)
      return
    }

    const node = ref.current
    if (!node) return

    // If already in view or scrolled past (e.g. reload at scrolled position), reveal immediately
    const rect = node.getBoundingClientRect()
    if ((rect.top < window.innerHeight && rect.bottom > 0) || rect.bottom <= 0) {
      setRevealed(true)
      return
    }

    if (!('IntersectionObserver' in window)) {
      setRevealed(true)
      return
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setRevealed(true)
          observer.unobserve(entry.target)
        }
      },
      {
        threshold: 0.15,
        rootMargin: '0px 0px -10% 0px',
      }
    )

    observer.observe(node)

    return () => {
      observer.disconnect()
    }
  }, [])

  const combinedClassName = `reveal ${revealed ? 'revealed' : ''} ${className}`.trim()

  return (
    <Component ref={ref} className={combinedClassName} {...props}>
      {children}
    </Component>
  )
}
