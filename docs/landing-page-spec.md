# Amigo Landing / Waitlist Page — Implementation Spec

**Audience:** an implementing agent or developer who has not read the rest of this repository.
**Status:** revision 2. A v1 implementation exists under `site/`; this revision replaces its
palette (Section 4.1), its background treatment (Section 4.2), and its page structure and copy
(Section 5). Sections 6–12 carry forward from v1 except where noted.
**Governing documents:** [capability-matrix.md](capability-matrix.md) (copy rules),
[what-is-amigo.md](what-is-amigo.md) (positioning),
`.scratch/amigo-complete-product/decisions/11-cohort-and-recruitment.md` (recruitment limits).

---

## 0. Read this before writing any copy

Amigo is in **pre-beta**. This repository has a hard rule, stated in
[capability-matrix.md](capability-matrix.md) under "Copy and Demo Rule":

> Before publishing copy, screenshots, a demo script, or a sales claim:
> 1. Match every claimed capability to this matrix.
> 2. Call experimental behavior a beta experiment and state the relevant limitation.
> 3. Call future behavior roadmap and avoid dates or "coming soon" promises.

And decision 11 states, for the first beta cohort:

> Do not use paid advertising, Product Hunt, a broad public signup, or an uncontrolled public
> link for this cohort.

**Consequence for this page:** it is *not* a beta signup. It collects interest for general
availability *after* the closed cohort. It must never say "join the beta", "get early access",
"be one of the first 100", or imply that submitting the form leads to an invitation. Waitlist
submissions are a mailing list, not a recruitment funnel. Every word on the page is checkable
against the "Shipped in the current prototype" column of the capability matrix.

This constraint is an asset, not a tax. An honest "here is exactly what works and what does not"
section is more persuasive in 2026 than another page of superlatives, and Section 5.5 turns the
rule into the page's most distinctive block.

---

## 1. Repository decision: same repo, new `site/` workspace

**Recommendation: build it in this repository as a new sibling Vite app at `site/`, deployed as
its own Render static service. Do not create a new repository. Do not add it as a route inside
`web/`.**

| Option | Verdict | Reasoning |
|---|---|---|
| New route inside `web/` | No | `web/` is the authenticated dashboard. `web/src/App.jsx` branches on a Supabase session and has no router. Adding one means every anonymous visitor downloads `@supabase/supabase-js`, and a dashboard deploy becomes a marketing deploy. |
| **New `site/` workspace, same repo** | **Yes** | Copy stays next to `docs/capability-matrix.md`, so the copy rule is enforceable by a test (Section 9.2). The site keeps its own palette (Section 4.1); a guard test pins that palette so it cannot drift by accident (Section 9.1). One AGPL-3.0 licence, one CI, one `render.yaml`. Zero auth JavaScript on the marketing page. Independent deploy cadence. |
| Separate repository | No | Splits the copy from the matrix that governs it, and duplicates licence/CI/lint setup. Revisit only if a non-engineer needs to edit copy through a CMS. |

`site/` never imports from `web/`. The one thing they share is the palette, by value, enforced by
a test — see Section 4.1.

---

## 2. Inherited engineering constraints

These come from `CLAUDE.md` and apply to whoever implements this.

**Never modify without human review:** `.env`, `migrations/*.sql`, `src/config.py`,
`src/db/supabase.py`, `scripts/smoke_check.py`.
**Never auto-delete:** `tests/fakes.py`, `README.md`, `AGENTS.md`.

Practical effect: **Phase 1 of this page must not require a database migration or a backend
route.** Storage of waitlist emails is handled by a third-party provider behind a one-function
abstraction (Section 8). A Supabase-backed waitlist is Phase 2 and needs the founder's approval
of a new migration. Note that migration `015` is already reserved by parked work; a waitlist
table would be `016` or later.

Other rules that apply: Python 3.12, line length 100, ruff `E,F,I,N,UP,B,SIM` for any test file
added; frontend must pass `npm run lint` with `--max-warnings 0` and `npm run build`.

---

## 3. Research summary → design direction

### 3.1 Why the first palette was wrong

The v1 palette (`--ink #14121A`, `--ember #FF8A5B`, glassmorphism, radial ember glow) is the
default house style of machine-generated landing pages in 2026: near-black ground, one warm
gradient bloom, frosted cards. It is competent and completely anonymous. A page whose job is to
be a founder's first pitch cannot look like a template.

