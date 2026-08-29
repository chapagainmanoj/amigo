# Choose the Channel Expansion Priority

Parent: [Amigo Complete Product](../MAP.md)
Status: closed
Label: `wayfinder:grilling`
Type: HITL / grilling
Severity: `severity:medium`
Owner: Codex
Blocked by: [Choose the Invitation Cohort and Recruitment Protocol](11-cohort-and-recruitment.md), [Define Customer Readiness and the Sustainable Offer](12-customer-readiness-and-pricing.md)

## Question

Given beta demand and cost, should Amigo expand first through WhatsApp, voice, a PWA, a native
mobile application, or no additional channel, and what common capability contract is required?

## Comments

### 2026-08-29 — Surface Expansion taxonomy

- Messaging Channel means the service carrying conversational Messages and Reminders, initially
  Telegram and potentially WhatsApp.
- Interaction Modality means how a participant communicates within a supported surface, initially
  text and potentially voice.
- Client Surface means the application UI, initially the dashboard and potentially a PWA or native
  mobile application.
- Surface Expansion is the umbrella portfolio containing all three categories. WhatsApp, voice,
  PWA, and native mobile are not equivalent alternatives and do not receive a winner-takes-all
  ranking.
- Voice may first exist within Telegram; a PWA may improve dashboard access without becoming a
  Messaging Channel; native mobile must justify itself against the responsive dashboard/PWA.
- Keep the existing MessageChannel concept focused on messaging. Define explicit modality and
  client capabilities instead of forcing them into that abstraction.

### 2026-08-29 — Demand gates

- WhatsApp enters implementation only after at least three otherwise-qualified prospects refuse
  or abandon Amigo specifically because Telegram is required. Record these recruitment exclusions.
- Voice enters implementation only after at least three participants repeatedly attempt voice
  input or demonstrate a recurring situation where typing blocks the Core Loop.
- PWA enters implementation only after at least three repeated mobile-dashboard participants
  demonstrate that installation, push access, or weak connectivity materially limits use.
  Responsive mobile layout is baseline work, not a PWA demand signal.
- Native mobile enters implementation only after at least five participants demonstrate a
  recurring need that responsive web or PWA cannot reliably satisfy, such as OS-level notification
  control, background audio, or deeper accessibility integration.
- Hypothetical preference does not count. Require observed friction, attempted behavior,
  abandonment, or repeated use.
- If several gates pass, rank expected Core Loop/retention improvement, affected participants,
  delivery risk, recurring cost, and founder support burden. Implement one expansion at a time.
- No Expansion Yet is the default when no gate passes. All options remain on the destination map,
  and Not Yet or Do Not Build is a valid outcome.

### 2026-08-29 — Surface Capability and primary delivery

- Every Messaging Channel, Interaction Modality, and Client Surface declares support for inbound
  and outbound text, actions, delivery acknowledgement, message editing, audio, deep links,
  notifications, accessibility, and explicit fallback behavior.
- Maintain one canonical participant identity, consent state, Task and Reminder state, Memory,
  Mode state, quiet hours, and Notification Budget. Provider, chat, and device identifiers are
  linked endpoints rather than user identities.
- A participant may send from any linked Messaging Channel and receives the conversational reply
  there. Exactly one Primary Messaging Channel receives proactive Messages and Reminders; never
  fan out by default.
- Changing the Primary Messaging Channel is explicit and atomic. Pending Reminders resolve the
  primary endpoint at delivery time.
- An action from an older channel Message remains idempotent and resolves against canonical state.
  All channels share the one-active-Turn-per-user ordering rule.
- Export, deletion, consent, mute, and safety behavior propagate across linked endpoints.
- Core Loop semantics remain consistent across surfaces even when their presentation and
  capability fallbacks differ.

### 2026-08-29 — Current portfolio decision and evidence collection

- The current decision is **No Expansion Yet**. Complete the Telegram Core Loop external beta
  before implementing WhatsApp, voice, PWA, or native mobile. Responsive and mobile-accessible
  dashboard work remains baseline UX.
- During recruitment, record otherwise-qualified prospects excluded specifically by Telegram.
  Record content-free unsupported-input events such as voice attempts, plus mobile dashboard use,
  performance failure, and notification/access friction.
- Ask about observed channel and modality problems in baseline and D7 interviews without pitching
  solutions. Review the evidence after both beta waves.
- When several gates pass, prioritize Core Loop access blockers, then repeated interaction
  blockers, then retention/notification problems, then convenience improvements.
- Open only the matching WhatsApp, voice, or mobile decision ticket after its demand gate passes.
  Keep controls labelled Planned without dates or coming-soon promises.

### 2026-08-29 — Common release gate and resolution

- The expansion's demand gate and specialized decision ticket must close before implementation.
- Document and test its capability manifest and every unsupported-capability fallback.
- End-to-end coverage must pass for identity linking, inbound conversation, Task creation,
  Reminder delivery, Done/Skip/Later, Primary Messaging Channel switching, stale actions, mute,
  consent, export, deletion, and safety behavior.
- Permit zero duplicate or cross-account Messages/Reminders and zero canonical-state divergence.
  Reminder delivery must meet the same healthy-provider reliability and lateness thresholds as
  Telegram.
- All five moderated participants must understand the proactive-delivery endpoint; at least four
  must link, switch primary delivery, complete the Core Loop, mute, and disconnect without help.
- In a 14-day, at-most-five-participant trial, at least three must complete the Core Loop on three
  separate days and choose to retain the expansion.
- Variable cost and founder support stay within the approved 25% and 15-minute thresholds. Roll out
  one expansion at a time behind a kill switch.

Stop for identity confusion, duplicate delivery, missed actions, state divergence, privacy or
safety regression, unsupported-fallback failure, or unsustainable cost/support. The current
portfolio outcome remains No Expansion Yet until observed beta evidence opens a child decision.
