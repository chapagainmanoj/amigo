# Issue tracker: Local Markdown

Issues and PRDs for this repository live as Markdown files under `.scratch/`.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`
- The PRD, when present, is `.scratch/<feature-slug>/PRD.md`
- Implementation issues are `.scratch/<feature-slug>/issues/<NN>-<slug>.md`
- Issue numbering starts at `01` and follows dependency order
- Each issue records `Status:`, `Severity:`, `Type:`, and `Owner:` near the top
- Completion records the verification evidence and date in the issue
- Comments and history are appended under `## Comments`

## Publishing issues

When a skill says “publish to the issue tracker,” create an issue file under the appropriate
`.scratch/<feature-slug>/issues/` directory.

## Fetching issues

Read the referenced Markdown path. Users may identify an issue by its path or number.

## Wayfinding operations

Local Markdown has no native child, assignment, or dependency fields, so Wayfinder uses these
conventions:

- A map lives at `.scratch/<map-slug>/MAP.md` and carries `Label: wayfinder:map`.
- Child decision tickets live at `.scratch/<map-slug>/decisions/<NN>-<slug>.md`.
- Every child records `Parent: ../MAP.md`, `Status: open|closed`, `Type:`, `Owner:`, and
  `Blocked by:` near the top.
- `Owner: unassigned` means unclaimed. Claim a ticket by replacing it with the active developer
  or agent name before doing work.
- `Blocked by: none` means unblocked. Otherwise, list relative links to blocking decision files.
- The frontier is every child with `Status: open`, `Owner: unassigned`, and no open blocker.
- Resolve a ticket by appending a dated resolution under `## Comments`, setting `Status: closed`,
  clearing its claim, and adding a one-line linked gist under the map's `Decisions so far`.
- Create all child files before wiring dependency links so every blocker has a stable path.
- Concurrent sessions must re-read child metadata before claiming or changing a ticket.
