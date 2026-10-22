# Participant model choice and keys

Status: deferred
Date: 2026-10-22

Owner configures models per environment and Mode. Participant pins are restricted to owner and
internal dogfooding accounts. Participants cannot bring keys or choose a model in this release.

The small invitation audience does not justify provider/key support load or key liability.
Decision 04 requires updated processor disclosure and renewed consent before participant data
reaches Anthropic. Decision 09 requires per-Mode/model evaluation of tools, resulting state,
safety and language behavior. An owner pin does not authorize extending a processor to external
participants. Claude subscription CLI remains development-only; production Anthropic uses only
the platform key. Revisit when participants request model choice, after resolving consent,
per-model evaluation coverage, secret storage/liability, and support ownership.
