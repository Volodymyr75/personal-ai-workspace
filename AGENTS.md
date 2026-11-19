# AGENTS.md — Personal AI Workspace

This repository is a personal AI platform intended for open-source release, developed locally with a planned private online deployment built incrementally using Codex.

## Read before making changes

1. `PROJECT_BLUEPRINT.md` — product and architecture source of truth.
2. `PLANS.md` — current milestone and acceptance criteria, when present.
3. Relevant ADR(s) under `docs/adr/`, when present.

Do not start work on future milestones unless explicitly requested. Finish one coherent change and demonstrate that it works.

## Architecture and ownership

- Python backend uses a modular-monolith architecture; API and Worker are separate processes built from the same backend codebase.
- The platform API owns projects, files, run states, events, artifacts and graph registry, including **append-only system evolution history**. UI and n8n must not mutate registry tables directly.
- **Future External Projects Integration:** existing and future third-party projects remain in their own repositories/environments. PAW may register and observe them through optional typed connectors; never import their source into the PAW monorepo as a default architecture. Project identity must not depend on a GitHub URL. See Blueprint §14.1.
- n8n owns scheduling and external workflow triggers; it calls the platform's versioned HTTP API. Never access n8n internal tables from the platform.
- Frontend reads platform data through API contracts; no direct database access.
- Keep domain contracts independent of FastAPI, SQLAlchemy, n8n, Pydantic AI and LLM provider SDKs.
- Implement AI agents with explicit registration and restricted typed tools. Do not add a generic plugin engine prematurely.
- Preserve the possibility to extract modules into services, but do not create extra microservices without a demonstrated need.

## First MVP boundaries

- First complete workflow: upload a CSV, request analysis, invoke deterministic data tools, persist results, display report and chart.
- External-project catalog/connectors, repository sync, independent project watchers, GitHub access and external project control are **post-MVP**. Do not implement them in M0–M3 just because examples appear in the Blueprint.
- n8n is included as an independent service, with one real scheduled integration workflow.
- System Map and **Project Evolution** UI are deferred beyond the core MVP. Collect real component and relationship history from M0 so later visualization has factual data. Use explicitly synthetic fixtures for portfolio demonstrations.
- Demo/portfolio mode must use synthetic data isolated from private/local state.
- No arbitrary Python/shell/SQL execution by LLM, no production deployment automation, no payments or outbound postings without human approval.

## Product direction

- One owner; develop on MacBook, then deploy privately online after the deployment gate. Hosting/provider/budget choices remain open.
- Interface and general reports are English; Estonian and English learning explanations/translations are Ukrainian.
- Later capture channels include responsive web and Telegram for iPhone/MacBook; they share platform state through API contracts. No bot or language module in M0.
- Language workflows preserve all readable source text, flag uncertainty, prepare editable drafts, and let the owner select what to save. Keep source text distinct from AI-generated examples.
- Capture, execution and saved results are separate concerns; receiving a file does not automatically authorize paid model processing.

## Engineering standards

- Prefer readable, small, typed code over speculative abstractions.
- Use migrations for database schema changes.
- Version HTTP endpoints under `/api/v1` and keep Pydantic request/response schemas explicit.
- Use structured logs without secrets or private dataset contents.
- Tests must not depend on paid AI API calls; use fake providers and deterministic fixtures.
- Run formatter/linter, type checks, tests, and relevant build commands before reporting success when supported by the environment.
- Keep committed dependency versions reproducible (lockfiles).
- Use `.env.example` with placeholders; never commit real credentials, personal files, `.env`, DB dumps or n8n storage.
- **Pragmatic security (Blueprint §11):** keep local services private/loopback-only; M0 CI runs ordinary checks plus **one** lightweight secret-leak scan (Gitleaks preferred). Add no Bandit/Trivy/Vault/OAuth/security dashboards at M0. Confirmed exposed secrets and unsafe code execution are blockers; low-risk advisories are documented and prioritized, not automatically treated as reasons to abandon MVP.
- As features arrive, add focused controls: CSV input limits/tool allowlists in M1, isolated demo data when portfolio mode is introduced, authenticated n8n integration in M3. Before any live Internet deployment, perform separate authentication/TLS/rate-limit/container/dependency review. No live deployment should be presented as safe without that gate.
- Make API->worker asynchronous run lifecycle durable; protect against duplicate claims and lost work.
- Separate lifecycle (`system_events`), execution (`runs`/`run_events` from M1) and operational telemetry. Do not persist recurring health checks, model calls or routine backup/deployment results in architecture history. Add telemetry storage only with a concrete feature; do not add M0 tables.
- In M1, correlate execution through stable run IDs, distinct attempt IDs and optional correlation IDs; correlation does not replace idempotency. Record available provider/model, tokens, duration and explicitly estimated cost without inventing unavailable values. No LLM Gateway in M0.
- Keep graph API/domain contracts renderer-neutral; React Flow/3D layout details belong to frontend adapters. Animated activity replay, 3D, automatic rollback and self-healing are deferred.
- Annotate unobserved service health as `unknown`, not `healthy`; do not infer historical health from today's status.
- From **M0**, persist first actual component registrations in `system_events` with UTC server `recorded_at`; register only verified initialized components. Never fabricate/backdate project evolution to make growth look better.
- Use stable namespaced component keys; rename != new component. Write registry change and immutable lifecycle event in one transaction; make bootstrapping and retries idempotent.
- History must support as-of replay of labels, node types and links; event payloads contain only allowlisted non-sensitive metadata. Correct mistakes with an explicit corrective event, never an unnoticed rewrite.
- Growth charts should count distinct active agents/services/integrations at time cutoffs, not LLM calls or planned features. Future connected-project counts are separate; an idea, a known repository and an observed running service are different states. Missing instrumentation means `not collected`, not `0`.
- Historical replay/metrics UI belongs to a separate post-MVP visualization slice. M0 implements minimal service_nodes, service_edges and system_events schemas, verified registration/bootstrap and tests, with no graph frontend or historical query API.
- Future project connectors must be opt-in and read-only by default; never access private repos or modify/deploy third-party projects without scoped credentials and explicit owner approval. Show observed status only; demo mode uses synthetic project references.
- For significant design changes, add a short ADR explaining alternatives and tradeoffs.
- Update documentation and `PLANS.md` as work evolves.

## Working with Codex

At the start: summarize the exact scope of the requested task and identify affected modules.
At the end report:
1. Files changed.
2. What works and what remains unimplemented.
3. Tests/commands run, with pass/fail results.
4. Manual verification steps.
5. Follow-up task recommendation.

Do not claim tests passed unless actually executed. Do not silently broaden scope or replace fundamental architecture decisions.
