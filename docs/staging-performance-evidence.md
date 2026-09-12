# Staging Performance Evidence

This procedure closes the runtime-measurement portion of Internal Preflight issues 13 and 16. It
must run only against dedicated staging Telegram, Supabase, dashboard, and model resources. Never
send the workload to participant accounts or the beta-intended production bot.

## Required comparison

Run the same workload against two explicitly recorded revisions and the same staging topology:

1. The last synchronous-Supabase revision (the before candidate).
2. The native-async-Supabase revision (the after candidate).

Record revision, deployment ID, UTC start/end, Render plan/region, Supabase project/region, model,
prompt revision, test identities, and operator. A missing before run remains **Unknown**; do not
represent it as zero or infer it from `/health` latency.

## Workload

Run three consecutive trials. Each trial represents 10 dedicated test participants and includes:

- five simultaneous Turns with an ordered follow-up for each participant;
- 10 authenticated dashboard snapshots;
- 10 Reminders due within one minute, five while Turns are active;
- one replayed Telegram update; and
- one declared transient dependency failure.

The trial must verify final Task/Reminder state, update-claim uniqueness, delivery attempt
outcomes, scheduler/outbox drain, and absence of duplicate or cross-participant effects. Preserve
only content-free identifiers and timings in evidence.

## Measurements

Capture application logs from the exact trial interval. Store operations emit
`database_operation`, `outcome`, and `duration_ms`; the runtime monitor emits
`event_loop_delay_ms`. Summarize each interval with:

```bash
python scripts/summarize_runtime_evidence.py trial.log > trial-summary.json
```

Also record Turn latency, Reminder lateness from `get_reminder_reliability_health`, HTTP error and
timeout counts, Render CPU/memory, Supabase connections, queue utilization/rejections once those
limits exist, and whether all work drained. Do not mix warm-up or unrelated traffic into a trial.

## Pass evidence

For every trial, record p50/p95/max and sample count. The representative burst requires:

- event-loop delay p95 at most 50 ms and max at most 250 ms;
- Turn latency p95 at most 15 s and max at most 30 s;
- healthy-provider Reminder lateness p95 at most 10 s and max at most 30 s;
- no incorrect, duplicate, cross-participant, unexpected-error, timeout, restart, or rejection;
- at least 20% CPU and memory headroom, no connection exhaustion, and fully drained work; and
- the injected failure recorded with the approved bounded outcome/reconciliation behavior.

Attach raw content-free logs, summaries, state assertions, and resource screenshots/exports to the
issue evidence. A failed or incomplete trial does not pass by retrying an unchanged candidate.
