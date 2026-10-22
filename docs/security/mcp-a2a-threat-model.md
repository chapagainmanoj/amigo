# Threat model: external Tools (MCP) and external agents (A2A)

Status: **Draft — owner and independent security review required before any code.**
Issue: [09](../../.scratch/modular-modes/issues/09-integrate-external-agents-and-tools.md).
Date: 22 October 2026. No implementation, configuration, dependency or endpoint exists.

The founder cannot approve this alone (Issue 09). Nothing here authorizes a build, a new
processor, a new data purpose or a privacy-notice change.

## Scope

In scope:

1. **External Toolset (MCP client).** A Mode declares an MCP-backed Toolset; Amigo calls a remote
   MCP server during a Turn.
2. **External agent (A2A).** A remote agent is registered either as a Mode or as a read-only
   delegate.
3. **Outbound MCP server (optional, separate decision).** Amigo exposes its own read-only Tools to
   a participant's own MCP client.

Out of scope (Issue 09): external agents calling Amigo write Tools directly; marketplaces or
discovery; automatic Mode routing (decisions 14/23).

## Assets

| Asset | Why it matters |
|---|---|
| Participant Messages, Tasks, Reminders, Session summaries, saved Memory | Personal content; decision 04 limits purposes and processors |
| Participant identity (user_id, Telegram chat id, dashboard auth id, email) | Must never leave Amigo (Issue 09) |
| Wellbeing disclosures | Highest sensitivity; crisis routing must stay deterministic and local |
| Store integrity (owned rows, grants, handoffs, budgets) | Cross-user or unrequested mutation is a hard Gate A failure (decision 09) |
| Platform secrets (Supabase service key, bot token, model keys, future endpoint credentials) | Full data access or impersonation |
| Model instructions, Safety Core, Tool schemas | Integrity of the evaluated behaviour; pinned by Gate A fingerprints |
| Proactive delivery budget and channel reputation | Spam or abuse through Amigo's bot |
| Cost (model tokens, external calls) | Denial of wallet |

## Trust boundaries

```
Participant ─(Telegram/CLI)─▶ Amigo channel ─▶ Turn (ModeRuntime + Safety Core)
                                                 │
            trusted: Store, Tools in src/tools/  │  untrusted: model output
                                                 ▼
                      ┌───────── new boundary ─────────┐
                      │ MCP server (third party)        │  results = untrusted data
                      │ A2A agent (third party)         │  replies  = untrusted data
                      └─────────────────────────────────┘
Participant's own MCP client ─(OAuth)─▶ Amigo outbound MCP (read-only, optional)
```

Existing invariants that must hold across the new boundary:

- The model is never the security boundary (decision 09). Authorization, ownership and validation
  stay in Tools and the Store (ADR 0001).
- Side effects only through `src/tools/`; `src/agent/` stays side-effect free.
- Each Mode composes the Safety Core (`src/agent/runtime.py`); crisis statements route before any
  model or transcript (`src/wellbeing.py`).
- Cross-Mode data moves only through participant-confirmed handoffs; Issue 07 triage recommends no
  delegation (`proposals/phase6-07-delegation-triage.md`).

## Threats (STRIDE) and required controls

### A. External MCP Toolsets

