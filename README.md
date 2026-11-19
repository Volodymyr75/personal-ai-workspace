# Personal AI Workspace (PAW)

A personal AI workspace for turning everyday files, questions, and ideas into useful, reusable results.

PAW is both a practical tool and a learning project: an opportunity to build experience with AI engineering, backend development, workflow automation, and reliable software delivery while automating recurring personal tasks.

> **Status: M0 foundation and M1.1 CSV storage implemented locally.** Projects, validated CSV uploads and persistent file metadata are available through the API, alongside health/readiness, component history and a Next.js foundation shell. CSV analysis, agents, Worker, upload UI, Telegram, integrated n8n workflows and online deployment are not implemented. The complete product workflows below remain planned.

## What PAW is for

The first workflow will be deliberately small: upload a CSV, request an analysis, run deterministic calculations, and save a report and chart. CSV analysis establishes the foundation for later workflows involving images, screenshots, documents, and learning materials.

The longer-term experience connects three activities:

- **Capture:** send a file, screenshot, message, or idea into a shared inbox.
- **Process:** request a specific operation and track its progress and result.
- **Reuse:** review, edit, organize, and find saved materials and outputs.

Saving a material does not have to trigger an AI call. Tasks should run on an explicit request or a deliberately configured automation.

## Planned workflows

### File and data analysis

Upload a CSV and ask a question. Validated tools calculate statistics and aggregations; an AI model helps interpret the computed results. Reports and charts remain available after the task finishes.

Numerical results come from deterministic tools. Models will not receive arbitrary Python, shell, or SQL execution capabilities.

### Language learning from photos and screenshots

Submit an image or document containing Estonian or English learning material. The intended workflow is:

1. Preserve the original and extract all readable text, flagging uncertain passages.
2. Prepare draft words and expressions with Ukrainian explanations and source context, without silently discarding material as unimportant.
3. Let the owner select, correct, remove, or edit entries before saving them.
4. Keep the original and extracted text available for later review.

AI-generated examples will be distinguishable from text found in the source. Vocabulary storage, search, and simple review can grow into a learning module over time.

### Personal automation

Use scheduled workflows for recurring tasks and checks. Start with one small, observable n8n integration, then add further automations when there is a concrete need.

## Access and workspace experience

PAW is designed for one owner, with desktop and mobile access:

- **Responsive web interface:** review results, work with reports, organize materials, and manage tasks.
- **Telegram bot, planned for a later slice:** capture photos, screenshots, files, and messages; receive brief results and links to the workspace.
- **Optional device shortcuts, to be evaluated later:** reduce friction when capturing material on iPhone and MacBook.

The proposed workspace has an **Inbox** for incoming materials, **Tasks** for execution history, and a **Library** for saved sources and results. All channels use the same platform data and task lifecycle.

The interface and general reports will use English. Language-learning explanations and translations will use Ukrainian, while preserving the original language of the material.

## Planned architecture

PAW uses a modular Python backend with separate API and Worker processes built from the same codebase. Additional agents are modules with explicit registration and restricted typed tools.

| Component | Responsibility | Planned technology |
| --- | --- | --- |
| Web interface | Desktop and mobile workspace | Next.js, TypeScript |
| Platform API | Files, projects, task state, artifacts, registry, and events | FastAPI, Pydantic |
| Worker | Durable asynchronous execution and recovery | Python, PostgreSQL-backed job claiming |
| Database | Platform state and event history | PostgreSQL, SQLAlchemy, Alembic |
| Agent runtime | Model-assisted tasks behind replaceable interfaces | Pydantic AI, provider adapters |
| Data tools | Validated calculations and chart generation | Pandas, chart tooling |
| Automation | Schedules and external workflow triggers | Self-hosted n8n |
| File storage | Original materials and generated artifacts | Local volumes initially, replaceable storage adapter |
| Development environment | Reproducible local services | Docker Compose |

The platform owns durable run state and system history. The frontend, bots, and n8n communicate through the versioned HTTP API; they do not modify platform database tables directly. n8n keeps its own state separate.

External AI APIs are part of the intended design. Provider choice and hosting budget remain open until the first workflows can be measured. Tests will use deterministic fixtures and fake model providers rather than paid API calls.

