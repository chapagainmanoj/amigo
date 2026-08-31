# Choose the Invitation Cohort and Recruitment Protocol

Parent: [Amigo Complete Product](../MAP.md)
Status: closed
Label: `wayfinder:grilling`
Type: HITL / grilling
Severity: `severity:high`
Owner: unassigned
Blocked by: [Define Release Evidence and Gate Thresholds](01-release-evidence-and-gates.md), [Lock the Beta Promise and Capability Exclusions](02-beta-promise-and-exclusions.md), [Choose the Beta Offer and Support Contract](03-beta-offer-and-support.md), [Define the Proportionate Beta Privacy and Retention Contract](04-beta-privacy-retention.md), [Approve the Dashboard-First Activation Journey](10-dashboard-activation-prototype.md)

## Question

Where will Amigo recruit 5–10 qualifying US/Canada-focused participants, how will it screen for
the Target Segment and clinical exclusions, and how will founder intervention be recorded without
invalidating onboarding evidence?

## Comments

### Decision 1 — cohort size and staged admission

- Recruit eight qualifying participants plus a four-person waitlist, never exceeding 10 active
  Beta Participants in this cohort.
- Admit Wave 1 with three participants. Observe onboarding, support demand, and Reminder
  reliability for at least 72 hours. Admit Wave 2 with five more participants only while all beta
  stop conditions remain green.
- Use the waitlist to replace withdrawals and candidates who become ineligible; do not quietly
  enlarge the cohort.
- Seek representation from both the United States and Canada and at least two North American
  timezones without hard geo-blocking access.
- A friend or acquaintance qualifies only by independently meeting the Target Segment. Personal
  convenience is not an inclusion criterion.

### Decision 2 — recruitment sources

- Use warm second-degree referrals through the founder's professional and personal network in
  the United States and Canada as the primary source. Ask contacts to introduce a qualifying
  person rather than treating the contact as qualified.
- Use one or two small productivity/accountability communities that permit recruitment as the
  secondary source. Frame the need as abandoning task apps and wanting conversational follow-up;
  do not recruit through diagnostic, therapy, depression, crisis, or other clinical framing.
- Do not use paid advertising, Product Hunt, a broad public signup, or an uncontrolled public link
  for this cohort.
- At least four of eight participants must be at arm's length: not close friends, family,
  household members, employees, or people dependent on the founder. Admit no more than three
  participants from one source.
- Use the same short interest form and invitation copy. Record source, founder relationship,
  country/timezone, invitation date, and qualification outcome so recruitment bias remains
  visible.

### Decision 3 — screening and clinical exclusion

- Require age 18+, comfortable English use, United States/Canada location for this operational
  cohort, a personal email/Dashboard Account and Telegram account (or willingness to install it),
  everyday follow-through difficulty several times per week, abandonment of at least one
  conventional task/planner system, intended use for ordinary non-safety-critical Tasks, and
  availability for the 30-day beta plus baseline and D7 interviews.
- Exclude intended reliance on medication, emergency, legal, financial, caregiving, or other
  safety-critical Reminders; diagnosis, therapy, mood treatment, clinical guidance, or monitored
  crisis support; predominantly non-English support; shared accounts; automated/high-volume use;
  or adversarial security testing.
- Do not ask about diagnosis or medical history. A voluntarily disclosed diagnosis does not
  disqualify a candidate; intended use and support needs determine eligibility.
- Store structured answers and a short qualification reason. Avoid unnecessary sensitive free
  text and do not retain rejected-candidate data beyond the recruitment purpose and disclosed
  retention period.

### Decision 4 — Preflight Usability Panel and intervention

- Recruit a separate five-person Preflight Usability Panel before opening the invitation cohort.
  Panel members test only the Activation Journey in staging with synthetic test data under a
  short usability-testing disclosure; they are not yet 30-day Beta Participants.
