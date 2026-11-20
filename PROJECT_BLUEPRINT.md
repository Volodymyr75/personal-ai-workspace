# Personal AI Workspace (PAW)
## Project Blueprint — Vision, Architecture, MVP and Delivery Plan

**Version:** 1.5 (Operational boundaries and traceability, 2026-11-19)
**Status:** Target architecture; M0 local foundation implemented, later milestones planned (see PLANS.md)
**Language:** Ukrainian/English design documentation; English code, UI and general reports; Ukrainian language-learning explanations
**Repository:** `personal-ai-workspace` (working name)
**Primary development assistant:** OpenAI Codex
**Target:** Open-source portfolio project + useful personal system

> **Guiding principle:** Start with one complete, useful end-to-end scenario. Make system boundaries explicit from day one so that additional agents, tools, automations, providers, deployments and visualization layers can be introduced incrementally.

---

## 1. Product vision

PAW — розширювана персональна платформа для AI-агентів, автоматизацій, аналізу даних, навчання та роботи над власними програмними проєктами.

Система має дві однаково важливі цілі:

1. **Практична користь:** аналіз даних, робота з рекламними кампаніями, вивчення мов, дослідження ML, створення та контроль pet-проєктів.
2. **Навчальний та портфолійний результат:** вивчення AI engineering, workflow automation (n8n), backend, API, Docker, архітектури сервісів, тестування, CI/CD, моніторингу і поступового переходу до мікросервісів.

Платформа розрахована на **одного власника**. Розробка починається локально на MacBook; приватне онлайн-розгортання забезпечить доступ із MacBook та iPhone незалежно від роботи ноутбука. Мультикористувацький SaaS не входить до MVP. Хостинг, AI-провайдер і бюджет ще не обрані.

### 1.1 Продуктові принципи

- **One useful workflow first:** спочатку завершена вертикальна функція, а не десятки заготовок агентів.
- **Modular core, separate runtime processes:** модульний Python-код із різними процесами API та Worker, окремим n8n і frontend.
- **API-first:** інтерфейси та автоматизації працюють із системою через документований API.
- **Agents are replaceable:** не прив'язувати доменну логіку до конкретного agent framework або LLM-провайдера.
- **Tools are reusable:** обчислення, робота з файлами, конектори та дозволені операції ізольовані від prompt-логіки.
- **External projects stay independent:** PAW can catalog, observe, and later assist projects that live in their own repositories/deployments; linking never requires copying their code into the PAW monorepo.
- **Observability and evolution from day one:** поточний реєстр, незмінна історія змін компонентів/зв’язків і часові позначки — основа для Live System Map, Growth Analytics та історичного відтворення. Не намагатися реконструювати відсутні минулі дані.
- **Human-in-control:** зміни у файлах/репозиторіях, платежі, публікація контенту й інші ризикові зовнішні дії потребуватимуть явного дозволу.
- **Public code, private data:** публікуємо вихідний код та синтетичні демонстраційні дані; жодних приватних файлів, логів, credential або токенів у Git.
- **Security proportional to risk:** захист впроваджується поступово. На M0 — мінімальні дешеві захисні заходи, а не повноцінний security stack; додаткові перевірки активуються разом із новими ризиками або перед публічним розгортанням. Безпечний локальний MVP має пріоритет над нескінченним security-hardening.

### 1.2 Owner workflows and access

CSV analysis is the first learning and implementation slice, not the product's only purpose. Later workflows may process photos, screenshots, documents and voice notes. A proposed shared Inbox, Tasks and Library separates capture, execution and saved results. Responsive web and a later Telegram bot use the same platform API; no separate bot-owned library or run state. Saving a material does not itself start a paid AI call.

The first language-learning candidate extracts all readable text from an Estonian or English source, flags uncertain text, and prepares editable word/expression drafts with Ukrainian explanations and source context. The owner selects, edits or discards drafts before saving. Preserve original material and extracted text; distinguish generated examples from source quotations. Vocabulary search and simple review precede more advanced learning features. This is a future slice, not M0–M3 scope.

External AI APIs are allowed. Keep source-to-result traceability separate from system evolution events; private content must not enter the topology event stream. Model usage should be recorded when execution is introduced and the provider supplies it; do not invent cost totals.

See [ADR-012](docs/adr/ADR-012-delivery-and-history.md) for the revised delivery and historical-data boundary.

## 2. Architectural approach

**Обраний підхід: modular monolith + independently deployed infrastructure services.**

- Python backend структуровано як модулі з чіткими інтерфейсами.
- FastAPI API і Worker виконуються як **два процеси/контейнери з одного backend codebase**.
- n8n, PostgreSQL і Next.js — окремі сервіси в Docker Compose.
- У MVP не створюємо окремий мережевий сервіс на кожного агента.
- Агентні модулі взаємодіють через контракти; в майбутньому execution adapter може викликати віддалений агент через API/queue.
- n8n відповідає за тригери, інтеграції та розклади, **але не володіє станом агентних запусків**.
- FastAPI/Platform Core відповідає за проєкти, запуски, артефакти, правила доступу, реєстр середовища та події. Зміни топології записуються атомарно з оновленням поточного стану, щоб історію можна було відтворити незалежно від frontend.

**Чому не full microservices зараз:** контейнеризація не є проблемою; зайві service boundaries, мережеві збої та окремі схеми даних для ще не сформованих доменів збільшать обсяг підтримки без користі. Виділяємо мікросервіси тільки за явними критеріями (розділ 14).

## 3. Deployment topology (MVP)

```text
Browser
  |
  v
[Next.js / Web UI] ----HTTP----> [FastAPI / API]
                                      |
                         create run, query events
                                      |
                                      v
                               [PostgreSQL]
                                      ^
                                      |
                           claim queued runs
                                      |
                              [Python Worker]
                                      |
                            Agent Runtime + Tools
                                      |
                            LLM Provider Adapter
                                      |
                           [OpenAI or other API]

[n8n] --HTTP (internal token)--> [FastAPI integration endpoints]
   |
   +-- Schedule Trigger / Webhooks / external connectors

[File storage volume] <---- API / Worker

[Deferred System Graph + Evolution UI] <---- GET /api/v1/graph (?as_of)
                               + GET /api/v1/events
                               + GET /api/v1/evolution/{metrics,timeline}
```

**Target core-MVP Compose services (introduced incrementally):** `web`, `api`, `worker`, `postgres`, `n8n` (five services; `api` and `worker` share image/build). Optional profile for development DB tooling; do not add Redis/Grafana/Langfuse yet.

