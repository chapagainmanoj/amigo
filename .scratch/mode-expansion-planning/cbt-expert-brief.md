# Practitioner Collaboration Brief — CBT-Informed Thought Examination

Status: proposed scope for a prospective collaborator; nobody appointed; no clinical endorsement
Prepared: 2026-10-03

The founder is still looking for a practitioner and corrected the sequence: build a small research
MVP first, then recruit a practitioner and develop further research together. The initial MVP uses
provisional patterns, with no expert-validation claim; recruitment is not a prerequisite to its
engineering. This does not approve personal input or model-provider processing.

## Research goal

Study whether bounded AI-adaptive questioning can follow an explicitly reviewed CBT-informed
thought-examination method across different fictional everyday situations. Compare against a
fixed-question baseline rather than assume either approach is faithful to expert practice.

The founder is not a CBT expert and intends to involve a qualified practitioner. The desired
collaborator has verifiable relevant professional credentials, substantive CBT training and
practice, and experience evaluating guided questioning. Appropriate credentials depend on their
jurisdiction; no particular registration or individual is assumed to be sufficient.

This collaboration does not make Amigo a therapist, clinical service, monitored crisis service,
or treatment. Clinical study or commercial claims need a new governance/release decision.

## Already-selected scope

- Founder-only future experimentation; no customers or other participants.
- One everyday situation per run, one question at a time, optional steps and takeaway, immediate stop.
- In-memory personal input only; no saved inputs, generated replies, summaries, or content logs.
- Separate research harness, not the production catalogue, Reflect, or general Memory.
- Synthetic evaluation precedes personal input; personal-input/provider/safety gates remain open.

## What we need the practitioner to define

1. One specific non-clinical thought-examination framework, its boundaries, and appropriate claims.
2. Which situations fit it, which do not, and when thought examination should not continue.
3. Permitted question types, their purpose and preconditions, and examples of inappropriate use.
4. How to preserve guided discovery without leading answers, forced positivity, imposed conclusions,
   invalidation of real harm, pressure to disclose, or repeated questioning after a refusal.
5. Which sequencing/wording changes AI may make and which changes need additional review.
6. Exact start, skip, stop, discomfort, completion, limitation, and referral wording for review.
7. Source and licensing permission for any borrowed materials; no copying proprietary worksheets
   or assessment instruments into prompts or cases without permission.
8. A written review rubric and versioned synthetic scenarios, including failures and exclusions.

## Suggested engineering work after those choices

- Encode allowed question types/transitions and refusal/stop controls deterministically.
- Keep model adaptation inside that envelope; no side-effect Tools or other Mode histories.
- Record method/prompt/model versions and content-free run metadata only as approved.
- Compare fixed and adaptive responses on the same synthetic cases, with blind scoring where
  practical. Review each follow-up, not only the final answer or friendly tone.
- Treat any prohibited behavior as a failed run; do not hide it in an average helpfulness score.
- Have an independent engineering reviewer verify isolation, data handling, and boundary controls.

## Proposed review dimensions, not an established clinical scale

Question relevance to the stated situation; evidence for assumptions; appropriate timing and
sequence; non-leading language; respect for refusal and uncertainty; handling of actual harm;
stop/completion behavior; boundary adherence. The practitioner must revise and approve the rubric.
Agreement on simulated cases does not establish therapeutic efficacy or equivalence to a therapist.

The practitioner initially reviews synthetic dialogue only. Founder personal content is not saved
or silently sent to them. Any future live/supervised review needs a separate explicit arrangement.

## Starting sources, not our approved method

Beck Institute describes collaborative guided discovery rather than telling a person their thoughts
are wrong. It also discusses selecting techniques according to the situation, including cases
where thoughts are accurate. These support investigating applicability rather than imposing a
universal script; they do not certify an AI implementation or authorize all described techniques.

- [Guided discovery rather than challenging cognitions](https://beckinstitute.org/blog/why-cbt-therapists-dont-challenge-clients-cognitions-and-why-it-matters/).
- [Selecting techniques in CBT](https://beckinstitute.org/blog/selecting-techniques-in-cbt/).

Checked 2026-10-03. No source text or licensed clinical instrument has been reproduced here.

## Still open

Practitioner identity/credentials and responsibilities; exact method and review deliverables;
numeric bounds; model/provider data handling; safety resources; ethics requirements if scope grows;
and explicit approval before founder personal use. Research-only labeling is not approval.
