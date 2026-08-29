# Choose the Project Source License and Contribution Contract

Parent: [Amigo Complete Product](../MAP.md)
Status: closed
Label: `wayfinder:grilling`
Type: HITL / grilling
Severity: `severity:high`
Owner: Codex
Blocked by: [Define Customer Readiness and the Sustainable Offer](12-customer-readiness-and-pricing.md)

## Question

Should Amigo remain unlicensed/source-visible, adopt a permissive license, adopt network
copyleft, or use another reviewed licensing model, and what contribution and security-reporting
contract must exist before calling the project open source?

## Comments

- The hosted-first commercial model does not itself decide source licensing.
- Until this ticket is resolved and the selected license is present, public copy must not call
  Amigo open source or promise supported self-hosting.

### 2026-08-29 — License family

- Founder decision: license the project under AGPL-3.0.
- Intent: permit use, study, modification, and redistribution while requiring operators that
  provide a modified version over a network to offer the corresponding source under the same
  license.
- This decision does not by itself promise a supported self-hosted product. Hosted Amigo remains
  the commercial offer, and self-hosting support must be described separately.
- Amigo must not be described as open source until the actual license text is present in the
  repository and public notices have been made consistent with it.

### 2026-08-29 — Contribution attestation

- Accept external contributions under the repository's AGPL-3.0 license using Developer
  Certificate of Origin 1.1 attestation through a `Signed-off-by` commit trailer.
- Do not require a Contributor License Agreement for the current project stage.
- `CONTRIBUTING.md` must explain the sign-off command, what the attestation means, review and test
  expectations, and that submitting a change does not guarantee acceptance.
- If Amigo later needs proprietary dual licensing, reassess the contribution agreement before
  accepting contributions intended for that model; do not silently reinterpret prior grants.

### 2026-08-29 — Security reporting

- Use GitHub private vulnerability reporting as the primary public reporting route. Do not direct
  reporters to a founder's personal email address.
- `SECURITY.md` must identify supported versions, explain how to open a private report, request
  reproduction and impact details without requesting unnecessary personal data, and ask for
  coordinated disclosure until a fix or agreed disclosure date.
- Target acknowledgement within three business days and an initial assessment within seven
  business days. These are response targets, not guarantees that a fix will exist by then.
- Do not advertise a bug bounty, payment, broad legal safe harbor, or guaranteed remediation time
  unless a separately reviewed program actually exists.
- Public issues and chat support are not acceptable places for unpatched vulnerability details;
  redirect accidental public reports to the private channel and minimize further exposure.

### 2026-08-29 — Repository scope and resolution

- Apply AGPL-3.0 to Amigo's original source code, scripts, and documentation across the
  repository.
- Third-party dependencies, vendored materials, trademarks, and assets retain their applicable
  licenses or rights and must be identified rather than relicensed by implication.
- Add the canonical AGPL-3.0 license text at the repository root and use concise source-file
  notices only where tooling or distribution context makes them useful; do not require boilerplate
  headers in every file.
- The license decision is closed. Milestone 0 remains responsible for adding and checking the
  actual `LICENSE`, `CONTRIBUTING.md`, and `SECURITY.md`, enabling GitHub private vulnerability
  reporting, and reconciling public open-source and self-hosting language.