**Networking:** local development bound to loopback where possible; database/worker accessible only on internal Compose network. Public hosting needs authentication, TLS, reverse proxy and network policy as a separate deployment milestone.

## 4. Technology decisions

| Concern | MVP selection | Evolution path |
|---|---|---|
| Language | Python 3.12+ (choose and test one concrete version) | Update with CI |
| Backend API | FastAPI + Pydantic | Keep HTTP contracts stable |
| ORM / migrations | SQLAlchemy 2.x + Alembic | Independent schemas/services later |
| Database | PostgreSQL | Separate DB per extracted service if needed |
| Agent execution | Pydantic AI behind local adapter interface | Add LangGraph or another runtime behind adapter |
| Data analysis | Pandas, optionally Plotly | Specialized analytical tools |
| Web app | Next.js + TypeScript | Separate/public demo frontend if needed |
| Graph UI | React Flow (`@xyflow/react`) | More advanced layout/graphics later |
| Automation | Self-hosted n8n | Workflows exported and versioned |
| Local orchestration | Docker Compose | CI/CD and cloud deployment later |
| CI | GitHub Actions | More advanced test/security pipeline later |
| Provider | Single configurable model/provider adapter | LiteLLM Gateway when multi-provider routing justified |
| Telemetry | Structured logs + append-only DB events + health/readiness | OpenTelemetry, Langfuse, Grafana |
| Storage | Local Docker volume + storage interface | S3-compatible object storage |
| Async jobs | Dedicated Python worker using PostgreSQL job claiming | Task queue/broker when load demands |

**Dependency policy:** pin tested versions via lockfiles; verify upstream documentation when implementing. Do not hardcode assumptions about latest library APIs.

**Licensing note:** PAW's own code can use MIT. n8n is a separate third-party product under Sustainable Use License (source-available/fair-code, not OSI open source). Do not vendor/relicense n8n code; reference its official image and respect its terms.

## 5. Logical backend modules

```text
backend/src/paw/
  api/               # HTTP routes, request/response DTOs
  application/       # use cases and orchestration of platform operations
  domain/            # stable entities, contracts and domain rules
  agents/
    registry.py       # explicit registration of allowed agents
    data_analyst/     # first implementation
  tools/              # deterministic validated tools
  infrastructure/
    db/               # SQLAlchemy repositories and Alembic integration
    llm/              # provider adapters
    execution/        # worker, job claims, run lifecycle
    storage/          # local file adapter
    n8n/              # integration API adapter
    observability/    # append-only evolution events, health, structured logs
  config.py
```

**Dependency direction:** API and infrastructure depend on application/domain interfaces, never the other way around. Domain does not import FastAPI, SQLAlchemy, React Flow or n8n. The Data Analyst should not import tools of an unrelated agent or access raw database tables directly.

### 5.1 Core abstractions (interfaces, not a plugin framework)

- `AgentDefinition`: stable `agent_key`, version, description, supported task input/output models, authorized tool keys, execution limits.
- `AgentRunner`: `run(context, input) -> structured result`. Initial implementation wraps Pydantic AI.
- `Tool`: typed name, input schema, output schema and permission category; no arbitrary code evaluation.
- `ModelClient`: minimal interface for model invocation and usage metadata; adapter hides provider specifics.
- `ArtifactStore`: `save`, `read`, `delete` behind one storage adapter.
- `RunRepository`: persistence and transitions of runs and run events.
- `GraphRegistry`: current-state projection of registered components and typed links; runtime health is separate.
- `SystemEventRecorder`: appends redacted, versioned and idempotent lifecycle events in the same transaction as registry mutations.
- `EvolutionReadModel`: derives time-based counts, timeline and topology at a recorded moment without mutating state.
- **Future** `ExternalProjectConnector` (not part of MVP): reads narrowly scoped external-project metadata/status through typed adapters (e.g., remote repository, service API, manual status). Must not own the external project's implementation or state.
- `ExecutionDispatcher`: initially database queue + worker; replaceable implementation.

**Avoid premature abstractions:** implement an interface only when there is a clear boundary or imminent second implementation. A registry can initially be a typed Python mapping, not a dynamic marketplace of plugins.

### 5.2 Operations visibility and event boundaries

A future Operations view will combine services, agents, integrations, deployments, health observations, errors and backup status. The Service Registry remains the source of truth for component identity and topology. Observations reference stable component keys; they do not create a second inventory. A unified API view does not require a unified event table or a new monitoring service.

Keep three categories distinct:

| Category | Examples | Storage boundary |
| --- | --- | --- |
| System lifecycle | Registration, modification, retirement, topology change, explicit milestone | Append-only `system_events`; atomic with registry changes |
| Execution | Agent runs, tool calls, LLM requests, run-related workflow steps and errors | `runs` and `run_events` from M1 |
| Operational telemetry | Health checks, availability observations, deployment attempts, backup outcomes | Minimal dedicated storage only with the feature that needs it |

Do not put recurring health checks, per-request usage or routine backup/deployment results into `system_events`. An explicit release milestone or a resulting component/topology change may have a separate lifecycle event referencing the relevant operation. Errors belong to their execution or operational context, not a duplicate global error schema. An independent n8n health workflow is operational activity; an n8n-triggered agent run has normal run events and may reference the external workflow execution ID.

M0 still creates only the three agreed history tables. Its health/readiness endpoints do not persist every probe. In M3, introduce only the operational persistence needed by the first monitoring workflow, with bounded retention. Deployment and backup status belong to M4 when those operations exist. n8n owns triggers and its workflow state; PAW owns the accepted application state and observations. Notifications, automatic rollback and self-healing require separately scoped future work.

### 5.3 Execution traceability and model usage (M1)

Use stable `run_id` values across API, Worker, tool/model events and structured logs. Identify execution attempts separately so retries and lease recovery remain distinguishable. Propagate an optional correlation ID across incoming triggers and related runs where useful; it is not an idempotency key or proof of authorization. Add these fields with the M1 execution model, not as unused M0 schema.

The provider adapter should expose provider/model identity, available input/output token counts, measured request duration and estimated cost when a supported pricing basis exists. Identify individual model calls within an attempt so duplicate event delivery does not duplicate usage records; a real retry that invokes the provider again is a separate call. Keep unavailable values null/explicitly unavailable, not zero; do not assume failed requests are free. Label cost as an estimate with currency and pricing basis/version, separate from provider billing. Keep prompts and private source contents out of these metadata events. No dedicated LLM Gateway, billing subsystem or distributed tracing platform is required.

