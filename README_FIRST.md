# Personal AI Workspace — documentation guide

This repository is at the documentation stage. Blueprint v1.5 incorporates the owner's November 19, 2026 decisions. No application or deployment exists yet.

## Read in this order

1. [README.md](README.md) — public project overview and intended experience.
2. [AGENTS.md](AGENTS.md) — implementation rules and scope boundaries.
3. [PROJECT_BLUEPRINT.md](PROJECT_BLUEPRINT.md) — architecture and milestone requirements.
4. [PLANS.md](PLANS.md) — current state, next slice and acceptance checklist.
5. [ADR-012](docs/adr/ADR-012-delivery-and-history.md) — rationale for revised delivery and history collection.
6. [ADR-013](docs/adr/ADR-013-operations-and-visualization-boundaries.md) — lifecycle/execution/telemetry separation and visualization boundaries.
7. [CODEX_START.md](CODEX_START.md) — implementation brief for M0, to use when starting that milestone.

## Delivery sequence

The Git repository and introductory README already exist. Preserve their history. Implement M0 in small verifiable slices, then durable CSV analysis, responsive web use and an actual n8n workflow (M1–M3). Private online deployment is M4 and has its own access and deployment checks.

Record verified components and logical links from M0. Defer System Map, historical query APIs, growth charts and synthetic portfolio demonstrations to a separate post-MVP slice; never reconstruct missing facts by backdating.

Image-to-vocabulary processing and Telegram capture are later practical workflows. External-project connectors remain optional and post-MVP. Examples in the Blueprint do not authorize connections to other repositories.

Keep credentials, personal files, environment files and database volumes out of Git. Public demonstrations use isolated synthetic content. Security remains proportional to the current feature and deployment boundary.
