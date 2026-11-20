"""Typed analysis inputs and attempt-owned report/chart metadata."""

from alembic import op

revision = "0004_analysis_artifacts"
down_revision = "0003_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE runs DROP CONSTRAINT runs_task_type_check;
        ALTER TABLE runs ADD CONSTRAINT runs_task_type_check
            CHECK (task_type IN ('diagnostic','csv_analysis'));
        ALTER TABLE runs ADD COLUMN file_id uuid REFERENCES files(id);
        ALTER TABLE runs ADD COLUMN analysis_json jsonb;
        ALTER TABLE runs ADD CONSTRAINT runs_analysis_input_check CHECK (
            (task_type='diagnostic' AND file_id IS NULL AND analysis_json IS NULL) OR
            (task_type='csv_analysis' AND file_id IS NOT NULL AND analysis_json IS NOT NULL));
        ALTER TABLE run_events DROP CONSTRAINT run_events_event_type_check;
        ALTER TABLE run_events ADD CONSTRAINT run_events_event_type_check CHECK (event_type IN
            ('queued','started','lease_expired','completed','diagnostic_failed','attempts_exhausted',
             'analysis_failed'));
        CREATE TABLE artifacts (
            id uuid PRIMARY KEY,
            run_id uuid NOT NULL REFERENCES runs(id),
            attempt_id uuid NOT NULL,
            kind text NOT NULL CHECK (kind IN ('report','chart')),
            mime_type text NOT NULL CHECK (mime_type IN ('application/json','image/png')),
            size_bytes integer NOT NULL CHECK (size_bytes BETWEEN 1 AND 2097152),
            sha256 varchar(64) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            UNIQUE(run_id,kind)
        );
    """)


def downgrade() -> None:
    raise RuntimeError("Destructive artifact downgrade is disabled")
