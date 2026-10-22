# Memory Inspector independent source and browser verification

22 October2026. Scope: MemoryInspector.jsx/CSS and AppShell navigation. Separate reviewer from UI
author. Existing Amigo review surface style retained. Parent ran the single detector pass; this
review did not repeat it or edit UI source.

Commands: `node /tmp/amigo-memory-preview.mjs` and `node /tmp/amigo-memory-verify.cjs`.
Retained source: `memory-inspector-independent-probes/preview.mjs` and `verify.cjs`.
Localhost5181 Vite preview used virtual auth/API modules and an empty envDir. Browser intercepted
all requests and blocked non-localhost hosts. All participant data and mutation outcomes fictional.
Preview server stopped; browser/context closed. No Supabase, Telegram or model requests.

Two viewport results: desktop1440×1000 and mobile390×844. Both passed:

- All three saved versions, state filtering, provenance and expanded version-specific use history.
- Complete JSON/CSV downloads and spreadsheet formula escaping.
- Separate learning/use pauses; master Pause all sends both Boolean flags and expected version.
- Exact edit and explicit scope preview, read-only review, no silent content mutation in preview.
- First opt-in cannot confirm before explicit checkbox; request includes enable_memory=true and
  memory-explicit-v1 policy version alongside the exact first item token.
- Stale/uncertain action locks writes and exports; refresh restores controls. Failed first save
  creates no item, and a fresh preview/checkbox supports retry.
- Saving admission OFF disables saving while inspection, pause/export/forget rights remain usable.
- Item and Forget all require separate explicit checks and show the limited Saved Memory scope;
  forgetting never claims Conversation Messages, summaries or provider-copy deletion.
- Zero page errors and no horizontal overflow. Current mobile screenshots show normal top header,
  readable reflow and touch controls; desktop preserves incumbent sidebar and hierarchy.

Evidence: `.impeccable/review/memory-inspector/verification.json`; desktop.png/mobile.png;
desktop-first-opt-in.png/mobile-first-opt-in.png; both viewport JSON/CSV downloads.
One initial batched pass and one confirmation batch. Confirmation corrected only preview fixture
metadata (goal_state and dates) and screenshot scroll position, then added master-pause assertion;
no UI change resulted from this reviewer. Fictional preview expiry is2099 to keep tests stable;
actual ten-minute token expiry is a backend contract and is not certified by these screenshots.

Source verdict: no blocking defect found in reviewed UI. Native labels/controls, focus on exact
review, explicit destructive scope, optimistic versions, bounded action state and conservative
stale lock align with the application contracts. This is mocked browser behavior, not backend
integration, complete accessibility conformance or a release/privacy-readiness certification.

## Focus correction check

A separate finish reviewer found Edit/Forget inserted panels above the inventory without moving
keyboard focus. Parent added heading refs and tabIndex=-1; effects depend on operation/item IDs,
not text. Focused corrective browser command: `node /tmp/amigo-memory-focus.cjs` (retained focus.cjs).
Desktop1440×1000 and mobile390×844 both PASS: Edit heading receives focus; filling and typing
additional characters keeps textarea focus and exact text; Forget heading receives focus.
`focus-verification.json` and merged `verification.json` contain all three true fields per viewport.
No additional screenshots, detector run or broader defect pass. Local preview stopped/browser closed.
This correction supersedes the earlier source-only no-blocker verdict on panel discoverability.

Fresh no-history Impeccable finish reviewer `/root/impeccable_finish_reviewer` reviewed both required
captures/source and found one material keyboard/task-discovery defect: Edit/Forget panels appeared
above inventory without moving focus. Root fixed heading refs/tabIndex and effects keyed to item
identity/operation, not typed text. Focused corrective browser checks pass on desktop/mobile:
Edit heading focus, textarea typing retains focus/text, Forget heading focus. No additional defect
hunt or detector run. Fresh reviewer verified exact source and focus-verification.json; final
**disposition: ship**, no remaining material finding. Existing design artifacts preserved.