See [ADR-013](docs/adr/ADR-013-operations-and-visualization-boundaries.md) for the clarification and deferred work.

## 6. Data model (incremental target)

Recommended entities:

| Table / entity | Essential fields | Purpose |
|---|---|---|
| `workspaces` | `id`, `name`, timestamps | One default personal workspace; future scoping |
| `projects` | `id`, `workspace_id`, `name`, `description` | Stable PAW project identity; initially groups runs and artifacts, later may reference independently hosted projects via optional connections |
| `files` | `id`, `workspace_id`, `original_name`, `stored_path`, `mime_type`, `size_bytes`, `sha256` | Metadata only; bytes in volume |
| `runs` | `id`, `project_id`, `agent_key`, `status`, `input_json`, `output_json`, `error_code`, `created_at`, `started_at`, `finished_at`, `lease_expires_at` | Durable execution lifecycle |
| `run_events` | `id`, `run_id`, `type`, `service_key`, `summary`, `payload_redacted`, `created_at` | Execution trace, no sensitive raw payloads |
| `artifacts` | `id`, `run_id`, `file_path`, `kind`, `mime_type`, `created_at` | Charts and reports |
| `service_nodes` | `key`, `kind`, `display_name`, `visibility`, `lifecycle_state`, `registered_at`, `retired_at`, `metadata_json` | Current-state projection; `key` remains stable after rename |
| `service_edges` | `id`, `source_key`, `target_key`, `relation`, `registered_at`, `retired_at` | Current typed relationships; soft-retire rather than erase history |
| `system_events` | `id`, `sequence`, `event_type`, `entity_key`, `source`, `schema_version`, `occurred_at`, `recorded_at`, `idempotency_key`, `payload_safe_json` | **Append-only** project evolution, inventory changes and milestones |
| `service_heartbeats` | `service_key`, `last_seen_at`, `last_result` | Latest availability observation; not a full historical telemetry log |

Use UUIDs for run/project/file/artifact and system-event IDs. Use stable namespaced strings for `service_key`, e.g. `service:api`, `agent:data_analyst`; never use a display name as an identity. Index `system_events(recorded_at, sequence)` and `system_events(entity_key, recorded_at)`; make `idempotency_key` unique where provided. Index runs by status/time and run events by run/time. All timestamps are UTC. n8n uses its own DB/schema and DB user; PAW must not query n8n internal tables.

**External-project extensibility (future only):** The `projects` entity must remain source-agnostic: do not assume every PAW project is a repository, is hosted by PAW, or has a deployment. Later migrations may add optional `project_connections` (e.g., `project_id`, `connection_kind`, `remote_ref`, allowed capabilities, sync state) and project lifecycle metadata. No external-project tables, GitHub connector or sync logic belong in M0–M3 unless explicitly promoted to scope.

**Incremental migrations:** M0 creates **only** `service_nodes`, `service_edges` and `system_events` plus a controlled, idempotent first-registration command for confirmed components and their verified logical relationships. M1 introduces run/file/project/artifact tables. Historical read models/API are deferred to the visualization slice. Do not create all future tables during M0. Every actual registration/change must have an associated durable event from its first day; mere code definitions are not proof of a deployed component.

**Run lifecycle:** `queued -> running -> completed | failed`. Future `waiting_approval`, `cancelled`, `timed_out` reserved but not necessarily implemented now. Transition rules are enforced in application layer. Worker claims jobs with transaction safety (`SKIP LOCKED` or equivalent), lease/recovery semantics and bounded retries; maintain idempotency for external event handlers.

## 7. Versioned public API (incremental target contract)

Prefix `/api/v1`, JSON errors with stable codes. OpenAPI docs generated by FastAPI.

| Endpoint | Action |
|---|---|
| `GET /api/v1/health` | Fast liveness |
| `GET /api/v1/ready` | Dependency readiness |
| `GET /api/v1/agents` | Available registered agent definitions |
| `GET /api/v1/projects` / `POST /api/v1/projects` | Project listing and creation |
| `POST /api/v1/files` | Validated CSV upload, returns file ID |
| `POST /api/v1/runs` | Create queued run; **202** + `run_id` |
| `GET /api/v1/runs/{run_id}` | Status and structured outcome |
| `GET /api/v1/runs/{run_id}/events` | Detailed run timeline |
| `GET /api/v1/artifacts/{artifact_id}` | Download permitted artifact |
| `GET /api/v1/graph` | Current nodes + typed edges + observed state (deferred visualization slice) |
| `GET /api/v1/graph?as_of=<UTC-ISO-8601>` | Historical topology known at the selected recorded time (deferred visualization slice) |
| `GET /api/v1/events` | Recent platform activity, paginated |
| `GET /api/v1/evolution/metrics?from=...&to=...&grain=day` | Historical counts and activity time series (deferred visualization slice) |
| `GET /api/v1/evolution/timeline?from=...&to=...` | Component changes, integrations and milestones (deferred visualization slice) |
| `POST /api/v1/integrations/n8n/events` | Authenticated internal automation signal |

**API stability:** frontend and n8n must depend on API contracts, not direct DB access. Use typed DTOs and contract tests. Breaking changes require `/api/v2` or documented migrations, not silent changes.

**Example run request:**

```json
{
  "project_id": "<existing-project-uuid>",
  "agent_key": "agent:data_analyst",
  "input": {
    "file_id": "<uploaded-file-uuid>",
    "question": "Compare CTR and CPC by campaign"
  }
}
```

Example response: `202 Accepted`, body `{"run_id":"<uuid>","status":"queued"}`.

## 8. First end-to-end scenario: Data Analyst

### 8.1 User journey

1. User opens local web app, creates or selects a project.
2. Uploads a CSV file (sample advertising metrics or another tabular dataset).
3. Enters an analytical request in natural language.
4. Frontend calls `POST /api/v1/runs` and receives a run ID.
5. Worker claims run and calls Data Analyst with the selected tools.
6. Deterministic Pandas tools compute descriptive stats, group-by aggregations and optional chart data.
7. LLM produces grounded interpretation of computed outputs (not invented figures).
8. The system saves a structured report and chart artifact, marks the run as completed.
9. Frontend shows results and execution timeline; activity is persisted for the later system map.

### 8.2 MVP tools

