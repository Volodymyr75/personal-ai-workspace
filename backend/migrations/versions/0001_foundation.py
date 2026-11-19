"""Minimal registry and append-only evolution history; no operational telemetry."""

from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE service_nodes (
            key varchar(160) PRIMARY KEY,
            kind varchar(32) NOT NULL CHECK (kind IN ('service', 'storage')),
            display_name varchar(120) NOT NULL,
            lifecycle_state varchar(16) NOT NULL CHECK (lifecycle_state IN ('active', 'retired')),
            registered_at timestamptz NOT NULL,
            retired_at timestamptz,
            metadata_json jsonb NOT NULL CHECK (jsonb_typeof(metadata_json) = 'object'),
            CHECK ((lifecycle_state = 'active' AND retired_at IS NULL)
                OR (lifecycle_state = 'retired' AND retired_at IS NOT NULL
                    AND retired_at >= registered_at))
        );
        CREATE TABLE service_edges (
            key varchar(200) PRIMARY KEY,
            source_key varchar(160) NOT NULL REFERENCES service_nodes(key),
            target_key varchar(160) NOT NULL REFERENCES service_nodes(key),
            relation varchar(32) NOT NULL CHECK (relation = 'persists_to'),
            registered_at timestamptz NOT NULL,
            retired_at timestamptz CHECK (retired_at >= registered_at),
            UNIQUE (source_key, target_key, relation)
        );
        CREATE TABLE system_events (
            id uuid PRIMARY KEY,
            sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE NOT NULL,
            event_type varchar(64) NOT NULL,
            entity_key varchar(200) NOT NULL,
            source varchar(64) NOT NULL,
            schema_version integer NOT NULL CHECK (schema_version > 0),
            occurred_at timestamptz NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            idempotency_key varchar(240) UNIQUE,
            payload_safe_json jsonb NOT NULL CHECK (jsonb_typeof(payload_safe_json) = 'object')
        );
        CREATE INDEX ix_system_events_recorded_sequence ON system_events(recorded_at, sequence);
        CREATE INDEX ix_system_events_entity_recorded ON system_events(entity_key, recorded_at);
        CREATE FUNCTION paw_record_event_time() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            NEW.recorded_at := clock_timestamp();
            RETURN NEW;
        END;
        $$;
        CREATE TRIGGER system_events_recorded_at BEFORE INSERT ON system_events
            FOR EACH ROW EXECUTE FUNCTION paw_record_event_time();
        CREATE FUNCTION paw_reject_history_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'system_events is append-only; use an explicit corrective event';
        END;
        $$;
        CREATE TRIGGER system_events_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON system_events
            FOR EACH STATEMENT EXECUTE FUNCTION paw_reject_history_mutation();
    """)


def downgrade() -> None:
    # This is a history foundation: dropping it would erase the actual evolution record.
    raise RuntimeError("Destructive history downgrade is disabled; restore a backup explicitly")