**Reference the founder named:** [Wellsy](https://www.wellsy.se/en). Its published tokens are
`--forest #22372B`, `--forest-2 #587163`, `--ink #5b6a60`, `--cream #FDFCF8`, `--sand #F2EDE3`,
`--line #e8e3d6`, with Source Serif 4 as the display face. What actually makes it feel premium is
not the green — it is the **restraint**: a warm light ground, no gradients, no glow, no glass,
hairline rules instead of card borders and shadows, one deep full-bleed band as a rhythm break,
and a single sand-coloured panel for the closing CTA.

**Do not copy Wellsy's green.** It belongs to an adjacent product. Take the discipline, not the
hue.

### 3.2 The design idea: colour carries the product's meaning

Amigo's entire product is *one well-timed nudge*. So the page is near-monochrome — warm oat
ground, warm near-black ink, taupe secondary — and exactly one saturated colour, `--signal`,
which appears **only** on the reminder bubble in the demo and on the waitlist CTA. Nothing else
on the page is allowed to use it.

The result: the eye lands on the two things that matter, the page reads as considered rather than
decorated, and the accent means something instead of being brand garnish.

### 3.3 Conversion and layout findings retained from v1

| Finding | Applied as |
|---|---|
| Highest-converting waitlist pages put the email field **inside** the hero. | Unchanged. One field above the fold. |
| Nav is part of the funnel, not a directory. | Wordmark, GitHub, one CTA. |
| An animated product demonstration near the hero is the strongest 2026 pattern. | The Telegram thread, kept, restyled. |
| Minimal motion that adds meaning. | Scroll reveal + the typed demo. No parallax, no glow pulse. |
| Headlines 48–64px, body 16–18px, tracking −0.02em to −0.04em on display sizes. | Section 4.3. |
| Fake waitlist counters and invented social proof. | Still rejected. |
| Grainy gradients / mesh backgrounds. | **Dropped.** This was the generic part. Replaced by flat warm fields and hairlines. |

### 3.4 Market grounding (drives Sections 5.6 and 5.7)

- Habit-tracking apps: ~US$2.2B in 2026 → ~US$6.4B by 2034, ~14% CAGR; >298M active users,
  ~120M in the US alone, concentrated in 25–40-year-olds — the segment most willing to pay.
- **52% abandon their habit app within the first month; ~70% discontinue lifestyle and
  mental-health apps within 100 days.** This is the number the page is built around.
- The dominant complaint is not missing features. It is streak mechanics and guilt: the app
  becomes a source of shame after one slip, and tracking becomes more work than the habit.
- Competitors: Focusmate (scheduled human body-doubling), Finch (gamified self-care), Rocky.ai
  (conversational AI coach), plus a 2026 wave of AI-only entrants (Overlord, NOZERO, Coach Call
  AI). All of them are **an app you must open**. None are native to a messenger the user is
  already in.

**The wedge, in one line:** every competitor adds a surface you have to remember to visit; Amigo
removes it.

---

## 4. Design system

### 4.1 Colour tokens

```css
:root {
  /* Ground */
  --oat:         #FBF8F2;  /* page background */
  --sand:        #F1E9DC;  /* raised panel, closing CTA, demo chrome */
  --rule:        #E5DCCB;  /* hairlines — replaces all card borders and shadows */

  /* Text */
  --ink:         #1F1A17;  /* primary — warm near-black, never pure black. Also the CTA fill. */
  --ink-2:       #6F655C;  /* secondary — warm taupe */

  /* The signal */
  --signal:      #EA5A2D;  /* FILL ONLY */
  --signal-ink:  #1F1A17;  /* text placed ON the signal fill */
  --signal-deep: #A33A0B;  /* signal-coloured text on --oat / --sand */

  /* The single full-bleed inversion */
  --band:        #241E1A;
  --band-soft:   #A99E93;  /* secondary text on the band */
}
```

**THE ONE RULE: `--signal` appears exactly once in the rendered page — the reminder bubble in
the Telegram demo. The waitlist CTA is `--ink`.**

**These ten tokens are shared with the dashboard.** `web/src/index.css` declares exactly the same
values, because a participant crosses from this page into the dashboard mid-activation and the
two surfaces are one product. `tests/test_landing_page.py` pins both and fails on drift. The
dashboard adds three status colours of its own (`--ok #10664C`, `--warn #8A5A06`,
`--danger #B91C1C`, all ≥ 4.5 on both `--oat` and `--sand`) and carries `--signal` for exactly
one thing: a Reminder that is due now. That is the same meaning the accent has here.

The first draft spent the accent on both the CTA and the bubble. That made the two most
prominent elements the same colour, which is not an accent — it is a second brand colour, and
the page read as decorated rather than considered. An ink CTA on a warm ground is also the
stronger, more premium button, and it leaves the signal free to mark the one moment the product
actually exists. `tests/test_landing_page.py` enforces this.

The deep band is `--band`, a warm espresso — *not* a green. A green band under a warm accent
reads muddy and dated; a warm near-black band reads as a deepening of the same material, so the
page holds together as one thing.

**Measured WCAG contrast — verified, do not alter a hex without recomputing:**

| Pair | Ratio | Use |
|---|---|---|
| `--ink` on `--oat` | 16.26 | body and headings |
| `--ink-2` on `--oat` | 5.37 | secondary text |
| `--ink-2` on `--sand` | 4.72 | secondary text on panels |
| `--oat` on `--ink` | 16.26 | **the CTA label** |
| `--signal-ink` on `--signal` | 4.92 | **the reminder bubble label** |
| `--signal-deep` on `--oat` | 6.25 | error text |
| `--signal-deep` on `--sand` | 5.50 | error text on panels |
| `--oat` on `--band` | 15.53 | text on the deep band |
| `--band-soft` on `--band` | 6.27 | secondary text on the deep band |

Three traps, all recorded because each one was hit during implementation:

- **`--oat` on `--signal` is 3.30 and fails.** Text on the signal fill must be `--signal-ink`.
- **`--signal` as text on `--oat` is 3.58 and fails.** It is a fill, never type.
- **The demo's shared `.telegram-time` opacity of 0.65 drops to 2.99 on the signal fill.** The
  reminder bubble's timestamp is overridden to full opacity (4.92).

### 4.2 Rules that make it not look generic

These are constraints, not suggestions:

1. **No gradients anywhere.** No mesh, no radial bloom, no glow. Flat fields only.
2. **No `backdrop-filter`, no glassmorphism.** Delete every instance from v1.
3. **No `box-shadow`.** Separation comes from `1px solid var(--rule)` and from field changes
   (`--oat` → `--sand`).
4. **`--signal` appears exactly twice** — the reminder bubble in the demo, and the waitlist
   submit button. Nowhere else. Not on links, not on the kicker, not on icons.
5. **One deep band per page** (`--band`), used once, for Section 5.6. It is the only inversion.
6. **The CTA is never `--signal`.** See 4.1.
7. **No icon set decoration.** Drop `lucide-react` unless a specific element needs it; numerals
   and type do the work.
8. Grain overlay: optional, at most `opacity: 0.02`. If in doubt, omit it.

### 4.3 Typography

- **Display:** a serif with real character. `@fontsource-variable/fraunces` (variable, warm,
  `SOFT`/`WONK` axes) is the first choice; `@fontsource/instrument-serif` is the fallback.
  Import the **latin subset only** (`/latin.css`).
- **Body:** `@fontsource-variable/inter/latin.css` — latin only. The v1 import pulled Cyrillic,
  Greek and Vietnamese into `dist`.
- Self-host. Never the Google Fonts CDN.
- **Signature move, borrowed as a technique rather than a look:** set one word of the H1 in the
  display face's *italic*. It costs nothing and makes the headline look authored.

| Role | Size | Weight | Tracking | Line height |
|---|---|---|---|---|
| H1 | `clamp(2.75rem, 6vw, 4.5rem)` | 400 serif | `-0.03em` | 1.02 |
| H2 | `clamp(1.875rem, 3.6vw, 2.6rem)` | 400 serif | `-0.02em` | 1.1 |
| H3 | `1.0625rem` | 600 sans | `-0.005em` | 1.35 |
| Body | `clamp(1rem, 1.3vw, 1.0625rem)` | 400 sans | `0` | 1.65 |
| Lead | `clamp(1.125rem, 1.7vw, 1.25rem)` | 400 sans | `-0.005em` | 1.55 |
| Kicker | `0.6875rem` | 600 sans | `0.14em`, uppercase | 1 |
| Stat numeral | `clamp(2.5rem, 5vw, 3.5rem)` | 400 serif | `-0.02em` | 1 |
| Micro | `0.8125rem` | 400 sans | `0` | 1.5 |

Body column never exceeds `62ch`.

### 4.4 Spacing, rhythm, elevation

- Section rhythm: `clamp(80px, 13vh, 150px)`.
- Radii: `6px` controls, `14px` panels, `999px` pills. Softer than v1, not pill-shaped.
- **Elevation is forbidden.** No shadow, no blur, no layering. Hairlines and field changes only.
- Feature grids use shared hairline rules between cells, not individually bordered cards — the
  cells sit directly on the ground.

### 4.5 Motion

| Element | Behaviour |
|---|---|
| Section entry | Fade + 10px rise, 420ms `cubic-bezier(.22,.61,.36,1)`, `IntersectionObserver` at `threshold: 0.15`, `rootMargin: '0px 0px -10% 0px'`, fires once. |
| Telegram demo | Messages in sequence, 700ms apart, typing indicator before each Amigo reply. Starts at 40% visible. Plays once, holds the final state. |
| Stat numerals (5.1) | Count up once on reveal, 900ms, `ease-out`. Static under reduced motion. |
| CTA | 120ms fill shift `--signal` → `--signal-deep`. No lift, no glow. |
| Focus | `outline: 2px solid var(--ink); outline-offset: 2px`. The gold ring from v1 is gone with the palette. |

Everything above must be inert inside `@media (prefers-reduced-motion: reduce)`, with the demo
showing its **completed** thread immediately.

---

## 5. Page structure and exact copy

Two things changed from v1, both from founder feedback:

- **Curiosity.** v1 answered every question and then said *"That is the whole product."* That is
  a closed loop — nothing pulls the reader down the page. The rewrite opens with a number the
  reader wants explained, and holds the product reveal until after the problem lands.
- **Vision.** v1's honesty table listed only present-tense limitations, ending on *"A finished,
  reliable, publicly open service — not built."* An investor reads that as "this is not a
  company." Honesty stays, but it now sits **beside** a direction, not instead of one.

The capability rules in Section 0 are unchanged: the direction column is labelled as direction,
carries no dates, and is never written in the present tense.

Order is fixed. Copy is final text — use it verbatim.

### 5.1 Hero — lead with the number, not the product

```
[kicker]   INVITATION-ONLY · NOT YET OPEN

[h1]       Most task apps are
           abandoned in a *month*.        ← "month" in display italic

[lead]     Not because people stop caring. Because the app is one more thing to
           open, groom, and feel guilty about. Amigo doesn't ask you to open
           anything.

[form]     [ you@example.com ] [ Join the waitlist ]
           [ ] Email me once, when Amigo opens.

[micro]    No newsletter, no launch countdown. One message when there is
           something real to try.
```

Beneath the fold edge, a hairline-separated stat row — three numerals, counted up on reveal:

| Numeral | Caption |
|---|---|
| `52%` | `abandon their habit app within the first month` |
| `70%` | `quit lifestyle and wellbeing apps inside 100 days` |
| `0` | `new apps Amigo asks you to install` |

The third breaks the pattern deliberately: two facts about the market, then the answer. That is
the curiosity hook — the reader now wants to know *how*, which is exactly what 5.2 shows.

### 5.2 The demo — the answer to the hook

Unchanged script (user asks at 2:14, reminder fires at 3:00, Done, confirmation). Restyled: sand
chrome, hairline border, no shadow, no phone bezel illustration. The reminder bubble is the one
place `--signal` appears.

Caption changes from v1's closed statement to an open one:

> **It lives in a chat you already have open.** One sentence in, one reminder out, three buttons
> to close it. Nothing to install, nothing to organise, nothing to abandon.

### 5.3 How it works — 3 cells, hairline-separated

Copy unchanged from v1 (`Say it in passing` / `Get asked, once` / `Close it in one tap`).
Restyle only: no card fills, no borders — cells divided by `--rule`, numerals in display serif.

### 5.4 Why a messenger — the wedge, stated plainly

**H2:** `Every other tool adds a surface. This one removes it.`

> Focusmate books you a stranger. Finch gives you a pet. The new wave of AI coaches gives you
> another chat window to remember. All of them assume you will come back to an app you have
> already stopped opening.
>
> Amigo starts in Telegram, where you already are — and the only time it appears is the moment
> you asked it to.

No competitor logos, no comparison table, no disparagement beyond the factual difference. This
section is written for the investor reading for a wedge, and it reads naturally to a user.

### 5.5 Honest state — reframed as three columns

**H2:** `Where this actually is`
**Lead:** `Amigo is small and unfinished, and built in the open. Here is the real state of it.`

| Working today | Being proven now | Where it goes |
|---|---|---|
| Telegram conversation, in plain language | Reminder reliability under real load | Amigo learns which nudges you actually act on |
| Tasks created from what you type | Task state staying consistent across surfaces | Timing that adapts to you rather than a fixed clock |
| Reminders at the time you ask for | Whether people activate without hand-holding | Modes you switch on deliberately, never automatically |
| Done, Skip, and Later, in the chat | Whether the loop is useful without being annoying | Surfaces beyond Telegram, only if people ask for them |
| A dashboard for your tasks and reminders | | |

Column rules, non-negotiable:
- **Column 1** maps one-to-one to the "Shipped" column of `docs/capability-matrix.md`.
- **Column 2** is headed with the sub-label `open questions we're answering before we open up`.
- **Column 3** is headed with the sub-label `direction, not promises — every one of these can end
  in "no"`. Set the whole column in `--ink-2`, not `--ink`, so it reads visually as lighter-weight
  than the other two. No dates, no present tense, no "coming soon".

Column 3 is what v1 was missing. It is also the honest version of a roadmap: the disclaimer is
the column heading, not a footnote.

**Boundary notice** below, in a `--sand` panel with a `--rule` border:

> Amigo is a non-clinical accountability companion. It is not therapy, diagnosis, treatment, or a
> crisis service, and it is not monitored. If you are in crisis, please contact your local
> emergency services.

### 5.6 The deep band — the one inversion, and the investor paragraph

Full-bleed `--band`. Type in `--oat` and `--band-soft`. This is the page's only dark field and
the only place the argument is made explicitly.

**H2:** `Why this is worth building`

> Every accountability tool eventually learns the same thing: the hard part was never the list.
> It was the moment. The right question, at the moment a person can still act on it.
>
> That moment is the only thing Amigo does. Each reminder that gets a Done, a Skip, or a Later is
> a small, specific fact about when this person can actually follow through — and that is the
> thing no task app has ever been in a position to learn, because nobody opens a task app at the
> moment of truth.
>
> We are building the boring parts first: delivery that doesn't drop, state that stays consistent,
> and a bar for not being annoying. Then the interesting part gets a chance to be real.

This is the paragraph an investor will screenshot. It names the wedge, the data loop, and the
sequencing, without claiming any of it is shipped.

### 5.7 Open source strip

Copy unchanged from v1. Restyle to hairline links in `--ink`, arrow glyphs in `--ink-2`.

### 5.8 FAQ

Copy unchanged from v1 — six items, native `<details>`/`<summary>`, hairline dividers, no
JavaScript. Remove the v1 chevron/card styling.

### 5.9 Closing CTA + footer

`--sand` panel, `14px` radius, centred, no glow.

**H2:** `One message, when there is something to try.`
Form repeated (`variant="closing"`).

Footer: wordmark, `© 2026 Amigo`, `AGPL-3.0`, GitHub link. The `Privacy` link is **removed**
until a real privacy page exists — pointing it at `SECURITY.md`, as v1 allowed, mislabels
vulnerability-reporting instructions as a privacy statement on a page that collects email
addresses under a consent checkbox. Add the link back when there is a page to link to.

---
## 6. File plan

```
site/
├── index.html                   # charset, viewport, and the <!--seo--> placeholder
├── package.json                 # name: amigo-site, same scripts as web/package.json
├── vite.config.js               # entries, and the plugin that writes each <head> from meta.js
├── eslint.config.js             # copy web/eslint.config.js verbatim
├── public/
│   ├── favicon.svg
│   └── og.png                   # 1200×630, --oat ground, --ink wordmark + h1
└── src/
    ├── main.jsx                 # mirrors web/src/main.jsx
    ├── App.jsx                  # composes the sections in the order of Section 5
    ├── styles/
    │   ├── tokens.css           # the :root block from Section 4.1, nothing else
    │   └── site.css             # everything else
    ├── content/                 # every word the site says, and the per-page SEO
    │   ├── meta.js               # titles, descriptions, OG — vite writes each <head> from this
    │   ├── shared.jsx            # nav, footer, waitlist form, and the sentences said twice
    │   ├── home.jsx              # section 5 of this spec, as data
    │   ├── modes.jsx             # the modes page
    │   └── legal.jsx             # the privacy notice
    ├── lib/
    │   └── waitlist.js          # submitWaitlist(email) — the only network call on the page
    └── components/
        ├── SiteNav.jsx
        ├── Hero.jsx
        ├── WaitlistForm.jsx     # props: { variant: 'hero' | 'closing' }
        ├── TelegramDemo.jsx
        ├── HowItWorks.jsx
        ├── HonestyBlock.jsx
        ├── OpenSource.jsx
        ├── Faq.jsx
        ├── SiteFooter.jsx
        └── Reveal.jsx           # IntersectionObserver wrapper used by every section
```

Components hold structure; `src/content/` holds words. A component that carries its own copy
fails `tests/test_site_content.py`, and a page with no entry in `content/meta.js` fails the build
rather than shipping without a title. `sitemap.xml` and `robots.txt` are generated from the same
page list, so neither can be left behind when a page is added.

Conventions to match the existing `web/` code: function components with named default exports,
hooks from `react`, `lucide-react` for icons (already a dependency in `web/`; add it to `site/`),
plain CSS with BEM-ish class names — **no Tailwind, no CSS-in-JS, no component library.** The
repository has an established plain-CSS token system; introducing a second styling paradigm for
one page is not worth it.

### `render.yaml` — add a third service

```yaml
  - type: web
    name: amigo-site
    runtime: static
    buildCommand: cd site && npm ci && npm run build
    staticPublishPath: site/dist
    envVars:
      - key: VITE_WAITLIST_ENDPOINT
        sync: false
```

`render.yaml` is not on the protected list, but flag the change in the pull request description.

---

## 7. Responsive behaviour

| Breakpoint | Layout |
|---|---|
| ≥1024px | Content column `--max-w`. Hero text left, Telegram demo right (`grid-template-columns: 1.1fr 0.9fr`). Bento 3-up. Honesty block 2-up. |
| 768–1023px | Demo moves below the hero, centred. Bento 3-up becomes 2-up + 1 wide. Honesty block stays 2-up. |
| <768px | Everything single column. Hero `<br>` suppressed. Form stacks: full-width input, then full-width button. Honesty block stacks with the two column headings retained. Nav CTA shrinks to `Waitlist`. |

Minimum side gutter 20px at every width. Tap targets ≥44px. Nothing scrolls horizontally.

---

## 8. Waitlist submission

### 8.1 Phase 1 — no backend, no migration

`site/src/lib/waitlist.js` exposes exactly one function:

```js
export async function submitWaitlist(email) {
  // POST to import.meta.env.VITE_WAITLIST_ENDPOINT
  // Returns { ok: true } or throws an Error with a user-safe .message
}
```

Point `VITE_WAITLIST_ENDPOINT` at a hosted form provider that supports double opt-in
(Buttondown, Resend Audiences, and Formspree all do). **The founder chooses the provider and
sets the environment variable** — the implementer must not sign up for a service or paste a key
into the repository. If the variable is unset, the form renders in a disabled state with the
message `Waitlist signup isn't configured yet.` — the same fail-visible pattern
`web/src/components/AuthView.jsx` uses for missing Supabase config. Never silently no-op.

### 8.2 Phase 2 — Supabase-backed (not in this task)

A `waitlist_signups` table, RLS permitting anonymous insert only, and either a PostgREST insert
or a `POST /api/waitlist` route. This requires a new migration and therefore **explicit founder
approval** under the repository's guardrails, plus mirroring any new store method across
`MemoryStore`, `InMemoryStore`, and `FakeStore`. Keeping `submitWaitlist()` as the only call site
means Phase 2 touches one file.

### 8.3 Form behaviour, states, and consent

- Validate with `type="email"` plus a shape check; show errors inline, never in an alert.
- Disable the submit button while in flight; label swaps to a spinner. Never double-submit.
- **Success:** cross-fade the form to
  `Check your inbox. Click the link in the confirmation email and you're on the list.`
  (this wording only if the provider actually sends a confirmation — otherwise
  `You're on the list. We'll email you once, when Amigo opens.`)
  Move focus to the confirmation text so screen readers announce it. Do not show a fake counter,
  a queue position, or a referral gimmick.
- **Duplicate email:** treat as success. Never reveal whether an address is already stored.
- **Failure:** keep the entered email in the field, show
  `That didn't go through — try again in a moment.` Network failure and server failure get the
  same message.
- **Consent:** checkbox unchecked by default, `required`, label reading
  `Email me once, when Amigo opens.`
- **Retention:** state it in the FAQ answer (5.7) — addresses that never confirm are purged, and
  anyone can request deletion. Pick and honour a retention window with the founder; 24 months
  after last interaction is the common default for launch lists.
- **No third-party analytics, no tracking pixels, no cookie banner.** If measurement is wanted
  later, use a cookieless, self-hostable option and add it deliberately.

---

## 9. Guard tests

This repository's established pattern is a test that parses two artifacts and asserts they agree.
Add both of these under `tests/`, matching the existing style in
`tests/test_dashboard_snapshot.py` and `tests/test_activation.py`.

### 9.1 `test_landing_palette_is_the_approved_one`

**This replaces v1's `test_landing_tokens_match_the_dashboard`. Delete that test.** The site and
the dashboard now run different palettes on purpose (Section 4.1), so a test asserting they are
identical asserts something we no longer want. Do not keep it "just in case" — a guard that
contradicts the design is worse than none.

Parse the `:root` block of `site/src/styles/tokens.css` and assert it declares exactly the ten
tokens of Section 4.1 with exactly those hex values — no missing keys, no extras, no drifted
digits. This catches the two failures that actually happen: a token quietly deleted (every
`var()` referencing it silently falls back to nothing) and a hex nudged by hand without
recomputing contrast.

Add a second assertion in the same file: **no `.css` file under `site/src/` may contain
`box-shadow`, `backdrop-filter`, or `gradient(`.** Those three are the generic-look constraints
of Section 4.2, and they are the ones an implementer reaches for by reflex.

**Verify both assertions fail** when mutated — change one hex digit, then add a `box-shadow`.

### 9.2 `test_landing_copy_makes_no_unshipped_claims`

Read every `.jsx` file under `site/src/` and assert that a forbidden-phrase list does not appear
outside the honesty block's "not built" column. Suggested list, drawn from the roadmap column of
the capability matrix:

`"coming soon"`, `"early access"`, `"join the beta"`, `"your AI friend"`, `"remembers you"`,
`"learns your habits"`, `"therapy"`, `"therapist"`, `"coach you"`, `"mental health"`,
`"checks in on you"`, `"WhatsApp"`, `"voice"`, `"mobile app"`.

Case-insensitive. Exempt the `HonestyBlock.jsx` right-hand column and `Faq.jsx` answers that
explicitly negate a claim — implement the exemption by matching whole strings, not by skipping
whole files. **Verify this test fails** when you add `coming soon` to `Hero.jsx`.

---

## 10. Accessibility and performance

**Accessibility (non-negotiable):**
- One `<h1>`. Sections use `<section>` with `aria-labelledby` pointing at their `<h2>`.
- Every interactive element reachable by keyboard in visual order; the gold focus ring is never
  removed.
- The Telegram demo is decorative motion — wrap it in `aria-hidden="true"` and provide a
  visually-hidden text transcript of the same six messages immediately before it.
- Form errors use `aria-live="polite"` and `aria-describedby` on the input.
- Respect `prefers-reduced-motion` everywhere (Section 4.5).
- Run an axe scan before calling it done; zero violations.

**Performance budget:**
- Largest Contentful Paint < 1.8s on a simulated Fast 3G / 4× CPU throttle.
- Total JS ≤ 90KB gzipped. React + the sections fit; if you exceed it, the cause is a library you
  should not have added.
- No layout shift from fonts: `font-display: swap` plus a matched fallback metric.
- `og.png` ≤ 150KB. No other raster images — icons are `lucide-react`, the phone mock is CSS.
- Lighthouse ≥ 95 on Performance, Accessibility, Best Practices, SEO.

---

## 11. Acceptance checklist

Implementation is done when every line is true:

- [ ] `cd site && npm ci && npm run build` succeeds.
- [ ] `cd site && npm run lint` passes with zero warnings.
- [ ] `python -m pytest tests/ -v` passes, including the two new guard tests.
- [ ] `ruff check src tests scripts` passes.
- [ ] Both guard tests were confirmed to fail when their target is mutated.
- [ ] No file under `web/`, `src/`, `migrations/`, or `.env` was modified. `render.yaml` gains
      exactly one service block.
- [ ] `--signal` appears in exactly two places in the rendered page: the demo's reminder bubble
      and the waitlist submit button. Grep the CSS and confirm.
- [ ] No `box-shadow`, no `backdrop-filter`, no `gradient(` anywhere under `site/src/`.
- [ ] Column 3 of Section 5.5 carries its "direction, not promises" heading, is set in `--ink-2`,
      names no date, and uses no present-tense verb.
- [ ] Every capability claim on the page maps to the "Shipped in the current prototype" column of
      `docs/capability-matrix.md`.
- [ ] The page never says "beta signup", "early access", or "coming soon", and states no date.
- [ ] The non-clinical boundary notice is present and not hidden behind an accordion.
- [ ] Waitlist form: unconfigured state, loading, success, duplicate, and failure all verified by
      hand.
- [ ] Consent checkbox is unchecked on load and blocks submission when unticked.
- [ ] Renders correctly at 375px, 768px, 1024px, and 1440px with no horizontal scroll.
- [ ] Full keyboard pass: nav → form → checkbox → submit → FAQ → footer, focus always visible.
- [ ] `prefers-reduced-motion: reduce` shows the completed Telegram thread with no animation.
- [ ] axe: zero violations, including heading order (no `<h3>` before the first `<h2>`).
- [ ] Lighthouse ≥ 95 across all four categories.
- [ ] Fonts import the latin subset only; `dist` contains no Cyrillic/Greek/Vietnamese woff2.

---

## 12. Out of scope — do not build these

Blog, pricing page, docs site, authentication, a dashboard link, a cookie banner, third-party
analytics, a live waitlist counter, referral mechanics, a testimonial section (there are no
users yet), a countdown timer, a Supabase migration, any change to `web/`, or a privacy policy
written from scratch.

---

## Sources

- [10 SaaS Landing Page Trends for 2026 — SaaSFrame](https://www.saasframe.io/blog/10-saas-landing-page-trends-for-2026-with-real-examples)
- [8 Landing Page Design Trends for B2B SaaS in 2026 — SaaSHero](https://www.saashero.net/design/landing-page-design-inspiration-2026/)
- [15 Waitlist Landing Page Examples That Convert — LaunchList](https://getlaunchlist.com/blog/waitlist-landing-page-examples-that-convert)
- [Waitlist Landing Page Examples That Convert at 20% — Flowjam](https://www.flowjam.com/blog/waitlist-landing-page-examples-10-high-converting-pre-launch-designs-how-to-build-yours)
- [Waitlist Pages: One Field, and the Screen After It — 21st.dev](https://21st.dev/blog/react-waitlist-page-components)
- [Top Web Design Trends for 2026 — Figma](https://www.figma.com/resource-library/web-design-trends/)
- [App Landing Page Design Trends for 2026 — theswiftkit](https://theswiftk.it.com/blog/app-landing-page-design-trends-2026)
- [Double Opt-in for Waitlists — Waitlister](https://waitlister.me/features/double-opt-in)
- [Guidelines for a GDPR-compliant sign-up form — Brevo](https://help.brevo.com/hc/en-us/articles/360000454204-Guidelines-for-a-GDPR-compliant-sign-up-form)
- [A GDPR-conscious waitlist checklist for founders — DEV](https://dev.to/followtheduck/a-gdpr-conscious-waitlist-checklist-for-founders-43a8)
