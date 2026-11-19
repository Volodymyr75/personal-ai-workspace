# PAW delivery plan

Updated: 2026-11-19

## Current state

- Introductory README published; repository connected to GitHub.
- Blueprint v1.4, repository rules and M0 brief aligned with the owner discussion.
- ADR-012 records the revised delivery and history boundary.
- No backend, frontend, database, worker, bot, CI or deployment implemented.
- No runtime system events exist yet. Documentation commits are not component-registration events.

## Next task: M0 — repository foundation

Status: Not started. Use [CODEX_START.md](CODEX_START.md) as the implementation brief and [ADR-012](docs/adr/ADR-012-delivery-and-history.md) for the history boundary. Do not implement M1 or later features during this task.

Suggested sequence within M0:

1. Inspect available Python, Node and Docker tooling; select concrete supported versions, package managers and lockfiles. Add minimal FastAPI liveness/readiness contracts and development configuration.
2. Add PostgreSQL, migrations and the three minimal history tables. Implement verified, transactional, idempotent node/link bootstrap and isolated database tests.
3. Add a labeled Next.js foundation shell, local Compose configuration and inactive optional n8n profile.
4. Add CI, one lightweight secret check, MIT license, setup/security documentation and run the relevant checks.

### M0 acceptance checklist

- [ ] `/api/v1/health` reports liveness; `/api/v1/ready` reports actual database readiness, including failure behavior.
- [ ] Migrations create only `service_nodes`, `service_edges` and `system_events` for domain storage.
- [ ] Bootstrap verifies the running API and database before registering their stable node keys and logical `persists_to` link.
- [ ] Projection changes and safe full after-state events commit or roll back together.
- [ ] Repeated and concurrent bootstrap do not duplicate nodes, links or events, or alter original registration timestamps.
- [ ] Append-only history is enforced for ordinary application writes; timestamp/order and metadata rules are tested.
- [ ] PostgreSQL integration tests validate database behavior; mocks are not the only evidence of atomicity or duplicate protection.
- [ ] Compose exposes development services only on loopback and keeps the database internal with persistent storage.
- [ ] Frontend clearly labels its foundation state and does not invent telemetry.
- [ ] n8n profile is inactive by default; no workflow or integration is claimed to exist.
- [ ] Reproducible dependency locks, formatter/linter/type checks, tests, frontend build and Compose validation pass where supported.
- [ ] CI includes ordinary checks and one lightweight secrets scan; no broad scanner stack.
- [ ] README has reproducible setup and manual verification steps; limitations and unexecuted checks are recorded honestly.

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
- **M1:** CSV formats and limits, aggregation semantics, lease/recovery rules, stale-worker protection, provider/model and bounded spending policy.
- **M3:** integration secret handling, bounded delivery retries and observable n8n failures when the API is down.
- **M4:** hosting and budget based on measured requirements; owner access, HTTPS, storage durability and tested restoration.
- **Later learning slice:** vocabulary draft representation and review UI; retain all readable source text and owner control.

Do not collect credentials in documentation or fabricate progress. Update this plan with actual commands and acceptance evidence as implementation proceeds.
