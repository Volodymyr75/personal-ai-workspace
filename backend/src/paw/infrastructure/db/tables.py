from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()
nodes = Table(
    "service_nodes",
    metadata,
    Column("key", String(160), primary_key=True),
    Column("kind", String(32), nullable=False),
    Column("display_name", String(120), nullable=False),
    Column("lifecycle_state", String(16), nullable=False),
    Column("registered_at", DateTime(timezone=True), nullable=False),
    Column("retired_at", DateTime(timezone=True)),
    Column("metadata_json", JSONB, nullable=False),
)
edges = Table(
    "service_edges",
    metadata,
    Column("key", String(200), primary_key=True),
    Column("source_key", ForeignKey("service_nodes.key"), nullable=False),
    Column("target_key", ForeignKey("service_nodes.key"), nullable=False),
    Column("relation", String(32), nullable=False),
    Column("registered_at", DateTime(timezone=True), nullable=False),
    Column("retired_at", DateTime(timezone=True)),
    UniqueConstraint("source_key", "target_key", "relation"),
)
events = Table(
    "system_events",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("sequence", BigInteger, Identity(always=True), nullable=False, unique=True),
    Column("event_type", String(64), nullable=False),
    Column("entity_key", String(200), nullable=False),
    Column("source", String(64), nullable=False),
    Column("schema_version", Integer, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column(
        "recorded_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    ),
    Column("idempotency_key", String(240), unique=True),
    Column("payload_safe_json", JSONB, nullable=False),
)

workspaces = Table(
    "workspaces",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("name", String(120), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=text("clock_timestamp()")),
)
projects = Table(
    "projects",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("workspace_id", ForeignKey("workspaces.id"), nullable=False),
    Column("name", String(120), nullable=False),
    Column("description", String(2000), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=text("clock_timestamp()")),
)
files = Table(
    "files",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("project_id", ForeignKey("projects.id"), nullable=False),
    Column("original_name", String(255), nullable=False),
    Column("storage_key", String(40), nullable=False, unique=True),
    Column("mime_type", String(64), nullable=False),
    Column("size_bytes", BigInteger, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("row_count", Integer, nullable=False),
    Column("column_count", Integer, nullable=False),
    Column("delimiter", String(1), nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=text("clock_timestamp()")),
)
