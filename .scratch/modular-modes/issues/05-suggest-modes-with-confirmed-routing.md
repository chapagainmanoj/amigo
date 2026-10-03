# Suggest a Mode with Participant-Confirmed Routing

Status: open
Label: `needs-info`
Severity: `severity:low`
Type: HITL
Owner: unassigned
Phase: 4 of 5 (part 1 of 3)
Blocked by: [04-build-coach-mode-with-coaching-program.md](04-build-coach-mode-with-coaching-program.md),
[../../amigo-complete-product/decisions/23-automatic-routing-and-adaptation.md](../../amigo-complete-product/decisions/23-automatic-routing-and-adaptation.md),
[../../amigo-complete-product/decisions/28-specialized-mode-routing-evidence.md](../../amigo-complete-product/decisions/28-specialized-mode-routing-evidence.md)

> Lighter spec. Expand with `to-spec` once the blockers close.

## Problem Statement

With explicit entry from issue 03, a participant has to know that a Mode exists and remember to
enter it. Decision 14 allows automatic routing only after two Modes independently pass their
release evidence, and only once explicit-selection evidence shows that switching friction is a
real problem (decision 28). Decision 23 must also approve it. Silent routing is currently
unapproved.

## Solution (direction)

A new routing policy, `SuggestThenConfirm`, adds a lightweight classifier step. When a Turn in one
Mode looks like it belongs to another Mode the participant can use, Amigo offers a one-tap switch.
It never switches silently. The suggestion reuses issue 03's confirmation mechanics. The routing
policy stays a replaceable component, so a fully automatic policy is a configuration choice if
decision 23 ever approves one.

## Key Decisions to Make

- **Classifier.** A separate cheap model call, a rule set, or a Tool on the current Mode. This
  affects cost per Turn (issue 02's Turn Record) and latency.
- **Suggestion limits.** How many suggestions per Session, and how declining one suppresses
  repeats.
- **Evaluation.** The routing policy needs its own suite: routing precision and recall, no
  suggestion for Modes the participant isn't granted, and no suggestion in the middle of a Crisis
  Referral.
- **Signals.** Which ones are forbidden. Following decision 14, sentiment, assumed mood, and silence
  can't be routing inputs.

## Out of Scope

- Silent automatic switching (unapproved).
- Interaction Style adaptation.

## Comments
