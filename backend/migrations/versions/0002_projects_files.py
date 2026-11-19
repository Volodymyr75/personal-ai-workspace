"""Single-owner projects and CSV metadata. No run or agent models yet."""

from alembic import op

revision = "0002_projects_files"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE workspaces (
            id uuid PRIMARY KEY,
            name varchar(120) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp()
        );
        INSERT INTO workspaces (id, name)
            VALUES ('00000000-0000-0000-0000-000000000001', 'Personal workspace');
        CREATE TABLE projects (
            id uuid PRIMARY KEY,
            workspace_id uuid NOT NULL REFERENCES workspaces(id),
            name varchar(120) NOT NULL CHECK (length(btrim(name)) > 0),
            description varchar(2000) NOT NULL DEFAULT '',
            created_at timestamptz NOT NULL DEFAULT clock_timestamp()
        );
        CREATE INDEX ix_projects_created ON projects(created_at, id);
        CREATE TABLE files (
            id uuid PRIMARY KEY,
            project_id uuid NOT NULL REFERENCES projects(id),
            original_name varchar(255) NOT NULL,
            storage_key varchar(40) UNIQUE NOT NULL,
            mime_type varchar(64) NOT NULL CHECK (mime_type = 'text/csv'),
            size_bytes bigint NOT NULL CHECK (size_bytes > 0 AND size_bytes <= 10485760),
            sha256 varchar(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
            row_count integer NOT NULL CHECK (row_count BETWEEN 1 AND 100000),
            column_count integer NOT NULL CHECK (column_count BETWEEN 1 AND 200),
            delimiter varchar(1) NOT NULL CHECK (delimiter IN (',', ';')),
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            CHECK (storage_key = id::text || '.csv')
        );
        CREATE INDEX ix_files_project_created ON files(project_id, created_at, id);
    """)


def downgrade() -> None:
    raise RuntimeError(
        "Destructive file metadata downgrade is disabled; restore a backup explicitly"
    )
