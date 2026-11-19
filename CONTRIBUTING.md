# Contributing

Read `AGENTS.md`, `PROJECT_BLUEPRINT.md`, `PLANS.md` and relevant ADRs before changing code. Keep changes within the active milestone. See [development.md](docs/development.md) for setup and required checks.

Commit dependency lockfiles, use Alembic for schema changes and keep domain contracts independent of frameworks. Never commit private data, real credentials or generated local state. Tests must not depend on paid AI APIs. Explain what changed, how it was verified and any remaining limitations.
