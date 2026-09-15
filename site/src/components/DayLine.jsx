import Reveal from './Reveal'

// The wedge, drawn: a whole waking day, and the only marks on it are the moments you asked for.
// The emptiness is the picture. Built from rules and positioned marks rather than an SVG so the
// labels stay real type at 375px instead of scaling down with a viewBox.
//
// The times are illustrative — a day someone might have asked for — not measured data.
const START = 7
const END = 23
const HOURS = [7, 11, 15, 19, 23]
const MARKS = [
  { at: 9, label: '9:00' },
  { at: 14.5, label: '2:30 PM' },
  { at: 18.75, label: '6:45 PM' },
]

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

      <figcaption className="day-line-caption">
        One waking day. The three marks are reminders someone asked for — and they are Amigo&rsquo;s
        entire presence in it. There is nothing else to open, and nothing accumulating while you are
        away.
      </figcaption>
    </Reveal>
  )
}
