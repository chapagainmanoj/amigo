import SiteNav from './components/SiteNav'
import Hero from './components/Hero'
import TelegramDemo from './components/TelegramDemo'
import HowItWorks from './components/HowItWorks'
import Wedge from './components/Wedge'
import HonestyBlock from './components/HonestyBlock'
import WhyBand from './components/WhyBand'
import OpenSource from './components/OpenSource'
import Faq from './components/Faq'
import ClosingCta from './components/ClosingCta'
import SiteFooter from './components/SiteFooter'

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
          <ClosingCta titleId="closing-cta-title" />
        </div>
      </main>
      <SiteFooter />
    </div>
  )
}
