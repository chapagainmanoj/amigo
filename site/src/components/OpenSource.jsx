import Reveal from './Reveal'

export default function OpenSource() {
  return (
    <section className="open-source-section" aria-labelledby="open-source-title">
      <Reveal>
        <h2 id="open-source-title" className="section-title">
          Built in the open
        </h2>
        <p className="open-source-body">
          Amigo&rsquo;s source and its full capability matrix are public under AGPL-3.0. If a
          claim on this page isn&rsquo;t backed by code, you can go and check.
        </p>
        <div className="open-source-links">
          <a
            href="https://github.com/chapagainmanoj/amigo"
            target="_blank"
            rel="noopener noreferrer"
            className="open-source-link"
          >
            Read the source &rarr;
          </a>
          <a
            href="https://github.com/chapagainmanoj/amigo/blob/develop/docs/capability-matrix.md"
            target="_blank"
            rel="noopener noreferrer"
            className="open-source-link"
          >
            See the capability matrix &rarr;
          </a>
        </div>
      </Reveal>
    </section>
  )
}
