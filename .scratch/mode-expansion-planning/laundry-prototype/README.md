# Throwaway Laundry Decision Prototype

Question: does combining participant-stated drying options, preference, urgency, washing window,
and fictional weather produce useful recommendations without pretending to know drying times?

From the repository root:

```bash
.venv/bin/python .scratch/mode-expansion-planning/laundry-prototype/prototype_cli.py
```

Use `--demo` to print eleven illustrative cases without interactive input. The keyboard menu lets
you toggle drying options and cycle preferences, urgency, time availability, and forecast state.
The full scenario and advice are rendered after every change; nothing is saved.

With rain expected and an outdoor preference: a suitable dryer wins; without a dryer, a flexible
deadline means postpone. An urgent deadline justifies asking about indoor drying. `[i]` declares
indoor drying available/suitable or removes it; `[k]` distinguishes unknown from explicitly ruled
out when it is absent. A rejected option is not asked about repeatedly. These are internal
discussion rules, not real-weather or deadline guarantees.

No dependencies beyond Python's standard library. No Gemini, Supabase, Telegram, weather service,
personal location, other Mode history, Task/Reminder Tools, or production imports. Forecasts are
fictional labels, not real weather or a validated freshness policy. Equipment must be declared
available and suitable; no actual drying duration, machine operation, or deadline is guaranteed.

This demonstrates explicit branching, not model intelligence or learned personalization. Trade-off
rules are intentionally exploratory. Do not copy them into production without reviewing the findings.

After the question is answered, capture the decision in NOTES.md and delete or deliberately absorb
the prototype. Recommender remains planned; no release gate is satisfied by this demonstration.
