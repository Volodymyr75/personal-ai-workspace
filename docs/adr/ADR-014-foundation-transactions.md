# ADR-014: Foundation bootstrap and history enforcement

- Status: Accepted
- Date: 2026-11-19
- Scope: M0 only

## Decision

Use synchronous SQLAlchemy/psycopg in synchronous FastAPI routes. M0 has small bounded database operations; a second asynchronous persistence stack is unnecessary. Keep readiness as an injected domain port for offline API tests.

Run Alembic as a separate one-shot Compose service before API startup. Do not silently migrate on each HTTP request or each future worker startup. Bootstrap is a separate explicit CLI operation that checks the running API and the database before registering the known foundation components and logical link.

Serialize registry mutation through one PostgreSQL advisory transaction lock and commit projections plus event snapshots together. Add database uniqueness for component/link identities and registration idempotency. This is simpler than per-entity concurrency control for this very small registry, and concurrent bootstrap is covered by actual PostgreSQL tests.

Enforce server-recorded timestamps and append-only events using PostgreSQL triggers. Historical mutation or destructive downgrade is rejected; future corrections append events. Locks are transaction scoped, so a failed process releases them on rollback. The mechanism does not pretend to protect against a malicious schema owner.

## Alternatives and consequences

An in-memory registry or SQLite-only tests would not establish PostgreSQL atomicity or concurrency behavior. A generic event-sourcing framework and event broker are unnecessary. Automatic bootstrapping on each app import could register an API that never becomes usable.

Bootstrap trusts the explicitly configured local API URL and shared deployment configuration; it is not a cryptographic remote-attestation protocol. Run it inside the API service. Additional component kinds, lifecycle operations and tools must arrive with their actual feature and migration; no speculative agent tables or registry HTTP writes are added now.

The base backend image can run API, migrations or CLI and later a Worker. Test dependencies are confined to a separate image target. The inactive n8n profile targets its own logical PostgreSQL database/user; provisioning that database and the real workflow belongs to M3. It never shares PAW tables.