- `inspect_csv(file_id)`: validate headers, row/column counts, types, missingness; no dangerous interpretation of external contents.
- `summarize_numeric(file_id, columns?)`: basic statistics, min/max/mean/median, allowed metrics.
- `aggregate_table(file_id, group_by, metrics, operations)`: validated groupings and aggregations.
- `create_chart(file_id, chart_spec)`: allowlisted bar/line chart specs; store Plotly JSON artifact or safe HTML rendering.

**Agent limits:** allowlist tools, at most ~8 tool calls/run, per-run wall clock timeout, bounded file size (initially 10 MB), row count cap, max chart count. Exact limits configured centrally; do not allow agent-generated arbitrary Python, shell or SQL. Avoid sending full CSV contents to any LLM by default: pass structural metadata and computed summaries only. Warn users before processing personal/sensitive data through external models.

### 8.3 Structured output

```json
{
  "title": "Campaign analysis",
  "summary": "Short evidence-backed conclusion",
  "findings": [
    {"claim": "Campaign A has the highest CPC", "support": "computed aggregate reference"}
  ],
  "artifact_ids": ["<chart-id>"],
  "limitations": ["CTR comparisons do not establish causality"]
}
```

Data Analyst runs must be testable with an offline fake model. Numerical values come from tools and their deterministic test fixtures.

## 9. n8n integration from MVP

n8n is a **separate workflow automation service**, not the system's agent runtime or database owner.

**First real n8n workflow** (simple, safe and inspectable):

```text
Schedule Trigger (every hour)
  -> HTTP GET FastAPI /api/v1/health
  -> classify result
  -> HTTP POST /api/v1/integrations/n8n/events
  -> persist operational observation + update latest automation heartbeat
  -> API/activity UI reflects the event (map later)
```

Save an exportable, sanitized workflow JSON in `automation/n8n/workflows/`. Credentials and tokens remain only in n8n credential storage or private environment configuration. PAW authenticates n8n calls with a server-side integration secret, enforces request size limits and `event_id` idempotency. A single automation should never write directly to PAW tables. Registration of `integration:n8n` is a lifecycle event; recurring checks are operational observations, never `system_events`. Introduce only the minimal observation storage needed at M3.

Future n8n workflows: nightly report triggers, reminders, scheduled site health checks, notifications, marketing connectors, feeds, language-study prompts. Use HTTP API to request a run and query completion; do not duplicate agent logic in n8n nodes.

## 10. Deferred System Map (portfolio differentiator)

### 10.1 Visual requirements

Implement a distinct **System Map** page in Next.js using React Flow. It shows real nodes and **typed directed links**, not a decorative animation pretending to be live infrastructure.

The backend exposes renderer-neutral node identities, kinds, labels, typed relationships, observed states and event references. React Flow coordinates, handles, colors and other rendering options belong to the frontend adapter/layout layer, not the domain model or lifecycle payloads. A future Three.js or other renderer should reuse these domain contracts; its layout and interactions still require frontend work. Do not build renderer infrastructure or 3D graphics in M0.

Target nodes **once each component actually exists and has been registered** (never register a component just because it is listed here):
- `ui:web` — Next.js
- `service:api` — FastAPI
- `service:worker` — Worker (from M1)
- `service:n8n` — n8n runtime (from M3)
- `integration:n8n` — configured authenticated API integration (from M3); distinct from the runtime service
- `storage:postgres` — PostgreSQL
- `agent:data_analyst` — Data Analyst (from M1)
- `external:llm_provider` — Configured AI provider (external, not health-inferred).

An absent/future component must not be shown as active in the live map. Planned components can appear only in a separately labeled roadmap view. The same rule applies to future external projects: an idea is **not** a connected project, and a linked project is **not** a confirmed running service.

Edges: `calls`, `triggers`, `executes`, `persists_to`, `uses`, `visualizes`. Distinguish logical dependency from measured activity. For example, UI `calls` API; Worker `executes` Data Agent; API `persists_to` PostgreSQL; n8n `triggers` API.

Interactions: pan/zoom, click node for details, filter by type/status, show latest 20–50 events, highlight relevant node during a run, show counts of runs by status. Include a compact **Project Evolution** tab with a timeline, growth chart and a date selector that switches the map between current and historical state. Support basic dark theme; prioritize clarity over 3D visuals.

### 10.2 Source of truth and event semantics

- Nodes and links come from **explicit graph registry** (seeded/migrated definitions; later dynamic registrations possible).
- Health states use observed heartbeat/readiness data: `healthy`, `degraded`, `down`, `unknown`; **unknown is not healthy**.
- Recent activity comes from `run_events` and platform events; avoid inventing activity animations.
- When visualization is implemented, start with API polling every 3–5 seconds; SSE/WebSockets only if justified later.
- Every event includes timestamp, type, source, optional run_id and sanitized short message. **System lifecycle events** are a separate append-only stream from potentially high-volume `run_events`; neither may be overwritten to rewrite history.
- No hostname, internal IP, token, personal message, raw user data or secret in publicly accessible map data.

### 10.3 Two presentation modes

- **Private live mode:** actual personal data and observed states; local initially, then owner-only online after the deployment gate.
- **Portfolio demo mode:** completely isolated, synthetic fixtures; no real API keys, private endpoints, personal documents or production logging. Clearly label it as demo/simulation.

### 10.4 Project Evolution / Growth Analytics — deferred UI, early history

**Goal:** visualize real growth of the workspace as a portfolio narrative while keeping the private operational system factual. Historical data collection begins at **M0**; visual analytics are delivered in a **separate post-MVP slice**. Animated playback can be added after MVP without migrating historical data.

**Core views (deferred visualization slice):**

1. **Growth overview:** counts of registered active agents, platform services, external integrations and typed relationships at the selected end-of-day/end-of-week date; distinguish current count from lifetime registrations.
2. **Activity history:** completed/failed agent runs, observed LLM invocations and n8n workflow events over a time range **only when an actual source emits these events**. Missing telemetry means `not collected`, not zero.
3. **Project timeline:** events such as `agent.registered`, `agent.retired`, `service.registered`, `service.retired`, `integration.registered`, `link.added`, `link.removed`, `milestone.reached`, `release.published`. Milestones are explicitly entered with an honest date and safe text.
4. **Historical topology:** choose a date/time to render nodes and edges that were **recorded as registered by then**, with a clear `Historical snapshot` label and an easy `Return to live` action. Historical health is `unknown` unless actual historical observations are available; do not reuse today's health status.
5. **Comparison:** current state vs selected historical date, showing additions/removals and net change. Animated playback is optional post-MVP UI polish, not a dependency of history storage.

