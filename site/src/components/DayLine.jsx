import Reveal from './Reveal'
import { DAY_LINE } from '../content/home'

// Built from rules and positioned marks rather than an SVG so the labels stay real type at 375px
// instead of scaling down with a viewBox. The hours and the marks themselves are copy, not
// layout, so they live in the content module.
const { start: START, end: END, hours: HOURS, marks: MARKS } = DAY_LINE

const pct = (hour) => ((hour - START) / (END - START)) * 100

const clockLabel = (hour) => {
  const h = Math.floor(hour)
  const suffix = h < 12 ? 'AM' : 'PM'
  const display = h % 12 === 0 ? 12 : h % 12
  return `${display} ${suffix}`
}

export default function DayLine() {
  return (
    <Reveal className="day-line" as="figure">
      <div className="day-line-track">
        {HOURS.map((hour, index) => (
          <span key={hour} className="day-tick" style={{ left: `${pct(hour)}%` }}>
            {/* The end labels anchor inward: centred on a 0%/100% tick they hang half outside
                the content column and get clipped at narrow widths. */}
            <span
              className={`day-tick-label ${
                index === 0 ? 'day-tick-label--first' : ''
              } ${index === HOURS.length - 1 ? 'day-tick-label--last' : ''}`}
            >
              {clockLabel(hour)}
            </span>
          </span>
        ))}

        {MARKS.map((mark) => (
          <span key={mark.label} className="day-mark" style={{ left: `${pct(mark.at)}%` }}>
            <span className="day-mark-label">{mark.label}</span>
          </span>
        ))}
      </div>

      <figcaption className="day-line-caption">{DAY_LINE.caption}</figcaption>
    </Reveal>
  )
}
