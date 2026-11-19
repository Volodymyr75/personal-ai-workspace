# Development and verification

## Tools

For the complete container workflow, install and start Docker Desktop (Apple Silicon on M-series Macs), plus Git. No AI account, API key, hosting account or n8n integration credentials are needed for M0.

For native code checks, install Python 3.13.18 through uv 0.13.9 and Node.js 24.22.3 with npm. Versions are recorded in `backend/.python-version` and `.node-version`. `uv sync --frozen` and `npm ci` install the committed dependency sets. Project-local `.tools/` installations are ignored and optional; they are not part of the repository.

## Container workflow (from repository root)

```sh
python3 scripts/init_local_env.py
docker compose --env-file .env -f infrastructure/compose.yaml config --quiet
docker compose --env-file .env -f infrastructure/compose.yaml up --build -d api web
docker compose --env-file .env -f infrastructure/compose.yaml exec api python -m paw.cli bootstrap
curl --fail http://127.0.0.1:8000/api/v1/health
curl --fail http://127.0.0.1:8000/api/v1/ready
```

Open `http://127.0.0.1:3000`. The foundation pages are English, responsive and explicitly mark unavailable workflows. The shell does not query or imply live health. API docs are at `http://127.0.0.1:8000/docs`.

Compose runs migrations before starting the API. Run bootstrap again: it should log `bootstrap_unchanged`. Verify the actual database counts and timestamps without printing credentials:

```sh
docker compose --env-file .env -f infrastructure/compose.yaml exec postgres psql -U paw -d paw -c "SELECT event_type, entity_key, sequence, recorded_at FROM system_events ORDER BY sequence;"
```

Expected first installation: two nodes, one link and three events. The times are when this installation actually registered the components, not the repository creation date. A database volume reset loses this installation's history; do not remove volumes casually.

## Checks

```sh
cd backend
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest tests/unit -q
cd ../frontend
npm ci
npm run lint
npm run format:check
npm run typecheck
npm run build
cd ..
docker compose --env-file .env -f infrastructure/compose.yaml --profile test run --build --rm tests
```

Docker tests use a separate `paw_test` database with temporary storage and a fresh random schema per test. They never drop/reset the live `paw` database. Native integration tests require `PAW_TEST_DATABASE_URL` pointing to a dedicated database named exactly `paw_test`; without it they are skipped, which is not evidence of database correctness. CI and the Compose test service set it and run the full suite.

The integration suite verifies migrations, real readiness, concurrent bootstrap, retry idempotency, full event after-state, rollback after an injected failure, append-only enforcement and server-controlled timestamps. A missing historical event for an existing registry entry is rejected rather than backfilled.

## M1.1 manual CSV check

Open [API docs](http://127.0.0.1:8000/docs). Use **Try it out** on `POST /api/v1/projects` with `{"name":"CSV practice","description":"Synthetic example"}`. Copy the returned `id`, then use `POST /api/v1/files`: enter it as `project_id`, leave delimiter as comma and select `examples/sample_campaigns.csv` from this repository. A successful upload returns HTTP 201, three data rows, column count and a SHA-256 checksum.

Use `GET /api/v1/projects/{project_id}/files` and `GET /api/v1/files/{file_id}` to retrieve metadata. Restart the API and repeat the GET: metadata and original bytes should persist. The web frontend remains the foundation shell; it has no upload controls yet. Upload does not start analysis or call an AI provider.

CSV must be UTF-8 (BOM allowed), with unique nonblank headers and consistent columns. Maximum: 10 MiB, 100,000 data rows, 200 columns, 256 characters per header and 32,768 characters per cell. Semicolon requires explicitly selecting `;`. Unsupported file media types return 415, invalid CSV returns 422, oversize returns 413 and unavailable persistence returns 503. Errors do not echo source contents. Project/file lists support `limit` (1–100) and `offset` (0–100000).

Originals use server UUID names in the dedicated `file_data` Docker volume. Database and file volumes form one installation and must be preserved together. Cleanup after failed writes is tested; recovery details and limitations are in [ADR-015](adr/ADR-015-projects-and-csv-storage.md). Download, delete, editing, runs and analysis remain unimplemented.

## Stop and recover

```sh
docker compose --env-file .env -f infrastructure/compose.yaml stop
```

Named live volumes persist. Start again with `up -d api web`; registration must remain unchanged. To test readiness failure manually, stop only `postgres`: `/ready` returns 503 while `/health` returns 200. Start `postgres` again and wait for readiness recovery. Do not run destructive volume-removal commands on history you intend to preserve.

## Optional n8n

See [automation/n8n/README.md](../automation/n8n/README.md). It is deliberately inactive in the default workflow. No scheduled automation, integration endpoint, worker or AI agent is implemented in M0.