**Event design (start in M0):**

- Current `service_nodes`/`service_edges` tables are query-efficient projections. `system_events` is the immutable history of project/inventory changes. A single transactional service method updates projection **and** appends the corresponding event; direct table writes from n8n or UI are forbidden.
- Stable keys (`agent:data_analyst`, `service:api`, `integration:n8n`) persist across rename; the same entity must not be counted twice. `kind` is explicit (`agent`, `service`, `integration`, `storage`, etc.), not inferred from a label.
- Include a monotonically increasing `sequence` for deterministic ordering, `schema_version`, trusted `source`, `idempotency_key`, `occurred_at` (when action claims to have happened) and server-generated `recorded_at` (when the platform learned about it); sort/reconstruct **as known at `recorded_at`**, then `sequence`. A late-arriving or manually backdated event must not be presented as proof the system knew it earlier.
- Registration/update/retirement and relationship events store **sufficient sanitized after-state details** to reconstruct historical labels/types/edges. For updates include relevant previous values or an explicit full after-state; use allowlisted metadata only. Never include prompts, credentials, file paths, emails, internal hostnames or sensitive payloads.
- Inserts are append-only under normal operation, with deduplication for retries. Fix incorrect history using an explicit corrective event, not a silent rewrite. System events are never derived from timestamps on today's registry alone.
- **M0 seed:** register only components **actually verified as initialized** in the local installation (at minimum `service:api`, `storage:postgres` once usable). Register their verified logical `persists_to` link with a stable identity and `link.added` event; preserve both projection and event atomically. Readiness proves initialization, not permanent health. First-registration timestamps reflect first recorded registration, **not the date the project was imagined or coded**. On repeated startups, do not create duplicate registration events or inflate growth.
- Persist events in PostgreSQL; no Kafka, Redis, event sourcing platform, or snapshot scheduler is required for MVP. Historical topology is reconstructed by chronological event folding. Aggregate counts can be computed on demand for this small dataset and cached/materialized later if necessary.

**Metric definitions:**

| Metric | Meaning | Source / caveat |
|---|---|---|
| `active_agents` | Distinct registered `kind=agent` nodes not retired by cutoff | Lifecycle events; not number of concurrent model executions |
| `active_services` | Distinct registered `kind=service` nodes not retired by cutoff | Lifecycle events; not healthy-server count |
| `active_integrations` | Distinct registered `kind=integration` nodes not retired by cutoff | Lifecycle events; not proof API is connected now |
| `active_links` | Relationships added minus removed by cutoff | Typed link lifecycle events |
| `new_agents` | First registrations in selected interval | Count distinct stable keys; exclude edits/renames |
| `completed_runs` / `failed_runs` | Runs entering corresponding terminal states in interval | M1+ run events; availability indicator for earlier periods |
| `llm_calls` | Measured LLM calls in interval | Instrumented ModelClient only; no estimated or fabricated totals |
| `milestones` | Recorded significant project events | Explicit `milestone.reached` / `release.published` events |
| `connected_external_projects` (future) | Distinct PAW project records with a verified active external connection as of cutoff | Only after External Projects Integration is implemented; counted separately from services and agents |

Counts are computed in UTC and grouped by user-selected `day | week | month`; display interval boundaries and distinction between **observed/recorded** and **planned**. No false comparisons for periods before instrumentation. If historical replay is incomplete for a period, show a conspicuous limitation rather than extrapolating.

**Deferred visualization API contract:** `GET /api/v1/graph?as_of=...`, `GET /api/v1/evolution/metrics`, `GET /api/v1/evolution/timeline`. A local-only, explicit command or authenticated owner action can record milestone events; GitHub releases are not assumed to have been imported unless an integration actually does so. Each endpoint uses stable DTOs, pagination/bounds and a consistent UTC interpretation. Private live data and synthetic portfolio data must be backed by **different fixtures/data sources**; never publish a redacted live DB dump as the public demo.

**Tests:** double registration is idempotent; rename doesn't increase entity count; retirement reduces active count; reactivation follows an explicit event; link add/remove changes historical topology; historical labels are preserved; `as_of` cutoff excludes future events; event timestamp/order and UTC behavior are deterministic; no PII in demo/events; project growth charts match known synthetic fixtures.

### 10.5 Four conceptual views and replay limits

- **Live System Map:** registered topology plus the latest observed state, including observation time and unknown/stale status when evidence is missing or outdated.
- **Project Evolution / Growth Analytics:** lifecycle history, historical topology and component growth from `system_events`.
- **Historical Activity Replay:** execution and operational activity over a selected interval, correlated with the topology known at that time. Animated playback is a post-MVP enhancement.
- **Portfolio Demo:** an isolated synthetic presentation mode that can demonstrate the other views; it has no access to private live storage.

Topology snapshots cannot reconstruct past tool calls, health checks or backups. A latest-heartbeat row cannot reconstruct availability history. Choose event detail and retention when execution/telemetry features arrive; replay must show coverage gaps and expired/uncollected periods honestly. Preserve lifecycle history independently of bounded operational retention. No replay API, animation, Three.js dependency or new event broker belongs in M0.

## 11. Pragmatic security baseline — secure enough to build, not security theater

**Decision:** PAW starts as a **single-owner, loopback-only local development system**. Security must prevent predictable mistakes without postponing the first working feature. The list below is a **phased plan**, not a requirement to install every scanner in M0. Keep security work proportionate to what is actually deployed.

### 11.1 M0 — lightweight, required foundation

- Keep `.env`, credential files, personal datasets, database/n8n volumes and generated artifacts out of Git; provide placeholder-only `.env.example`. Never commit a real API key, token, password or local DB dump.
- Bind published development ports to `127.0.0.1` when practical, keep PostgreSQL internal to the Compose network, and do **not** expose n8n administration or live API publicly. Document that local endpoints have **no production authentication** and must not be Internet-exposed.
- Use non-hardcoded credentials injected from private local environment configuration; no real passwords in source or Compose examples. Do not print secrets in errors/logs.
- CI runs the existing lint/type/unit tests **plus one lightweight secret-leak check** on committed changes (prefer a pinned Gitleaks action/CLI). Do not add a full bundle of scanners. A confirmed leaked secret is a blocker; investigate potential false positives and document narrow exceptions instead of disabling the entire check.
- Add a concise `docs/security.md`: local-only assumptions, protected data/entry points, what is *not* protected yet, the public-deployment gate below, and an incident step: revoke/rotate a leaked credential and remove it from Git history when necessary. Keep it short.

