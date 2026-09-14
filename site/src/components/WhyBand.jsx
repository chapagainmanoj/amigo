import Reveal from './Reveal'

// The page's single inversion. Written for the reader who is evaluating whether this is
// worth building, and readable by everyone else. Nothing here is claimed as shipped.
export default function WhyBand() {
  return (
    <section className="why-band" aria-labelledby="why-title">
      <div className="why-band-inner">
        <Reveal>
          <h2 id="why-title" className="section-title">
            Why this is worth building
          </h2>
          <div className="why-body">
            <p>
              Every accountability tool eventually learns the same thing: the hard part was
              never the list. It was the moment — the right question, asked while a person
              can still act on it.
            </p>
            <p>
              <strong>That moment is the only thing Amigo does.</strong> Each reminder that
              gets a Done, a Skip, or a Later is a small, specific fact about when this
              person can actually follow through — and that is the thing no task app has
              ever been positioned to learn, because nobody opens a task app at the moment
              of truth.
            </p>
            <p>
              We are building the boring parts first: delivery that doesn&rsquo;t drop,
              state that stays consistent across surfaces, and a bar for not being annoying.
              Then the interesting part gets a chance to be real.
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
