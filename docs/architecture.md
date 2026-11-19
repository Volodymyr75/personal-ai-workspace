# Architecture — M0 foundation

The backend is a modular monolith. M0 runs the API; a separate Worker will share its codebase/image in M1. The web shell uses Next.js and contains no fabricated operational data. PostgreSQL is internal to Compose. n8n is an inactive optional profile and is not registered by bootstrap.

## Boundaries

- `domain`: immutable foundation definitions and framework-free ports. No FastAPI, SQLAlchemy or provider imports.
- `application`: verifies prerequisites before requesting bootstrap.
- `api`: explicit versioned health/readiness response schemas.
- `infrastructure/db`: connections, migration-owned tables and transactional persistence.
- `cli`: explicit local administration entry point; there is no unauthenticated registry-write HTTP endpoint.

`GET /api/v1/health` is process liveness. `GET /api/v1/ready` checks database connectivity, expected migration revision and the three foundation tables. It returns 503 with a stable code on failure, without SQL, credentials or connection details. Probes do not write events.

## Actual evolution history

Bootstrap checks the running PAW API's health/readiness, then verifies its configured database and registers only `service:api`, `storage:postgres` and `link:api:persists_to:postgres`. Run it inside the API container so its settings refer to the same installation. This is point-in-time initialization evidence, not continuous health or measured traffic.

A PostgreSQL transaction-scoped advisory lock serializes registry bootstrap. All node/edge inserts and their registration events commit together. Stable keys and unique idempotency keys provide database duplicate protection. Existing entries are not renamed or reactivated by bootstrap. Missing history is an error, not an opportunity to fabricate a registration date.

Events contain sanitized full after-state snapshots. A trigger assigns server `recorded_at` even if an insert supplies a different value. Identity sequence breaks timestamp ties; gaps after rolled-back transactions are valid. PostgreSQL triggers reject UPDATE, DELETE and TRUNCATE of history. Administrative owners can still drop objects or disable triggers; this is not tamper-proof storage against a malicious DB administrator. Destructive migration downgrade is deliberately disabled.

Future mutation methods must use the same transaction/lock discipline, stable identities, allowlisted payloads and corrective events. Historical query APIs and replay are not implemented in M0.

## Event separation

Lifecycle history belongs in `system_events`. Execution belongs in future `runs`/`run_events` (M1). Recurring health, deployment and backup observations will use feature-specific storage later. React Flow layout and rendering choices remain outside the domain.

## Runtime and dependency choices

- Python 3.13.18, uv 0.13.9, reproducible `backend/uv.lock`.
- Node.js 24.22.3, exact direct dependencies and `frontend/package-lock.json`.
- PostgreSQL 17 image, API and frontend images pinned in container configuration.
- CI pins action revisions and one Gitleaks version; dependency updates are deliberate changes with revalidation.

See [ADR-014](adr/ADR-014-foundation-transactions.md) for implementation tradeoffs and [development.md](development.md) for checks.
