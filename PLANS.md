# PAW delivery plan

Updated: 2026-11-19

## Current state

- Introductory README published; repository connected to GitHub.
- Blueprint v1.5, repository rules and M0 brief aligned with the owner discussion.
- ADR-012 records the revised delivery and history boundary; ADR-013 clarifies operations, traceability and visualization without expanding M0.
- M0 backend/API, migrations, registry bootstrap, web shell, local Compose and CI configuration implemented. Worker, agents, bots, integrated n8n workflows and online deployment remain unimplemented.
- Local bootstrap persisted two verified nodes, one logical link and three actual registration events. These are private installation data in the Docker volume, not Git fixtures.

## M0 — repository foundation

Status: Complete. Local checks and GitHub Actions passed for implementation commit `ce6e04b`. Use [CODEX_START.md](CODEX_START.md) as the implementation brief and [ADR-012](docs/adr/ADR-012-delivery-and-history.md) for the history boundary. Also read [ADR-013](docs/adr/ADR-013-operations-and-visualization-boundaries.md) for event separation. Do not implement M1 or later features during this task.

Implementation sequence completed:

1. Inspect available Python, Node and Docker tooling; select concrete supported versions, package managers and lockfiles. Add minimal FastAPI liveness/readiness contracts and development configuration.
2. Add PostgreSQL, migrations and the three minimal history tables. Implement verified, transactional, idempotent node/link bootstrap and isolated database tests.
3. Add a labeled Next.js foundation shell, local Compose configuration and inactive optional n8n profile.
4. Add CI, one lightweight secret check, MIT license, setup/security documentation and run the relevant checks.

### M0 acceptance checklist

- [x] `/api/v1/health` reports liveness; `/api/v1/ready` reports actual database readiness, including failure behavior.
- [x] Health/readiness probes do not append lifecycle events; no telemetry or execution schema is introduced in M0.
- [x] Migrations create only `service_nodes`, `service_edges` and `system_events` for domain storage.
- [x] Bootstrap verifies the running API and database before registering their stable node keys and logical `persists_to` link.
- [x] Projection changes and safe full after-state events commit or roll back together.
- [x] Repeated and concurrent bootstrap do not duplicate nodes, links or events, or alter original registration timestamps.
- [x] Append-only history is enforced for ordinary application writes; timestamp/order and metadata rules are tested.
- [x] PostgreSQL integration tests validate database behavior; mocks are not the only evidence of atomicity or duplicate protection.
- [x] Compose exposes development services only on loopback and keeps the database internal with persistent storage.
- [x] Frontend clearly labels its foundation state and does not invent telemetry.
- [x] n8n profile is inactive by default; no workflow or integration is claimed to exist.
- [x] Reproducible dependency locks, formatter/linter/type checks, tests, frontend build and Compose validation pass where supported.
- [x] CI includes ordinary checks and one lightweight secrets scan; no broad scanner stack.
- [x] README has reproducible setup and manual verification steps; limitations and unexecuted checks are recorded honestly.

## Remaining milestones

| Milestone | Scope | Status |
| --- | --- | --- |
| M1 | Durable runs, validated CSV uploads, deterministic reports/charts, then model interpretation | Not started |
| M2 | Responsive English web workflow, history, results and error states | Not started |
| M3 | Authenticated, idempotent n8n integration and reproducible core MVP | Not started |
| M4 | Owner-only online deployment, targeted release checks, storage and backup/restore | Not started |
| Visualization | Historical APIs, System Map, evolution metrics and isolated synthetic portfolio mode | Deferred |
| Capture and learning | Shared capture/provenance, full text extraction, Ukrainian learning explanations and owner-reviewed vocabulary | Deferred |
| Telegram | API-backed capture and result delivery for the owner | Deferred |
| External projects | One explicitly chosen, scoped read-only connector | Optional, post-MVP |

Core MVP completion requires M0–M3, not visualization. Online availability requires the separate deployment gate even if the system has only one user.

## Decisions to make when relevant

- **M0:** concrete dependency/tool versions, bootstrap verification mechanism and database enforcement of immutable events.
- **M1:** CSV formats and limits, aggregation semantics, lease/recovery rules, stale-worker protection, provider/model and bounded spending policy; run/attempt/call identifiers, optional correlation IDs, available usage metadata and cost-estimate provenance.
- **M3:** integration secret handling, bounded delivery retries and observable n8n failures when the API is down; minimal operational observation storage and retention, separate from lifecycle history.
- **M4:** hosting and budget based on measured requirements; owner access, HTTPS, storage durability and tested restoration; actual backup outcomes and deployment tracking.
- **Visualization:** renderer-neutral graph DTOs; separate evolution from activity replay. Define replay coverage using retained execution/telemetry data. Animation, 3D, automatic rollback and self-healing remain post-MVP.
- **Later learning slice:** vocabulary draft representation and review UI; retain all readable source text and owner control.

Do not collect credentials in documentation or fabricate progress. Update this plan with actual commands and acceptance evidence as implementation proceeds.

## M0 verification evidence (2026-11-19)

- Backend Ruff lint/format and strict mypy checks passed.
- Unit/API tests: 13 passed offline; full Docker PostgreSQL suite: 23 passed, including concurrency, rollback, immutable history and server timestamps.
- Frontend ESLint, Prettier, TypeScript and production build passed; both pages returned HTTP 200 with the expected foundation labels.
- Compose configuration validated; API/web started with PostgreSQL internal and published ports on loopback. Bootstrap repeated without extra events.
- Database outage/recovery and API restart smoke checks passed: readiness returned 503, liveness stayed 200, recovery restored readiness and registration IDs/timestamps remained unchanged.
- Gitleaks staged-diff and existing-history scans passed with no leaks. Two descriptive n8n placeholders initially triggered generic-key detection; they were replaced by empty placeholders, with no scanner rule suppression. GitHub Actions passed all three jobs: [M0 checks](https://github.com/Volodymyr75/personal-ai-workspace/actions/runs/44583671581).
- No browser/screen automation used. Responsive CSS is present; visual inspection on iPhone remains a manual check.

Nonblocking tooling notes: Starlette warns that its httpx test-client compatibility path is deprecated; it currently passes all tests. ESLint 9 reports end of support; the pinned configuration passes, with a tooling refresh to be considered separately. GitHub Actions also reports a Node 20 action-runtime deprecation while successfully running the pinned action on Node 24. These tooling notices are not known exposed credentials or failing application checks; update the affected tooling in a focused maintenance slice.

## Recommended next task

M1, first slice: durable run state, validated CSV storage and deterministic analysis. Define leases/recovery and numerical fixtures before adding model interpretation. Do not implement Telegram, vocabulary, graphs or infrastructure automation in that slice.
