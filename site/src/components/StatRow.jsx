import { useEffect, useRef, useState } from 'react'

// Two facts about the market, then the answer. The third cell breaks the pattern on purpose:
// it is the only one that is about Amigo, and the only one that carries --signal-deep.
const STATS = [
  { value: 52, suffix: '%', caption: 'abandon their habit app within the first month' },
  { value: 70, suffix: '%', caption: 'quit lifestyle and wellbeing apps inside 100 days' },
  { value: 0, suffix: '', caption: 'new apps Amigo asks you to install', answer: true },
]

function useCountUp(target, start) {
  const [value, setValue] = useState(start ? 0 : target)

  useEffect(() => {
    if (!start) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setValue(target)
      return
    }
    if (target === 0) {
      setValue(0)
      return
    }

    let frame
    const duration = 900
    const began = performance.now()

    const tick = (now) => {
      const progress = Math.min((now - began) / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      setValue(Math.round(target * eased))
      if (progress < 1) frame = requestAnimationFrame(tick)
    }

    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [target, start])

  return value
}

function Stat({ stat, start }) {
  const value = useCountUp(stat.value, start)
  return (
    <div className={`stat-cell ${stat.answer ? 'stat-cell--answer' : ''}`}>
      <span className="stat-num">
        {value}
        {stat.suffix}
      </span>
      <span className="stat-caption">{stat.caption}</span>
    </div>
  )
}

export default function StatRow() {
  const ref = useRef(null)
  const [started, setStarted] = useState(false)

  useEffect(() => {
    const node = ref.current
    if (!node) return
    if (!('IntersectionObserver' in window)) {
      setStarted(true)
      return
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setStarted(true)
          observer.disconnect()
        }
      },
      { threshold: 0.3 }
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  return (
    <div className="stat-row" ref={ref}>
      {STATS.map((stat) => (
        <Stat key={stat.caption} stat={stat} start={started} />
      ))}
    </div>
  )
}