## System history before visualization

The future System Map and Project Evolution views will show how the workspace actually develops. Their interface can come later; the information needed to build them must be collected from the beginning.

The foundation will record verified components and their logical relationships with stable identities and server timestamps. Node and link changes will have durable, append-only history from M0. Retries and renames must not inflate growth counts.

Historical views must distinguish what was recorded from what was merely planned. Missing health observations are **unknown**, and unavailable telemetry is **not collected**. Earlier topology must not be invented from the current system state.

Source-to-result traceability is a separate concern: a saved vocabulary entry or report should retain its connection to the material and task that produced it.

## Delivery direction

The project will be delivered in small, verifiable slices. The following is a direction of travel, not a claim of completed milestones or a fixed release schedule.

1. **Foundation (M0):** API health and readiness, PostgreSQL migrations, initial component history, a minimal web shell, development tooling, and CI.
2. **First useful workflow:** durable queued runs, validated CSV uploads, deterministic analysis, persisted reports and charts, then AI interpretation.
3. **Everyday web use:** upload, task tracking, result review, and history through a responsive interface.
4. **Automation and private online access:** a real n8n workflow and a separately verified deployment for the owner.
5. **Additional practical workflows:** image and document processing, language-learning materials, and Telegram capture, introduced one at a time.
6. **System visualization and portfolio presentation:** historical maps and growth views built from recorded events, with a separate synthetic demonstration dataset.

Detailed milestone acceptance criteria are maintained in [PLANS.md](PLANS.md) and [PROJECT_BLUEPRINT.md](PROJECT_BLUEPRINT.md). The map UI is deferred while history collection remains an M0 requirement; [ADR-012](docs/adr/ADR-012-delivery-and-history.md) explains the decision.

## Development, deployment, and privacy

Development starts locally on a MacBook. A private online deployment is planned so the workspace can eventually be used independently of the development laptop. Hosting has not been selected or provisioned.

Security will grow with the features being introduced: keep credentials and personal materials out of version control, validate file inputs, restrict tool capabilities, and protect access to private data. Online deployment requires authentication, HTTPS, and a focused deployment review. These controls should remain proportionate to a single-owner system.

Public portfolio demonstrations will use isolated synthetic content, not private files, logs, or a copied personal database.

## Scope boundaries

The initial project does not include a multi-user SaaS product, a generic plugin marketplace, arbitrary model-generated code execution, automatic production deployments, or a large collection of placeholder agents.

Connections to independent external projects are a post-MVP possibility. Those projects will remain in their own repositories and environments; any future connector must be explicitly selected and scoped.

## Getting started

Install Git and start Docker Desktop. No AI-provider registration or paid API key is needed for M0 or M1.1. From the repository root:

```sh
python3 scripts/init_local_env.py
docker compose --env-file .env -f infrastructure/compose.yaml up --build -d api web
docker compose --env-file .env -f infrastructure/compose.yaml exec api python -m paw.cli bootstrap
```

Wait until the API is healthy before bootstrap (`docker compose --env-file .env -f infrastructure/compose.yaml ps`). Open [the local workspace](http://127.0.0.1:3000) or [API documentation](http://127.0.0.1:8000/docs).

```sh
curl --fail http://127.0.0.1:8000/api/v1/health
curl --fail http://127.0.0.1:8000/api/v1/ready
docker compose --env-file .env -f infrastructure/compose.yaml --profile test run --build --rm tests
```

First bootstrap registers two verified nodes and one logical link with three real events. Repeating it leaves the same records and timestamps. The frontend is a labeled foundation shell, not a working analyzer or live dashboard. Database state persists in a Docker volume. Optional n8n is inactive by default.

See [development and manual verification](docs/development.md), [architecture](docs/architecture.md) and [local security boundaries](docs/security.md). PAW's original code is available under the [MIT license](LICENSE); third-party services retain their own licenses.

For the documentation reading order and implementation handoff, see [README_FIRST.md](README_FIRST.md). Repository working rules are in [AGENTS.md](AGENTS.md), and the M0 task brief is in [CODEX_START.md](CODEX_START.md).
