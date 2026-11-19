# First Codex task — milestone M0 (repository foundation)

Copy the prompt below into Codex in the existing documentation repository; preserve its Git history and README. Do **not** ask Codex to build all future agents in one turn.

---

You are the software engineer implementing the first milestone of Personal AI Workspace, a personal AI platform developed locally with a planned private online deployment.

**Read first:** `AGENTS.md`, `PROJECT_BLUEPRINT.md`, `PLANS.md` and `docs/adr/ADR-012-delivery-and-history.md`. Use them as requirements and architecture constraints. Do not silently change the architecture. You may consult upstream official documentation for the current library APIs.

**Future extensibility constraint:** The Blueprint's External Projects Integration (§14.1) is a **post-MVP design boundary**. Keep the existing project/domain architecture extensible, but **do not** implement connectors, project watchers, external repo access, or migrations for them in M0. The sample future projects are illustrative, not registered platform components.

**Task:** Implement **M0 — Repository Foundation** only. Produce a coherent, working minimal slice, not a skeleton full of placeholder agent implementations.

**Scope:**

1. Extend the existing repository into a clean monorepo structure matching `PROJECT_BLUEPRINT.md`, without creating unnecessary empty packages.
2. Create a minimal FastAPI backend with a versioned `GET /api/v1/health` endpoint and `GET /api/v1/ready` endpoint checking database readiness.
3. Configure one supported Python version, dependencies, formatting, linting and test tooling; use reproducible dependency locking.
4. Add PostgreSQL with SQLAlchemy setup and Alembic migrations. Create only three minimal historical foundation tables:
   - `service_nodes`: stable key, kind, safe display name, lifecycle state, registered/retired UTC timestamps, allowlisted metadata.
   - `service_edges`: stable relationship identity, source/target node keys, allowlisted relation, registered/retired UTC timestamps; unique logical relationship.
   - `system_events`: immutable event ID, monotonic sequence, type, entity key, source, version, UTC `occurred_at` / server `recorded_at`, unique optional idempotency key, sanitized full after-state JSON.
   The current node and edge registries are projections, and system events are the durable evolution history. Do **not** add all future tables yet.
5. Add a documented **idempotent bootstrap command** that registers only components actually initialized in the installation (normally `service:api` and `storage:postgres` after readiness). Record `service.registered`/`storage.registered` events in the same transaction as each registration. Re-running the command must not add events or change original timestamps. Do not backdate events to fictional project start dates. After verifying the running API and its database readiness, register the API-to-PostgreSQL `persists_to` relationship with a sanitized `link.added` event in the same transaction. This records a configured logical relationship, not measured traffic. Use a stable edge identity and preserve it across retries.
6. Provide `infrastructure/compose.yaml` that can start at least the API and PostgreSQL. Use loopback port bindings for published development services and keep the database internal; never publish admin/DB services to the Internet. Add a common backend image/build design suitable for a future separate worker.
7. Add a minimal Next.js/TypeScript frontend shell with a clearly labeled future `Workspace` page; do not fabricate live telemetry or implement React Flow graph yet.
8. Add directory and documented Compose configuration for n8n as a separate service, in an inactive optional profile so it can be started when the automation milestone begins. Do not add n8n credentials or pretend a workflow already runs.
9. Add CI via GitHub Actions for backend lint/tests and frontend checks, **plus one lightweight secret-leak check** (prefer pinned Gitleaks; do not install a broad security-scanner stack). Add `.env.example`, `.gitignore`, MIT `LICENSE`, English README quickstart, `docs/architecture.md`, a **short** `docs/security.md` describing local-only boundaries and a future public deployment gate, and update the existing `PLANS.md` with actual M0 progress.
10. Write automated tests covering health endpoint, readiness behavior, event append and idempotent component bootstrapping (with unit/API tests plus isolated PostgreSQL integration tests for transaction rollback, append-only enforcement and concurrent/idempotent registration).
11. Keep all personal data, tokens, DB volumes, `.n8n` state and generated files out of version control.

**Out of scope:** external-project connections or catalogs, GitHub repository reads/writes, external project monitoring or map nodes, Pydantic AI execution, Data Analyst, file upload, worker queue, live System Map, Growth Analytics UI, historical `as_of`/metrics endpoints, graph replay, Telegram, Inbox/Library features and language learning, complete n8n workflow, **production** authentication, cloud hosting, Redis, LangGraph, Kubernetes, Grafana, LiteLLM, Bandit/Trivy scans, Vault, OAuth, penetration testing and public-deployment hardening.

**Acceptance criteria:**

- A developer can follow the README from a fresh checkout to install tools and start the stack.
- `GET /api/v1/health` responds 200 when the API runs.
- `GET /api/v1/ready` reflects actual DB readiness.
- Initial lifecycle event records are actually persisted with server UTC timestamps, not inferred from current-state rows.
- No external projects or future ideas are registered as active components during initial bootstrap.
- Running bootstrap twice produces the same registered nodes/edges and no extra registration events; renaming a node in later milestones must not inflate growth counts.
- Tests validate registry + append-only history atomicity, event idempotency and non-disclosure of secret metadata.
- Docker Compose configuration is valid, with persistent DB storage, loopback-only published development ports, and no real secrets in Git.
- A single lightweight secrets check is configured in CI. Do not expand the M0 security scope beyond Blueprint §11.1; document any scanner limitations clearly.
- Backend unit/API tests and lint/type checks run cleanly in the available environment.
- Frontend starts and shows a plainly labeled foundation UI with no false claims about operational status.
- CI workflow is syntactically correct and targets meaningful tests/checks.
- `PLANS.md` lists remaining work and the next narrow vertical slice.

**Working approach:**

- First inspect repo and give a short implementation plan.
- Implement only M0. Work in small, verifiable steps.
- Run tests/build/compose validation when supported. If Docker or network is unavailable, clearly identify exactly what was and was not verified.
- At the end, summarize changed files, test results, setup commands, **minimal** security measures, and the recommended **next** Codex task. Do not pause feature delivery for speculative security improvements; report nonblocking future checks in `PLANS.md`.

---

**After M0:** Use one Codex task per milestone or smaller vertical slice. Review changes and commit only after running the relevant tests. M1 should implement durable queued runs and deterministic CSV analysis first, followed by the LLM interpretation layer. **Do not postpone historical event collection**: the later visualization slice adds growth UI, time-sliced read models and historical graphs using facts already recorded since M0.
