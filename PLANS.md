# PAW delivery plan

Updated: 2026-11-20

## Current state

- Introductory README published; repository connected to GitHub.
- Blueprint v1.5, repository rules and M0 brief aligned with the owner discussion.
- ADR-012 records the revised delivery and history boundary; ADR-013 clarifies operations, traceability and visualization without expanding M0.
- M0 backend/API, migrations, registry bootstrap, web shell, local Compose and CI configuration implemented. M1.2 adds a separate diagnostic Worker; agents, bots, integrated n8n workflows and online deployment remain unimplemented.
- Local bootstrap persisted two verified nodes, one logical link and three actual registration events. These are private installation data in the Docker volume, not Git fixtures.

## M0 — repository foundation

Status: Complete. Local checks and GitHub Actions passed for implementation commit `ce6e04b`. Use [CODEX_START.md](CODEX_START.md) as the implementation brief and [ADR-012](docs/adr/ADR-012-delivery-and-history.md) for the history boundary. Also read [ADR-013](docs/adr/ADR-013-operations-and-visualization-boundaries.md) for event separation. This M0 scope is complete; the active task below is M1.3.

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
| M1 | Durable runs, validated CSV uploads, deterministic reports/charts, then model interpretation | M1.1–M1.3 implemented; AI interpretation not started |
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

M1.4: provider-neutral model interpretation of verified tool results, offline fake-provider tests and bounded usage. Discuss provider, data-sharing boundaries and spending limits before implementation. No provider account or API key is needed for M1.3.

## Completed task — M1.1 projects and CSV storage

Complete: project create/list/detail, bounded CSV upload, durable local file storage and metadata, failure cleanup, API tests and documentation. No Worker, runs, analysis, LLM or frontend features in this slice. M1.2 will introduce durable execution; M1.3 deterministic analysis; M1.4 model interpretation.

- Migration 0002 adds one internal workspace, projects and files; existing lifecycle history remains intact.
- CSV bounds and local persistence/recovery decisions are recorded in ADR-015.
- Weekly Dependabot updates configured for backend/frontend; first scheduled execution is not yet verified.
- Full Docker/PostgreSQL suite: 63 passed, including failed database/disk writes, orphan cleanup, restart and concurrent uploads. The existing test-client deprecation warning remains nonblocking.
- Ruff lint/format and strict mypy passed (24 source files). `git diff --check` passed.
- Live migration from M0 completed; synthetic project/upload returned 201, checksum matched, metadata and original bytes survived API container restart. Bootstrap reported unchanged and the original three lifecycle events retained their timestamps.
- Gitleaks staged-diff and history scans passed with no leaks.
- GitHub CI passed all three jobs for implementation commit `8bdb9a5`: [M1.1 checks](https://github.com/Volodymyr75/personal-ai-workspace/actions/runs/44604761110), including backend tests/live bootstrap, frontend lint/format/types/build and the secret scan. No browser/screen automation used.

## Completed task — M1.2 durable diagnostic execution

Complete, authorized by owner. Scope: run API, PostgreSQL claims, bounded lease recovery,
attempt fencing, separate Worker, diagnostic success/failure only. No CSV analysis or AI.
Design: 15-second lease, heartbeat every 3 seconds, 45-second attempt deadline,
maximum 3 claims. Explicit execution failures are terminal; only expired claims retry.
Progress checkpoint: domain, migration 0003, repository, typed API, separate Worker,
transactional Worker lifecycle registration, Compose and CI smoke implemented.
Full Docker/PostgreSQL suite: 76 passed. Ruff and strict mypy passed (30 source files).
Live diagnostic success/failure/idempotency smoke passed. Queued work survived an actual
API restart. SIGKILL interrupted Worker; lease expiry produced a new attempt, which
completed successfully. Original lifecycle events retained their timestamps; Worker
added exactly its node/link events (five total), with no duplicates after restarts. Documentation and ADR-016 added; no new dependencies.
Final diff checks and Gitleaks staged/history scans passed with no leaks.
Implementation commit `81a88f2` is pushed. [GitHub CI](https://github.com/Volodymyr75/personal-ai-workspace/actions/runs/44609974845)
passed all three jobs, including the live diagnostic Worker smoke, backend/PostgreSQL
tests, frontend checks/build and secret scan. M1.3 has not started.
Owner also confirmed the M1.1 sample upload manually before starting this slice.


## Active task — M1.3 deterministic CSV analysis

Complete, authorized 2026-11-20 after the owner verified M1.2. Scope: explicit typed CSV analysis,
numeric summaries, bounded grouping, optional ratios, one static chart, persisted
report/chart artifacts and API retrieval. No LLM, agent registration or frontend changes.
Preserve diagnostic requests and existing run IDs/history.

Implementation plan: migration for analysis inputs/artifact metadata; deterministic
Pandas tools with fixtures; process-bounded execution with lease heartbeats; atomic
fenced artifact publication using the local volume; retrieval API and full checks.
Limits/semantics: explicit numeric columns (max 8), one optional group column (max 100
report groups), one selected chart metric (max 30 plotted groups, disclosed in report).
Empty/whitespace cells are missing; invalid numeric values fail, not silently coerce.
Ratios use summed paired nonmissing rows, with zero denominator returning null.
Progress checkpoint: migration 0004, typed analysis API, bounded Pandas/Matplotlib
pipeline, child-process execution, fenced local artifact publication/recovery, artifact
retrieval and tests implemented. ADR-017 records semantics and persistence limits.
51 unit tests and final full Docker/PostgreSQL suite of 97 tests passed. Strict mypy passed
(35 source files). Synthetic PNG visually inspected; report values checked against fixtures.
Ruff lint/format and mypy passed. Live migration and CSV upload -> analysis -> JSON/PNG
smoke passed, as did the existing diagnostic smoke. Persisted artifacts survived a
rebuild/restart, previous upload metadata remained intact and lifecycle history stayed
at five events. Documentation includes the complete manual API request and expected values.
Final staged-diff/history Gitleaks scans passed with no leaks. Implementation commit
`63e2ec4` is pushed; [GitHub CI](https://github.com/Volodymyr75/personal-ai-workspace/actions/runs/44701675383)
passed for this exact commit, including backend tests, live diagnostic and CSV-analysis
smokes, frontend checks/build and secret scan. M1.4 has not started.
The owner confirmed M1.2 manually before authorizing this slice.
