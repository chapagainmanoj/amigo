# Next slice: real-model selection on synthetic CBT-research fixtures

Status: proposed planning only; no adapter implemented or model/API calls authorized/executed
Prepared: 2026-10-03

Build the small engineering MVP first, then collaborate with a qualified practitioner on method
and research. Recruitment does not block this slice. Neither scripted nor real-model success
establishes expert validation, clinical usefulness, or permission for personal input.

## Facts from the current code

- No current `ModelProvider` protocol or `GeminiProvider` class was found in repository Python
  sources. [ADR 0002](../../docs/adr/0002-agentic-tool-calling-loop.md) supersedes them with
  Pydantic AI behind an owned application interface. Do not revive obsolete provider APIs.
- [`src/agent/runtime.py`](../../src/agent/runtime.py) selects Google via a `google:` model
  identifier. Its `ModeRuntime` requires registered live Modes and ToolContext; it returns opaque
  framework messages, emits Turn telemetry, and may retry an unavailable primary once before
  an approved fallback. Framework `Agent(retries=1)` is also an output/validation retry budget,
  not that separate transport retry. `provider_unavailable` accepts connect/timeouts and HTTP
  408/429/5xx; refusal, auth errors, and invalid output are not availability errors.
- [`src/turns.py`](../../src/turns.py) persists participant/reply Messages and loads Session
  history. The research harness must **not** call this path, synthesize a participant identity,
  register `cbt_research`, or import its production default runtime.
- [`src/telemetry.py`](../../src/telemetry.py) disables framework content capture and additionally
  allowlists span attributes/events, suppressing exception text/status descriptions. The extra
  filtering matters: `include_content=False` alone is not the tested privacy boundary. Existing
  sentinel coverage is in [`tests/test_mode_policy.py`](../../tests/test_mode_policy.py).
  No exporter is installed there, but an operator-installed global exporter can receive spans.
- [`scripts/run_gate_a_eval.py`](../../scripts/run_gate_a_eval.py) demonstrates explicit
  `GoogleModel(..., provider=GoogleProvider(api_key=...))` construction and request spacing.
  It is **not** a private research runner: evidence writes include traces/replies, and incident
  records can include `str(error)`. Do not reuse its evidence writer or ordinary Turn orchestration.
- Installed SDK inspection only: `pydantic_ai/providers/google.py` creates a google-genai Client
  with explicit timeout derived from its HTTP client; google-genai `_api_client.py:retry_args`
  uses one attempt when retry options are absent. Configured retry options can enable retries
  with exception-bearing sleep logs; some SDK debug paths also log request information. These
  local facts do not prove all SDK/HTTP logging is content-free or any provider-side retention.

No secrets were read and no provider request was made during this planning inspection.

## Minimum candidate adapter

Keep a separate research entry point next to the synthetic MVP, not production Modes. Add a small
async question-selector interface with the existing scripted implementation and a real-model
implementation. It receives only the selected **allowlisted fictional fixture**, consumed fictional
responses, already asked/skipped pattern IDs, and the remaining explicit engineering budget.
No arbitrary input, file upload, Session context, Tasks, Memory, or participant lookup.

The model selects a permitted next **question ID**, not free-form question wording, an exercise,
clinical conclusion, assessment, rationale, or takeaway. Proposed structured output:

```json
{"question_id": "uncertainty"}
```

For each state, compute eligible next IDs deterministically before the call. Strictly validate
the output object (required enum field, extra fields forbidden); then independently enforce
eligibility, non-repeat, and remaining budget. Render the existing versioned question text locally.
Even a syntactically valid allowed ID cannot bypass state constraints. Fixed baseline remains
deterministic and makes no provider calls; only the adaptive candidate calls the model.