### 11.2 M1–M3 — protect the features we actually implement

- **M1 (Data Agent / files):** cap upload sizes, validate CSV structure, prevent path traversal, allowlist tools, enforce runtime/resource limits and **never execute arbitrary model-generated Python, shell, SQL or spreadsheet formulas**. Treat untrusted files and LLM output as data. Test these boundaries with focused negative cases.
- **M1 (dependencies):** enable weekly Dependabot updates *or* a scheduled/manual `pip-audit` check when the dependency set becomes real. Prefer **one** dependency-vulnerability workflow initially; keep informational findings triaged rather than creating automatic PR-blocking churn for every advisory.
- **Visualization / portfolio slice:** redact sensitive event fields; use strictly synthetic fixtures for public portfolio demonstration. No private logs, files, hostnames or real access tokens in demo payloads.
- **M3 (n8n):** keep admin interface local/private, persist encryption credentials securely, authenticate incoming integration events, enforce request bounds and idempotency. No public unauthenticated webhooks to sensitive actions.
- For all stages, require explicit owner approval for external writes or dangerous capabilities. Future Developer Agent must execute untrusted code only in a restricted sandbox and receive separate permission review before deployment.

### 11.3 M4 and before any public exposure — explicit release gate

**Only if/when the live system is reachable from the Internet or external users:** add authentication/authorization, HTTPS/TLS, rate limiting, narrow CORS, appropriate network isolation, backup/restore plan, permission review and public-facing error/log redaction. Validate these controls **before** opening ports or deploying a writable endpoint publicly. Basic local read-only demos with wholly synthetic data may be isolated separately.

Run a targeted pre-release security review: check dependencies (`pip-audit` or equivalent), scan release images with **Trivy**, validate containers' privileges and network exposure, and review n8n/API secrets. **Bandit** may be introduced when custom Python code or tool-execution surface justifies it; do not make it an automatic M0 requirement. Prefer a small documented checklist to a heavyweight continuous security platform.

### 11.4 What blocks a milestone, and what does not

- **Block immediately:** real secret committed or exposed; a publicly reachable unauthenticated privileged operation; arbitrary code execution introduced into a user/LLM tool path; proven critical vulnerability in the shipped path; failing core tests; unsafe upload path traversal.
- **Track and schedule, do not automatically block local MVP:** informational scanner warnings, low-risk dependency advisories without an applicable exploit path, future-only multi-user/auth/SSO capabilities, formal penetration tests, Kubernetes policies, complex secrets management, full SBOM/compliance infrastructure.
- Findings live in GitHub Issues or `PLANS.md` with severity, rationale and next action. A scanner failure must be investigated, not silently ignored; a documented false positive can be narrowly waived.

**Scope boundary:** M0 is **not** a security project. Do not implement OAuth, Vault, security dashboards, public HTTPS reverse proxies, multi-tenant permissions or an enterprise threat-modeling program before the first useful end-to-end workflow.

## 12. Target repo layout (create directories only with their feature)

```text
personal-ai-workspace/
├── AGENTS.md                  # durable Codex instructions
├── PROJECT_BLUEPRINT.md       # this document
├── PLANS.md                   # work plan and milestone status
├── README.md                  # English project overview and quickstart
├── CONTRIBUTING.md
├── LICENSE                    # MIT for original repository code
├── .env.example
├── .gitignore
├── .github/workflows/ci.yml
├── backend/
│   ├── pyproject.toml
│   ├── src/paw/
│   │   ├── api/
│   │   ├── application/
│   │   ├── domain/
│   │   ├── agents/data_analyst/
│   │   ├── tools/
│   │   └── infrastructure/{db,llm,execution,storage,n8n,observability}/
│   ├── migrations/
│   └── tests/{unit,integration,contract}/
├── frontend/
│   ├── app/                   # or src/app, choose consistently
│   ├── components/system-map/
│   ├── components/project-evolution/
│   └── tests/
├── automation/n8n/workflows/
├── infrastructure/compose.yaml
├── docs/
│   ├── architecture.md
│   ├── security.md
│   ├── development.md
│   └── adr/
├── examples/
│   ├── sample_campaigns.csv
│   └── demo_graph.json
└── scripts/
```

`AGENTS.md` stays short and practical; detailed decisions belong in `PROJECT_BLUEPRINT.md`, ADRs and `PLANS.md`.

## 13. Development milestones — vertical slices

### M0 — Repository foundation

**Deliverables:** repo scaffold, docs, license, `.env.example`, clean `.gitignore`, lint/type/test configuration, CI **with one lightweight secret check**, Docker Compose with PostgreSQL + FastAPI health check, loopback-only published ports, and a **short** `docs/security.md`; include an inactive optional n8n Compose profile; actual integration and registration belong to M3. **Additionally:** a minimal `service_nodes` + `service_edges` + **append-only** `system_events` schema/migration, idempotent first-registration command for verified `service:api` and `storage:postgres`, and verified API-to-database link registration, with PostgreSQL integration tests for atomicity, append-only enforcement and concurrent duplicate protection. The project starts recording its actual evolution now (no fabricated backstory).

**Acceptance:** a fresh checkout can boot the minimal local-only stack using documented commands; `GET /api/v1/health` returns 200; automated lint/tests and the minimal secret check run successfully; no credentials in Git and no unintended public ports. Running bootstrap twice leaves the same components and event counts, and recorded timestamps are UTC. Do **not** delay M0 to add extra security scanners or production authentication.

### M1 — Durable agent execution + CSV processing

**Deliverables:** remaining run/file/project models and migrations; upload endpoint with size/type/path validation; `runs` API; separate worker; deterministic CSV tools with an allowlist and execution bounds; Data Analyst with provider adapter; run-event persistence; offline fake model tests. Add a weekly dependency check once dependencies are in use (Dependabot **or** `pip-audit`, not a large scanner matrix). Register the agent only when the executable agent exists and record its lifecycle event.

**Acceptance:** request returns `run_id` with `202`, worker transitions through states and persists a numerically correct report and chart. Restarting API must not discard queued work. Failing tools produce a failed run with an explainable error, not hanging indefinitely. Worker interruption and lease expiry must recover work; an expired claimant cannot overwrite a newer attempt. CSV fixtures define aggregation semantics, missing-value behavior and zero-denominator handling.

### M2 — Responsive workflow UI

