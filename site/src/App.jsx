import SiteNav from './components/SiteNav'
import Hero from './components/Hero'
import TelegramDemo from './components/TelegramDemo'
import HowItWorks from './components/HowItWorks'
import Wedge from './components/Wedge'
import HonestyBlock from './components/HonestyBlock'
import WhyBand from './components/WhyBand'
import OpenSource from './components/OpenSource'
import Faq from './components/Faq'
import WaitlistForm from './components/WaitlistForm'
import SiteFooter from './components/SiteFooter'
import Reveal from './components/Reveal'

export default function App() {
  return (
    <div className="site-app">
      <SiteNav />
      <main>
        <div className="site-container">
          <Hero />
          <TelegramDemo />
          <HowItWorks />
          <Wedge />
          <HonestyBlock />
        </div>

        {/* Full-bleed: deliberately outside the content column. */}
        <WhyBand />

        <div className="site-container">
          <OpenSource />
          <Faq />
          <section className="closing-cta-section" aria-labelledby="closing-cta-title">
            <Reveal className="closing-cta-content">
              <h2 id="closing-cta-title" className="closing-cta-title">
                One message, when there is something to try.
              </h2>
              <p className="closing-cta-lead">
                No newsletter, no countdowns. We will not email you again until Amigo opens.
              </p>
              <WaitlistForm variant="closing" />
            </Reveal>
          </section>
        </div>
      </main>
      <SiteFooter />
    </div>
  )
}