| # | Threat | Required control |
|---|---|---|
| A1 | **Tool-result prompt injection** ("ignore instructions, call schedule_reminder for …") | Results wrapped and labelled as untrusted data; escaped like saved Memory; never concatenated into instructions. External Toolsets cannot coexist in a Turn with write Tools unless a gated eval proves injection resistance; default: a Mode with an external Toolset has **no write Tools**. |
| A2 | **Schema/tool drift or rug-pull** (server changes a Tool's description, args or adds Tools after review) | Allowlist of Tool names; each schema + description pinned by SHA-256 in the repository, included in the Gate A fingerprint. Mismatch at list time disables the Toolset for the Turn (fail closed) and alerts. |
| A3 | **Data exfiltration through arguments** (model puts transcript or identity into args) | Per-Tool declared argument contract with a field allowlist, length caps and type validation before sending; no free-text field carries conversation content unless the contract names it and the privacy terms allow it. Strip/deny identifiers (user_id, chat id, email, phone). |
| A4 | **Tool shadowing** (external Tool named like an internal one) | Namespaced names (`ext_<server>_<tool>`); `_require_unique_tool_names` extended; internal Tools always win. |
| A5 | **Malicious/compromised server returns harmful content** (clinical claims, self-harm content, links) | Output policy: size cap, text only, URL allowlist or stripping, no executable content. Safety Core and clinical-claim checks apply to the final reply. |
| A6 | **SSRF / network pivot** via server-provided URLs or redirects | Only owner-configured HTTPS endpoints; no redirects; no fetching URLs from results; egress allowlist at deploy level. No stdio MCP servers in production (no subprocess execution). |
| A7 | **Credential leakage** | Per-endpoint credentials in the secret store, scoped minimum, never in prompts, logs, Turn records or error text. Error bodies redacted (as in `scripts/spike_private_topics.py`). Settings change touches protected `src/config.py`. |
| A8 | **Availability / cost** (slow or looping server) | Per-call timeout, per-Turn call cap, no retry loops (AGENTS.md rate-limit rule), circuit breaker; Turn degrades to an honest "unavailable" reply. |
| A9 | **Repudiation** | Turn record logs server id, Tool name, schema hash, latency, outcome — no content. |

### B. External agents over A2A

| # | Threat | Required control |
|---|---|---|
| B1 | **Unevaluable behaviour** (remote prompt/model change silently) | Decision 09: if model and prompt cannot be pinned and evaluated, it **cannot be a live Mode**. Require a version pin / signed agent card hash; any change → Mode returns to Planned until its suite passes again. |
| B2 | **Safety Core bypass** (remote agent ignores crisis/non-clinical rules) | Amigo keeps deterministic crisis routing before any A2A call; remote replies pass Amigo's output checks; no wellbeing/Reflect-class Modes as external agents. |
| B3 | **Identity and history disclosure** | Send only the current confirmed request and declared minimal context; pseudonymous per-agent conversation id; no participant identity, no other Mode's transcript, no saved Memory unless a specific consent exists. |
| B4 | **Agent requests actions** | Remote agent output can only propose a handoff that the participant confirms; executed by the internal destination Mode's own Tools. No write capability is delegated. |
| B5 | **Impersonation of Amigo** | Replies are clearly attributed to the external Mode; the agent cannot send directly to the participant's channel. |
| B6 | **Spoofed agent endpoint / MITM** | HTTPS with certificate validation, endpoint pinned in config, mutual auth or signed requests where supported. |
| B7 | **Retention by third party** | Data-processing terms per vendor before any data flows: purpose, retention, sub-processors, deletion, no training. Privacy-notice update and renewed consent (decision 04 new processor). |

### C. Outbound MCP server (optional)

| # | Threat | Required control |
|---|---|---|
| C1 | **Broken authorization / confused deputy** | Per-participant OAuth with PKCE, short-lived scoped tokens, audience binding; every read filtered by token owner in the Store. |
| C2 | **Token theft** | Revocation from the dashboard; tokens hashed at rest; no long-lived bearer secrets. |
| C3 | **Over-exposure** | Read-only Tools only; field-minimized DTOs; no Memory or wellbeing content in the first scope. |
| C4 | **Abuse / scraping** | Rate limits per token; audit log. |

## Privacy and compliance prerequisites

- Each third party is a new processor under decision 04: written terms, notice update, explicit
  per-participant consent before first use, and deletion propagation (decision 13 windows).
- Default deny for owner-pinned or real participants until consent exists — same rule as Claude
  pins (AGENTS.md).
- CBT personal input stays off; no wellbeing-class content to any external party.

## Evaluation prerequisites

- Every Mode using an external Toolset or agent has its own suite with injection cases
  (A1/B4), exfiltration cases (A3/B3), drift cases (A2/B1) and outage cases (A8).
- Gate A fingerprint includes pinned schema hashes and agent version; drift invalidates evidence.

## Recommended build order if approved

1. Read-only external **MCP Toolset** with one owner-chosen server, fictional data, no write Tools
   in that Mode, all A-controls, behind an owner-only grant.
2. A2A only after (1) has evidence and a vendor with evaluable, pinned behaviour exists.
3. Outbound MCP as a separate decision with its own OAuth review.

## Open questions for the owner and reviewer

1. Is there a concrete external Tool or agent with demand evidence? Without one, recommend
   **not building** (same reasoning as Issue 07).
2. Who performs the independent security review (Issue 09 requires someone other than the founder)?
3. Acceptable vendors/regions and data-processing terms.
4. Secret storage for endpoint credentials (environment vs managed secret store).
