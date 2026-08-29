# Define the Proportionate Beta Privacy and Retention Contract

Parent: [Amigo Complete Product](../MAP.md)
Status: closed
Label: `wayfinder:grilling`
Type: HITL / grilling
Severity: `severity:critical`
Owner: unassigned
Blocked by: none

## Question

For a small US/Canada-focused invitation cohort, what data may Amigo retain, for how long, through
which processors, and through which founder-operated export, deletion, consent, and support paths?

## Comments

### Resolution — 2026-08-29

#### Data inventory

The beta may collect Dashboard Account email/auth identifiers/timestamps; Telegram chat identity,
Pairing state, and connection time; preferred name, timezone, and onboarding state; Messages,
Tasks, Reminders, and status changes; Session type/timestamps/summaries; submitted feedback and
contact permission; Telegram update IDs, redacted errors, delivery/latency/model usage/cost and
security/audit events; and export/deletion request evidence.

The beta does not intentionally collect contacts, precise location, government identifiers,
payment data, audio, photos/files, medical records, diagnoses, inferred health profiles,
advertising identifiers, durable semantic Memory, mood history, or coaching adaptation. Raw
Message/Task content is prohibited from routine analytics and logs. Onboarding warns participants
not to share medical, financial, identity, or emergency information.

#### Permitted purposes

Data may be used only for authentication and Pairing; conversation, Task, Reminder, Session, and
dashboard behavior; support/export/deletion; security and abuse prevention; privacy-minimized
reliability, Activation, cost, and aggregate beta measurement; and redacted failure diagnosis.
Amigo does not sell data, advertise with it, build unrelated profiles, train/fine-tune a general
model on participant content, or publish identifiable content/outcomes. New purposes require fresh
consent. De-identified evaluation examples require explicit permission and documented review.

#### Retention

- Pairing tokens expire after 15 minutes and consumed/expired records purge within seven days.
- Profile, connection, Messages, Tasks, Reminders, and Sessions remain during participation and
  delete within 30 days after closure/withdrawal unless access is extended.
- Identifiable feedback/interview notes delete or de-identify within 90 days after exit.
- Redacted application/error logs retain for 30 days.
- Security/access/deletion/audit events and identifiable usage events retain for 90 days; usage
  then deletes or irreversibly aggregates.
- Non-content aggregate metrics retain up to 12 months.
- Minimal deletion proof retains 12 months without conversation or Task content.
- Provider backups target no more than 30 days. Restores reapply completed deletion requests.
- Participants may request earlier deletion. Genuine legal preservation is disclosed when
  permitted.

#### Processors and cross-border processing

Disclose Telegram for transport/chat identity/buttons/delivery; Supabase for auth, database,
realtime, and backups; Google Gemini for Message and Turn Context processing; Render for hosting,
traffic, and operational logs; and the selected support-email provider. Add any future analytics
or error provider before it receives participant data. Data may cross state, province, or country;
Amigo does not promise US/Canada-only storage unless verified. Each processor receives only what
its function needs. Review provider retention/training settings before Gate B. Material provider
or purpose changes require updated notice and, where sensitive or unexpected, renewed
acknowledgment.

#### Consent

Before Pairing, require unchecked acknowledgment of the beta privacy/retention contract,
experimental limits, non-clinical boundary, processors/cross-border processing, and age 18+.
Record policy version, timestamp, and Dashboard Account. Necessary Core Loop processing is a
condition of participation; declining means the beta cannot operate. Research contact and use of
de-identified examples are separate optional choices. Mood journaling, reflective Memory, voice,
or sensitive wellbeing processing requires future separate opt-in. Withdrawal stops future
processing except what is needed to complete deletion, prevent fraud, or meet a genuine legal
obligation. Material purpose, processor, retention, or wellbeing changes require renewed
acknowledgment.

#### Founder-operated export

Accept requests from an authenticated dashboard action or verified account email, acknowledge in
one business day, re-verify ownership, and complete within seven calendar days. Supply a
human-readable summary and machine-readable JSON containing profile/Pairing metadata, Messages,
Tasks, Reminders, Sessions, feedback, consent history, associated usage events, retention schedule,
and processor list. Exclude secrets, abuse-sensitive security signals, and other participants'
data. Use a seven-day authenticated download, never a raw-content email attachment, then remove
the archive. Log requester, verification, categories, completion, and archive deletion without
copying content into logs.

#### Founder-operated deletion

Accept authenticated-dashboard or verified-email requests, explain scope, and require explicit
confirmation. Acknowledge in one business day and finish active-system deletion within seven
calendar days. On start, disable new Turns, cancel Reminders, revoke Pairing tokens, and unlink
Telegram. Delete/anonymize auth identity, Telegram Profile/connection, Messages, Sessions, Tasks,
Reminders, feedback, identifiable usage, consent records except minimal proof, exports, and caches.
Retain only non-identifiable aggregates and 12-month minimal proof. Backups age out within 30 days
and restored systems reapply deletions. Explain that Amigo deletion does not remove independent
Telegram/email/provider copies. Test deletion with seeded data before Gate B and after schema
changes.

#### Support, correction, and incidents

Publish a dedicated privacy/support email plus dashboard privacy, export, deletion, and correction
links. `/privacy` and `/help` point to the same resources. Acknowledge requests in one business day
and normally complete them within seven calendar days. Participants can correct preferred name,
timezone, Task data, and inaccurate account metadata. Maintain a content-free request ledger and
one founder escalation path. Cross-user access, exposed Pairing tokens, or incorrect deletion are
Critical incidents.

A suspected exposure pauses affected functionality and, if Critical, enrollment; preserves
redacted evidence; and revokes exposed credentials/tokens. Begin assessment within 24 hours and
notify affected participants without unreasonable delay after confirming material risk. Notices
state what happened, data categories, actions, participant steps, and contact path, without
unsupported assurances. Record investigation, decisions, notification, and remediation. Handle
jurisdictional notifications with proportionate professional advice. Enrollment resumes only
under the resolved stop/resume gate.