**Deliverables:** English Next.js UI with file upload, run form, report/chart view, history, error states and mobile-friendly layouts. Continue recording actual component and relationship changes.

**Acceptance:** the owner can complete the CSV workflow from a desktop or mobile browser, revisit results and inspect failures. No System Map, growth charts or historical query APIs are required for M2.

### M3 — n8n integration + core MVP reproducibility

**Deliverables:** n8n container and persistence; private admin access, protected credentials, authenticated event endpoint; scheduled health-check workflow, exportable JSON; sanitized setup walkthrough and README quickstart. Portfolio fixtures and visualization remain deferred.

**Acceptance:** n8n workflow produces an authenticated, idempotent event visible through the API and task/activity UI; a second fresh checkout can reproduce setup. If the API is unavailable, n8n records the failure locally and performs bounded delivery retries; it cannot report an outage through the same unavailable API immediately.

**MVP COMPLETE:** only when M0–M3 pass. At this point the first useful browser workflow, durable execution, factual history collection and automation component function end to end. Visualization and online deployment have separate acceptance gates.

### M4 — Private online deployment and release

Choose hosting and a budget based on the working stack. Deploy one owner-only system that operates independently of the development MacBook; do not introduce bidirectional development/production database synchronization. Add test coverage, a **targeted** security review, documentation, sample data, versioned release and clearer error handling. Before publishing a **live** deployment, perform the public-exposure gate in §11.3 (auth/TLS/rate limiting, dependency audit, Trivy scan, n8n review). Optional Bandit and expanded CI only if relevant risk warrants it. Avoid making portfolio work contingent on enterprise-grade security tooling.

### Post-MVP — Separately scoped extensions (not scheduled)

**Visualization:** implement §10 historical APIs, map, growth charts and isolated synthetic portfolio fixtures. Validate known earlier topology, label/type changes, retirements, links and metrics without backdating.

**Capture and learning:** implement shared capture and source provenance, then one image-to-vocabulary workflow with full extraction and owner review. Add Telegram as a channel through the API. Order these slices according to actual use; do not build them all together.

### M5+ — Optional External Projects Integration (post-MVP, not scheduled)

Introduce a generic project catalog and read-only external connections **only when a concrete connection is requested**. Support independent repository/service lifecycles, verifiable status, project-specific timeline and optional map nodes. No project-specific agents, background watchers, or code changes to external projects are promised at this stage. The first actual integration should be delivered as a separate, narrowly scoped vertical slice with its own tests and explicit authorization.

## 14. Future extensions and boundaries

### 14.1 External Projects Integration — planned architectural capability (post-MVP)

**Purpose:** PAW becomes a personal coordination and visibility layer for **independent projects**, including projects that already exist outside PAW and future work. Their code, deployments, CI/CD, data and release lifecycles remain under the ownership of their original repositories/systems. **PAW is not a monorepo into which those projects must be moved.**

**Conceptual model (no implementation in M0–M3):**

- **Project catalog:** a stable PAW `project_id` identifies each project independently from its URL/name. A project can be an internal PAW workstream or an externally hosted project. External locations are optional connections, not project identity.
- **Project connections:** an external project may expose zero or more links (GitHub repository, external API, deployment/health endpoint, manual record). A typed, replaceable connector reads the relevant information; adding GitHub should not lock the domain model to GitHub.
- **Progressive integration:** `catalog only` (known project) → `connected / observe` (authorized read-only metadata, checks and history) → `assisted` (optionally create issues/PRs or schedule jobs) → `controlled actions` (only with explicit approval and least-privilege credentials). Each capability is independently opt-in; there is no automatic takeover of an existing project.
- **Monitoring and visualization:** optional project nodes/links may appear on the system map once a connection is **actually registered**. Their status must reflect observed evidence, otherwise `unknown`. Keep `project` counts separate from `agent`, `service` and `integration` growth metrics. Clearly distinguish unconnected/idea/planned items from live systems.
- **Evolution history:** record connection/retirement and meaningful project milestones as sanitized, versioned, idempotent events (`project.registered`, `project.connected`, `project.disconnected`, `project.milestone`, etc.). Use actual recorded times; do not backdate connected status from old Git commits. Historical map replay must not show a future connection in an earlier snapshot.
- **Safety and ownership:** external access is read-only by default, secrets remain out of Git/logs/event payloads, private repository names/URLs are hidden in portfolio mode, webhooks are verified, rate limits/retries are bounded, and write/deploy actions require explicit owner approval and isolated permissions.
- **Scope discipline:** no external-project adapter, project watcher, new database tables, remote repo cloning, external-project endpoints or connection UI in **M0–M3**. Only preserve boundary compatibility and document the future extension. Implement the smallest useful connector later when the owner chooses a project.

**Future candidates — examples only, not specifications or commitments:**

