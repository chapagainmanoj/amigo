import Reveal from './Reveal'

const STEPS = [
  {
    num: '01',
    title: 'Say it in passing',
    body: "Type the thing you need to do the way you'd say it to a friend. Amigo pulls out the task and the time.",
  },
  {
    num: '02',
    title: 'Get asked, once',
    body: "A reminder arrives in Telegram when you said you wanted it. Not a badge you'll swipe away — a message you'll actually read.",
  },
  {
    num: '03',
    title: 'Close it in one tap',
    body: 'Done, Skip, or Later. The dashboard keeps the record if you ever want to look.',
  },
]

export default function HowItWorks() {
  return (
    <section className="how-it-works-section" aria-labelledby="how-it-works-title">
      <Reveal>
        <h2 id="how-it-works-title" className="section-title">
          How it works
        </h2>
        <div className="how-grid">
          {STEPS.map((step) => (
            <div key={step.num} className="how-cell">
              <span className="how-num">{step.num}</span>
              <h3 className="how-title">{step.title}</h3>
              <p className="how-body">{step.body}</p>
            </div>
          ))}
        </div>
      </Reveal>
    </section>
  )
}
