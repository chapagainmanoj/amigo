# Synthetic research-flow design preview — throwaway

Question: does a fixed, fictional fact-versus-interpretation flow make explicit start, one question
at a time, backtracking, an optional takeaway, and immediate stop/exit understandable?

This explores **flow controls only**. It is not a qualified-reviewed Thought Check/CBT exercise,
a personal-use version, a live AI mode, a research protocol approval, or evidence of safety or
clinical usefulness. Founder-only personal experimentation is the intended later audience;
this preliminary preview accepts only fixed fictional examples and menu keys.

Run from the repository root:

```bash
.venv/bin/python -B .scratch/mode-expansion-planning/cbt-research-prototype/prototype_cli.py
```

Use `--demo` for a deterministic printed walkthrough. No new runtime or dependencies are needed.
The preview runs directly from scratch, not through Amigo's CLI or production registry.

## Scope

- Two original fictional everyday examples; no personal-content field or user-authored scenarios.
- Menu-key input only; unrecognized strings are rejected and never stored in flow state or echoed
  by the application. **Do not paste personal text:** an interactive terminal itself echoes typed
  characters and may retain them in scrollback. This is not a secure sensitive-input surface.
- In-memory state only; no data files, transcript, analytics, model, network, `.env`, database,
  scheduler,
  participant lookup, production imports, Task/Reminder/Memory Tools, or Daily handoff.
- `s` clears selections and stops; `q` clears selections and exits. `b` returns to the preceding
  step and clears that step's answer. Restart after completion/stop requires the preview notice.
- No crisis classification or claimed support is implemented: there is no personal-content channel.
  A later personal-use harness needs reviewed stop/referral behavior and its own data gate.

The `-B` flag also avoids Python's ordinary bytecode-cache writes. The logic module is a pure async
reducer; the thin CLI handles rendering and menu input. Read
[NOTES.md](NOTES.md) before considering reuse. Nothing here registers `cbt_research` or authorizes
founder personal content. Delete the shell or absorb only a deliberately validated design after
the question has been answered; do not quietly promote the preview into production.
