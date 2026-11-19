# ADR-016 — Durable execution before analysis

Status: Accepted. Scope: M1.2 only, 2026-11-19.

## Decision

Keep the modular monolith. The API accepts `diagnostic` tasks; a separate Worker process
uses the same backend and database. No AI agent is registered, no source CSV is read,
and no report or chart is claimed. This explicit diagnostic contract will coexist with
future typed analytical inputs rather than accepting arbitrary code or task names.

`POST /api/v1/runs` requires a caller-generated UUID `request_id`. Repeated identical
requests return the same run and current status with 202; changing input with the same
key returns 409. The key is globally unique in this single-owner installation. Optional
UUID `correlation_id` groups related activity; it is not an idempotency key.

Runs progress `queued -> running -> completed | failed`. Claim a row in a short
transaction using `FOR UPDATE SKIP LOCKED`. Execution occurs outside that transaction.
Use a fresh attempt UUID per claim, a server-clock 15-second lease, heartbeat every
3 seconds, and a 45-second absolute attempt deadline. Diagnostic delay is bounded to
0–30 seconds. Ordinary diagnostic failure is terminal. Only expired/interrupted
claims retry, up to three attempts; exhaustion becomes `failed/attempts_exhausted`.

Lock the run before checking ownership on heartbeat/finalization. Verify current attempt,
status, lease and absolute deadline using PostgreSQL time; an expired worker cannot
renew itself or persist a late result, even before another worker claims the run.
Commit every state transition together with its execution event. Heartbeats do not
produce event noise. Read events by monotonic sequence cursor; gaps are valid.

SIGTERM stops polling/execution cooperatively and leaves interrupted ownership to expire.
A database failure leaves durable state authoritative; the Worker retries polling. If a
COMMIT response is lost, persisted state or lease recovery decides what happens next.
The Compose restart policy restarts a crashed process, but work stays queued while no
Worker is running. No availability guarantee is implied while the Mac is asleep.

## Traceability and history

`runs` retains current state and the latest attempt; `run_events` retains each start,
expiry and terminal event with its attempt ID. Correlation is obtained through the run;
structured logs include run/attempt/correlation IDs, without private input. No token or
cost values exist because there are no LLM calls in this slice.

On successful database/schema initialization, the actual Worker registers
`service:worker` and its `persists_to` link through the existing registry transaction.
This is initialization evidence, not a health heartbeat. Repeated starts are idempotent.
Run activity never enters `system_events`. Existing foundation history is preserved.

## Alternatives and limits

An in-memory queue loses work on restart; a broker adds infrastructure without a current
need. PostgreSQL explicitly describes `SKIP LOCKED` as suitable for queue consumers:
[SELECT locking reference](https://www.postgresql.org/docs/17/sql-select.html).

Delivery is at least once, not exactly once: interrupted execution can repeat. Attempt
fencing protects database results, not arbitrary external side effects. Future tools,
artifact publication and provider calls need their own idempotency and time bounds.
This diagnostic executor has no such side effects and does not introduce a generic
plugin runner, cancellation API, manual retry API or an attempts/telemetry subsystem.
M1.3 must add bounded deterministic tools and artifact semantics before real analysis.