- The founder observes silently and records timestamps, confusion, and assistance. Intervene only
  when the participant requests help, explicitly reports being stuck, or cannot progress for two
  minutes. Any intervention makes the run assisted and ineligible for the Gate-B four-of-five
  unassisted requirement.
- Record technical failures separately, but treat them as journey failures rather than participant
  errors. Manual resets or workarounds are assistance.
- A panel member may later enter the beta, but their repeated onboarding cannot count as
  first-time Activation evidence and their prior exposure must be marked.
- Delete staging panel data after retaining the minimized usability evidence required by the
  disclosed research purpose.

### Decision 5 — baseline and D7 research

- Before invitation, run a standardized 15-minute baseline interview without demonstrating Amigo
  or eliciting feature requests. Capture one recent follow-through failure, frequency and
  consequence, previously attempted systems and abandonment reasons, current workaround, one
  non-clinical seven-day desired outcome, and one observable success signal.
- D1 is an analytics/support checkpoint, not a mandatory interview. Collect participant-initiated
  `/feedback` and privacy-minimized operational events; the founder does not provide unsolicited
  personal coaching.
- At D7, run a standardized 20-minute interview. Revisit the baseline outcome through concrete
  examples; ask what worked, failed, confused, or felt intrusive; compare follow-through with the
  prior approach; ask what would be missed if access ended and whether the participant wants to
  continue. Record observed outcome, participant perception, trust concerns, and support burden
  separately.

### Decision 6 — Intervention Log and metric accounting

- Record a privacy-minimized Intervention Log entry with pseudonymous participant and Activation
  attempt identifiers, timestamp/stage, trigger, support category, intervention type, founder time,
  outcome, and linked issue/severity. Do not copy unnecessary conversation or sensitive content.
- Standard product copy, automated help available to everyone, and silent observation are not
  assistance. A hint, direct answer, walkthrough, screen share, token reset, admin mutation, or
  founder-performed product action makes that Activation assisted.
- An outage notice is not assistance, but the attempt remains a technical failure. Support after
  completed Activation does not change its classification and is tracked as support burden.
- Never remove assisted, failed, withdrawn, or incomplete attempts. Report them separately. The
  primary Activation denominator contains every eligible participant who starts the journey;
  assisted success is never counted as unassisted success.

### Decision 7 — research compensation

- Pay each Preflight Usability Panel member USD/CAD equivalent of $20 after the session and each
  Beta Participant $25 after completing the D7 interview.
- Compensation does not depend on liking Amigo, successful Activation, Task completion, continued
  use, or positive feedback. A participant who attends the scheduled research session is paid even
  if the product attempt fails. Withdrawal remains voluntary.
- Disclose compensation in invitation and consent materials. Do not pay referral bounties.
- Keep research compensation distinct from the free beta offer; this cohort does not test
  willingness to pay.

### Resolution — 2026-08-29

#### Operating cadence and enrollment control

- Maintain one restricted registry with explicit states: interested, screened, eligible,
  usability panel, waitlisted, invited, activated-unassisted, activated-assisted, incomplete,
  withdrawn, and completed.
- On every active beta day, review safety/security alerts, Reminder delivery and lateness,
  duplicates, Pairing failures, support backlog, and spend. Weekly, review Activation, D1/D7
  return, participant outcome progress, Intervention Log time, feedback themes, and unresolved
  issues.
- Admit Wave 2 only after Wave 1 has run for at least 72 hours with no stop condition, no open
  Critical or required High issue, Reminder reliability inside the approved gate, operational
  monitoring/scheduler heartbeat/kill switch/support, no support request beyond its response
  target, and manageable founder support demand.
- A stop condition immediately pauses new invitations. Existing access continues only when safe;
  incident handling may suspend an affected function or account. Resume only after the fix,
  regression evidence, and explicit founder approval required by ticket 01.
- At D7, explicitly continue, pause for fixes, or stop the cohort. At day 30, offer each
  participant the approved extension, waitlist, or account-closure choice.
