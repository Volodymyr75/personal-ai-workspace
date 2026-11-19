"""Durable diagnostic runs and correlated execution events."""

from alembic import op

revision = "0003_runs"
down_revision = "0002_projects_files"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE runs (
            id uuid PRIMARY KEY,
            project_id uuid NOT NULL REFERENCES projects(id),
            request_id uuid UNIQUE NOT NULL,
            correlation_id uuid,
            task_type text NOT NULL CHECK (task_type = 'diagnostic'),
            delay_seconds integer NOT NULL CHECK (delay_seconds BETWEEN 0 AND 30),
            outcome text NOT NULL CHECK (outcome IN ('success','failure')),
            status text NOT NULL CHECK (status IN ('queued','running','completed','failed')),
            attempt_id uuid,
            attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count BETWEEN 0 AND 3),
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            started_at timestamptz,
            finished_at timestamptz,
            lease_expires_at timestamptz,
            attempt_deadline timestamptz,
            error_code text,
            output jsonb,
            CHECK ((status = 'running') = (lease_expires_at IS NOT NULL)),
            CHECK ((status IN ('completed','failed')) = (finished_at IS NOT NULL)),
            CHECK (status <> 'running' OR (attempt_id IS NOT NULL AND attempt_deadline IS NOT NULL))
        );
        CREATE INDEX ix_runs_claim ON runs(status, created_at, id);
        CREATE TABLE run_events (
            id uuid PRIMARY KEY,
            sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE NOT NULL,
            run_id uuid NOT NULL REFERENCES runs(id),
            attempt_id uuid,
            event_type text NOT NULL CHECK (event_type IN
                ('queued','started','lease_expired','completed','diagnostic_failed','attempts_exhausted')),
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
        );
        CREATE INDEX ix_run_events_run_sequence ON run_events(run_id, sequence);
    """)


def downgrade() -> None:
    raise RuntimeError("Destructive run history downgrade is disabled")