- `grants` — an existing independent project; technical details and connection method to be determined later.
- [`estonian_petitions`](https://github.com/Volodymyr75/estonian_petitions) — an existing external GitHub project; repo has **not** been analyzed as part of this Blueprint.
- Interactive map of Estonian YouTube — future project idea.
- Automated discovery and evaluation of passive-income or business ideas — future project idea.
- Other future projects, including ones with no GitHub repository or public endpoint.

Do **not** treat the listed candidates as deployed/connected, create agents for them, or count them as live nodes. Their product scope, infrastructure, integrations and timeline are explicitly deferred.

### 14.2 Other potential extensions

| Addition | Main new module | Stable contract / migration |
|---|---|---|
| Language Tutor | `agents/language_tutor`, study store, progress | Uses run API, events, tool interfaces |
| Marketing Analyst | advertising connectors and metrics adapters | Uses Data Agent analysis tools |
| Research/ML Agent | retrieval + safe experiment tools | Uses agent registry/runtime |
| Developer Agent | GitHub integration, sandboxed code actions, approval workflow | Uses run + artifact + approval contracts |
| External Projects Integration | Catalog + typed read-only repository/service adapters; optional observed nodes and milestones | Independent project identity, project connections and append-only history; post-MVP |
| Project Watcher | scheduler + health checks + notifications | Uses n8n + run/event API |
| Multi-agent plans | orchestrator workflow and state machine | `AgentRunner` remains replaceable |
| Multi-LLM routing | LiteLLM or custom gateway | `ModelClient` boundary |
| Shared semantic memory | vector search / pgvector if justified | `MemoryStore` adapter introduced then |
| Distributed jobs | Redis + queue or equivalent | `ExecutionDispatcher` replacement |
| Cloud deployment | IaC/reverse proxy/auth/secret manager | API contracts unchanged |
| Advanced observability | OpenTelemetry, Langfuse, Grafana | structured events already collected |

### 14.3 Service extraction policy

**Criteria for extraction to microservice:** independent scaling or deployment need; independent ownership/lifecycle; security isolation; different resource/runtime characteristics; sustained workload. Extraction requires moving ownership of data, adding contract and network failure tests, monitoring and migrations. It is possible but never completely automatic.

**Explicitly not in MVP:** Kubernetes, public SaaS, multi-user auth, agent marketplace, arbitrary shell/code execution, automatic production deployments, vector DB, complex RAG, 3D graphics, an AI model router, 10 prebuilt agents, direct billing and payments, **external project connections/synchronization/control**.

## 15. QA and Definition of Done

All features must ship with:

- working unit tests and integration tests for changed behavior;
- meaningful error handling and structured logs;
- documentation updates and, for major choices, an ADR;
- stable API shape or a documented migration;
- no secrets/PII in fixtures or logs; apply the proportional security checks for the **current** milestone (§11) rather than the entire future checklist;
- valid Docker Compose startup (when environment permits);
- clean lint/format/type checks;
- an explicit manual acceptance test for the user;
- clear notes if commands could not be run in Codex environment.

### End-to-end MVP acceptance tests

1. With a clean local environment, start stack; API/readiness checks succeed.
2. Open the responsive web UI and inspect actual task history and results.
3. Upload bundled sample CSV and run deterministic statistics; assert known CTR/CPC totals are correct.
4. Submit natural-language request and obtain persisted run output/artifact through UI.
5. Refresh browser/restart API; run history and artifacts remain accessible.
6. Cause a controlled failed analysis; view error state/events instead of fake success.
7. Trigger scheduled n8n check; see its authenticated event in the API and activity UI.
8. Confirm source files and generated artifacts remain associated with the correct run.
9. Run automated tests without real LLM credentials using model mocks/fakes.
10. CI fails on lint, test or typecheck regressions and a **confirmed** secret leak; lower-risk advisory findings are tracked according to §11 rather than forcing a halt to local MVP.
11. Verify lifecycle changes preserve stable keys and sanitized full after-state events; retries do not duplicate registrations.
12. Verify real node/link changes are recorded atomically with their projections, with no future/planned components registered.
13. Restart/reseed the stack and confirm no duplicate system lifecycle events appear.
14. Verify unavailable health and telemetry are represented as unknown/not collected, not fabricated success or zero.
15. No unconnected external project idea or repository is shown as a healthy/running PAW service or counted as an active agent/integration; the future external-project mechanism must be opt-in and separately authorized.

### Additional acceptance gates

- **M4:** verify owner authentication, HTTPS, bounded requests, private database/admin services, persistent storage and backup/restore before online use.
- **Visualization:** replay earlier topology with historical labels and links; verify counts against event fixtures, exclude future events and do not reuse present-day health.
- **Portfolio:** demonstrate that synthetic data sources cannot read live/private storage; clearly label simulated history.

## 16. Codex delivery rules

Codex should **not implement the entire project in one pass**. Use one milestone or coherent vertical slice per task, review changes and tests, and commit after successful validation. Read `AGENTS.md` and `PLANS.md` before working. Use `PROJECT_BLUEPRINT.md` for requirements and architecture decisions; for unclear implementation details, choose minimal compatible decisions and document them in an ADR.

At the end of each task Codex must report:

- what changed and why;
- files created/modified;
- commands/tests run and results;
- technical tradeoffs and unresolved issues;
- exact steps to manually verify;
- recommended next task.

### M0 starter command for Codex

See `CODEX_START.md`. It intentionally requests only the repository foundation and one small executable slice.

---

## 17. Architecture decision register

ADR-001–011 below are design summaries, not claims that separate ADR files or implementations exist. ADR-012 records the approved revision to delivery scope.

- **ADR-001**: Modular monolith with separate API and worker processes.
- **ADR-002**: n8n external automation service; platform owns durable agent runs.
- **ADR-003**: PostgreSQL for platform state, separate logical n8n database.
- **ADR-004**: Provider-neutral `ModelClient`; no mandatory AI gateway in MVP.
- **ADR-005**: System Map backed by explicit registry, observed health and real event log.
- **ADR-006**: Single-owner local development, later private online deployment; public demo uses isolated synthetic fixtures (updated by ADR-012).
- **ADR-007**: Data Analyst as first complete vertical slice; safe deterministic tools.
- **ADR-008**: Append-only `system_events` from M0 plus current registry projection; historical reconstruction and growth metrics in a deferred visualization slice; minimal link history also begins in M0 (ADR-012).
- **ADR-009**: Project Evolution replay uses recorded UTC timestamps and separate synthetic portfolio fixtures.
- **ADR-010 (planned)**: External Projects Integration keeps repositories independent and adds connections via typed least-privilege adapters, not by importing projects into PAW. Not implemented in MVP.
- **ADR-011**: Proportional security: minimal M0 secrets/local-network safeguards; feature-specific input and capability controls during MVP; public-exposure review as a distinct gate, not an M0 prerequisite.

- **[ADR-012](docs/adr/ADR-012-delivery-and-history.md)**: Single-owner online direction, deferred visualization, factual node/link history from M0, and later capture/language workflows.
- **[ADR-013](docs/adr/ADR-013-operations-and-visualization-boundaries.md)**: Separate lifecycle, execution and operational data; future correlated usage and renderer-neutral views without expanding M0.
- **[ADR-018](docs/adr/ADR-018-google-ads-json-batches.md)**: M1.4 local Google Ads JSON batches preserve report grains, exact decimals, provenance and coverage limitations before later evidence/AI processing.

## 18. Source and licensing references

- Codex AGENTS.md: https://learn.chatgpt.com/docs/agent-configuration/agents-md
- Codex workflow planning: https://developers.openai.com/cookbook/examples/codex/iterating-development-workflows-with-codex
- FastAPI background tasks: https://fastapi.tiangolo.com/tutorial/background-tasks/
- Pydantic AI: https://pydantic.dev/docs/ai/core-concepts/agent/
- React Flow: https://reactflow.dev/
- n8n Docker: https://docs.n8n.io/hosting/installation/docker/
- n8n community licensing: https://github.com/n8n-io/n8n/blob/master/LICENSE.md

These links are references, not dependencies to vendor into PAW. Verify license terms and current versions before publication and deployments.
