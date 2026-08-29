# Capture the Render and Supabase Runtime Baseline

Parent: [Amigo Complete Product](../MAP.md)
Status: closed
Label: `wayfinder:task`
Type: AFK / task
Severity: `severity:high`
Owner: unassigned
Blocked by: none

## Question

What event-loop delay, database latency, Reminder lateness, connection use, CPU, and memory does
the current Render/Supabase system exhibit under an explicitly documented beta-sized workload?

## Comments

### Resolution — 2026-08-29

Captured the currently deployed production topology and every metric exposed without changing or
redeploying the service. The result is a **topology/ambient baseline, not a representative
beta-workload baseline**: the deployed system lacks the instrumentation and always-on runtime
required to measure the ticket's core event-loop, database-call, and Reminder-lateness signals.
Treat an absent measurement as unknown, never as zero or passing.

#### Evidence scope

- Repository and deployed-revision inspection.
- Read-only Render and Supabase dashboards in the founder's existing signed-in browser.
- One warm public `/health` request followed by ten concurrent public `/health` requests.
- Render dashboard windows of 12 and 48 hours and Supabase's ambient last-60-minute window.
- No Telegram Turns, Task/Reminder mutations, secrets, deployment changes, or synthetic database
  workload were used. Therefore this run did not claim to be the Gate-B representative burst.

#### Deployed topology

- Render backend `amigo`: Docker web service in Singapore, Free plan, selected compute of 0.1 CPU
  and 512 MB RAM, one instance maximum/no scaling, and automatic spin-down after inactivity.
  Render warns that wake-up can delay requests by 50 seconds or more.
- The Docker command starts one Uvicorn process. Its FastAPI lifespan starts the in-process
  `AsyncIOScheduler`; there is no separate worker, durable scheduler, or external wake mechanism.
  When Render spins the instance down, Amigo cannot execute a due Reminder. An incoming request
  may wake the web service later, but a due in-memory job cannot wake it.
- Live Render revision was `177a437565932b35a4f91ebf037bc015635703d7` from branch `develop`,
  exactly matching repository `HEAD` at inspection time. Render reported no events in the prior
  12 hours and no instance data captured in the prior 48 hours, consistent with an idle/sleeping
  service. Outbound bandwidth for the billing month was 1 MB.
- Render Free hides historical application CPU and memory values. The service limits are known;
  actual process CPU/RAM under load are unknown.
- `fly.toml` remains deployable with a different production URL, but the inspected Render service
  was the live backend. This audit did not verify Fly machine state or Telegram's current webhook.
- `/health` returns process/environment liveness only. It does not verify Supabase, Telegram,
  scheduler heartbeat, pending jobs, or delivery ability.

#### Supabase topology and ambient snapshot

- Amigo project: Free-plan NANO (`t3a.nano`) primary database in AWS `us-west-2`/West US (Oregon),
  while Render runs in Singapore. This cross-region path adds unavoidable network latency and
  variance to every synchronous database call.
- Project status was Healthy. Dashboard snapshot: CPU 3%, disk 15%, RAM 51%, and 8 of 60 database
  connections in use.
- Organization usage showed a 27 MB database, 0 monthly active users, and 0 MB reported egress.
- The prior 60 minutes showed 48 total requests with 100% success: 27 API Gateway, 13 Realtime,
  5 Postgres, and 3 Auth. This was ambient founder/dashboard activity, not a controlled workload.
- Supabase showed no managed migration history and no scheduled backup. This does not prove the
  schema is absent—the SQL migrations were applied manually—but it means the dashboard has no
  migration lineage and no recorded backup evidence.

#### Request observations

The warm `/health` request completed in 190 ms. Ten concurrent requests all returned HTTP 200:

- Median total client-observed latency: approximately 142 ms.
- Minimum: 114 ms.
- Maximum and nearest-rank p95 for this ten-request sample: 400 ms.
- Connection setup ranged from approximately 9–15 ms.

These values prove only that a warmed process can serve a trivial endpoint. `/health` performs no
database/model/Telegram work and does not measure server queueing or event-loop delay; this tiny
sample is not a capacity result.

#### Requested metric disposition

| Metric | Current evidence | Disposition |
|---|---|---|
| Event-loop delay | No application instrumentation | Unknown |
| Supabase call latency | No per-operation timing/tracing | Unknown |
| Turn latency | No controlled synthetic Turns or tracing | Unknown |
| Reminder lateness | No scheduled-vs-delivered timestamps/metric | Unknown |
| Database connections | 8/60 during ambient dashboard activity | Observed, not load-tested |
| Render CPU/RAM | Free plan hides history; limits 0.1 CPU/512 MB | Unknown under load |
| Supabase CPU/RAM | 3% CPU/51% RAM ambient snapshot | Observed, not load-tested |
| Errors/timeouts | Supabase 48/48 successful ambient requests | Not representative |

#### Conclusion

The current Render Free topology is unsuitable for even a small Reminder beta regardless of
throughput: automatic sleep violates continuous scheduler ownership. There is no honest basis yet
for a safe concurrency number or Gate-B burst pass. Before invitations, Amigo must:

1. Use one always-on Render instance with exactly one scheduler owner.
2. Add event-loop, database-operation, Turn, Reminder-lateness, outbox/scheduler, CPU, memory,
   connection, error, and timeout instrumentation.
3. Create a staging environment or explicitly isolated synthetic identities/data.
4. Run the documented mixed 5–10-participant workload after the runtime-I/O and Reminder metric
   contracts are settled.
5. Record pass/fail evidence and safe backpressure limits; topology evidence alone is not a waiver.

This task is complete because it established what the current deployment can and cannot measure.
It unblocks the runtime-strategy and Reminder-reliability decisions; those decisions must not
reinterpret unknown performance values as an acceptable baseline.
