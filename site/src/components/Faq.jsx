import Reveal from './Reveal'

const FAQ_ITEMS = [
  {
    q: 'When does it open?',
    a: "We don't have a date, and we're not going to invent one. Security, reminder reliability, and privacy work come first. You'll get one email when there's something real to try.",
  },
  {
    q: 'Why Telegram?',
    a: "Because you're already in it. A reminder in a chat you check beats a notification from an app you've muted. Other channels are possible later; none are promised.",
  },
  {
    q: 'What will it cost?',
    a: "Nothing during the invitation beta. Beyond that we're testing a hypothesis of about US$9 per month. That's research, not a price list.",
  },
  {
    q: 'What do you do with my email?',
    a: 'Store it to send you one message when Amigo opens, and nothing else. No newsletter, no sharing, no advertising. You can unsubscribe or ask us to delete it at any time, and we purge addresses that never confirm.',
  },
  {
    q: 'Who is it for?',
    a: "Adults who keep abandoning task apps and would rather just say what they need to do. It's not built for safety-critical reminders like medication or medical appointments.",
  },
  {
    q: 'Can I self-host it?',
    a: "The licence allows it. Supported self-hosting isn't something we promise yet.",
  },
]

export default function Faq() {
  return (
    <section className="faq-section" aria-labelledby="faq-title">
      <Reveal>
        <h2 id="faq-title" className="section-title">
          Questions &amp; answers
        </h2>
        <div className="faq-list">
          {FAQ_ITEMS.map((item) => (
            <details key={item.q} className="faq-item">
              <summary className="faq-question">{item.q}</summary>
              <div className="faq-answer">
                <p>{item.a}</p>
              </div>
            </details>
          ))}
        </div>
      </Reveal>
    </section>
  )
}