Suggested Pydantic AI shape: standalone typed-output Agent, no Toolsets/deps/history, explicit
GoogleModel/GoogleProvider construction, `retries=0`, explicit model/output-token/timeout settings,
one request per selection and no automatic fallback. Structured-output mechanisms used by the
SDK are not permission for application Tools; verify the actual outbound declaration/request.
This requires no change to `src/config.py`, Daily model policy, production runtime, or schema.

## Privacy and failure handling

- Credentials only from a specifically approved environment variable at explicit launch; do not
  load `.env` through shared Settings or expose keys in arguments/stdout/errors. A plan does not
  authorize use of any available credential. Pin provider/account and model explicitly; no alias
  chosen by production defaults and no fallback provider or alternate data destination.
- Use reviewed content-free instrumentation or disable harness instrumentation/exporters entirely
  for the first slice. Clamp SDK/HTTP logger levels and test the request/error paths; do not assume
  application log filtering controls every dependency or global instrumentation hook.
- Return a small owned result: selected ID, requested/observed model, token counts, latency,
  availability/validation outcome, exception **class** and numeric status only. No raw framework
  message lists, exception bodies, stack-local dumps, prompt, response body, headers, or API key.
- No transcript/evidence files by default. Display only fixture IDs, selected question IDs,
  bounded metrics, and pass/fail. Any persistent metadata artifact needs an explicitly selected
  location/schema; no reuse of Gate A's raw evidence writer. Synthetic content can be reviewed
  as versioned fixtures without saving provider transcripts.
- Provisional first real-model budget: at most four selections/transport requests per run,
  zero provider or validation retries, no fallback. Timeout/408/429/5xx terminates that run with
  content-free availability failure. 400/401/403/refusal/malformed output terminates without retry;
  distinguish categories for engineering measurement, never treat failure as passing adherence.
  No retry/backoff loop. A later once-only transport retry requires an explicit total-call/cost
  budget and SDK-level count verification, consistent with the repository's one-retry ceiling.
- Stop before dispatch does not send another request; stop during an in-flight request cancels
  locally and discards its output. Cancellation cannot retract data already sent to the provider.
  This caveat is mandatory before eventual personal-use approval.

## Offline tests before any paid/external run

1. Mock transport captures exact outbound inputs: only fixed fixture/current consumed answers and
   bounded instructions, never other Mode context, arbitrary strings, files, secrets, or Tools.
2. All allowed/invalid/extra-field/repeated/out-of-state IDs, prose instead of JSON, multiple
   questions, injected fictional instructions, clinical/treatment/Task requests, and disclosure
   bait fail closed without widening the output contract. Raw output is never shown as guidance.
3. Four-request bound includes failed attempts; SDK and framework retry settings cannot multiply
   requests. Timeout, rate limit, auth failure, malformed output, cancellation, and provider body
   sentinels yield only bounded safe metadata. Unknown observed-model cost stays unknown.
4. Capture stdout/logs/spans/events/status/error paths with sentinels and a mock global exporter;
   assert no prompt/reply/key/error-body content or saved files. Verify import/validate-only
   commands do not initialize a provider, read secrets, or dispatch network requests.
5. Synthetic cases compare sequence appropriateness against a provisional engineering rubric,
   not therapeutic outcomes. Crisis-language fixtures may test refusal/selection boundaries;
   they do not validate personal crisis handling or replace the separate static-referral gate.

## Exact approval needed for the first real-model synthetic batch

The owner must authorize **external processing and spend**, specifying provider/account and key
source, exact model, approved fixture/prompt/question-policy versions or hashes, run count and
maximum requests/output tokens/spend, timeout/request spacing, and permitted output/metadata
retention. Confirm applicable provider processing/retention settings before sending even the
fictional fixture batch. No API call occurs merely because adapter code or a key exists.

This approval excludes founder personal content, any other person, transcript retention,
production Mode registration, clinical claims, or commercial rollout. Founder personal use still
needs explicit personal-data/provider/safety protocol approval and verified access/stop/kill-switch/
referral controls. Practitioner collaboration follows MVP development; exact-method expert
validation remains unclaimed until performed.
